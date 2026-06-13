// ==UserScript==
// @name         StreetEasy Floor-Plan Harvester
// @namespace    https://github.com/dzikrisyairozi/streeteasy-floorplan-datasets
// @version      0.1.0
// @description  Harvest StreetEasy rental floor-plan keys (bucketed by bedrooms) from YOUR trusted browser session, then download a harvest.json the Python tool ingests. Free path that sidesteps PerimeterX — your real browser is already trusted.
// @match        https://streeteasy.com/*
// @match        https://www.streeteasy.com/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

/*
 * HOW TO USE
 *   A) Tampermonkey: install this file, open https://streeteasy.com/ , click the
 *      "▶ Harvest floor plans" button that appears bottom-right.
 *   B) No extension: open https://streeteasy.com/ , open DevTools console, paste
 *      this whole file, press Enter, then click the button (or run seHarvest()).
 *
 * It calls the same GraphQL API the site itself uses. Because it runs in your
 * real, already-trusted browser, PerimeterX lets it through (no proxy needed).
 * If a "Press & Hold" / "Access denied" page ever appears, solve it like a human,
 * then click the button again — it resumes from where it can.
 *
 * Output: harvest.json -> feed it to the Python tool:
 *     streeteasy-floorplans ingest harvest.json --download
 */

(function () {
  "use strict";
  if (window.__seHarvestLoaded) { console.log("[harvest] already loaded — click the button"); }
  window.__seHarvestLoaded = true;

  // ---- config (tweak if needed) -------------------------------------------
  const ENDPOINT = "https://api-v6.streeteasy.com/";
  const PER_PAGE = 50;          // results per page; lower if the API rejects it
  const PAGE_CAP = 100;         // StreetEasy's hard search-page cap
  const DELAY_MIN = 350, DELAY_MAX = 850;   // politeness delay between requests (ms)
  const BLOCK_RETRY = 3, BLOCK_WAIT = 8000; // on a PerimeterX block: retries + wait

  // ---- baked-in reference data (generated from constants.py) --------------
  const BUCKETS = [{"name":"studio","label":"Studio","min":0,"max":null===0?0:0},{"name":"1br","label":"1 Bedroom","min":1,"max":1},{"name":"2br","label":"2 Bedrooms","min":2,"max":2},{"name":"3br","label":"3 Bedrooms","min":3,"max":3},{"name":"4plus","label":"4+ Bedrooms","min":4,"max":null}];
  BUCKETS[0].max = 0; // studio: exactly 0 bedrooms
  const BOROUGHS = [{"code":100,"slug":"manhattan"},{"code":200,"slug":"bronx"},{"code":300,"slug":"brooklyn"},{"code":400,"slug":"queens"},{"code":500,"slug":"staten-island"}];
  const NEIGH = {"100":[101,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,120,121,122,123,124,130,131,132,133,134,136,137,138,140,141,142,143,145,146,147,148,149,150,151,152,153,154,155,157,158,159,161,162,163,164,165,166],"200":[201,202,203,204,205,207,208,209,210,211,212,213,214,215,216,218,219,220,221,224,225,226,227,228,229,231,232,233,234,235,236,237,238,240,241,242,243,244,245,246,248,249,260,265,266,267,270,271,272,273,274,276],"300":[301,302,303,304,305,306,307,308,309,310,312,313,314,315,316,317,318,319,320,321,322,323,324,325,326,327,328,329,330,331,332,333,334,335,336,337,338,339,340,341,342,343,344,345,346,347,348,349,350,352,353,354,355,358,359,360,361,362,363,364,365,366,367,370,373],"400":[401,402,403,404,405,406,407,408,409,410,411,412,413,414,415,416,417,418,419,420,421,422,423,424,425,426,427,428,429,430,431,432,433,434,435,436,437,438,439,440,441,442,443,444,445,446,447,448,449,450,451,452,453,454,455,456,457,459,460,461,462,463,464,465,466,467,468,469,470,471,473,474,477,478,479,480],"500":[501,502,503,504,505,507,508,509,510,511,512,514,516,517,518,519,522,523,524,525,526,527,528,529,530,531,532,533,537,538,540,543,544,545,546,547,548,549,550,551,553,554,556,557,560,561,562,563,565,566,568,569,571,573,575,576,577,578,580,582,583,584,591,592]};
  const PRICE_BANDS = [[null,2000],[2000,3000],[3000,4000],[4000,5000],[5000,7000],[7000,10000],[10000,null]];

  // ---- helpers ------------------------------------------------------------
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const jitter = (a, b) => Math.floor(a + Math.random() * (b - a));
  const uuid = () => (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, "") :
    "x".repeat(32).replace(/x/g, () => ((Math.random() * 16) | 0).toString(16)));

  function rangeLiteral(name, lo, hi) {
    if (lo == null && hi == null) return null;
    const parts = [];
    if (lo != null) parts.push(`lowerBound: ${lo}`);
    if (hi != null) parts.push(`upperBound: ${hi}`);
    return `${name}: { ${parts.join(", ")} }`;
  }

  function buildSearchQuery(areaCodes, bucket, page, token, pmin, pmax) {
    const b = BUCKETS.find((x) => x.name === bucket);
    const filters = [
      `areas: [${areaCodes.join(", ")}]`,
      "rentalStatus: ACTIVE",
      rangeLiteral("bedrooms", b.min, b.max),
      rangeLiteral("price", pmin, pmax),
    ].filter(Boolean).join(", ");
    const input = `{ sorting: { attribute: RECOMMENDED, direction: DESCENDING }, filters: { ${filters} }, adStrategy: NONE, userSearchToken: "${token}", perPage: ${PER_PAGE}, page: ${page} }`;
    return `query SearchRentalsFederated {
  searchRentals(input: ${input}) {
    __typename
    edges {
      __typename
      ... on OrganicRentalEdge { node { __typename ...D } }
      ... on FeaturedRentalEdge { node { __typename ...D } }
      ... on SponsoredRentalEdge { node { __typename ...D } }
    }
    totalCount
  }
}
fragment L on LeadMedia { __typename photo { __typename key } floorPlan { __typename key } }
fragment D on SearchRentalListing { __typename id areaName bedroomCount buildingType isNewDevelopment leadMedia { __typename ...L } livingAreaSize photos { __typename key } price street unit urlPath }`;
  }

  const BLOCK_RE = /jsClientSrc|firstPartyEnabled|Press & Hold|Access to this page has been denied|px-captcha/;

  async function gql(query) {
    const res = await fetch(ENDPOINT, {
      method: "POST",
      credentials: "include",
      headers: {
        "content-type": "application/json",
        "accept": "application/json",
        "apollographql-client-name": "srp-frontend-service",
        "apollographql-client-version": "version  50bef71ef923e981bdcb7c781851c3bfdb12a0c1",
        "os": "web",
        "app-version": "1.0.0",
      },
      body: JSON.stringify({ query }),
    });
    const text = await res.text();
    if (res.status !== 200 || BLOCK_RE.test(text)) {
      const e = new Error("BLOCKED " + res.status);
      e.blocked = true;
      throw e;
    }
    const json = JSON.parse(text);
    if (json.errors) throw new Error("GraphQL: " + json.errors.map((x) => x.message).join("; "));
    return json.data;
  }

  async function gqlRetry(query, logFn) {
    for (let i = 1; i <= BLOCK_RETRY; i++) {
      try {
        return await gql(query);
      } catch (e) {
        if (!e.blocked || i === BLOCK_RETRY) throw e;
        logFn(`  · blocked, waiting ${BLOCK_WAIT / 1000}s then retrying (${i}/${BLOCK_RETRY})…`);
        await sleep(BLOCK_WAIT);
      }
    }
  }

  const KEEP_EDGES = new Set(["OrganicRentalEdge", "FeaturedRentalEdge"]);

  function parseEdges(searchRentals, bucket) {
    const out = [];
    for (const edge of searchRentals.edges || []) {
      if (!edge || !KEEP_EDGES.has(edge.__typename)) continue;
      const n = edge.node;
      if (!n || n.id == null) continue;
      const fp = n.leadMedia && n.leadMedia.floorPlan && n.leadMedia.floorPlan.key;
      const url = n.urlPath
        ? (n.urlPath.startsWith("http") ? n.urlPath : "https://streeteasy.com" + n.urlPath)
        : `https://streeteasy.com/rental/${n.id}`;
      out.push({
        id: String(n.id),
        bucket,
        bedroom_count: n.bedroomCount ?? null,
        area_name: n.areaName ?? null,
        url,
        street: n.street ?? null,
        unit: n.unit ?? null,
        price: n.price ?? null,
        living_area_size: n.livingAreaSize ?? null,
        building_type: n.buildingType ?? null,
        is_new_development: n.isNewDevelopment ?? null,
        has_floor_plan: !!fp,
        floor_plan_keys: fp ? [fp] : [],
        photo_keys: (n.photos || []).map((p) => p && p.key).filter(Boolean),
        source: "harvest-graphql",
      });
    }
    return out;
  }

  function subdivide(shard) {
    const hasBand = shard.pmin != null || shard.pmax != null;
    if (hasBand) return null;
    if (BOROUGHS.some((b) => b.code === shard.area)) {
      return (NEIGH[String(shard.area)] || []).map((c) => ({ area: c, bucket: shard.bucket, pmin: null, pmax: null }));
    }
    return PRICE_BANDS.map(([lo, hi]) => ({ area: shard.area, bucket: shard.bucket, pmin: lo, pmax: hi }));
  }

  function describe(s) {
    const band = (s.pmin != null || s.pmax != null) ? ` $${s.pmin || 0}-${s.pmax || "∞"}` : "";
    return `area:${s.area}/${s.bucket}${band}`;
  }

  async function enumerateShard(shard, sink, logFn) {
    const token = uuid();
    let page = 1, total = null, got = 0, reachedCap = false;
    while (page <= PAGE_CAP) {
      if (window.__seStop) throw new Error("stopped by user");
      const data = await gqlRetry(buildSearchQuery([shard.area], shard.bucket, page, token, shard.pmin, shard.pmax), logFn);
      const sr = data.searchRentals || {};
      if (total == null) total = sr.totalCount || 0;
      const recs = parseEdges(sr, shard.bucket);
      if (recs.length === 0) break;
      recs.forEach(sink);
      got += recs.length;
      logFn(`  ${describe(shard)} p${page}: +${recs.length} → ${got}${total ? "/" + total : ""}`);
      if (got >= total) break;
      if (page === PAGE_CAP) { reachedCap = true; break; }
      page++;
      await sleep(jitter(DELAY_MIN, DELAY_MAX));
    }
    return { total: total || 0, got, capped: reachedCap && got < (total || 0) };
  }

  async function harvest(buckets, areaCodes, logFn, onProgress) {
    window.__seStop = false;
    const byId = new Map();
    try {
      for (const bucket of buckets) {
        logFn(`\n[bucket ${bucket}]`);
        const seeds = (areaCodes && areaCodes.length)
          ? areaCodes.map((c) => ({ area: c, bucket, pmin: null, pmax: null }))
          : BOROUGHS.map((b) => ({ area: b.code, bucket, pmin: null, pmax: null }));
        const queue = seeds.slice();
        while (queue.length) {
          const shard = queue.shift();
          const sink = (r) => {
            const prev = byId.get(r.id);
            if (!prev || (r.has_floor_plan && !prev.has_floor_plan)) byId.set(r.id, r);
          };
          const { total, got, capped } = await enumerateShard(shard, sink, logFn);
          const fp = [...byId.values()].filter((r) => r.has_floor_plan).length;
          logFn(`  ${describe(shard)}: total≈${total}, collected ${got}${capped ? " (capped → subdividing)" : ""} | unique ${byId.size}, w/ floor plan ${fp}`);
          onProgress(byId.size, fp);
          if (capped) {
            const subs = subdivide(shard);
            if (subs) queue.push(...subs);
            else logFn(`  ! ${describe(shard)} still capped at finest grain — some unreached`);
          }
          await sleep(jitter(DELAY_MIN, DELAY_MAX));
        }
      }
    } catch (e) {
      // Always keep what we collected so a Stop / block still yields a file.
      if (e.message === "stopped by user") logFn("\n[stopped — saving partial results]");
      else {
        logFn(`\n[error: ${e.message} — saving partial results]`);
        if (e.blocked) logFn("PerimeterX blocked you. Reload, browse a listing as a human, then retry.");
      }
    }
    return [...byId.values()];
  }

  function downloadJSON(obj, filename) {
    const blob = new Blob([JSON.stringify(obj)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  }

  // ---- UI -----------------------------------------------------------------
  function ui() {
    if (document.getElementById("se-harvest-box")) return;
    const box = document.createElement("div");
    box.id = "se-harvest-box";
    box.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:999999;background:#0a1f44;color:#fff;font:12px/1.4 monospace;padding:10px;border-radius:8px;width:340px;box-shadow:0 4px 16px rgba(0,0,0,.4)";
    box.innerHTML = `
      <div style="font-weight:bold;margin-bottom:6px">StreetEasy Floor-Plan Harvester</div>
      <label style="display:block;margin-bottom:6px">Buckets:
        <select id="se-buckets" multiple size="5" style="width:100%;margin-top:3px">
          ${BUCKETS.map((b) => `<option value="${b.name}" selected>${b.label}</option>`).join("")}
        </select>
      </label>
      <label style="display:block;margin-bottom:6px">Area codes (blank = all 5 boroughs; e.g. 313 = Bushwick, good for a quick test):
        <input id="se-area" placeholder="blank = all NYC" style="width:100%;margin-top:3px;box-sizing:border-box"/>
      </label>
      <button id="se-start" style="background:#1f6feb;color:#fff;border:0;padding:6px 10px;border-radius:5px;cursor:pointer">▶ Harvest floor plans</button>
      <button id="se-stop" style="background:#8b2c2c;color:#fff;border:0;padding:6px 10px;border-radius:5px;cursor:pointer;margin-left:6px">■ Stop</button>
      <div id="se-stat" style="margin-top:6px">idle</div>
      <pre id="se-log" style="max-height:160px;overflow:auto;background:#06122b;padding:6px;border-radius:5px;margin-top:6px;white-space:pre-wrap"></pre>`;
    document.body.appendChild(box);
    const logEl = box.querySelector("#se-log");
    const statEl = box.querySelector("#se-stat");
    const log = (m) => { logEl.textContent += m + "\n"; logEl.scrollTop = logEl.scrollHeight; console.log("[harvest]" + m); };
    const progress = (n, fp) => { statEl.textContent = `collected ${n} listings · ${fp} with floor plans`; };

    box.querySelector("#se-stop").onclick = () => { window.__seStop = true; log("\n[stopping after current request…]"); };
    box.querySelector("#se-start").onclick = async () => {
      const buckets = [...box.querySelectorAll("#se-buckets option:checked")].map((o) => o.value);
      if (!buckets.length) { log("pick at least one bucket"); return; }
      const areaRaw = box.querySelector("#se-area").value.trim();
      const areaCodes = areaRaw ? areaRaw.split(",").map((s) => parseInt(s.trim(), 10)).filter(Boolean) : null;
      logEl.textContent = "";
      log(`starting: ${buckets.join(", ")}${areaCodes ? " | area " + areaCodes.join(",") : " | all NYC"}`);
      const listings = await harvest(buckets, areaCodes, log, progress);  // never throws — returns partial
      if (!listings.length) { log("\nno listings collected (blocked on the first request?)"); return; }
      const withFp = listings.filter((r) => r.has_floor_plan).length;
      const payload = { generated_at: new Date().toISOString(), buckets, total: listings.length, with_floorplan: withFp, listings };
      downloadJSON(payload, "harvest.json");
      log(`\nDONE: ${listings.length} listings, ${withFp} with floor plans → harvest.json downloaded`);
      log(`next: streeteasy-floorplans ingest harvest.json --download`);
    };
  }

  // expose for console use + auto-build UI
  window.seHarvest = (buckets, areaCodes) =>
    harvest(buckets || BUCKETS.map((b) => b.name), areaCodes || null, console.log, () => {});
  ui();
  console.log("[harvest] ready — click ▶ Harvest floor plans (bottom-right), or run seHarvest()");
})();
