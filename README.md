# streeteasy-floorplan-datasets

Build a bedroom-categorized dataset of **StreetEasy rental floor plans**
(studio / 1 / 2 / 3 / 4+), with listings that have **no** floor plan detected and
recorded automatically — no manual sorting.

Feasibility research and the approach decision are written up in
[issue #2](https://github.com/dzikrisyairozi/streeteasy-floorplan-datasets/issues/2).
This repo is the implementation of that plan.

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

### Beating the 100-page cap with adaptive sharding

StreetEasy caps any single search at ~100 pages, so a popular bucket (e.g.
NYC-wide 1BR) can't be fully reached from one query. The enumerator shards
**per borough**, and when a shard is still capped it subdivides
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

**Verification status:** unit tests (20/20) and the offline CLI are green. The
live happy path (a successful api-v6 fetch) requires a real US residential proxy
pool and was **not** exercised here — without one, every cold request is
PerimeterX-403'd, which the client correctly detects and surfaces as
`BlockedError`. Point `SE_PROXY_URL` at a residential gateway to run it for real.

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
  pipeline.py    # adaptive sharding, enumerate, enrich, index, download, summarize
  cli.py         # command-line interface
tests/           # offline tests + a real captured SRP fixture
```

---

## Legal / ToS

Scraping StreetEasy is **against its Terms of Service**, and floor-plan images
are likely **copyrighted** by the listing brokers / StreetEasy. PerimeterX
exists specifically to prevent this. This project documents technical
feasibility and is intended for personal research; redistributing scraped
copyrighted floor plans carries materially more risk than private analysis.
Decide your use and risk before running at scale. Not affiliated with StreetEasy
or Zillow Group.

Code is MIT-licensed; the GraphQL query shapes and area codes are derived from
the MIT-licensed [`evandcoleman/streeteasy-api`](https://github.com/evandcoleman/streeteasy-api)
and [`eneakllomollari/streeteasy-cli`](https://github.com/eneakllomollari/streeteasy-cli).
