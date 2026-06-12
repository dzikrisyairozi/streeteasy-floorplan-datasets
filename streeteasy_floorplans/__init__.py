"""StreetEasy floor-plan dataset builder.

Collect NYC rental floor plans from StreetEasy, categorized by bedroom count
(studio / 1 / 2 / 3 / 4+), using the StreetEasy GraphQL API (api-v6).

Floor-plan presence is a structured field (``leadMedia.floorPlan`` in search,
``media.floorPlans[]`` in listing detail) — detection is deterministic, no image
classification required. See ``README.md`` and GitHub issue #2 for the full
feasibility write-up.

The parser / dataset / proxy / model layers are pure-stdlib and import without
``curl_cffi``; only the live HTTP layer (``http_client``) needs it.
"""

__version__ = "0.1.0"
