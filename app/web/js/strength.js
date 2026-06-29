// PASSWORD STRENGTH METER. Informational only — never blocks submit (a weak
// password can still be created). Scoring follows the passwordmeter.com model:
// length × variety give bonuses; single-class, repeats and sequences give
// penalties. analyzePassword() is pure (no DOM) so it can be reasoned about and
// node-checked on its own; strengthMeter() is the DOM widget that renders the
// red→green bar, the label/score, and the info-button checklist.

import { el, icon } from "./components.js";

// --- character-class helpers ---------------------------------------------
const isUpper = (c) => c >= "A" && c <= "Z";
const isLower = (c) => c >= "a" && c <= "z";
const isDigit = (c) => c >= "0" && c <= "9";
const isLetter = (c) => isUpper(c) || isLower(c);
const isSymbol = (c) => !isUpper(c) && !isLower(c) && !isDigit(c); // anything else (incl. space)

// Sequences we penalise (3+ in a row, forward or reverse). Lower-cased letters,
// digits, and a common keyboard-symbol run — mirrors passwordmeter's lists.
const SEQ_ALPHA = "abcdefghijklmnopqrstuvwxyz";
const SEQ_NUM = "0123456789";
const SEQ_SYM = ")!@#$%^&*()";

function countSequences(lower, seq) {
  let n = 0;
  for (let i = 0; i < seq.length - 2; i++) {
    const fwd = seq.slice(i, i + 3);
    const rev = fwd.split("").reverse().join("");
    if (lower.includes(fwd) || lower.includes(rev)) n++;
  }
  return n;
}

// Case-insensitive repeated-character penalty (passwordmeter's weighted form):
// closer repeats hurt more, normalised by the count of unique characters.
function repeatPenalty(pw) {
  const len = pw.length;
  let repInc = 0;
  let repChars = 0;
  for (let i = 0; i < len; i++) {
    let found = false;
    for (let j = 0; j < len; j++) {
      if (i !== j && pw[i].toLowerCase() === pw[j].toLowerCase()) {
        found = true;
        repInc += Math.abs(len / (j - i));
      }
    }
    if (found) repChars++;
  }
  const unique = len - repChars;
  return unique ? Math.ceil(repInc / unique) : Math.ceil(repInc);
}

const BANDS = ["Very Weak", "Weak", "Fair", "Strong", "Very Strong"];

function bandFor(score) {
  if (score < 20) return 0;
  if (score < 40) return 1;
  if (score < 60) return 2;
  if (score < 80) return 3;
  return 4;
}

// The user-facing "how to get a better password" criteria. Each is a boolean
// derived from the same scan; the checklist renders one row per entry.
export const CRITERIA = [
  ["length16", "At least 16 characters"],
  ["upper", "Uppercase letter (A–Z)"],
  ["lower", "Lowercase letter (a–z)"],
  ["number", "Number (0–9)"],
  ["symbol", "Symbol (!@#$…)"],
  ["noRepeats", "No repeated characters"],
  ["noSequences", "No sequences (abc, 123)"],
];

// Pure scorer. Returns { score 0–100, band 0–4, label, checks }.
export function analyzePassword(pw) {
  pw = pw || "";
  const len = pw.length;
  const empty = {
    length16: false, upper: false, lower: false, number: false,
    symbol: false, noRepeats: false, noSequences: false,
  };
  if (len === 0) return { score: 0, band: 0, label: "—", checks: empty };

  let nUpper = 0, nLower = 0, nNum = 0, nSym = 0, nMid = 0;
  for (let i = 0; i < len; i++) {
    const c = pw[i];
    if (isUpper(c)) nUpper++;
    else if (isLower(c)) nLower++;
    else if (isDigit(c)) { nNum++; if (i > 0 && i < len - 1) nMid++; }
    else { nSym++; if (i > 0 && i < len - 1) nMid++; }
  }
  const lower = pw.toLowerCase();

  // --- additions ---
  let score = len * 4;
  if (nUpper > 0 && nUpper < len) score += (len - nUpper) * 2;
  if (nLower > 0 && nLower < len) score += (len - nLower) * 2;
  if (nNum > 0 && nNum < len) score += nNum * 4;
  score += nSym * 6;
  score += nMid * 2;

  const reqs = [len >= 8, nUpper > 0, nLower > 0, nNum > 0, nSym > 0];
  const nReq = reqs.filter(Boolean).length;
  const minReq = len >= 8 ? 4 : 3;
  if (nReq > minReq) score += nReq * 2;

  // --- deductions ---
  const onlyLetters = nUpper + nLower === len;
  const onlyNumbers = nNum === len;
  if (onlyLetters) score -= len;
  if (onlyNumbers) score -= len;
  score -= repeatPenalty(pw);

  const consec = (cls) => {
    let n = 0;
    for (let i = 1; i < len; i++) if (cls(pw[i]) && cls(pw[i - 1])) n++;
    return n;
  };
  score -= consec(isUpper) * 2;
  score -= consec(isLower) * 2;
  score -= consec(isDigit) * 2;

  const seqAlpha = countSequences(lower, SEQ_ALPHA);
  const seqNum = countSequences(lower, SEQ_NUM);
  const seqSym = countSequences(lower, SEQ_SYM);
  score -= (seqAlpha + seqNum + seqSym) * 3;

  score = Math.max(0, Math.min(100, Math.round(score)));

  const checks = {
    length16: len >= 16,
    upper: nUpper > 0,
    lower: nLower > 0,
    number: nNum > 0,
    symbol: nSym > 0,
    noRepeats: repeatPenalty(pw) === 0,
    noSequences: seqAlpha + seqNum + seqSym === 0,
  };

  // A perfect 100 must mean every best-practice box is ticked. Each unmet
  // criterion lowers the achievable ceiling proportionally, so the score can
  // never claim "perfect" (or near it) while the checklist still has gaps.
  const met = Object.values(checks).filter(Boolean).length;
  const total = Object.keys(checks).length;
  score = Math.min(score, Math.round((met / total) * 100));

  return { score, band: bandFor(score), label: BANDS[bandFor(score)], checks };
}

// --- DOM widget -----------------------------------------------------------
// strengthMeter(inputEl) returns a node that lives under the password field and
// updates live on every keystroke. Non-blocking by construction: it only reads
// the input, never gates the form.
export function strengthMeter(inputEl) {
  const label = el("span", { class: "pw-meter-label" }, "—");
  const scoreEl = el("span", { class: "pw-meter-score mono" }, "");

  const infoBtn = el("button", {
    type: "button",                       // never submit the form
    class: "pw-info-btn",
    "aria-label": "Password requirements",
    "aria-expanded": "false",
  }, icon("info", 14));

  const head = el("div", { class: "pw-meter-head" }, [
    el("span", { class: "pw-meter-title" }, "Password strength"),
    el("span", { class: "pw-meter-readout" }, [label, scoreEl]),
    infoBtn,
  ]);

  const fill = el("div", { class: "pw-meter-fill band-0" });
  const track = el("div", { class: "pw-meter-track" }, [fill]);

  // checklist popover — one row per criterion, ticked live
  const rows = CRITERIA.map(([key, text]) =>
    el("li", { class: "pw-crit", "data-key": key }, [
      el("span", { class: "pw-crit-mark" }, icon("circle", 14)),
      el("span", { class: "pw-crit-text" }, text),
    ]),
  );
  const popover = el("div", {
    class: "pw-criteria",
    role: "region",
    "aria-label": "Password requirements",
    hidden: "",
  }, [
    el("p", { class: "pw-criteria-tip" }, "Longer is stronger — aim for a long passphrase."),
    el("ul", { class: "pw-criteria-list" }, rows),
  ]);

  const wrap = el("div", { class: "pw-meter" }, [head, track, popover]);

  // --- open/close the popover ---
  let open = false;
  const setOpen = (v) => {
    open = v;
    infoBtn.setAttribute("aria-expanded", String(v));
    if (v) popover.removeAttribute("hidden");
    else popover.setAttribute("hidden", "");
  };
  infoBtn.addEventListener("click", () => setOpen(!open));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && open) setOpen(false); });
  document.addEventListener("click", (e) => { if (open && !wrap.contains(e.target)) setOpen(false); });

  // --- live update ---
  const update = () => {
    const { score, band, label: text, checks } = analyzePassword(inputEl.value);
    fill.className = "pw-meter-fill band-" + band;
    fill.style.width = score + "%";
    label.textContent = text;
    scoreEl.textContent = inputEl.value ? score + "/100" : "";
    for (const li of rows) {
      const met = checks[li.getAttribute("data-key")];
      li.classList.toggle("met", met);
      const mark = li.querySelector(".pw-crit-mark");
      mark.replaceChild(icon(met ? "check" : "circle", 14), mark.firstChild);
    }
  };
  inputEl.addEventListener("input", update);
  update();

  return wrap;
}
