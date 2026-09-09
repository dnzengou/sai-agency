/* SAI Agency — Deal Radar. Fetches /deals.json and renders a filterable,
 * ARM-classified deal dashboard with lead capture. No inline handlers
 * (CSP script-src 'self'). */
(function () {
  "use strict";

  var TYPE_COLOR = {
    grant: "var(--c1)",
    public_tender: "var(--c2)",
    accelerator: "var(--c3)",
    funding_round: "var(--c5)",
    partnership: "var(--c4)",
    rfp: "var(--c6)",
    property_scheme: "var(--c2)",
    business_succession: "var(--c6)",
    venture: "var(--c3)",
  };
  var TYPE_LABEL = {
    grant: "Grant",
    public_tender: "Public tender",
    accelerator: "Accelerator",
    funding_round: "Funding round",
    partnership: "Partnership",
    rfp: "RFP",
    property_scheme: "Relocation / €1 house",
    business_succession: "Business succession",
    venture: "Venture / co-investment",
  };

  var CATEGORY_LABEL = {
    ai_ml: "AI / ML",
    repopulation: "Repopulation",
    succession: "Succession",
    venture: "Venture",
  };

  var state = { deals: [], region: "All", type: "All", country: "All", category: "All", q: "", sort: "impact" };
  var $ = function (sel) { return document.querySelector(sel); };

  function euro(n) {
    if (!n) return "—";
    if (n >= 1e9) return "€" + (n / 1e9).toFixed(1) + "B";
    if (n >= 1e6) return "€" + (n / 1e6).toFixed(1) + "M";
    if (n >= 1e3) return "€" + Math.round(n / 1e3) + "k";
    return "€" + n;
  }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // --- URL <-> state sync (shareable deep-links) ---
  var URL_KEYS = ["region", "type", "country", "category", "q", "sort"];
  function readURL() {
    var p = new URLSearchParams(location.search);
    URL_KEYS.forEach(function (k) { if (p.has(k)) state[k] = p.get(k); });
  }
  function writeURL() {
    var p = new URLSearchParams();
    URL_KEYS.forEach(function (k) {
      var def = k === "sort" ? "impact" : k === "q" ? "" : "All";
      if (state[k] && state[k] !== def) p.set(k, state[k]);
    });
    var qs = p.toString();
    history.replaceState(null, "", qs ? "?" + qs : location.pathname);
  }

  function filtered() {
    var q = state.q.trim().toLowerCase();
    return state.deals.filter(function (d) {
      if (state.region !== "All" && d.region !== state.region) return false;
      if (state.type !== "All" && d.type !== state.type) return false;
      if (state.country !== "All" && d.country !== state.country) return false;
      if (state.category !== "All" && d.category !== state.category) return false;
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

  // Bi: ARM portfolio-intelligence panel (Business / Property / AI-deals /
  // Ventures + ARM stage distribution + next-action queue).
  var PORTFOLIO_LABEL = {
    business: "Businesses (succession)",
    property: "Property (relocation)",
    ai_deals: "AI / ML deals",
    ventures: "Ventures",
  };
  var ARM_STAGE_LABEL = {
    prospect: "Prospect", qualified: "Qualified", engaged: "Engaged",
    proposal: "Proposal", won: "Won", lost: "Lost",
  };

  function renderPortfolio(summary) {
    var arm = summary.arm;
    var wrap = $("#portfolio");
    if (!wrap || !arm) return;
    wrap.hidden = false;
    wrap.innerHTML = "";

    // Portfolio dimension cards.
    var dims = el("div", "card");
    dims.appendChild(el("h2", null, "Portfolio intelligence"));
    var grid = el("div", "portfolio-grid");
    Object.keys(PORTFOLIO_LABEL).forEach(function (k) {
      var p = (arm.portfolio || {})[k];
      if (!p) return;
      var cell = el("div", "portfolio-cell");
      cell.appendChild(el("div", "label", PORTFOLIO_LABEL[k]));
      cell.appendChild(el("div", "value", String(p.count)));
      cell.appendChild(el("div", "sub", p.open + " open · " + euro(p.value_eur)));
      grid.appendChild(cell);
    });
    dims.appendChild(grid);
    wrap.appendChild(dims);

    // ARM pipeline stage distribution.
    var stageCard = el("div", "card");
    stageCard.appendChild(el("h2", null, "ARM pipeline stages"));
    var stageMount = el("div");
    stageCard.appendChild(stageMount);
    var stageRows = Object.keys(arm.by_arm_stage || {})
      .map(function (k) { return { label: ARM_STAGE_LABEL[k] || k, value: arm.by_arm_stage[k], color: "var(--c2)" }; })
      .sort(function (a, b) { return b.value - a.value; });
    bars(stageMount, stageRows, {});
    wrap.appendChild(stageCard);

    // Next-action queue.
    var q = arm.next_action_queue || [];
    if (q.length) {
      var qCard = el("div", "card");
      qCard.appendChild(el("h2", null, "Next-action queue"));
      var ul = el("ul", "action-queue");
      q.forEach(function (item) {
        var li = el("li", null, item.action);
        li.appendChild(el("span", "count", String(item.count)));
        ul.appendChild(li);
      });
      qCard.appendChild(ul);
      wrap.appendChild(qCard);
    }
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
      top.appendChild(el("h3", null, d.title));
      top.appendChild(badge("type", TYPE_LABEL[d.type] || d.type, { color: TYPE_COLOR[d.type] }));
      if (d.category && d.category !== "ai_ml") {
        top.appendChild(badge("region", CATEGORY_LABEL[d.category] || d.category));
      }
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
      imp.appendChild(document.createTextNode(d.impact_score != null ? d.impact_score.toFixed(2) : "—"));
      meta.appendChild(imp);
      card.appendChild(meta);

      if (d.next_action) {
        var next = el("div", "next");
        next.appendChild(el("b", null, "Next: "));
        next.appendChild(document.createTextNode(d.next_action));
        card.appendChild(next);
      }

      var actions = el("div", "actions");
      var pursue = el("button", "pursue", "Pursue this deal →");
      pursue.type = "button";
      pursue.addEventListener("click", function () { openModal(d); });
      actions.appendChild(pursue);
      if (d.source_url) {
        var a = el("a", null, "Source: " + (d.source_name || "link"));
        a.href = d.source_url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        actions.appendChild(a);
      }
      card.appendChild(actions);
      list.appendChild(card);
    });
  }

  // --- Pursue-deal modal ---
  var lastFocus = null;
  function openModal(deal) {
    lastFocus = document.activeElement;
    $("#modal-deal").textContent = deal.title + " — " + (deal.org || "") + " (" + deal.country + ")";
    $("#modal-deal-field").value = deal.title + " · " + (deal.org || "");
    $("#modal-deal-url").value = deal.source_url || "";
    $("#interest-msg").textContent = "";
    $("#modal").hidden = false;
    $("#pi-name").focus();
  }
  function closeModal() {
    $("#modal").hidden = true;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  // --- Netlify Forms: progressive enhancement (native POST still works) ---
  function enhanceForm(form, msgEl, onOk) {
    if (!form) return;
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var data = new URLSearchParams(new FormData(form));
      msgEl.className = "form-msg";
      msgEl.textContent = "Sending…";
      fetch("/", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: data.toString(),
      })
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          msgEl.className = "form-msg ok";
          msgEl.textContent = "Thanks — you're on the list. We'll be in touch.";
          form.reset();
          if (onOk) onOk();
        })
        .catch(function () {
          // Fallback: let the browser submit natively to Netlify.
          msgEl.className = "form-msg";
          msgEl.textContent = "";
          form.submit();
        });
    });
  }

  // --- CSV export (lead magnet, client-side) ---
  function exportCSV() {
    var rows = filtered();
    var cols = ["title", "org", "country", "region", "sector", "type", "value_eur",
      "stage", "deadline", "impact_score", "arm_stage", "owner", "source_url"];
    var lines = [cols.join(",")];
    rows.forEach(function (d) {
      lines.push(cols.map(function (c) {
        var v = d[c] == null ? "" : String(d[c]);
        return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
      }).join(","));
    });
    var blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = el("a");
    a.href = url;
    a.download = "sai-agency-deals.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 0);
  }

  function buildFilters() {
    var regions = ["All"].concat(unique(state.deals.map(function (d) { return d.region; })));
    var rc = $("#region-chips");
    regions.forEach(function (r) {
      var c = el("button", "chip", r);
      c.type = "button";
      c.setAttribute("aria-pressed", String(r === state.region));
      c.addEventListener("click", function () {
        state.region = r;
        [].forEach.call(rc.children, function (ch) { ch.setAttribute("aria-pressed", String(ch.textContent === r)); });
        writeURL();
        renderDeals();
      });
      rc.appendChild(c);
    });

    // Keep the "Get weekly alerts" region dropdown in sync with the dataset so
    // it always reflects the actual (worldwide) coverage without hardcoding.
    var areg = $("#alert-region");
    if (areg) {
      regions.filter(function (r) { return r && r !== "All"; }).sort().forEach(function (r) {
        var o = el("option", null, r);
        o.value = r;
        areg.appendChild(o);
      });
    }

    var types = unique(state.deals.map(function (d) { return d.type; }));
    var tsel = $("#type-select");
    types.forEach(function (t) {
      var o = el("option", null, TYPE_LABEL[t] || t);
      o.value = t;
      tsel.appendChild(o);
    });
    tsel.value = state.type;
    tsel.addEventListener("change", function () { state.type = tsel.value; writeURL(); renderDeals(); });

    var countries = unique(state.deals.map(function (d) { return d.country; })).sort();
    var csel = $("#country-select");
    countries.forEach(function (c) {
      var o = el("option", null, c);
      o.value = c;
      csel.appendChild(o);
    });
    csel.value = state.country;
    csel.addEventListener("change", function () { state.country = csel.value; writeURL(); renderDeals(); });

    var catsel = $("#category-select");
    if (catsel) {
      unique(state.deals.map(function (d) { return d.category; })).sort().forEach(function (c) {
        var o = el("option", null, CATEGORY_LABEL[c] || c);
        o.value = c;
        catsel.appendChild(o);
      });
      catsel.value = state.category;
      catsel.addEventListener("change", function () { state.category = catsel.value; writeURL(); renderDeals(); });
    }

    var search = $("#search");
    search.value = state.q;
    search.addEventListener("input", function (e) { state.q = e.target.value; writeURL(); renderDeals(); });

    var sort = $("#sort");
    sort.value = state.sort;
    sort.addEventListener("change", function (e) { state.sort = e.target.value; writeURL(); renderDeals(); });

    $("#export-csv").addEventListener("click", exportCSV);
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

  function wireModalAndForms() {
    $("#modal-close").addEventListener("click", closeModal);
    $("#modal").addEventListener("click", function (e) { if (e.target === $("#modal")) closeModal(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !$("#modal").hidden) closeModal(); });
    enhanceForm($(".alerts"), $("#alerts-msg"), null);
    enhanceForm($("#modal form"), $("#interest-msg"), function () { setTimeout(closeModal, 1400); });

    // Show confirmation if a native (no-JS) submission redirected back.
    var p = new URLSearchParams(location.search);
    if (p.has("subscribed")) {
      $("#alerts-msg").className = "form-msg ok";
      $("#alerts-msg").textContent = "Thanks — you're subscribed to deal alerts.";
    }
  }

  readURL();
  wireModalAndForms();

  fetch("/deals.json", { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (data) {
      state.deals = (data.deals || []).slice();
      renderStats(data.summary);
      renderCharts(data.summary);
      renderPortfolio(data.summary);
      buildFilters();
      renderDeals();
      if (data.generated_at) {
        $("#generated").textContent = "Dataset generated " + new Date(data.generated_at).toISOString().slice(0, 10) +
          " · sources: " + (data.summary && data.summary.regions ? data.summary.regions.join(", ") : "");
      }
    })
    .catch(function (e) { fail("Could not load deals.json (" + e.message + "). Run: python -m sai_agents.deals.generate"); });
})();
