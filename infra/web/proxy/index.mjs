// Web proxy: the only thing the browser talks to (through CloudFront, at /api/*).
//
//   POST /api/session  {code}                       -> {token}         access code check, new session
//   POST /api/upload   {token, type, size}          -> {url, fields, key}  presigned S3 POST for one screenshot
//   POST /api/chat     {token, message, keys, as_of} -> NDJSON stream of agent UI events
//
// Cost guards: an access code, a per-session turn cap and a daily turn cap, both counted in DynamoDB.
// Nothing personal is logged. The agent runtime, bucket and table come from the environment.

import { randomBytes, randomUUID, timingSafeEqual } from "node:crypto";
import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from "@aws-sdk/client-bedrock-agentcore";
import { DynamoDBClient, GetItemCommand, PutItemCommand, UpdateItemCommand } from "@aws-sdk/client-dynamodb";
import { S3Client } from "@aws-sdk/client-s3";
import { createPresignedPost } from "@aws-sdk/s3-presigned-post";

const { RUNTIME_ARN, TABLE, UPLOAD_BUCKET, ACCESS_CODE } = process.env;
const MAX_TURNS = Number(process.env.MAX_TURNS_PER_SESSION || 30);
const MAX_DAY = Number(process.env.MAX_TURNS_PER_DAY || 400);
const SESSION_HOURS = 6;
const MAX_MESSAGE = 2000;
const MAX_UPLOAD = 5_000_000;
const TYPES = { "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp" };

const agent = new BedrockAgentCoreClient({});
const db = new DynamoDBClient({});
const s3 = new S3Client({});

class HttpError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

const now = () => Math.floor(Date.now() / 1000);

function body(event) {
  try {
    const raw = event.isBase64Encoded ? Buffer.from(event.body || "", "base64").toString() : event.body || "{}";
    const value = JSON.parse(raw);
    if (value && typeof value === "object") return value;
  } catch { /* fall through */ }
  throw new HttpError(400, "Request body must be JSON.");
}

function codeMatches(given) {
  const a = Buffer.from(String(given || "")), b = Buffer.from(ACCESS_CODE || "");
  return b.length > 0 && a.length === b.length && timingSafeEqual(a, b);
}

async function newSession(req) {
  if (!codeMatches(req.code)) throw new HttpError(401, "That code didn't work. Check it and try again.");
  const token = randomBytes(24).toString("base64url");
  const sessionId = `${randomUUID()}-web`; // AgentCore needs at least 33 characters
  await db.send(new PutItemCommand({
    TableName: TABLE,
    Item: { pk: { S: `s#${token}` }, session: { S: sessionId }, turns: { N: "0" },
            expires: { N: String(now() + SESSION_HOURS * 3600) } },
  }));
  return { token };
}

async function session(token) {
  if (typeof token !== "string" || token.length < 20) throw new HttpError(401, "Please enter the access code again.");
  const out = await db.send(new GetItemCommand({ TableName: TABLE, Key: { pk: { S: `s#${token}` } } }));
  if (!out.Item || Number(out.Item.expires.N) < now()) throw new HttpError(401, "Your session ended. Please enter the access code again.");
  return out.Item.session.S;
}

async function countTurn(token) {
  const day = new Date().toISOString().slice(0, 10);
  try {
    await db.send(new UpdateItemCommand({
      TableName: TABLE, Key: { pk: { S: `day#${day}` } },
      UpdateExpression: "ADD turns :one SET expires = if_not_exists(expires, :exp)",
      ConditionExpression: "attribute_not_exists(turns) OR turns < :max",
      ExpressionAttributeValues: { ":one": { N: "1" }, ":max": { N: String(MAX_DAY) }, ":exp": { N: String(now() + 3 * 86400) } },
    }));
    await db.send(new UpdateItemCommand({
      TableName: TABLE, Key: { pk: { S: `s#${token}` } },
      UpdateExpression: "ADD turns :one",
      ConditionExpression: "turns < :max",
      ExpressionAttributeValues: { ":one": { N: "1" }, ":max": { N: String(MAX_TURNS) } },
    }));
  } catch (e) {
    if (e.name === "ConditionalCheckFailedException") {
      throw new HttpError(429, "This demo has reached its message limit for now. Please try again later.");
    }
    throw e;
  }
}

async function upload(req) {
  const sessionId = await session(req.token);
  const ext = TYPES[req.type];
  if (!ext) throw new HttpError(400, "Please upload a PNG, JPEG or WebP screenshot.");
  if (!(req.size > 0 && req.size <= MAX_UPLOAD)) throw new HttpError(400, "Screenshots must be under 5 MB.");
  const key = `uploads/${sessionId}/${randomUUID()}.${ext}`;
  const post = await createPresignedPost(s3, {
    Bucket: UPLOAD_BUCKET, Key: key, Expires: 300,
    Conditions: [["content-length-range", 1, MAX_UPLOAD], ["eq", "$Content-Type", req.type]],
    Fields: { "Content-Type": req.type },
  });
  return { url: post.url, fields: post.fields, key };
}

export function prompt(req, sessionId) {
  const message = typeof req.message === "string" ? req.message.trim() : "";
  if (message.length > MAX_MESSAGE) throw new HttpError(400, `Please keep messages under ${MAX_MESSAGE} characters.`);
  const keys = Array.isArray(req.keys) ? req.keys : [];
  if (keys.length > 6 || keys.some((k) => typeof k !== "string" || !k.startsWith(`uploads/${sessionId}/`))) {
    throw new HttpError(400, "Those uploads don't belong to this session.");
  }
  if (!message && !keys.length) throw new HttpError(400, "Please type a message.");
  const lines = [];
  if (/^\d{4}-\d{2}-\d{2}$/.test(req.as_of || "")) lines.push(`[Demo date: ${req.as_of}]`);
  if (message) lines.push(message);
  for (const k of keys) lines.push(`Uploaded: ${k}`);
  return lines.join("\n");
}

// The runtime answers with server-sent events: "data: {...}" blocks separated by blank lines.
export async function* events(stream) {
  const decoder = new TextDecoder();
  let buffer = "";
  for await (const chunk of stream) {
    buffer += decoder.decode(chunk, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, cut).trim();
      buffer = buffer.slice(cut + 1);
      if (!line.startsWith("data:")) continue;
      try {
        const value = JSON.parse(line.slice(5).trim());
        if (value && typeof value === "object" && value.t) yield value;
      } catch { /* ignore keep-alives and partial noise */ }
    }
  }
}

async function chat(req, out) {
  const sessionId = await session(req.token);
  const text = prompt(req, sessionId);
  await countTurn(req.token);
  const response = await agent.send(new InvokeAgentRuntimeCommand({
    agentRuntimeArn: RUNTIME_ARN, qualifier: "DEFAULT", runtimeSessionId: sessionId,
    contentType: "application/json", accept: "text/event-stream",
    payload: Buffer.from(JSON.stringify({ prompt: text, actorId: "web" })),
  }));
  const stream = awslambda.HttpResponseStream.from(out, {
    statusCode: 200, headers: { "content-type": "application/x-ndjson", "cache-control": "no-store" },
  });
  try {
    for await (const ev of events(response.response)) stream.write(JSON.stringify(ev) + "\n");
    stream.write(JSON.stringify({ t: "done" }) + "\n");
  } catch (e) {
    console.error("chat stream failed", e.name);
    stream.write(JSON.stringify({ t: "error", v: "The assistant stopped unexpectedly. Please send your message again." }) + "\n");
  }
  stream.end();
}

function json(out, status, value) {
  const stream = awslambda.HttpResponseStream.from(out, {
    statusCode: status, headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
  stream.write(JSON.stringify(value));
  stream.end();
}

export const handler = awslambda.streamifyResponse(async (event, out) => {
  const method = event.requestContext?.http?.method;
  const path = event.rawPath || "";
  try {
    if (method !== "POST") throw new HttpError(405, "Use POST.");
    const req = body(event);
    if (path.endsWith("/api/session")) return json(out, 200, await newSession(req));
    if (path.endsWith("/api/upload")) return json(out, 200, await upload(req));
    if (path.endsWith("/api/chat")) return await chat(req, out);
    throw new HttpError(404, "Not found.");
  } catch (e) {
    if (e instanceof HttpError) return json(out, e.status, { error: e.message });
    console.error("request failed", path, e.name);
    return json(out, 500, { error: "Something went wrong on our side. Please try again." });
  }
});
