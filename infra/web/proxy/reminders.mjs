// Email reminders for the deadlines on the Case file.
//
// The page sends only {date, citation, kind} for each deadline plus an email address. Everything a person reads
// (the wording of each reminder) comes from the fixed LABELS table below, never from the request, so a request
// cannot put its own text in an email. Nothing about the case itself (transactions, amounts) is stored: only the
// address, the deadline dates and a sent flag, and the record deletes itself after the last reminder.
//
// Pure functions first (they are unit tested without AWS), then the AWS calls.

import { DeleteItemCommand, DynamoDBClient, GetItemCommand, PutItemCommand, UpdateItemCommand } from "@aws-sdk/client-dynamodb";
import { CreateScheduleCommand, DeleteScheduleCommand, SchedulerClient } from "@aws-sdk/client-scheduler";
import { GetEmailIdentityCommand, SESv2Client, SendEmailCommand } from "@aws-sdk/client-sesv2";
import { randomBytes } from "node:crypto";

export const MAX_ITEMS = 8;
export const MAX_SETS_PER_SESSION = 3;
export const MAX_SETS_PER_DAY = 25;
export const MAX_SENDS_PER_SESSION = 6;  // the demo "send now" button
export const MAX_SENDS_PER_DAY = 40;     // well under SES's sandbox quota of 200 a day
const PREVIEW_ONLY_SECONDS = 3600;       // a preview-only record, with no address, lives an hour
const IST_OFFSET_MIN = 330;
const SEND_HOUR = "09:00:00";

// Citation (as the rules engine prints it) -> what the reminder says. Only these deadlines get reminders.
export const LABELS = {
  "76M, 76T(1)(b)": "Report the fraud to your bank and to 1930 / the cybercrime portal",
  "76Q": "Your bank must decide and reply to your complaint",
  "RB-IOS 2026": "Last safe date to file with the RBI Ombudsman",
  "2017 para 6(ii)": "Report to your bank for zero liability (3 working days from the alert)",
  "2017 para 9": "Your bank's provisional credit is due",
  "2017 para 10": "Your bank must resolve your complaint",
};

const EMAIL_RE = /^[^\s@<>()"',;:\\]{1,64}@[^\s@<>()"',;:\\]{1,190}\.[^\s@<>()"',;:\\]{2,}$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export class RemindError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

// ---- pure helpers ----------------------------------------------------------------------------

export function validEmail(value) {
  return typeof value === "string" && value.length <= 254 && EMAIL_RE.test(value);
}

function isoDate(value) {
  if (typeof value !== "string" || !DATE_RE.test(value)) return null;
  const d = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== value ? null : value;
}

function addDays(date, days) {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** "Now" in India as YYYY-MM-DDTHH:MM:SS, the clock EventBridge Scheduler uses with Asia/Kolkata. */
export function nowIst(nowMs = Date.now()) {
  return new Date(nowMs + IST_OFFSET_MIN * 60_000).toISOString().slice(0, 19);
}

/** Turn the page's deadlines into reminders: 9 AM IST the day before and on the day, for known hard deadlines. */
export function planReminders(deadlines, nowMs = Date.now()) {
  if (!Array.isArray(deadlines) || !deadlines.length) throw new RemindError(400, "There are no deadlines to remind you about yet.");
  if (deadlines.length > 20) throw new RemindError(400, "Too many deadlines.");
  const now = nowIst(nowMs);
  const seen = new Set(), items = [];
  for (const d of deadlines) {
    const date = isoDate(d && d.date), label = d && d.kind === "deadline" ? LABELS[d.citation] : null;
    if (!date || !label) continue;
    for (const [when, day] of [["tomorrow", addDays(date, -1)], ["today", date]]) {
      const at = `${day}T${SEND_HOUR}`;
      const key = `${at}|${label}`;
      if (at <= now || seen.has(key)) continue; // never schedule in the past
      seen.add(key);
      items.push({ label, citation: d.citation, date, when, at, sent: false });
    }
  }
  items.sort((a, b) => a.at.localeCompare(b.at) || a.label.localeCompare(b.label));
  if (!items.length) throw new RemindError(400, "All of these deadlines are in the past, so there is nothing to schedule.");
  if (items.length > MAX_ITEMS) items.length = MAX_ITEMS;
  return items;
}

const prettyDate = (iso) => new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

export function emailFor(item) {
  const when = item.when === "today" ? "today" : "tomorrow";
  const subject = `Liability Lens reminder: ${item.label} (${when}, ${prettyDate(item.date)})`;
  const text = [
    `This is the reminder you asked for.`,
    ``,
    `${item.label}`,
    `Date: ${prettyDate(item.date)} (${when})`,
    `Rule: ${item.citation}`,
    ``,
    `Check the date with your bank or the RBI Ombudsman before you rely on it. Where the rules are open to more than one reading, Liability Lens shows the earliest safe date.`,
    ``,
    `Liability Lens is independent and free. It is not RBI, the Government, the police, NCRP or your bank. It gives legal information, not legal advice, and it never files anything for you.`,
    ``,
    `To stop these reminders, open Liability Lens and choose "Cancel reminders".`,
  ].join("\n");
  return { subject, text };
}

// ---- DynamoDB attribute helpers (a tiny subset, so no extra dependency) -----------------------

const s = (v) => ({ S: String(v) });
const n = (v) => ({ N: String(v) });
const itemToAttr = (it) => ({ M: { label: s(it.label), citation: s(it.citation), date: s(it.date), when: s(it.when), at: s(it.at), sent: { BOOL: !!it.sent } } });
const attrToItem = (a) => ({ label: a.M.label.S, citation: a.M.citation.S, date: a.M.date.S, when: a.M.when.S, at: a.M.at.S, sent: !!a.M.sent.BOOL });

export function recordFromAttrs(attrs) {
  return { id: attrs.pk.S.slice(4), session: attrs.session.S, email: attrs.email.S, items: attrs.items.L.map(attrToItem) };
}

// ---- AWS ---------------------------------------------------------------------------------------

const env = () => ({
  table: process.env.TABLE, group: process.env.SCHEDULE_GROUP, target: process.env.REMINDER_ARN,
  role: process.env.SCHEDULER_ROLE_ARN, sender: process.env.SENDER_EMAIL,
});
const db = new DynamoDBClient({});
const scheduler = new SchedulerClient({});
const ses = new SESv2Client({});
const today = () => new Date().toISOString().slice(0, 10);

async function bump(key, max, message) {
  try {
    await db.send(new UpdateItemCommand({
      TableName: env().table, Key: { pk: s(key) },
      UpdateExpression: "ADD reminders :one SET expires = if_not_exists(expires, :exp)",
      ConditionExpression: "attribute_not_exists(reminders) OR reminders < :max",
      ExpressionAttributeValues: { ":one": n(1), ":max": n(max), ":exp": n(Math.floor(Date.now() / 1000) + 3 * 86400) },
    }));
  } catch (e) {
    if (e.name === "ConditionalCheckFailedException") throw new RemindError(429, message);
    throw e;
  }
}

/** Real emails only go to addresses verified in this account (SES sandbox). Anyone else gets an on-screen preview. */
export async function canDeliver(email) {
  try {
    const r = await ses.send(new GetEmailIdentityCommand({ EmailIdentity: email }));
    return r.VerifiedForSendingStatus === true;
  } catch (e) {
    if (e.name === "NotFoundException" || e.name === "BadRequestException") return false;
    throw e;
  }
}

export async function deliver(email, item) {
  const { subject, text } = emailFor(item);
  const preview = { subject, text, to: email };
  if (!email || !(await canDeliver(email))) return { delivered: false, preview };
  await ses.send(new SendEmailCommand({
    FromEmailAddress: env().sender, Destination: { ToAddresses: [email] },
    Content: { Simple: { Subject: { Data: subject, Charset: "UTF-8" }, Body: { Text: { Data: text, Charset: "UTF-8" } } } },
  }));
  return { delivered: true, preview };
}

export async function createReminders({ email, deadlines, sessionToken, sessionId }) {
  if (!validEmail(email)) throw new RemindError(400, "Please enter a valid email address.");
  const items = planReminders(deadlines);
  await bump(`remday#${today()}`, MAX_SETS_PER_DAY, "The demo has reached its reminder limit for today. Please try again tomorrow.");
  await bump(`remsess#${sessionToken}`, MAX_SETS_PER_SESSION, "You have set reminders three times in this session. Cancel one to set another.");
  const deliverable = await canDeliver(email);
  const id = randomBytes(12).toString("base64url");
  const nowSec = Math.floor(Date.now() / 1000);
  // Only a verified address gets real schedules, and only then is it kept. Anyone else gets a one-hour, address-free
  // record so the page can still show what would be sent: no schedules, nothing personal stored.
  const last = items[items.length - 1].at;
  const expires = deliverable ? Math.floor(new Date(`${last}Z`).getTime() / 1000) + 2 * 86400 : nowSec + PREVIEW_ONLY_SECONDS;
  await db.send(new PutItemCommand({
    TableName: env().table,
    Item: { pk: s(`rem#${id}`), session: s(sessionId), email: s(deliverable ? email : ""), items: { L: items.map(itemToAttr) },
            created: n(nowSec), expires: n(expires) },
  }));
  if (deliverable) {
    const made = [];
    try {
      for (let i = 0; i < items.length; i++) {
        await scheduler.send(new CreateScheduleCommand({
          Name: `ll-${id}-${i}`, GroupName: env().group,
          ScheduleExpression: `at(${items[i].at})`, ScheduleExpressionTimezone: "Asia/Kolkata",
          FlexibleTimeWindow: { Mode: "OFF" }, ActionAfterCompletion: "DELETE",
          Target: { Arn: env().target, RoleArn: env().role, Input: JSON.stringify({ id, n: i }),
                    RetryPolicy: { MaximumRetryAttempts: 2, MaximumEventAgeInSeconds: 3600 } },
        }));
        made.push(i);
      }
    } catch (e) {
      await cancelSchedules(id, made);
      await db.send(new DeleteItemCommand({ TableName: env().table, Key: { pk: s(`rem#${id}`) } }));
      throw e;
    }
  }
  return { id, count: items.length, items: items.map(({ label, date, when, at }) => ({ label, date, when, at })), deliverable, scheduled: deliverable };
}

async function cancelSchedules(id, indexes) {
  for (const i of indexes) {
    try { await scheduler.send(new DeleteScheduleCommand({ Name: `ll-${id}-${i}`, GroupName: env().group })); }
    catch (e) { if (e.name !== "ResourceNotFoundException") throw e; }
  }
}

async function load(id, sessionId) {
  if (typeof id !== "string" || !/^[A-Za-z0-9_-]{8,40}$/.test(id)) throw new RemindError(404, "Those reminders were not found.");
  const out = await db.send(new GetItemCommand({ TableName: env().table, Key: { pk: s(`rem#${id}`) } }));
  if (!out.Item || out.Item.session.S !== sessionId) throw new RemindError(404, "Those reminders were not found.");
  return recordFromAttrs(out.Item);
}

/** Demo button: send one reminder right now instead of waiting for its date. It does not mark it sent, so the real one still goes out. */
export async function sendNow({ id, sessionId, sessionToken, index }) {
  const rec = await load(id, sessionId);
  await bump(`remsendday#${today()}`, MAX_SENDS_PER_DAY, "The demo has reached its limit for sample emails today. Please try again tomorrow.");
  await bump(`remsend#${sessionToken}`, MAX_SENDS_PER_SESSION, `You have used all ${MAX_SENDS_PER_SESSION} sample emails for this session.`);
  const i = Number.isInteger(index) && index >= 0 && index < rec.items.length ? index : 0;
  const result = await deliver(rec.email, rec.items[i]);
  return { ...result, number: i + 1, of: rec.items.length };
}

export async function cancelReminders({ id, sessionId }) {
  const rec = await load(id, sessionId);
  await cancelSchedules(rec.id, rec.items.map((_, i) => i));
  await db.send(new DeleteItemCommand({ TableName: env().table, Key: { pk: s(`rem#${rec.id}`) } }));
  return { cancelled: rec.items.length };
}

/** Called by EventBridge Scheduler on the day (see reminder.mjs). */
export async function sendScheduled({ id, n: index }) {
  const out = await db.send(new GetItemCommand({ TableName: env().table, Key: { pk: s(`rem#${id}`) } }));
  if (!out.Item) return { skipped: "cancelled or expired" };
  const rec = recordFromAttrs(out.Item);
  const item = rec.items[index];
  if (!item || item.sent) return { skipped: "already sent" };
  const result = await deliver(rec.email, item);
  await db.send(new UpdateItemCommand({
    TableName: env().table, Key: { pk: s(`rem#${id}`) },
    UpdateExpression: `SET #items[${Number(index)}].#sent = :t`,
    ExpressionAttributeNames: { "#items": "items", "#sent": "sent" }, ExpressionAttributeValues: { ":t": { BOOL: true } },
  }));
  return { delivered: result.delivered };
}
