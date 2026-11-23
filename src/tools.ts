export type Category = "launch" | "acquire" | "own" | "gtm" | "insights";

export interface Tool {
  key: string;
  tab: string;
  cat: Category;
  name: string;
  tagline: string;
}

export const CATEGORIES: { key: Category; label: string; blurb: string }[] = [
  { key: "launch", label: "🚀 Launch", blurb: "Spin up an AI-powered micro-enterprise." },
  { key: "acquire", label: "🏪 Acquire", blurb: "Scan, diligence, and buy cash-flowing boring businesses." },
  { key: "own", label: "🧩 Own", blurb: "Fractional ownership from €10. Funding routes for operators." },
  { key: "gtm", label: "📈 GTM", blurb: "Marketing, sales, outreach, pipeline — four agents." },
  { key: "insights", label: "📊 Insights", blurb: "60-day dashboard and local-only analytics." },
];

export const TOOLS: Tool[] = [
  { key: "launcher", tab: "launcher", cat: "launch", name: "Business Launcher", tagline: "Pick a path. Get a 60-day plan." },
  { key: "niche", tab: "niche", cat: "launch", name: "Niche Selector", tagline: "Score prospects by client value × volume." },
  { key: "pricing", tab: "pricing", cat: "launch", name: "Service Pricing", tagline: "Three-tier anchor. Never lead with Basic." },
  { key: "outreach", tab: "outreach", cat: "launch", name: "Outreach Generator", tagline: "Cold emails that read like you wrote them." },
  { key: "discovery", tab: "discovery", cat: "launch", name: "Discovery Script", tagline: "15 / 30 / 45 / 60-minute call playbooks." },
  { key: "proposal", tab: "proposal", cat: "launch", name: "Proposal Generator", tagline: "Milestone-billed SOW in minutes." },
  { key: "dashboard", tab: "dashboard", cat: "launch", name: "60-Day Dashboard", tagline: "Checklist that compounds to first revenue." },

  { key: "scanner", tab: "scanner", cat: "acquire", name: "Small-Biz Scanner", tagline: "Boring businesses, ranked by moat and margin." },
  { key: "dd", tab: "dd", cat: "acquire", name: "Due Diligence", tagline: "The questions that stop you overpaying." },
  { key: "calc", tab: "calc", cat: "acquire", name: "Revenue Calculator", tagline: "SDE, SBA 7(a), seller note — all live." },
  { key: "deals", tab: "deals", cat: "acquire", name: "Saved Deals", tagline: "Pipeline of deals you're actually working." },

  { key: "funding", tab: "funding", cat: "own", name: "Funding Engine", tagline: "RBF, crowdfunding, syndicates — which fits." },
  { key: "ownership", tab: "ownership", cat: "own", name: "Fractional Ownership", tagline: "From €10. Compound over 10 years." },

  { key: "marketing", tab: "marketing", cat: "gtm", name: "Marketing Agent", tagline: "30-day launch + evergreen rhythm." },
  { key: "sales", tab: "sales", cat: "gtm", name: "Sales Agent", tagline: "Pipeline, weighted forecast, objection playbook." },
  { key: "gtm", tab: "gtm", cat: "gtm", name: "GTM Planner", tagline: "PLG · Sales · Community · Partner." },
  { key: "automation", tab: "automation", cat: "gtm", name: "Outreach Automation", tagline: "Multi-channel sequences. Export CSV." },

  { key: "analytics", tab: "analytics", cat: "insights", name: "Analytics", tagline: "Device-only. Zero fingerprints. One-click wipe." },
];
