# streeteasy-floorplan-datasets

Build a bedroom-categorized dataset of **StreetEasy rental floor plans**
(studio / 1 / 2 / 3 / 4+), with listings that have **no** floor plan detected and
recorded automatically — no manual sorting.

Feasibility research and the approach decision are written up in
[issue #2](https://github.com/dzikrisyairozi/streeteasy-floorplan-datasets/issues/2).
This repo is the implementation of that plan — and ships the resulting dataset.

---

## The dataset

`dataset/` contains **5,843 floor-plan images** across **13,068** NYC rental
listings, categorized by bedroom count, harvested **June 2026** via the free
browser path (below — no proxy, no paid service).

| Bucket | Listings | With floor plan | Rate | Images on disk |
|---|---:|---:|---:|---:|
| Studio | 2,216 | 1,311 | 59% | 1,210 |
| 1BR | 4,961 | 2,677 | 54% | 2,439 |
| 2BR | 3,823 | 1,590 | 42% | 1,529 |
| 3BR | 1,563 | 495 | 32% | 482 |
| 4+ | 505 | 185 | 37% | 183 |
| **Total** | **13,068** | **6,258** | **48%** | **5,843** |

- **Images on disk (5,843) < listings with a floor plan (6,258)** because identical
  plans (the same unit line reused across a building) are de-duplicated by content
  hash — 415 byte-identical copies collapsed, **0 duplicate files** remain.
- Floor-plan availability **declines as bedrooms rise** (studio 59% → 3BR 32%).
- The **6,810** listings with no floor plan are kept in `_no_floorplan.jsonl`
  (recorded, not dropped), so the dataset is auditable.
- Per-image manifest + sha256 in `floorplans.jsonl`; full index in `index.jsonl`;
  summary in `stats.json`. Layout details under [Output layout](#output-layout).

> ⚠️ The images are third-party copyrighted material, **not** covered by this
> repo's code license — see [License & legal](#license--legal).

---

## How it works

StreetEasy is a Next.js app backed by a GraphQL API at `api-v6.streeteasy.com`.
Two facts make full automation possible:

1. **Bedroom count is a structured field** (`bedroomCount` / `numberOfBedrooms`;
   `0` = studio). Bucketing is a lookup, not guesswork.
2. **Floor-plan presence is a structured field**, not something you eyeball:
   * search results expose `node.leadMedia.floorPlan.key` (nullable);
   * listing detail exposes the full `media.floorPlans[].key` array.

   A listing has a floor plan ⇔ that field is non-empty. Each key renders to an
   image at `https://photos.zillowstatic.com/fp/{key}-{size}.webp` (the CDN is
   public, not bot-walled).

The pipeline:

```
enumerate (GraphQL searchRentals, sharded)
   → floor-plan presence + key straight from leadMedia.floorPlan
   → [optional] detail enrichment (rentalByListingId.media.floorPlans[])
   → write index.jsonl + _no_floorplan.jsonl + stats.json
   → download floor-plan images into dataset/<bucket>/, de-duped by content hash
```

### Beating the ~1,000-result cap with adaptive sharding

StreetEasy only serves **~the first ~1,000 results per search** (it returns empty
pages beyond that), so a popular bucket can't be fully reached from one query —
Manhattan alone has 2,400+ 1-bedrooms. The enumerator shards **per borough**, and
when a shard comes back materially short of its `totalCount` it subdivides
**borough → neighborhood → price band**, de-duplicating listings by id across
shards (overlapping shards are harmless). Area codes for all five boroughs and
~250 neighborhoods are baked in (`streeteasy_floorplans/constants.py`).

---

## ⚠️ The hard part: PerimeterX, and why you need a residential proxy

`api-v6.streeteasy.com` is protected by **PerimeterX / HUMAN**. Verified live
(2026-06): a cold request — even from a residential IP, even from inside a real
browser page context — returns **HTTP 403** with a PerimeterX challenge body.
The reference open-source clients get through by rotating across a **pool of US
residential IPs**, where some sessions pass PerimeterX's probabilistic trust
scoring; from a single IP it fails every time. Datacenter IPs are blocked
outright.

**So: a US residential rotating proxy is required to actually fetch data.** This
tool builds the request correctly (Chrome TLS/JA3 impersonation via `curl_cffi`,
the verbatim Apollo `srp-frontend-service` headers, fresh proxy session per
request, retry/backoff with block detection) — but it can only succeed when
pointed at a real residential proxy. No proxy → expect 403s.

> No-proxy fallback for enumeration only: a **real browser** can load the
> search-results HTML pages (the PerimeterX sensor JS runs and passes). Save a
> search page's HTML from your browser and run `parse-srp` on it to extract
> listing ids + bedroom counts offline (floor plans still require a detail/API
> call, hence a proxy).

---

## 🆓 Free path (no proxy): harvest from your own browser

You don't need a paid proxy. Split the work by who PerimeterX trusts:

* the floor-plan **images** live on Zillow's CDN, which is **wide open** (no
  proxy, no auth — plain download);
* the only thing behind PerimeterX is fetching the floor-plan **keys**, and the
  one client PerimeterX trusts for free is **your own real Chrome** — when you
  browse StreetEasy normally, you're not blocked.

So: harvest the keys with a tiny script in your real browser, then let this tool
bulk-download the images.

1. Open <https://streeteasy.com/> in your normal Chrome.
2. Run **`tools/harvest.user.js`** — either install it in Tampermonkey, or open
   DevTools → Console, paste the file, press Enter. A **“▶ Harvest floor plans”**
   panel appears bottom-right. Pick buckets, click it. It paginates the GraphQL
   search (sharding across boroughs/neighborhoods to beat the 100-page cap),
   collects every listing's `leadMedia.floorPlan.key`, and downloads
   **`harvest.json`**. If a “Press & Hold” page ever appears, solve it like a
   human and click again.
3. Feed it to the tool — this part needs **no proxy** (open CDN):

   ```bash
   streeteasy-floorplans ingest harvest.json --download
   ```

   → fills `dataset/<bucket>/` with real floor-plan images, deduped + indexed.

Verified end-to-end here: `ingest --download` pulls real `.webp` floor plans
from the CDN, buckets them, and de-dupes identical plans by content hash. The
only manual step is running the harvester in your browser.

---

## Install

Requires Python ≥ 3.10.

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate     |  macOS/Linux:  source .venv/bin/activate
pip install -e .
# dev extras (tests):  pip install -e ".[dev]"
```

The parser / dataset / proxy core is pure-stdlib; only live fetching needs
`curl_cffi` (installed by the line above).

## Configure the proxy

Set a US residential proxy. Put the literal token `{{rand}}` in the userinfo to
get a fresh exit IP per request (rotating/sticky-session gateway):

```bash
export SE_PROXY_URL='http://USER-session-{{rand}}:PASS@gate.yourprovider.com:7000'
```

Other env knobs (all optional): `SE_OUT_DIR`, `SE_IMPERSONATE` (default
`chrome131`), `SE_PER_PAGE`, `SE_IMAGE_SIZE` (default `cc_ft_1536`, the largest),
`SE_MAX_RETRIES`, `SE_BACKOFF_BASE`, `SE_MIN_DELAY`, `SE_MAX_DELAY`.

## Usage

```bash
# Full pipeline for one bucket in one borough (good first run):
streeteasy-floorplans run --buckets studio --areas brooklyn --details hits

# Everything, all boroughs, authoritative floor-plan check, then download:
streeteasy-floorplans run --buckets studio,1br,2br,3br,4plus --details all

# Enumerate only (write index.jsonl, no image download):
streeteasy-floorplans enumerate --buckets 1br --areas manhattan

# Free path: ingest a browser-harvested harvest.json, then download images (no proxy):
streeteasy-floorplans ingest harvest.json --download

# Download floor-plan images from an existing index:
streeteasy-floorplans download

# Inspect one listing's floor-plan info (debug):
streeteasy-floorplans details 5063351

# Offline: parse a search-results HTML file you saved from your browser:
streeteasy-floorplans parse-srp page.html --bucket studio

# List area codes:
streeteasy-floorplans areas
streeteasy-floorplans areas --borough brooklyn
```

(No console script yet? Use `python -m streeteasy_floorplans <command>`.)

`--details` modes: `none` (trust search `leadMedia.floorPlan`, fastest) ·
`hits` (enrich flagged listings to grab *all* plan images) · `all` (call detail
for every listing — authoritative presence, slowest).

## Output layout

```
dataset/
  studio/  1br/  2br/  3br/  4plus/   # floor-plan images: <listing-id>[__n].webp
  index.jsonl          # one row per listing (id, bucket, beds, has_floor_plan, keys, …)
  _no_floorplan.jsonl  # listings with no floor plan — kept, not discarded
  floorplans.jsonl     # one row per downloaded image (path, sha256, dedupe info)
  stats.json           # totals + per-bucket counts + floor-plan hit rate
```

Identical floor plans (the same unit line reused across a building) are
de-duplicated by content hash, so each distinct image is stored once.

---

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

The suite runs fully offline. `tests/test_srp_html.py` validates the parser
against a **real captured StreetEasy search page**
(`tests/fixtures/srp_beds_le1_page1.html`): 14 listings, `totalCount=9227`,
`totalPages=100`, criteria `area:1|beds:0-1|status:open`. The GraphQL query
builder and response parsers, image URL/dedupe logic, proxy session rotation,
and sharding logic are covered too.

**Verification status:** 24 unit tests pass and the offline CLI is green. The
dataset above was built **for real** via the free browser-harvest path (see
`dataset/stats.json`). The headless proxy path (direct api-v6 from this tool)
requires a US residential proxy pool; without one, cold requests are
PerimeterX-403'd, which the client detects and surfaces as `BlockedError`.

---

## Project layout

```
streeteasy_floorplans/
  constants.py   # bedroom buckets, area-code table, GraphQL identity headers, CDN format
  config.py      # Settings (env + defaults)
  models.py      # Bucket, Shard, ListingRecord, FloorPlanAsset dataclasses
  proxy.py       # rotating-session proxy URL templating
  http_client.py # curl_cffi transport: impersonation, proxy, retry/backoff, block detection
  graphql.py     # query builders + response parsers + GraphQLClient
  srp_html.py    # fallback HTML/RSC (Flight) parser for search pages
  images.py      # key → CDN URL, download, content-hash dedupe
  pipeline.py    # adaptive sharding, enumerate, enrich, ingest, index, download, summarize
  cli.py         # command-line interface
tools/
  harvest.user.js  # browser-side floor-plan-key harvester (free, no-proxy path)
tests/           # offline tests + a real captured SRP fixture
```

---

## License & legal

**Code — MIT** (see [`LICENSE`](LICENSE)). The GraphQL query shapes and area codes
are derived from the MIT-licensed
[`evandcoleman/streeteasy-api`](https://github.com/evandcoleman/streeteasy-api) and
[`eneakllomollari/streeteasy-cli`](https://github.com/eneakllomollari/streeteasy-cli).

**Dataset (`dataset/`) — NOT MIT.** The floor-plan images are **not** the
project's to license: they are third-party material, copyright of the original
listing brokers / StreetEasy (Zillow Group), included here for research and
reference only. **No license to reuse or redistribute the images is granted.**

Scraping StreetEasy is also **against its Terms of Service**, and PerimeterX
exists specifically to prevent it. This project documents technical feasibility
and is intended for personal research; publishing or redistributing the images
carries real legal risk that is yours to assess. Not affiliated with StreetEasy
or Zillow Group.
