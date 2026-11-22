/* SAI Agency — Succession & Repopulation demo. Fetches /deals.json and renders
 * live counts + featured cards for the repopulation/succession categories.
 * No inline handlers (CSP script-src 'self'). */
(function () {
  "use strict";

  var TYPE_LABEL = {
    property_scheme: "Relocation / €1 house",
    business_succession: "Business succession",
    venture: "Venture / co-investment",
    grant: "Grant",
    partnership: "Partnership",
    funding_round: "Funding round",
    public_tender: "Public tender",
    accelerator: "Accelerator",
  };
  var CAT_LABEL = { repopulation: "Repopulation", succession: "Succession", venture: "Venture" };
  var $ = function (s) { return document.querySelector(s); };

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function card(d) {
    var a = el("a", "deal prio-" + (d.priority || "medium"));
    a.href = "/deals/" + d.id;
    a.style.textDecoration = "none";
    a.style.color = "inherit";
    a.style.display = "block";

    var top = el("div", "top");
    top.appendChild(el("h3", null, d.title));
    top.appendChild(el("span", "badge region", CAT_LABEL[d.category] || d.category));
    a.appendChild(top);
    a.appendChild(el("p", "org", [d.org, d.city, d.country].filter(Boolean).join(" · ")));
    if (d.description) a.appendChild(el("p", "desc", d.description.slice(0, 160)));
    var meta = el("div", "meta");
    var t = el("span");
    t.appendChild(el("b", null, "Type "));
    t.appendChild(document.createTextNode(TYPE_LABEL[d.type] || d.type));
    meta.appendChild(t);
    if (d.deadline) {
      var dl = el("span");
      dl.appendChild(el("b", null, "Deadline "));
      dl.appendChild(document.createTextNode(d.deadline));
      meta.appendChild(dl);
    }
    a.appendChild(meta);
    return a;
  }

  fetch("/deals.json", { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (data) {
      var deals = data.deals || [];
      var repop = deals.filter(function (d) { return d.category === "repopulation"; });
      var succ = deals.filter(function (d) { return d.category === "succession"; });
      var vent = deals.filter(function (d) { return d.category === "venture"; });
      var countries = {};
      repop.concat(succ).concat(vent).forEach(function (d) { if (d.country) countries[d.country] = 1; });

      // Stat tiles
      var stats = $("#stats");
      stats.innerHTML = "";
      [
        { label: "Repopulation schemes", value: repop.length, sub: "€1 houses & relocation" },
        { label: "Businesses seeking a successor", value: succ.length, sub: "incl. official registries" },
        { label: "Countries", value: Object.keys(countries).length, sub: "Europe, US & more" },
        { label: "Total opportunities", value: data.summary ? data.summary.total_deals : deals.length, sub: "across the Deal Radar" },
      ].forEach(function (t) {
        var tile = el("div", "tile");
        tile.appendChild(el("div", "label", t.label));
        tile.appendChild(el("div", "value", String(t.value)));
        tile.appendChild(el("div", "sub", t.sub));
        stats.appendChild(tile);
      });

      $("#repop-count").textContent = repop.length + " schemes across " +
        new Set(repop.map(function (d) { return d.country; })).size + " countries";
      $("#succ-count").textContent = succ.length + " opportunities & registries";
      var vc = $("#venture-count");
      if (vc) vc.textContent = vent.length + " venture & co-investment vehicles";

      // Featured: a few from each category, highest impact first.
      function top(arr, n) {
        return arr.slice().sort(function (a, b) { return (b.impact_score || 0) - (a.impact_score || 0); }).slice(0, n);
      }
      var featured = top(repop, 3).concat(top(succ, 2)).concat(top(vent, 2));
      var mount = $("#samples");
      mount.innerHTML = "";
      featured.forEach(function (d) { mount.appendChild(card(d)); });

      if (data.generated_at) {
        $("#generated").textContent = "Live data · generated " +
          new Date(data.generated_at).toISOString().slice(0, 10);
      }
    })
    .catch(function (e) {
      $("#samples").innerHTML = "";
      $("#samples").appendChild(el("div", "empty", "Could not load live data (" + e.message + ")."));
    });
})();
