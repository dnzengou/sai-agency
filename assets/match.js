/* SAI Agency — Matchmaking. Mirrors sai_agents.matching.scorer over deals.json.
 * No inline handlers (CSP script-src 'self'). */
(function () {
  "use strict";

  var W = { category: 0.30, region: 0.15, country: 0.15, budget: 0.20, sector: 0.20 };
  var LOOKING_FOR = { home: "repopulation", business: "succession", invest: "venture", ai: "ai_ml" };
  var TYPE_LABEL = {
    property_scheme: "Relocation / €1 house", business_succession: "Business succession",
    venture: "Venture / co-investment", grant: "Grant", public_tender: "Public tender",
    accelerator: "Accelerator", funding_round: "Funding round", partnership: "Partnership", rfp: "RFP",
  };
  var $ = function (s) { return document.querySelector(s); };
  var deals = [];

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls; if (text != null) e.textContent = text; return e;
  }
  function euro(n) {
    if (!n) return "price on request";
    if (n >= 1e9) return "€" + (n / 1e9).toFixed(1) + "B";
    if (n >= 1e6) return "€" + (n / 1e6).toFixed(1) + "M";
    if (n >= 1e3) return "€" + Math.round(n / 1e3) + "k";
    return "€" + n;
  }

  function budgetOk(deal, lo, hi) {
    var v = deal.value_eur;
    if (v == null) return null;
    if (lo != null && v < lo) return false;
    if (hi != null && v > hi) return false;
    return true;
  }

  function scoreMatch(profile, deal) {
    var total = 0, got = 0, reasons = [];
    var cat = profile.looking_for ? (LOOKING_FOR[profile.looking_for] || profile.looking_for) : null;
    if (cat) { total += W.category; if (deal.category === cat) { got += W.category; reasons.push("category: " + cat); } }
    if (profile.regions && profile.regions.length) {
      total += W.region; if (profile.regions.indexOf(deal.region) >= 0) { got += W.region; reasons.push("region: " + deal.region); }
    }
    if (profile.countries && profile.countries.length) {
      total += W.country; if (profile.countries.indexOf(deal.country) >= 0) { got += W.country; reasons.push("country: " + deal.country); }
    }
    if (profile.budget_min != null || profile.budget_max != null) {
      total += W.budget; var ok = budgetOk(deal, profile.budget_min, profile.budget_max);
      if (ok === true) { got += W.budget; reasons.push("within budget"); }
      else if (ok === null) { got += W.budget * 0.4; reasons.push("price on request"); }
    }
    if (profile.keywords && profile.keywords.length) {
      total += W.sector;
      var hay = [deal.title, deal.sector, deal.description, deal.org].join(" ").toLowerCase();
      var hit = null;
      profile.keywords.forEach(function (kw) { if (!hit && kw.trim() && hay.indexOf(kw.trim().toLowerCase()) >= 0) hit = kw.trim(); });
      if (hit) { got += W.sector; reasons.push("matches '" + hit + "'"); }
    }
    return { score: total === 0 ? 1 : got / total, reasons: reasons };
  }

  function rankMatches(profile, n) {
    return deals.map(function (d) {
      var r = scoreMatch(profile, d); return { deal: d, score: r.score, reasons: r.reasons };
    }).sort(function (a, b) {
      return (b.score - a.score) || ((b.deal.impact_score || 0) - (a.deal.impact_score || 0));
    }).slice(0, n);
  }

  function readProfile() {
    var lf = $("#m-looking").value;
    var region = $("#m-region").value;
    var country = $("#m-country").value;
    var budget = $("#m-budget").value; // "", "50000", "50000-200000", "200000-1000000", "1000000+"
    var lo = null, hi = null;
    if (budget) {
      if (budget.indexOf("-") >= 0) { var p = budget.split("-"); lo = +p[0]; hi = +p[1]; }
      else if (budget.slice(-1) === "+") { lo = +budget.slice(0, -1); }
      else { hi = +budget; }
    }
    var kw = $("#m-keywords").value.split(",").map(function (s) { return s.trim(); }).filter(Boolean);
    return {
      looking_for: lf || null,
      regions: region ? [region] : [],
      countries: country ? [country] : [],
      budget_min: lo, budget_max: hi, keywords: kw,
    };
  }

  function pct(s) { return Math.round(s * 100) + "%"; }

  function render(profile) {
    var matches = rankMatches(profile, 12);
    var mount = $("#matches");
    mount.innerHTML = "";
    // fill the match-request hidden fields with the profile + top matches
    $("#mr-profile").value = JSON.stringify(profile);
    $("#mr-matches").value = matches.slice(0, 5).map(function (m) { return m.deal.title; }).join(" | ");
    $("#request").hidden = false;
    $("#match-count").textContent = matches.length + " best matches";

    matches.forEach(function (m) {
      var d = m.deal;
      var card = el("article", "deal prio-" + (d.priority || "medium"));
      var top = el("div", "top");
      top.appendChild(el("h3", null, d.title));
      var badge = el("span", "badge type", pct(m.score) + " match");
      badge.style.background = m.score >= 0.75 ? "var(--good)" : m.score >= 0.5 ? "var(--c1)" : "var(--muted)";
      badge.style.color = "#fff"; badge.style.borderColor = "transparent";
      top.appendChild(badge);
      card.appendChild(top);
      card.appendChild(el("p", "org", [d.org, d.city, d.country].filter(Boolean).join(" · ")));
      if (d.description) card.appendChild(el("p", "desc", d.description.slice(0, 160)));
      var meta = el("div", "meta");
      function m2(l, v) { var s = el("span"); s.appendChild(el("b", null, l + " ")); s.appendChild(document.createTextNode(v)); meta.appendChild(s); }
      m2("Type", TYPE_LABEL[d.type] || d.type);
      m2("Value", euro(d.value_eur));
      if (m.reasons.length) m2("Why", m.reasons.join(", "));
      card.appendChild(meta);
      var actions = el("div", "actions");
      var a = el("a", "pursue"); a.href = "/deals/" + d.id; a.textContent = "View & pursue →";
      a.style.textDecoration = "none"; actions.appendChild(a);
      card.appendChild(actions);
      mount.appendChild(card);
    });
    mount.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function enhanceForm(form, msgEl) {
    if (!form) return;
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var data = new URLSearchParams(new FormData(form));
      msgEl.className = "form-msg"; msgEl.textContent = "Sending…";
      fetch("/", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: data.toString() })
        .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status);
          msgEl.className = "form-msg ok"; msgEl.textContent = "Thanks — we'll send matched intros to your inbox."; form.reset(); })
        .catch(function () { msgEl.className = "form-msg"; msgEl.textContent = ""; form.submit(); });
    });
  }

  // Populate region/country selects from the data, then wire the form.
  fetch("/deals.json", { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (data) {
      deals = data.deals || [];
      var regions = {}, countries = {};
      deals.forEach(function (d) { if (d.region) regions[d.region] = 1; if (d.country) countries[d.country] = 1; });
      Object.keys(regions).sort().forEach(function (r) { var o = el("option", null, r); o.value = r; $("#m-region").appendChild(o); });
      Object.keys(countries).sort().forEach(function (c) { var o = el("option", null, c); o.value = c; $("#m-country").appendChild(o); });
      $("#match-form").addEventListener("submit", function (e) { e.preventDefault(); render(readProfile()); });
      enhanceForm($("#request form"), $("#request-msg"));
    })
    .catch(function (e) { $("#matches").appendChild(el("div", "empty", "Could not load opportunities (" + e.message + ").")); });
})();
