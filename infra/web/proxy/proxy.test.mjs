// node --test infra/web/proxy/proxy.test.mjs   (no AWS needed)
import assert from "node:assert/strict";
import { test } from "node:test";

globalThis.awslambda = { streamifyResponse: (f) => f, HttpResponseStream: { from: (s) => s } };
const { countUse, events, prompt } = await import("./index.mjs");

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

// ---- reminders (pure parts) ----
const { LABELS, RemindError, emailFor, nowIst, planReminders, recordFromAttrs, validEmail } = await import("./reminders.mjs");

const HERO = [
  { date: "2027-01-08", kind: "deadline", citation: "76M, 76T(1)(b)" },
  { date: "2027-01-09", kind: "outer_limit", citation: "76M, 76T(1)(b)" },
  { date: "2027-02-20", kind: "deadline", citation: "76Q" },
  { date: "2027-02-20", kind: "opens", citation: "RB-IOS 2026" },
  { date: "2027-05-06", kind: "deadline", citation: "RB-IOS 2026" },
  { date: "2027-05-21", kind: "outer_limit", citation: "RB-IOS 2026" },
];
const MS = (iso) => Date.parse(iso + "+05:30"); // an IST wall-clock time as epoch ms

test("emails: accepts ordinary addresses, rejects anything that could inject headers or HTML", () => {
  for (const ok of ["a@b.co", "first.last+tag@example.com"]) assert.equal(validEmail(ok), true, ok);
  for (const bad of ["", "a@b", "a b@c.com", "a@b.com\nBcc: x@y.com", "<x>@y.com", "a@b.c", "x".repeat(300) + "@a.com", null, 5, "a@b.com,c@d.com"]) {
    assert.equal(validEmail(bad), false, String(bad));
  }
});

test("plan: hard deadlines only, 9 AM IST the day before and on the day, sorted, none in the past", () => {
  const items = planReminders(HERO, MS("2027-01-06T10:00:00"));
  assert.deepEqual(items.map((i) => `${i.at} ${i.when}`), [
    "2027-01-07T09:00:00 tomorrow", "2027-01-08T09:00:00 today", "2027-02-19T09:00:00 tomorrow",
    "2027-02-20T09:00:00 today", "2027-05-05T09:00:00 tomorrow", "2027-05-06T09:00:00 today"]);
  assert.ok(items.every((i) => i.sent === false && LABELS[i.citation]));
  assert.ok(!items.some((i) => i.date === "2027-01-09" || i.date === "2027-05-21")); // outer readings and "opens" are skipped
});

test("plan: past times are dropped, and an all-past plan is an error", () => {
  const items = planReminders(HERO, MS("2027-01-07T12:00:00"));
  assert.equal(items[0].at, "2027-01-08T09:00:00");
  assert.throws(() => planReminders(HERO, MS("2028-01-01T00:00:00")), (e) => e instanceof RemindError && /past/.test(e.message));
  assert.throws(() => planReminders([], Date.now()), /no deadlines/);
  assert.throws(() => planReminders("nope", Date.now()), RemindError);
});

test("plan: the request cannot supply its own wording, dates are checked", () => {
  const items = planReminders([
    { date: "2027-03-01", kind: "deadline", citation: "76Q", label: "<script>alert(1)</script>" },
    { date: "2027-02-30", kind: "deadline", citation: "76Q" },          // not a real date
    { date: "2027-03-05", kind: "deadline", citation: "made up rule" }, // unknown rule
    { date: "2027-03-06", kind: "bogus", citation: "76Q" },
  ], MS("2027-01-01T00:00:00"));
  assert.deepEqual(items.map((i) => i.label), [LABELS["76Q"], LABELS["76Q"]]);
  assert.ok(items.every((i) => i.date === "2027-03-01"));
});

test("plan: the same deadline twice is scheduled once", () => {
  const dup = [HERO[2], { ...HERO[2] }];
  assert.equal(planReminders(dup, MS("2027-01-01T00:00:00")).length, 2); // day before + day, not 4
});

test("nowIst is India time", () => {
  assert.equal(nowIst(Date.parse("2027-01-06T00:00:00Z")), "2027-01-06T05:30:00");
  assert.equal(nowIst(Date.parse("2027-01-06T20:00:00Z")), "2027-01-07T01:30:00");
});

test("email text: dates, rule and the safety lines, nothing about the case", () => {
  const { subject, text } = emailFor({ label: LABELS["76Q"], citation: "76Q", date: "2027-02-20", when: "tomorrow", at: "2027-02-19T09:00:00", sent: false });
  assert.match(subject, /tomorrow, 20 February 2027/);
  assert.match(text, /Rule: 76Q/);
  assert.match(text, /not RBI, the Government, the police, NCRP or your bank/);
  assert.match(text, /never files anything for you/);
  assert.doesNotMatch(text, /₹|Rs\.? ?\d/);
});

test("record round-trips through the DynamoDB shape", () => {
  const attrs = { pk: { S: "rem#abc123xyz" }, session: { S: "sess" }, email: { S: "a@b.co" },
    items: { L: [{ M: { label: { S: "L" }, citation: { S: "76Q" }, date: { S: "2027-02-20" }, when: { S: "today" }, at: { S: "2027-02-20T09:00:00" }, sent: { BOOL: false } } }] } };
  assert.deepEqual(recordFromAttrs(attrs), { id: "abc123xyz", session: "sess", email: "a@b.co",
    items: [{ label: "L", citation: "76Q", date: "2027-02-20", when: "today", at: "2027-02-20T09:00:00", sent: false }] });
});

// A stand-in for DynamoDB's conditional counter: refuses once the stored count has reached the ":max" the code sent.
function fakeCounterDb({ failWith } = {}) {
  const counts = new Map();
  return {
    counts,
    async send(cmd) {
      if (failWith) throw failWith;
      const key = cmd.input.Key.pk.S, max = Number(cmd.input.ExpressionAttributeValues[":max"].N);
      const used = counts.get(key) || 0;
      if (used >= max) { const e = new Error("conditional check failed"); e.name = "ConditionalCheckFailedException"; throw e; }
      counts.set(key, used + 1);
    },
  };
}

test("countUse allows exactly the limit, then refuses", async () => {
  const db = fakeCounterDb();
  const results = [];
  for (let i = 0; i < 5; i++) results.push(await countUse(db, "T", "sessday#2027-01-06", 3));
  assert.deepEqual(results, [true, true, true, false, false]);
  assert.equal(db.counts.get("sessday#2027-01-06"), 3);
});

test("countUse keeps separate counters separate (another session or another day starts fresh)", async () => {
  const db = fakeCounterDb();
  assert.equal(await countUse(db, "T", "up#tokenA", 1), true);
  assert.equal(await countUse(db, "T", "up#tokenA", 1), false);
  assert.equal(await countUse(db, "T", "up#tokenB", 1), true);
  assert.equal(await countUse(db, "T", "sessday#2027-01-07", 1), true);
});

test("countUse does not swallow real database errors", async () => {
  const boom = new Error("throttled"); boom.name = "ProvisionedThroughputExceededException";
  await assert.rejects(() => countUse(fakeCounterDb({ failWith: boom }), "T", "k", 5), /throttled/);
});
