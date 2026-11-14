// node --test infra/web/proxy/proxy.test.mjs   (no AWS needed)
import assert from "node:assert/strict";
import { test } from "node:test";

globalThis.awslambda = { streamifyResponse: (f) => f, HttpResponseStream: { from: (s) => s } };
const { events, prompt } = await import("./index.mjs");

const SID = "11111111-2222-3333-4444-555555555555-web";

test("SSE lines split across chunks become UI events", async () => {
  const enc = new TextEncoder();
  async function* chunks() {
    yield enc.encode('data: {"t":"text","v":"Hel');
    yield enc.encode('lo"}\n\ndata: {"t":"tool_start","name":"classify_case"}\n\n: keep-alive\n\ndata: {"no_t":1}\n\n');
  }
  const out = [];
  for await (const e of events(chunks())) out.push(e);
  assert.deepEqual(out, [{ t: "text", v: "Hello" }, { t: "tool_start", name: "classify_case" }]);
});

test("prompt adds the demo date and this session's uploads only", () => {
  const p = prompt({ message: " hi ", keys: [`uploads/${SID}/a.png`], as_of: "2027-01-06" }, SID);
  assert.equal(p, `[Demo date: 2027-01-06]\nhi\nUploaded: uploads/${SID}/a.png`);
  assert.throws(() => prompt({ message: "x", keys: ["uploads/other/a.png"] }, SID), /don't belong/);
  assert.throws(() => prompt({ message: "x".repeat(2001) }, SID), /under 2000/);
  assert.throws(() => prompt({ message: "  " }, SID), /type a message/);
  assert.equal(prompt({ message: "x", as_of: "6 Jan; drop table" }, SID), "x");
});
