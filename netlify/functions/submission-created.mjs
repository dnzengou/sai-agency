// Netlify Forms trigger: fires automatically on every form submission
// (the function name `submission-created` is the Netlify event hook).
//
// It bridges the lead into the KafCa stream as an impact-scored, ARM-classified
// LEAD_SIGNAL event. Bl (blacklist) drops jailbreak/injection junk. If
// KAFCA_WEBHOOK_URL is configured (a Kafka REST proxy, the agents service, or
// any HTTP sink), the event is POSTed there; otherwise it is emitted to the
// function logs as structured JSON — a graceful, lossless fallback.

import { screenLead, buildLeadEvent } from "./lib/lead.mjs";

export async function handler(event) {
  let submission;
  try {
    submission = JSON.parse(event.body || "{}");
  } catch {
    return { statusCode: 400, body: "invalid JSON" };
  }

  const payload = submission.payload || submission;
  const fields = payload.data || {};
  const formName = payload.form_name || fields["form-name"] || "unknown";

  // Honeypot: a filled bot-field means a bot slipped past — drop silently.
  if (fields["bot-field"]) {
    return { statusCode: 200, body: "ok" };
  }

  // Bl: refuse to forward unsafe input into the evolution loop.
  const verdict = screenLead(fields);
  if (verdict.blocked) {
    console.log(JSON.stringify({ level: "warning", event: "lead.blocked", form: formName, matched: verdict.matched }));
    return { statusCode: 200, body: "ok" };
  }

  const leadEvent = buildLeadEvent(formName, fields);
  const webhook = process.env.KAFCA_WEBHOOK_URL;

  if (webhook) {
    try {
      const res = await fetch(webhook, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(process.env.KAFCA_WEBHOOK_TOKEN ? { Authorization: `Bearer ${process.env.KAFCA_WEBHOOK_TOKEN}` } : {}),
        },
        body: JSON.stringify(leadEvent),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      console.log(JSON.stringify({ level: "info", event: "lead.forwarded", event_id: leadEvent.event_id, impact_score: leadEvent.impact_score }));
    } catch (err) {
      // Fallback: never lose the lead — log it structured for later replay.
      console.log(JSON.stringify({ level: "error", event: "lead.forward_failed", error: String(err), lead_event: leadEvent }));
    }
  } else {
    console.log(JSON.stringify({ level: "info", event: "lead.captured", lead_event: leadEvent }));
  }

  return { statusCode: 200, body: "ok" };
}
