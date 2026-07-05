// Lead bridge — pure logic (zero-dependency ESM).
// Mirrors the Python KafCa concepts (Bl blacklist + Impact + ARM) so a Netlify
// Forms submission becomes a clean, impact-scored, ARM-classified LEAD_SIGNAL
// event that evo-metaclaw / the KafCa stream can consume.

// --- Bl: blacklist signatures (subset of the Python defaults) ---
const BLACKLIST = [
  /ignore\s+(?:all|any|previous|prior|the|above)\b[\w\s]{0,40}?(?:instructions|prompts|rules)/i,
  /disregard\s+(?:all|any|the)\b[\w\s]{0,40}?(?:above|previous|prior|system|instructions)/i,
  /you are (now )?(dan|do anything now|jailbroken|unrestricted)/i,
  /developer mode/i,
  /reveal (your )?(system prompt|hidden|secret)/i,
  /print (your )?(system prompt|instructions|api[_ ]?key)/i,
  /exfiltrat/i,
  /bypass (the )?(safety|guardrail|filter|restriction)/i,
  /(drop|delete|truncate)\s+table/i,
  /rm\s+-rf\s+\//i,
];

export function screenLead(fields) {
  const text = Object.entries(fields || {})
    .filter(([k]) => k !== "bot-field" && k !== "form-name")
    .map(([, v]) => (v == null ? "" : String(v)))
    .join(" \n ");
  for (const rx of BLACKLIST) {
    const m = rx.exec(text);
    if (m) return { blocked: true, matched: rx.source };
  }
  return { blocked: false, matched: null };
}

const clamp01 = (n) => Math.max(0, Math.min(1, n));

// --- Im: impact scoring for a lead ---
export function scoreLeadImpact(formName, fields) {
  // A hand-raise on a specific deal is worth more than a newsletter opt-in.
  const base = formName === "deal-interest" ? 0.7 : 0.45;
  const hasCompany = fields && fields.company ? 0.1 : 0;
  const msgLen = fields && fields.message ? String(fields.message).length : 0;
  const engagement = clamp01(msgLen / 400) * 0.15; // longer intent -> higher
  const hasDeal = fields && fields.deal ? 0.05 : 0;
  return Math.round(clamp01(base + hasCompany + engagement + hasDeal) * 1e4) / 1e4;
}

// --- ARM: pipeline enrichment ---
export function classifyLeadArm(formName) {
  if (formName === "deal-interest") {
    return {
      arm_stage: "engaged",
      owner: "sales_gtm",
      next_action: "Qualify & respond within 24h (deal-specific interest)",
      priority: "high",
    };
  }
  return {
    arm_stage: "prospect",
    owner: "marketing",
    next_action: "Add to deal-alerts nurture sequence",
    priority: "medium",
  };
}

// --- Build the KafCa EvolutionEvent envelope (event_type: lead_signal) ---
export function buildLeadEvent(formName, fields, opts = {}) {
  const now = opts.now || new Date().toISOString();
  const id = opts.id || (globalThis.crypto?.randomUUID?.() ?? String(Math.random()).slice(2));
  const arm = classifyLeadArm(formName);
  const impact = scoreLeadImpact(formName, fields);
  // Never forward the honeypot or noisy internal fields.
  const { "bot-field": _bot, "form-name": _fn, ...clean } = fields || {};
  return {
    event_id: id,
    event_type: "lead_signal",
    timestamp: now,
    service: opts.service || "sai-agents",
    source_agent: "lead_bridge",
    impact_score: impact,
    schema_version: 1,
    payload: {
      form: formName,
      lead: clean,
      ...arm,
    },
  };
}
