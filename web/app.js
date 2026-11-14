// Liability Lens web page. Plain JS, no build step.
// The chat shows the model's words. The case file is drawn only from tool inputs and results streamed
// by the agent (see src/liability_lens/ui_events.py), so every amount, rule and date on it comes from code.
"use strict";

const $ = (id) => document.getElementById(id);
const state = { token: null, code: null, busy: false, pending: [], lang: "en", draftsAt: null,
  txns: [], outcome: null, entitlement: null, deadlines: null, drafts: null };

// ---- text --------------------------------------------------------------------------------
const T = {
  en: {},
  hi: {
    banner: "अभी पैसे कटे हैं? सबसे पहले 1930 और अपने बैंक की फ्रॉड हेल्पलाइन पर कॉल करें।",
    tagline: "ऑनलाइन फ्रॉड के बाद बैंक आपको क्या दे सकता है, RBI के किस नियम से, और कब तक।",
    code_label: "एक्सेस कोड", code_hint: "एक्सेस कोड सबमिशन नोट्स में है।", continue: "आगे बढ़ें",
    next_hint: "आप एक सहायक से बात करेंगे और आपकी केस फ़ाइल साथ-साथ बनती जाएगी।",
    synthetic_hint: "यह डेमो नकली डेटा पर चलता है। असली खाते की जानकारी न डालें।",
    gate_fine: "स्वतंत्र और निःशुल्क। RBI, सरकार, पुलिस या आपका बैंक नहीं। कानूनी जानकारी, कानूनी सलाह नहीं।",
    call: "पहले 1930 पर कॉल करें", demo_date: "डेमो तारीख", synthetic: "नकली डेमो डेटा", new_case: "नया केस",
    tab_chat: "बातचीत", tab_case: "केस फ़ाइल", case_file: "केस फ़ाइल",
    case_sub: "यह केवल नियम-इंजन भरता है, चैटबॉट के अपने शब्द नहीं।",
    welcome: "अपने शब्दों में बताइए क्या हुआ। आप SMS या UPI के स्क्रीनशॉट भी डाल सकते हैं। मैं बताऊँगा कि RBI का कौन-सा नियम लागू होता है, बैंक क्या दे सकता है, और आपकी समय-सीमाएँ क्या हैं, फिर कागज़ात का ड्राफ़्ट बनाऊँगा जिसे आप खुद जमा करेंगे।",
    try_sample: "नमूना केस आज़माएँ", start_own: "अपना केस शुरू करें", attach: "स्क्रीनशॉट जोड़ें",
    placeholder: "हिंदी या अंग्रेज़ी में लिखें…",
    footer: "स्वतंत्र और निःशुल्क · RBI, सरकार, पुलिस, NCRP या आपका बैंक नहीं · कानूनी जानकारी, सलाह नहीं · नियम अंतिम बार 13 नवंबर 2026 को जाँचे गए",
  },
};
const STEP = {
  extract_transactions: ["Reading screenshots", "स्क्रीनशॉट पढ़ रहे हैं"],
  classify_case: ["Checking RBI rules", "RBI नियम जाँच रहे हैं"],
  compute_entitlement: ["Working out what you may be owed", "हिसाब लगा रहे हैं"],
  deadline_calendar: ["Listing your deadlines", "समय-सीमाएँ निकाल रहे हैं"],
  draft_documents: ["Drafting documents", "ड्राफ़्ट बना रहे हैं"],
};
const VERDICT = {
  ZERO_LIABILITY_REVERSAL: "Zero liability: the bank should reverse the amount.",
  ZERO_LIABILITY_REVERSAL_BORDERLINE: "Zero liability if a day-5 report counts as within 5 calendar days.",
  ZERO_LIABILITY: "Zero liability.",
  PER_BANK_POLICY: "Liability set by the bank's board-approved policy.",
  CUSTOMER_LIABLE_UNTIL_REPORT_LESS_COMPENSATION: "Customer negligence candidate. The bank must prove it (76K).",
  CUSTOMER_LIABLE_UNTIL_REPORT: "Customer negligence candidate, until the fraud was reported. The bank must prove it.",
  CAPPED_LIABILITY: "Your liability is capped.",
  BANK_BEARS: "Happened after you reported, so the bank bears it.",
  LIABILITY_NOT_ESTABLISHED_BY_BANK: "No liability unless the bank proves it.",
  MANUAL_REVIEW: "Not clearly covered by the rules; needs review.",
  CANNOT_COMPUTE_DAY_ZERO: "No alert on record: the bank must produce its alert log.",
};
const WELCOME = "Tell me what happened, in your own words. You can upload SMS or UPI screenshots. I'll work out which RBI "
  + "rule applies, what the bank may owe you, and your deadlines, then draft the paperwork for you to file.";
const DOCS = { bank_notice: "Bank complaint", ncrp_narrative: "Cybercrime portal", ombudsman_complaint: "RBI Ombudsman" };

const t = (key, fallback) => (T[state.lang] && T[state.lang][key]) || fallback;
function applyLang() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.dataset.en ??= el.textContent;
    el.textContent = t(el.dataset.i18n, el.dataset.en);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.dataset.en ??= el.placeholder;
    el.placeholder = t(el.dataset.i18nPlaceholder, el.dataset.en);
  });
  document.querySelectorAll("[data-lang]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === state.lang)));
}

// ---- small helpers -----------------------------------------------------------------------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const rupees = (n) => "₹" + Math.round(Number(n) || 0).toLocaleString("en-IN");
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function day(iso) {
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  return y ? `${d} ${MONTHS[m - 1]} ${y}` : "";
}
function moment(iso) {
  const time = /T(\d{2}:\d{2})/.exec(iso || "");
  return day(iso) + (time && time[1] !== "00:00" ? `, ${time[1]}` : "");
}
const store = {
  get: (k) => { try { return sessionStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { v == null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch { /* private mode */ } },
};

async function api(path, payload) {
  const res = await fetch(`/api/${path}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
  if (res.status === 401) { signOut(); throw new Error((await res.json().catch(() => ({}))).error || "Please enter the access code again."); }
  return res;
}
async function apiJson(path, payload) {
  const res = await api(path, payload);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Something went wrong. Please try again.");
  return data;
}

// ---- minimal, safe markdown for the model's replies -------------------------------------
function inline(s) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}
function markdown(src) {
  const lines = src.replace(/\r/g, "").split("\n");
  let html = "", list = null, i = 0;
  const close = () => { if (list) { html += `</${list}>`; list = null; } };
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*\|.*\|\s*$/.test(line) && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1] || "")) {
      close();
      const raw = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const cells = (l) => raw(l).map(inline);
      const heads = cells(line), labels = raw(line).map((h) => h.replace(/[*`]/g, ""));
      html += "<table><thead><tr>" + heads.map((c) => `<th>${c}</th>`).join("") + "</tr></thead><tbody>";
      i += 2;
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        // data-label lets phones show each row as a small stacked card (see app.css)
        html += "<tr>" + cells(lines[i]).map((c, n) => `<td data-label="${esc(labels[n] || "")}">${c}</td>`).join("") + "</tr>";
        i++;
      }
      html += "</tbody></table>";
      continue;
    }
    let m;
    if ((m = /^\s*[-*]\s+(.*)/.exec(line))) { if (list !== "ul") { close(); html += "<ul>"; list = "ul"; } html += `<li>${inline(m[1])}</li>`; }
    else if ((m = /^\s*\d+[.)]\s+(.*)/.exec(line))) { if (list !== "ol") { close(); html += "<ol>"; list = "ol"; } html += `<li>${inline(m[1])}</li>`; }
    else if ((m = /^#{1,4}\s+(.*)/.exec(line))) { close(); html += `<h4>${inline(m[1])}</h4>`; }
    else if (/^\s*(---|\*\*\*)\s*$/.test(line)) { close(); html += "<hr>"; }
    else if (line.trim()) { close(); html += `<p>${inline(line)}</p>`; }
    else close();
    i++;
  }
  close();
  return html;
}

// Draft links are long presigned S3 URLs; the Drafts card shows them as buttons instead.
function hideDraftLinks(text) {
  return text
    .replace(/\[([^\]]+)\]\(https:\/\/[^\s)]*amazonaws\.com\/drafts\/[^\s)]*\)/g, "**$1** (in the Drafts card)")
    .replace(/https:\/\/\S*amazonaws\.com\/drafts\/\S*/g, "(in the Drafts card)");
}

// ---- chat --------------------------------------------------------------------------------
const log = $("log");
const scroll = () => { log.scrollTop = log.scrollHeight; };
function add(cls, html) {
  const el = document.createElement("div");
  el.className = cls;
  el.innerHTML = html;
  log.appendChild(el);
  scroll();
  return el;
}
function userMessage(text, files) {
  const thumbs = files.length ? `<div class="thumbs">${files.map((f) =>
    `<div class="thumb"><img alt="" src="${esc(f.preview)}"><span>${esc(f.name)}</span></div>`).join("")}</div>` : "";
  add("msg user", esc(text) + thumbs);
}
function step(name) {
  const label = STEP[name] ? STEP[name][state.lang === "hi" ? 1 : 0] : "Working";
  return add("step running", `<svg aria-hidden="true"><use href="#i-gear"/></svg><span>${esc(label)}…</span>`);
}
function stepDone(el, ok) {
  el.className = "step done";
  el.lastElementChild.textContent = el.lastElementChild.textContent.replace(/…$/, "");
  el.querySelector("use").setAttribute("href", ok ? "#i-tick" : "#i-gear");
}
// Suggested replies sit in a bar above the message box, outside the scrolling chat, so they are never scrolled out of sight.
function clearQuickReplies() { const bar = $("quick-bar"); bar.hidden = true; bar.innerHTML = ""; }
function quickReplies(options) {
  const bar = $("quick-bar");
  bar.innerHTML = options.map((o) => `<button type="button" class="chip">${esc(o)}</button>`).join("");
  bar.hidden = false;
  bar.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { const text = b.textContent; clearQuickReplies(); send(text); }));
}

async function send(text, keysOverride) {
  if (state.busy) return;
  const files = state.pending.filter((f) => f.key);
  const keys = keysOverride || files.map((f) => f.key);
  text = (text || "").trim();
  if (!text && !keys.length) return;
  if (state.pending.some((f) => !f.key)) { add("msg err", "Please wait for the screenshots to finish uploading."); return; }
  $("welcome")?.remove();
  clearQuickReplies();
  userMessage(text || "(screenshots)", files);
  state.pending = []; renderAttachments();
  setBusy(true);

  const bot = add("msg bot cursor", "");
  let raw = "", frame = 0, gotText = false;
  const steps = {};
  const paint = () => { frame = 0; bot.innerHTML = markdown(hideDraftLinks(raw)); scroll(); };
  try {
    const res = await api("chat", { token: state.token, message: text, keys, as_of: $("as-of").value });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || "Something went wrong. Please try again.");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let cut;
      while ((cut = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, cut); buf = buf.slice(cut + 1);
        if (!line.trim()) continue;
        let ev; try { ev = JSON.parse(line); } catch { continue; }
        if (ev.t === "text") { raw += ev.v; gotText = true; if (!frame) frame = requestAnimationFrame(paint); }
        else if (ev.t === "tool_start") {
          (steps[ev.name] ||= []).push(step(ev.name)); // a queue per tool: the same tool can run twice in one turn
          log.appendChild(bot); // keep the reply below its steps
          if (raw && !raw.endsWith("\n")) raw += "\n\n"; // text before and after a tool call are separate paragraphs
        }
        else if (ev.t === "tool_use") onToolUse(ev.name, ev.input || {});
        else if (ev.t === "tool_result") {
          const running = (steps[ev.name] || []).find((el) => el.classList.contains("running"));
          if (running) stepDone(running, !(ev.data && ev.data.error));
          onToolResult(ev.name, ev.data || {});
        }
        else if (ev.t === "error") throw new Error(ev.v);
      }
    }
    paint();
    if (!gotText) bot.remove();
  } catch (e) {
    if (!gotText) bot.remove();
    if (state.token) add("msg err", esc(e.message));
  } finally {
    bot.classList.remove("cursor");
    Object.values(steps).flat().forEach((s) => s.classList.contains("running") && stepDone(s, false));
    setBusy(false);
    if (state.askConfirm) { state.askConfirm = false; quickReplies(["Yes, that's correct", "Fix a value"]); }
    else if (state.offerDrafts && !state.drafts) quickReplies(["Yes, draft the three documents"]);
    if (state.justDrafted) { state.justDrafted = false; chatDrafts(); }
  }
}
function setBusy(on) {
  state.busy = on;
  $("send").disabled = on;
  $("try-sample") && ($("try-sample").disabled = on);
}

// ---- uploads -----------------------------------------------------------------------------
function renderAttachments() {
  const box = $("attachments");
  box.hidden = !state.pending.length;
  box.innerHTML = state.pending.map((f, i) => `<div class="thumb${f.key ? "" : " busy"}"><img alt="" src="${esc(f.preview)}">
    <span>${esc(f.key ? f.name : "Uploading…")}</span><button type="button" data-i="${i}" aria-label="Remove">×</button></div>`).join("");
  box.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { state.pending.splice(+b.dataset.i, 1); renderAttachments(); }));
}
async function uploadFile(file, name) {
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) throw new Error("Please upload PNG, JPEG or WebP screenshots.");
  if (file.size > 5_000_000) throw new Error("Each screenshot must be under 5 MB.");
  const item = { name: name || file.name, preview: URL.createObjectURL(file), key: null };
  state.pending.push(item); renderAttachments();
  try {
    const up = await apiJson("upload", { token: state.token, type: file.type, size: file.size });
    const form = new FormData();
    Object.entries(up.fields).forEach(([k, v]) => form.append(k, v));
    form.append("file", file);
    const res = await fetch(up.url, { method: "POST", body: form });
    if (!res.ok) throw new Error("The upload failed. Please try again.");
    item.key = up.key; renderAttachments();
    return item;
  } catch (e) {
    state.pending = state.pending.filter((p) => p !== item); renderAttachments();
    throw e;
  }
}
$("file").addEventListener("change", async (e) => {
  const files = [...e.target.files].slice(0, 6 - state.pending.length);
  e.target.value = "";
  for (const f of files) { try { await uploadFile(f); } catch (err) { add("msg err", esc(err.message)); } }
});

const SAMPLE = "My mother got a call on 4 January from someone who said her bank KYC would expire. She read out the OTPs "
  + "and two UPI payments went out. We called 1930 the same evening at 7:30 pm and reported it to the bank on 6 January "
  + "at 10 am. She is an individual with a savings account. Her name is Sunita Sharma, the bank is Example Bank and "
  + "the account ends in 4821. Screenshots attached.";
$("try-sample").addEventListener("click", async () => {
  $("as-of").value = "2027-01-06"; showDate();
  setBusy(true);
  try {
    for (const name of ["sms-1.png", "sms-2.png"]) {
      const blob = await (await fetch(`samples/${name}`)).blob();
      await uploadFile(new File([blob], name, { type: "image/png" }), name);
    }
    setBusy(false);
    $("input").value = SAMPLE;
    autosize();
    $("input").focus();
  } catch (e) { setBusy(false); add("msg err", esc(e.message)); }
});
$("start-own").addEventListener("click", () => { $("welcome")?.remove(); $("input").focus(); });

// ---- case file ---------------------------------------------------------------------------
function mergeTxns(list, confirmed) {
  const old = state.txns;
  state.txns = list.map((n, i) => {
    const match = old.find((o) => o.amount === n.amount && (!o.date || !n.date || o.date === n.date)) || old[i] || {};
    return { ...match, ...Object.fromEntries(Object.entries(n).filter(([, v]) => v != null && v !== "")), confirmed: confirmed || match.confirmed };
  });
}
function onToolUse(name, input) {
  if (Array.isArray(input.transactions) && input.transactions.length) {
    mergeTxns(input.transactions.map((x) => ({
      amount: Math.round(Number(x.amount) || 0), date: (x.txn_at || "").slice(0, 10),
      when: x.txn_at, utr: x.utr, mode: x.mode, to: x.beneficiary,
    })), true);
    renderCase();
  }
}
function onToolResult(name, data) {
  if (data.error) return;
  if (name === "extract_transactions") {
    const rows = (data.images || []).filter((im) => im.fields && im.fields.amount).map((im) => {
      const f = im.fields;
      return { amount: f.amount, date: f.txn_date, when: f.txn_date && f.time ? `${f.txn_date}T${f.time}` : f.txn_date,
        utr: f.utr, mode: f.counterparty && f.counterparty.includes("@") ? "UPI" : null, to: f.counterparty };
    });
    if (rows.length) { mergeTxns(rows, false); state.askConfirm = true; }
  } else if (name === "classify_case") state.outcome = data;
  else if (name === "compute_entitlement") state.entitlement = data;
  else if (name === "deadline_calendar") { state.deadlines = data; state.offerDrafts = true; }
  else if (name === "draft_documents") { state.drafts = data; state.draftsAt = Date.now(); state.offerDrafts = false; state.justDrafted = true; }
  renderCase();
}

function card(label, body, badge) {
  return `<section class="card"><div class="card-head"><span class="label">${esc(label)}</span>${badge || ""}</div>${body}</section>`;
}
const placeholder = (label) => `<section class="card placeholder"><div class="label">${esc(label)}</div><div class="small">Fills in as we talk</div></section>`;

function txnCard() {
  if (!state.txns.length) return placeholder("Transactions");
  const confirmed = state.txns.every((x) => x.confirmed);
  const badge = confirmed ? `<span class="badge">Confirmed</span>` : `<span class="badge amber">Read from screenshots · please confirm</span>`;
  const rows = state.txns.map((x) => `<tr><td>${esc(moment(x.when || x.date))}</td><td><b>${rupees(x.amount)}</b></td>
    <td>${esc(x.mode || "-")}</td><td class="mono">${esc(x.utr || "-")}</td></tr>`).join("");
  return card("Transactions", `<table class="table"><thead><tr><th>Date &amp; time</th><th>Amount</th><th>Mode</th><th>Reference</th></tr></thead><tbody>${rows}</tbody></table>`, badge);
}
function outcomeCard() {
  const o = state.outcome;
  if (!o) return placeholder("Likely outcome");
  const seen = new Set(), items = [];
  for (const tx of o.transactions || []) for (const r of tx.outcomes || []) {
    const k = r.citation + r.verdict;
    if (seen.has(k)) continue;
    seen.add(k);
    const cap = r.cap ? ` Cap: ${rupees(r.cap)}.` : "";
    items.push(`<div class="outcome"><span class="para">Para ${esc(r.citation)}</span><span>${esc(VERDICT[r.verdict] || r.verdict)}${cap}</span></div>`);
  }
  const several = items.length > 1 ? `<p class="note">More than one rule may apply. RBI doesn't say which comes first, so all are shown.</p>` : "";
  return card("Likely outcome", items.join("") + several + `<p class="note">A candidate only: the bank decides, and it carries the burden of proof.</p>`);
}
function entitlementCard() {
  const e = state.entitlement;
  if (!e) return placeholder("What you may be entitled to");
  let body = "";
  const n = e.new_regime;
  if (n && (n.status === "ELIGIBLE" || n.status === "BORDERLINE")) {
    const total = n.amount || 1, pct = (v) => `${(100 * v) / total}%`;
    body += `<div class="amount-row"><span class="big">${rupees(n.amount)}</span>
      <span class="muted">Compensation under para 76T · 85% of your ${rupees(n.net_loss)} net loss, capped at ₹25,000</span></div>
      <p class="note">If the bank treats this as customer negligence (76N). Paid once in a lifetime.</p>
      <div class="bar" aria-hidden="true"><span style="width:${pct(n.rbi)}"></span><span style="width:${pct(n.customer_bank)}"></span><span style="width:${pct(n.beneficiary_bank)}"></span></div>
      <div class="legend"><span><i style="background:var(--split-1)"></i>RBI ${rupees(n.rbi)}</span>
      <span><i style="background:var(--split-2)"></i>Your bank ${rupees(n.customer_bank)}</span>
      <span><i style="background:var(--split-3)"></i>Receiving bank ${rupees(n.beneficiary_bank)}</span></div>`;
    if (n.status === "BORDERLINE") body += `<p class="note">${esc((n.reasons || []).join(" "))}</p>`;
    if (n.after_later_recovery) body += `<p class="note">After the later recovery: ${rupees(n.after_later_recovery.customer_extra)} more to you (76T(3)).</p>`;
  } else if (n) {
    body += `<p><b>No 76T compensation in this case.</b></p><ul class="small">${(n.reasons || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>`;
  }
  if (n && n.also_consider) body += `<p class="note">${esc(n.also_consider)}</p>`;
  if (e.old_regime) {
    const rows = e.old_regime.liability.map((r) => `<tr><td>${esc(r.id)}</td><td>${rupees(r.amount)}</td><td>Para ${esc(r.citation)}</td>
      <td>${r.cap ? "at most " + rupees(r.cap) : esc(VERDICT[r.verdict] || r.verdict)}</td></tr>`).join("");
    body += `<table class="table small"><thead><tr><th></th><th>Amount</th><th>Rule</th><th>Your liability</th></tr></thead><tbody>${rows}</tbody></table>
      <p class="note">${esc(e.old_regime.note)}</p>`;
  }
  return card("What you may be entitled to", body || `<p class="small muted">Nothing to show yet.</p>`);
}
function shortLabel(i) {
  const l = i.label || "", id = (/^\[(\w+)\]/.exec(l) || [])[1];
  const pre = id ? `${id}: ` : "";
  if (i.citation === "76Q") return "Bank must reply";
  if (i.citation === "RB-IOS 2026") return i.kind === "opens" ? "Ombudsman opens" : i.kind === "outer_limit" ? "Ombudsman deadline (latest reading)" : "File with Ombudsman by";
  if (i.citation && i.citation.startsWith("76M")) return i.kind === "outer_limit" ? "5-day window ends (latest reading)" : "Report to bank and 1930 by";
  if (i.citation === "2017 para 6(ii)") return pre + "Report for zero liability";
  if (i.citation === "2017 para 9") return pre + "Provisional credit due";
  if (i.citation === "2017 para 10") return pre + "Bank must resolve";
  return l;
}
function deadlineCard() {
  const d = state.deadlines;
  if (!d) return placeholder("Deadlines");
  const groups = [];
  for (const it of d.deadlines || []) {
    if (!it.date) continue;
    const g = groups.find((x) => x.date === it.date);
    if (g) g.items.push(it); else groups.push({ date: it.date, items: [it], days: it.days_left });
  }
  const firstAhead = groups.find((g) => g.days >= 0 && g.items.some((i) => i.kind !== "outer_limit"));
  const html = groups.map((g) => {
    const outer = g.items.every((i) => i.kind === "outer_limit");
    const cls = ["tl-item", g.days < 0 ? "past" : "", outer ? "outer" : "", g === firstAhead && g.days <= 5 ? "soon" : ""].join(" ");
    const left = g === firstAhead ? `<span class="badge ${g.days <= 5 ? "amber" : "grey"} left">${g.days === 0 ? "today" : g.days + (g.days === 1 ? " day left" : " days left")}</span>` : "";
    const label = g.items.map((i) => `<span title="${esc(i.label)}">${esc(shortLabel(i))}</span>`).join("<br>");
    const cite = [...new Set(g.items.map((i) => i.citation))].join(", ");
    return `<div class="${cls}"><div class="dotm"></div><b>${esc(day(g.date))}</b>${left}<span>${label}</span><div class="small muted">${esc(cite)}</div></div>`;
  }).join("");
  const actions = (d.deadlines || []).filter((i) => !i.date).map((i) => `<p class="note"><b>${esc(i.label)}</b> (${esc(i.citation)})</p>`).join("");
  return card("Deadlines", `<div class="timeline">${html}</div>${actions}<p class="note">Counted from ${esc(day(d.as_of))}. Faded dates are the latest possible reading of a rule.</p>`);
}
const draftsExpired = () => Boolean(state.draftsAt) && Date.now() - state.draftsAt > 55 * 60 * 1000;
function draftButtons(d, expired) {
  return Object.entries(DOCS).map(([kind, label]) => {
    const doc = d && (d.documents || []).find((x) => x.kind === kind);
    if (doc && !expired) return `<a class="draft" href="${esc(doc.url)}" target="_blank" rel="noopener"><svg class="ok" aria-hidden="true"><use href="#i-tick"/></svg>${esc(label)}</a>`;
    return `<button type="button" class="draft pending" data-act="draft"><svg aria-hidden="true"><use href="#i-doc"/></svg>${esc(label)}</button>`;
  }).join("");
}
// On a phone the Case file is a separate tab, so the same buttons also appear in the chat, under the reply.
function chatDrafts() {
  const d = state.drafts;
  if (!d || !(d.documents || []).length) return;
  const blanks = d.fill_in && d.fill_in.length ? `Fill in by hand: ${d.fill_in.map(esc).join(" · ")}. ` : "";
  add("msg bot drafts-inline", `<div class="label">Your drafts</div><div class="drafts">${draftButtons(d, false)}</div>
    <p class="note">${blanks}Drafts only: read every line, sign and file them yourself. The links work for 1 hour.</p>`);
}
function draftsCard() {
  const d = state.drafts;
  const expired = draftsExpired();
  const buttons = draftButtons(d, expired);
  let note = d ? "Drafts only. You read, sign and file them." : "Tap a button to have these drafted. I'll ask for anything still missing. Drafts only: you read, sign and file them.";
  if (d && d.fill_in && d.fill_in.length) note = `Fill in by hand: ${d.fill_in.map(esc).join(" · ")}. ` + note;
  if (d && !expired) note += " Links expire in 1 hour, so download them now.";
  if (expired) note = "These links have expired. Tap a button to have them drafted again.";
  return card("Drafts", `<div class="drafts">${buttons}</div><p class="note">${note}</p>`);
}
function renderCase() {
  $("case").innerHTML = txnCard() + outcomeCard() + entitlementCard() + deadlineCard() + draftsCard();
  if ($("app").dataset.tab === "chat") $("case-dot").hidden = false;
}

// ---- gate, tabs, wiring ------------------------------------------------------------------
function showApp() {
  $("gate").hidden = true;
  $("app").hidden = false;
  $("app").dataset.tab = "chat";
  renderCase();
  $("case-dot").hidden = true;
  $("input").focus();
}
function signOut() {
  state.token = null;
  store.set("ll_token", null);
  $("app").hidden = true;
  $("gate").hidden = false;
  $("code").focus();
}
$("gate-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("gate-btn"), err = $("gate-error");
  err.hidden = true;
  const code = $("code").value.trim();
  if (!code) { err.textContent = "Please enter the access code."; err.hidden = false; return; }
  btn.disabled = true; btn.textContent = "Checking…";
  try {
    const { token } = await apiJson("session", { code });
    state.token = token; state.code = code;
    store.set("ll_token", token);
    showApp();
  } catch (ex) {
    err.textContent = ex.message; err.hidden = false;
  } finally {
    btn.disabled = false; btn.textContent = t("continue", "Continue");
  }
});
$("new-case").addEventListener("click", async () => {
  if (state.busy) return;
  if (!state.code) { signOut(); return; }
  try {
    const { token } = await apiJson("session", { code: state.code });
    state.token = token; store.set("ll_token", token);
    Object.assign(state, { txns: [], outcome: null, entitlement: null, deadlines: null, drafts: null, draftsAt: null, pending: [], offerDrafts: false });
    log.innerHTML = ""; clearQuickReplies(); renderAttachments(); renderCase(); $("case-dot").hidden = true;
    add("msg bot", `<p>${esc(t("welcome", WELCOME))}</p>`);
  } catch (ex) { add("msg err", esc(ex.message)); }
});
function showTab(name) {
  $("app").dataset.tab = name;
  document.querySelectorAll(".tab").forEach((x) => x.setAttribute("aria-selected", String(x.dataset.tab === name)));
  if (name === "case") $("case-dot").hidden = true;
}
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

// A draft button that is not ready yet is still a real button: tapping it starts the drafting if the case has been
// checked, and otherwise says what is still needed.
function startDrafting() {
  showTab("chat");
  if (state.busy) { add("msg bot", "<p>I'm still answering your last message. Please give me a moment, then tap again.</p>"); return; }
  if (state.deadlines) {
    send(state.drafts ? "Please draft the three documents again." : "Yes, draft the three documents.");
  } else {
    add("msg bot", `<p>To prepare your drafts I first need your confirmed transactions and a few answers. ${
      state.txns.length ? "Please reply to my last question below, and I'll draft them straight after." : "Tell me what happened, or try the sample case."}</p>`);
  }
}
document.addEventListener("click", (e) => { if (e.target.closest("[data-act='draft']")) startDrafting(); });
document.querySelectorAll("[data-lang]").forEach((b) => b.addEventListener("click", () => {
  state.lang = b.dataset.lang;
  store.set("ll_lang", state.lang);
  applyLang();
}));
function showDate() { $("as-of-text").textContent = day($("as-of").value); }
$("as-of").addEventListener("change", showDate);
$("as-of").addEventListener("click", () => { try { $("as-of").showPicker(); } catch { /* older browsers open it natively */ } });
showDate();
function autosize() { const el = $("input"); el.style.height = "auto"; el.style.height = Math.min(el.scrollHeight, 160) + "px"; }
$("input").addEventListener("input", autosize);
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("composer").requestSubmit(); }
});
$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("input").value;
  if (state.busy) return;
  $("input").value = ""; autosize();
  send(text);
});
let wasExpired = false;
setInterval(() => {
  const now = draftsExpired();
  if (state.drafts && now !== wasExpired) { wasExpired = now; renderCase(); }
}, 30_000);

state.lang = store.get("ll_lang") === "hi" ? "hi" : "en";
applyLang();
state.token = store.get("ll_token");
if (state.token) showApp(); else $("code").focus();
