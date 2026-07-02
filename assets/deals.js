/* SAI Agency — Deal Radar. Fetches /deals.json and renders a filterable,
 * ARM-classified deal dashboard. No inline handlers (CSP script-src 'self'). */
(function () {
  "use strict";

  var TYPE_COLOR = {
    grant: "var(--c1)",
    public_tender: "var(--c2)",
    accelerator: "var(--c3)",
    funding_round: "var(--c5)",
    partnership: "var(--c4)",
    rfp: "var(--c6)",
  };
  var TYPE_LABEL = {
    grant: "Grant",
    public_tender: "Public tender",
    accelerator: "Accelerator",
    funding_round: "Funding round",
    partnership: "Partnership",
    rfp: "RFP",
  };

  var state = { deals: [], region: "All", type: "All", country: "All", q: "", sort: "impact" };
  var $ = function (sel) { return document.querySelector(sel); };

  function euro(n) {
    if (!n) return "—";
    if (n >= 1e9) return "€" + (n / 1e9).toFixed(1) + "B";
    if (n >= 1e6) return "€" + (n / 1e6).toFixed(1) + "M";
    if (n >= 1e3) return "€" + Math.round(n / 1e3) + "k";
    return "€" + n;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function filtered() {
    var q = state.q.trim().toLowerCase();
    return state.deals.filter(function (d) {
      if (state.region !== "All" && d.region !== state.region) return false;
      if (state.type !== "All" && d.type !== state.type) return false;
      if (state.country !== "All" && d.country !== state.country) return false;
      if (q) {
        var hay = (d.title + " " + d.org + " " + d.sector + " " + d.description + " " + d.country).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    }).sort(function (a, b) {
      if (state.sort === "value") return (b.value_eur || 0) - (a.value_eur || 0);
      if (state.sort === "deadline") return String(a.deadline || "9999").localeCompare(String(b.deadline || "9999"));
      return (b.impact_score || 0) - (a.impact_score || 0);
    });
  }

  function renderStats(summary) {
    var s = $("#stats");
    s.innerHTML = "";
    var tiles = [
      { label: "Deals sourced", value: summary.total_deals, sub: summary.regions.join(" · ") },
      { label: "Open / upcoming", value: summary.open_or_upcoming, sub: "actionable now" },
      { label: "Pipeline value", value: euro(summary.total_pipeline_value_eur), sub: "known deal sizes" },
      { label: "Countries", value: (summary.countries || []).length, sub: (summary.countries || []).join(", ") },
    ];
    tiles.forEach(function (t) {
      var tile = el("div", "tile");
      tile.appendChild(el("div", "label", t.label));
      tile.appendChild(el("div", "value", String(t.value)));
      tile.appendChild(el("div", "sub", t.sub));
      s.appendChild(tile);
    });
  }

  function bars(mount, rows, opts) {
    opts = opts || {};
    var max = rows.reduce(function (m, r) { return Math.max(m, r.value); }, 0) || 1;
    mount.innerHTML = "";
    rows.forEach(function (r) {
      var row = el("div", "bar-row");
      row.appendChild(el("div", "bar-label", r.label));
      var track = el("div", "bar-track");
      var fill = el("div", "bar-fill");
      fill.style.width = Math.max(2, (r.value / max) * 100) + "%";
      fill.style.background = r.color || "var(--seq)";
      track.appendChild(fill);
      row.appendChild(track);
      row.appendChild(el("div", "bar-val", opts.fmt ? opts.fmt(r.value) : String(r.value)));
      mount.appendChild(row);
    });
  }

  function renderCharts(summary) {
    var byCountry = Object.keys(summary.by_country || {})
      .filter(function (k) { return k; })
      .map(function (k) { return { label: k, value: summary.by_country[k], color: "var(--seq)" }; })
      .sort(function (a, b) { return b.value - a.value; });
    bars($("#chart-country"), byCountry, {});

    var byType = Object.keys(summary.pipeline_value_by_type_eur || {})
      .map(function (k) { return { label: TYPE_LABEL[k] || k, value: summary.pipeline_value_by_type_eur[k], color: TYPE_COLOR[k] || "var(--c1)" }; })
      .sort(function (a, b) { return b.value - a.value; });
    bars($("#chart-type"), byType, { fmt: euro });
  }

  function badge(cls, text, extra) {
    var b = el("span", "badge " + cls, text);
    if (extra && extra.color) b.style.background = extra.color;
    if (extra && extra.dot) b.insertBefore(el("span", "dot"), b.firstChild);
    return b;
  }

  function renderDeals() {
    var list = $("#deals");
    var rows = filtered();
    $("#count").textContent = rows.length + " of " + state.deals.length + " deals";
    list.innerHTML = "";
    if (!rows.length) {
      list.appendChild(el("div", "empty", "No deals match these filters."));
      return;
    }
    rows.forEach(function (d) {
      var card = el("article", "deal prio-" + (d.priority || "medium"));

      var top = el("div", "top");
      var h = el("h3", null, d.title);
      top.appendChild(h);
      top.appendChild(badge("type", TYPE_LABEL[d.type] || d.type, { color: TYPE_COLOR[d.type] }));
      top.appendChild(badge("stage-" + (d.stage || "open"), d.stage || "open", { dot: true }));
      card.appendChild(top);

      card.appendChild(el("p", "org", [d.org, d.city, d.country].filter(Boolean).join(" · ")));
      if (d.description) card.appendChild(el("p", "desc", d.description));

      var meta = el("div", "meta");
      function m(label, val) {
        var span = el("span");
        span.appendChild(el("b", null, label + " "));
        span.appendChild(document.createTextNode(val));
        meta.appendChild(span);
      }
      m("Region:", d.region);
      m("Sector:", d.sector || "—");
      m("Value:", euro(d.value_eur));
      if (d.deadline) m("Deadline:", d.deadline);
      m("ARM:", (d.arm_stage || "prospect") + " · " + (d.owner || "unassigned"));
      var imp = el("span", "impact");
      imp.appendChild(el("b", null, "Impact "));
      imp.appendChild(document.createTextNode((d.impact_score != null ? d.impact_score.toFixed(2) : "—")));
      meta.appendChild(imp);
      card.appendChild(meta);

      if (d.next_action) {
        var next = el("div", "next");
        next.appendChild(el("b", null, "Next: "));
        next.appendChild(document.createTextNode(d.next_action));
        card.appendChild(next);
      }
      if (d.source_url) {
        var src = el("div", "next");
        var a = el("a", null, "Source: " + (d.source_name || "link"));
        a.href = d.source_url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        src.appendChild(a);
        card.appendChild(src);
      }
      list.appendChild(card);
    });
  }

  function buildFilters() {
    // Region chips
    var regions = ["All"].concat(unique(state.deals.map(function (d) { return d.region; })));
    var rc = $("#region-chips");
    regions.forEach(function (r) {
      var c = el("button", "chip", r);
      c.type = "button";
      c.setAttribute("aria-pressed", String(r === state.region));
      c.addEventListener("click", function () {
        state.region = r;
        [].forEach.call(rc.children, function (ch) { ch.setAttribute("aria-pressed", String(ch.textContent === r)); });
        renderDeals();
      });
      rc.appendChild(c);
    });
    // Type select
    var types = unique(state.deals.map(function (d) { return d.type; }));
    var tsel = $("#type-select");
    types.forEach(function (t) {
      var o = el("option", null, TYPE_LABEL[t] || t);
      o.value = t;
      tsel.appendChild(o);
    });
    tsel.addEventListener("change", function () { state.type = tsel.value; renderDeals(); });
    // Country select
    var countries = unique(state.deals.map(function (d) { return d.country; })).sort();
    var csel = $("#country-select");
    countries.forEach(function (c) {
      var o = el("option", null, c);
      o.value = c;
      csel.appendChild(o);
    });
    csel.addEventListener("change", function () { state.country = csel.value; renderDeals(); });
    // Search + sort
    $("#search").addEventListener("input", function (e) { state.q = e.target.value; renderDeals(); });
    $("#sort").addEventListener("change", function (e) { state.sort = e.target.value; renderDeals(); });
  }

  function unique(arr) {
    var seen = {}, out = [];
    arr.forEach(function (x) { if (x && !seen[x]) { seen[x] = 1; out.push(x); } });
    return out;
  }

  function fail(msg) {
    $("#deals").innerHTML = "";
    $("#deals").appendChild(el("div", "empty", msg));
  }

  fetch("/deals.json", { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (data) {
      state.deals = (data.deals || []).slice();
      renderStats(data.summary);
      renderCharts(data.summary);
      buildFilters();
      renderDeals();
      if (data.generated_at) {
        $("#generated").textContent = "Dataset generated " + new Date(data.generated_at).toISOString().slice(0, 10) +
          " · sources: " + (data.summary && data.summary.regions ? data.summary.regions.join(", ") : "");
      }
    })
    .catch(function (e) { fail("Could not load deals.json (" + e.message + "). Run: python -m sai_agents.deals.generate"); });
})();
