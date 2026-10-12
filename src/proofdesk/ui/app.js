"use strict";

const $ = (selector, root = document) => root.querySelector(selector);

function el(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "className") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== false && value != null) node.setAttribute(key, value === true ? "" : value);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

async function api(path, options) {
  const res = await fetch(path, options);
  let data = null;
  try { data = await res.json(); } catch (_) { /* leave null */ }
  if (!res.ok) throw new Error((data && data.error) || `The request failed (${res.status}).`);
  return data;
}

const post = (path, body) => api(path, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

const state = { config: null, docs: [], cache: new Map(), open: null, answer: null, active: null, step: 0 };

const SAMPLE_QUESTIONS = [
  "How many vacation days do full-time employees get?",
  "What is the company mascot?",
  "How soon must a SEV1 incident get a response?",
  "What is the capital of France?",
];

const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ---------- documents ---------- */

function renderDocs() {
  const list = $("#doc-list");
  list.replaceChildren(...state.docs.map(doc => el("li", { className: "doc-item" + (state.open === doc.id ? " open" : "") },
    el("button", { className: "doc-open", type: "button", onclick: () => openDoc(doc.id) },
      el("span", { className: "t" }, doc.title),
      el("span", { className: "m" }, `${doc.passages} passage${doc.passages === 1 ? "" : "s"}`)),
    el("button", { className: "doc-del", type: "button", "aria-label": `Remove ${doc.title}`, title: "Remove from this session",
      onclick: () => removeDoc(doc) }, "×"))));
}

async function loadDocs() {
  state.docs = await api("/api/docs");
  state.cache.clear();
  renderDocs();
}

async function getDoc(id) {
  if (!state.cache.has(id)) {
    const doc = await api("/api/docs/" + encodeURIComponent(id));
    // The server counts characters as code points; JavaScript strings count UTF-16 units. Convert once.
    doc.units = /[\ud800-\udfff]/.test(doc.text) ? codePointIndex(doc.text) : null;
    state.cache.set(id, doc);
  }
  return state.cache.get(id);
}

function codePointIndex(text) {
  const map = [];
  let unit = 0;
  for (const ch of text) { map.push(unit); unit += ch.length; }
  map.push(unit);
  return map;
}

const unitOf = (doc, cp) => (doc.units ? doc.units[Math.min(cp, doc.units.length - 1)] : cp);

async function openDoc(id, options = {}) {
  let doc;
  try { doc = await getDoc(id); } catch (err) { showPageMessage(err.message); return; }
  state.open = id;
  renderDocs();
  let hl = null;
  if (options.cite) {
    const c = options.cite;
    hl = { pStart: unitOf(doc, c.passage_start), pEnd: unitOf(doc, c.passage_end), sStart: unitOf(doc, c.span_start), sEnd: unitOf(doc, c.span_end) };
  } else if (options.passageId) {
    const p = doc.passages.find(x => x.id === options.passageId);
    if (p) hl = { pStart: unitOf(doc, p.start), pEnd: unitOf(doc, p.end), sStart: -1, sEnd: -1 };
  }
  $("#page-title").textContent = doc.title;
  $("#page-note").textContent = options.note || "Reading the whole document.";
  const body = $("#page-body");
  body.replaceChildren(buildBody(doc.text, hl));
  body.scrollTop = 0;
  const mark = $("mark.cited", body) || $(".in-passage", body);
  if (mark) {
    const top = mark.getBoundingClientRect().top - body.getBoundingClientRect().top + body.scrollTop - body.clientHeight / 3;
    body.scrollTo({ top: Math.max(0, top), behavior: reduceMotion() ? "auto" : "smooth" });
  }
}

function showPageMessage(message) {
  $("#page-title").textContent = "Evidence";
  $("#page-note").textContent = message;
  $("#page-body").replaceChildren();
}

function buildBody(text, hl) {
  const frag = document.createDocumentFragment();
  let pos = 0, para = null;
  const flush = () => { if (para) { frag.append(renderPara(text, para.start, para.end, hl)); para = null; } };
  for (const line of text.split("\n")) {
    const start = pos, end = pos + line.length;
    pos = end + 1;
    const heading = /^[ \t]*(#{1,6})[ \t]+(.+?)[ \t#]*$/.exec(line);
    if (heading) { flush(); frag.append(el("h4", { className: heading[1].length === 1 ? "h1" : "" }, heading[2])); }
    else if (!line.trim()) flush();
    else if (para) para.end = end;
    else para = { start, end };
  }
  flush();
  return frag;
}

function renderPara(text, start, end, hl) {
  const cuts = new Set([start, end]);
  if (hl) for (const c of [hl.pStart, hl.pEnd, hl.sStart, hl.sEnd]) if (c > start && c < end) cuts.add(c);
  const points = [...cuts].sort((a, b) => a - b);
  const p = el("p");
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i], b = points[i + 1], piece = text.slice(a, b);
    const inSpan = hl && a >= hl.sStart && b <= hl.sEnd;
    const inPassage = hl && a >= hl.pStart && b <= hl.pEnd;
    if (inSpan) p.append(el("mark", { className: "cited sweep" }, piece));
    else if (inPassage) p.append(el("span", { className: "in-passage" }, piece));
    else p.append(piece);
  }
  return p;
}

async function removeDoc(doc) {
  if (!window.confirm(`Remove "${doc.title}" from this session? The file on disk is not touched.`)) return;
  try { await api("/api/docs/" + encodeURIComponent(doc.id), { method: "DELETE" }); } catch (err) { window.alert(err.message); return; }
  if (state.open === doc.id) { state.open = null; showPageMessage("Click a source number in an answer, or pick a document, to read it here."); $("#page-title").textContent = "Evidence"; $("#page-body").replaceChildren(); }
  await loadDocs();
}

/* ---------- asking and answering ---------- */

async function ask(question) {
  question = question.trim();
  const button = $("#ask-btn");
  if (!question) { $("#question").focus(); return; }
  $("#question").value = question;
  button.disabled = true;
  const area = $("#answer-area");
  area.setAttribute("aria-busy", "true");
  try {
    const ans = await post("/api/ask", { question });
    state.answer = ans;
    renderAnswer(ans);
  } catch (err) {
    state.answer = null;
    area.replaceChildren(el("div", { className: "sheet refusal" }, el("h2", {}, "Couldn't ask"), el("p", {}, err.message)));
  } finally {
    button.disabled = false;
    area.removeAttribute("aria-busy");
  }
}

function hitsList(ans, openByDefault) {
  if (!ans.retrieved.length) return null;
  return el("details", { className: "how", open: openByDefault, id: "how-found" },
    el("summary", {}, openByDefault ? "Closest passages" : "How this was found"),
    el("ul", { className: "hits" }, ans.retrieved.map(h => el("li", { className: "hit" + (h.used ? " used" : "") },
      el("div", { className: "hit-top" },
        el("span", {}, `#${h.rank}`),
        el("span", { className: "id" }, h.passage_id),
        el("span", {}, `score ${h.score.toFixed(2)}`),
        el("span", { className: "grow" }, h.used ? "used in the answer" : ""),
        el("button", { type: "button", onclick: () => openDoc(h.doc_id, { passageId: h.passage_id, note: `Passage ${h.passage_id}, ranked #${h.rank} for your question.` }) }, "Open in document")),
      el("p", {}, h.preview + (h.preview.length >= 220 ? "…" : "")),
      el("div", { className: "terms" }, h.matched.length ? "Matched words: " + h.matched.join(", ") : "")))));
}

function renderAnswer(ans) {
  const area = $("#answer-area");
  state.active = null;
  if (ans.abstained) {
    const heading = { unverified: "Answer withheld", model_error: "Couldn't use the model", empty_question: "Ask a question" }[ans.reason] || "No answer in the documents";
    const sheet = el("div", { className: "sheet refusal" }, el("h2", {}, heading), el("p", {}, ans.message));
    if (ans.problems.length) sheet.append(el("div", { className: "notes" }, el("strong", {}, "What was checked"), el("ul", {}, ans.problems.map(p => el("li", {}, p)))));
    const hits = hitsList(ans, ans.reason === "not_found");
    if (hits) sheet.append(hits);
    area.replaceChildren(sheet);
    return;
  }
  const textBox = el("p", { className: "text" });
  ans.claims.forEach((claim, i) => {
    textBox.append(el("span", { className: "claim", dataset: { n: claim.cites[0] }, onclick: () => activate(claim.cites[0]) }, claim.text));
    for (const n of claim.cites) {
      const c = ans.citations[n - 1];
      textBox.append(el("button", { className: "cite" + (c.verified ? "" : " unverified"), type: "button", dataset: { n },
        "aria-pressed": "false", "aria-label": `Source ${n}: open the supporting sentence in ${c.title}`, onclick: () => activate(n) }, String(n)));
    }
    textBox.append(i < ans.claims.length - 1 ? ". " : ".");
  });
  const allOk = ans.citations.every(c => c.verified);
  const sheet = el("div", { className: "sheet answer" }, el("h2", {}, "Answer"), textBox,
    el("p", { className: "checked" },
      el("span", { className: allOk ? "ok" : "bad" }, allOk ? "Checked." : "Not fully checked."),
      allOk ? `Each claim was matched to a sentence in ${ans.citations.length === 1 ? "the document" : "the documents"} it cites. Click a number to read it.`
            : "Some citations could not be verified and are marked in red."));
  if (ans.problems.length) {
    sheet.append(el("div", { className: "notes" }, el("strong", {}, "Removed or flagged"), el("ul", {}, ans.problems.map(p => el("li", {}, p)))));
  }
  const hits = hitsList(ans, false);
  if (hits) sheet.append(hits);
  area.replaceChildren(sheet);
  activate(1, true);
}

async function activate(n, quiet) {
  const ans = state.answer;
  if (!ans || !ans.citations[n - 1]) return;
  const c = ans.citations[n - 1];
  state.active = n;
  for (const chip of document.querySelectorAll(".cite")) chip.setAttribute("aria-pressed", String(Number(chip.dataset.n) === n));
  const where = c.title + (c.section ? " › " + c.section : "");
  await openDoc(c.doc_id, { cite: c, note: `Source ${n}: ${where}. The highlighted sentence is the one the answer relies on.` });
  if (!quiet) $("#page-body").focus({ preventScroll: true });
}

/* ---------- adding documents ---------- */

function setupAddDialog() {
  const dialog = $("#add-dialog"), error = $("#add-error");
  const showError = msg => { error.textContent = msg; error.hidden = !msg; };
  $("#add-open").addEventListener("click", () => { $("#add-form").reset(); showError(""); dialog.showModal(); $("#add-name").focus(); });
  $("#add-cancel").addEventListener("click", () => dialog.close());
  $("#add-file").addEventListener("change", async event => {
    const file = event.target.files[0];
    if (!file) return;
    if (file.size > 1400000) { showError("That file is larger than 1.4 MB. Split it into smaller documents."); return; }
    $("#add-text").value = await file.text();
    if (!$("#add-name").value.trim()) $("#add-name").value = file.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
    showError("");
  });
  $("#add-form").addEventListener("submit", async event => {
    event.preventDefault();
    const title = $("#add-name").value.trim(), text = $("#add-text").value;
    if (!text.trim()) { showError("Paste some text or choose a file first."); return; }
    $("#add-save").disabled = true;
    try {
      const doc = await post("/api/docs", { title: title || "Untitled", text });
      dialog.close();
      await loadDocs();
      await openDoc(doc.id, { note: "Document added. Ask a question about it." });
    } catch (err) { showError(err.message); }
    finally { $("#add-save").disabled = false; }
  });
}

/* ---------- guide ---------- */

function guideSteps() {
  const sample = state.config.sample;
  return [
    { title: "Ask a question",
      text: sample ? "ProofDesk answers only from the documents on the left. This sample handbook belongs to a made-up company, Brindle Labs."
                   : "ProofDesk answers only from the documents on the left. Type a question whose answer is in one of them.",
      action: sample ? "Ask: What is the company mascot?" : "Start typing a question",
      run: async () => sample ? ask("What is the company mascot?") : $("#question").focus() },
    { title: "Check the source",
      text: "Every claim ends with a numbered source. Click the number and the document opens on the right, with the supporting sentence highlighted.",
      action: "Open source 1",
      run: async () => { if (!state.answer || state.answer.abstained) { if (sample) await ask("What is the company mascot?"); } await activate(1); } },
    { title: "See what happens when the documents don't know",
      text: "When nothing in the documents covers a question, ProofDesk says so instead of guessing. Closest passages are listed so you can look yourself.",
      action: sample ? "Ask: What is the capital of France?" : "Ask something unrelated",
      run: async () => ask(sample ? "What is the capital of France?" : "What is the capital of France?") },
    { title: "See how an answer was found",
      text: "Open “How this was found” under an answer. It lists the passages that were searched, their scores and the words that matched. Words like “vacation” are matched to “paid time off” with a short built-in synonym list.",
      action: sample ? "Ask: How many vacation days do full-time employees get?" : "Ask another question",
      run: async () => { if (sample) await ask("How many vacation days do full-time employees get?"); const d = $("#how-found"); if (d) { d.open = true; d.scrollIntoView({ block: "nearest" }); } } },
    { title: "Add your own document",
      text: "Paste text or choose a .txt or .md file. It stays in memory until you stop the server. To load a whole folder, start ProofDesk with --docs followed by the folder name.",
      action: "Open the Add document form",
      run: async () => $("#add-open").click() },
  ];
}

function renderGuide() {
  const steps = guideSteps(), s = steps[state.step];
  $("#guide-step-label").textContent = `Step ${state.step + 1} of ${steps.length}`;
  $("#guide-title").textContent = s.title;
  $("#guide-text").textContent = s.text;
  $("#guide-do").textContent = s.action;
  $("#guide-back").disabled = state.step === 0;
  $("#guide-next").textContent = state.step === steps.length - 1 ? "Done" : "Next";
}

function setupGuide() {
  const guide = $("#guide");
  const open = () => { guide.hidden = false; renderGuide(); };
  const close = () => { guide.hidden = true; try { localStorage.setItem("proofdesk.guide.seen", "1"); } catch (_) { /* private mode */ } };
  $("#guide-open").addEventListener("click", () => (guide.hidden ? open() : close()));
  $("#guide-close").addEventListener("click", close);
  $("#guide-back").addEventListener("click", () => { state.step = Math.max(0, state.step - 1); renderGuide(); });
  $("#guide-next").addEventListener("click", () => {
    if (state.step >= guideSteps().length - 1) { close(); return; }
    state.step += 1; renderGuide();
  });
  $("#guide-do").addEventListener("click", async () => { const b = $("#guide-do"); b.disabled = true; try { await guideSteps()[state.step].run(); } finally { b.disabled = false; } });
  let seen = false;
  try { seen = localStorage.getItem("proofdesk.guide.seen") === "1"; } catch (_) { /* treat as first visit */ }
  if (!seen) open();
}

/* ---------- start ---------- */

async function init() {
  state.config = await api("/api/config");
  $("#model-badge").textContent = state.config.model === "offline-extractive" ? "Offline demo model" : state.config.model;
  $("#model-badge").title = state.config.model_description;
  $("#docs-note").textContent = state.config.sample
    ? "A sample handbook for a made-up company. Add your own with Add document."
    : "Documents added here last until you stop the server.";
  if (state.config.sample) {
    $("#examples").replaceChildren(...SAMPLE_QUESTIONS.map(q => el("button", { className: "example", type: "button", onclick: () => ask(q) }, q)));
  }
  $("#ask-form").addEventListener("submit", event => { event.preventDefault(); ask($("#question").value); });
  $("#question").addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); ask($("#question").value); } });
  setupAddDialog();
  await loadDocs();
  setupGuide();
}

init().catch(err => {
  $("#answer-area").replaceChildren(el("div", { className: "sheet refusal" }, el("h2", {}, "Couldn't start"), el("p", {}, err.message)));
});
