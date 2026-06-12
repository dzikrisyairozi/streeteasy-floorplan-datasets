"""Static StreetEasy reference data: bedroom buckets, area codes, API identity.

The ``AREAS`` table and the GraphQL client-identity headers are transcribed
verbatim from the open-source reference clients (evandcoleman/streeteasy-api and
eneakllomollari/streeteasy-cli, both MIT). Numeric area codes are what the
GraphQL ``searchRentals`` filter expects in ``filters.areas``.
"""

from __future__ import annotations

from .models import Bucket

# --- Bedroom buckets (the dataset categories) -------------------------------
# Studio is bedroomCount == 0; the 4+ bucket is open-ended.
BUCKETS: list[Bucket] = [
    Bucket("studio", "Studio", 0, 0),
    Bucket("1br", "1 Bedroom", 1, 1),
    Bucket("2br", "2 Bedrooms", 2, 2),
    Bucket("3br", "3 Bedrooms", 3, 3),
    Bucket("4plus", "4+ Bedrooms", 4, None),
]
BUCKETS_BY_NAME: dict[str, Bucket] = {b.name: b for b in BUCKETS}


def bucket_for_beds(beds: int | None) -> Bucket | None:
    for b in BUCKETS:
        if b.matches(beds):
            return b
    return None


# --- Areas ------------------------------------------------------------------
ALL_NYC_AND_NJ = 1

BOROUGHS: dict[int, str] = {
    100: "manhattan",
    200: "bronx",
    300: "brooklyn",
    400: "queens",
    500: "staten-island",
}

# name -> numeric area code (verbatim from streeteasy-api src/constants.ts `Areas`).
AREAS: dict[str, int] = {
    "ALL_NYC_AND_NJ": 1,
    # Manhattan (100s)
    "MANHATTAN": 100, "ROOSEVELT_ISLAND": 101, "ALL_DOWNTOWN": 102, "CIVIC_CENTER": 103,
    "FINANCIAL_DISTRICT": 104, "TRIBECA": 105, "STUYVESANT_TOWN_PCV": 106, "SOHO": 107,
    "LITTLE_ITALY": 108, "LOWER_EAST_SIDE": 109, "CHINATOWN": 110, "TWO_BRIDGES": 111,
    "BATTERY_PARK_CITY": 112, "GRAMERCY_PARK": 113, "FULTON_SEAPORT": 114, "CHELSEA": 115,
    "GREENWICH_VILLAGE": 116, "EAST_VILLAGE": 117, "NOHO": 118, "ALL_MIDTOWN": 119,
    "MIDTOWN": 120, "CENTRAL_PARK_SOUTH": 121, "MIDTOWN_SOUTH": 122, "MIDTOWN_EAST": 123,
    "MIDTOWN_WEST": 124, "MURRAY_HILL": 130, "SUTTON_PLACE": 131, "TURTLE_BAY": 132,
    "KIPS_BAY": 133, "BEEKMAN": 134, "ALL_UPPER_WEST_SIDE": 135, "LINCOLN_SQUARE": 136,
    "UPPER_WEST_SIDE": 137, "MANHATTAN_VALLEY": 138, "ALL_UPPER_EAST_SIDE": 139,
    "UPPER_EAST_SIDE": 140, "LENOX_HILL": 141, "YORKVILLE": 142, "CARNEGIE_HILL": 143,
    "ALL_UPPER_MANHATTAN": 144, "HUDSON_HEIGHTS": 145, "HUDSON_YARDS": 146,
    "MORNINGSIDE_HEIGHTS": 147, "HAMILTON_HEIGHTS": 148, "WASHINGTON_HEIGHTS": 149,
    "INWOOD": 150, "FORT_GEORGE": 151, "HELLS_KITCHEN": 152, "WEST_HARLEM": 153,
    "CENTRAL_HARLEM": 154, "EAST_HARLEM": 155, "WEST_VILLAGE": 157, "FLATIRON": 158,
    "NOMAD": 159, "MANHATTANVILLE": 161, "NOLITA": 162, "WEST_CHELSEA": 163,
    "UPPER_CARNEGIE_HILL": 164, "SOUTH_HARLEM": 165, "HUDSON_SQUARE": 166, "MARBLE_HILL": 226,
    # Bronx (200s)
    "BRONX": 200, "MOTT_HAVEN": 201, "MELROSE": 202, "PORT_MORRIS": 203, "HUNTS_POINT": 204,
    "LONGWOOD": 205, "MORRISANIA": 207, "CLAREMONT": 208, "CROTONA_PARK_EAST": 209,
    "HIGHBRIDGE": 210, "CONCOURSE": 211, "MORRIS_HEIGHTS": 212, "UNIVERSITY_HEIGHTS": 213,
    "FORDHAM": 214, "MT_HOPE": 215, "EAST_TREMONT": 216, "BELMONT": 218, "WEST_FARMS": 219,
    "KINGSBRIDGE_HEIGHTS": 220, "BEDFORD_PARK": 221, "KINGSBRIDGE": 224, "RIVERDALE": 225,
    "FIELDSTON": 227, "SOUNDVIEW": 228, "CASTLE_HILL": 229, "PARKCHESTER": 231,
    "THROGS_NECK": 232, "PELHAM_BAY": 233, "CO_OP_CITY": 234, "WESTCHESTER_SQUARE": 235,
    "CITY_ISLAND": 236, "MORRIS_PARK": 237, "PELHAM_PARKWAY": 238, "VAN_NEST": 240,
    "LACONIA": 241, "WILLIAMSBRIDGE": 242, "BAYCHESTER": 243, "WOODLAWN": 244,
    "WAKEFIELD": 245, "EASTCHESTER": 246, "TREMONT": 248, "SPUYTEN_DUYVIL": 249,
    "NORWOOD": 260, "BRONXWOOD": 265, "PELHAM_GARDENS": 266, "LOCUST_POINT": 267,
    "WOODSTOCK": 270, "NORTH_NEW_YORK": 271, "WESTCHESTER_VILLAGE": 272, "COUNTRY_CLUB": 273,
    "SCHUYLERVILLE": 274, "EDENWALD": 276,
    # Brooklyn (300s)
    "BROOKLYN": 300, "GREENPOINT": 301, "WILLIAMSBURG": 302, "DOWNTOWN_BROOKLYN": 303,
    "FORT_GREENE": 304, "BROOKLYN_HEIGHTS": 305, "BOERUM_HILL": 306, "DUMBO": 307,
    "VINEGAR_HILL": 308, "FARRAGUT": 309, "BEDFORD_STUYVESANT": 310, "STUYVESANT_HEIGHTS": 312,
    "BUSHWICK": 313, "EAST_NEW_YORK": 314, "NEW_LOTS": 315, "CITY_LINE": 316,
    "STARRETT_CITY": 317, "RED_HOOK": 318, "PARK_SLOPE": 319, "GOWANUS": 320,
    "CARROLL_GARDENS": 321, "COBBLE_HILL": 322, "SUNSET_PARK": 323, "WINDSOR_TERRACE": 324,
    "CROWN_HEIGHTS": 325, "PROSPECT_HEIGHTS": 326, "WEEKSVILLE": 327,
    "COLUMBIA_ST_WATERFRONT_DISTRICT": 328, "PROSPECT_LEFFERTS_GARDENS": 329, "WINGATE": 330,
    "BAY_RIDGE": 331, "DYKER_HEIGHTS": 332, "FORT_HAMILTON": 333, "BENSONHURST": 334,
    "MAPLETON": 335, "BATH_BEACH": 336, "GRAVESEND": 337, "BOROUGH_PARK": 338,
    "OCEAN_PARKWAY": 339, "KENSINGTON": 340, "CONEY_ISLAND": 341, "BRIGHTON_BEACH": 342,
    "DITMAS_PARK": 343, "HOMECREST": 344, "SEAGATE": 345, "FLATBUSH": 346,
    "CYPRESS_HILLS": 347, "MIDWOOD": 348, "SHEEPSHEAD_BAY": 349, "MANHATTAN_BEACH": 350,
    "FISKE_TERRACE": 352, "OCEAN_HILL": 353, "BROWNSVILLE": 354, "PROSPECT_PARK_SOUTH": 355,
    "EAST_FLATBUSH": 358, "CANARSIE": 359, "FLATLANDS": 360, "MARINE_PARK": 361,
    "MILL_BASIN": 362, "BERGEN_BEACH": 363, "CLINTON_HILL": 364, "OLD_MILL_BASIN": 365,
    "MADISON": 366, "GREENWOOD": 367, "GERRITSEN_BEACH": 370, "EAST_WILLIAMSBURG": 373,
    # Queens (400s)
    "QUEENS": 400, "ASTORIA": 401, "LONG_ISLAND_CITY": 402, "SUNNYSIDE": 403, "WOODSIDE": 404,
    "JACKSON_HEIGHTS": 405, "EAST_ELMHURST": 406, "NORTH_CORONA": 407, "ELMHURST": 408,
    "CORONA": 409, "MASPETH": 410, "MIDDLE_VILLAGE": 411, "RIDGEWOOD": 412, "GLENDALE": 413,
    "REGO_PARK": 414, "FOREST_HILLS": 415, "FLUSHING": 416, "WHITSTONE": 417,
    "COLLEGE_POINT": 418, "FRESH_MEADOWS": 419, "KEW_GARDENS_HILLS": 420, "JAMAICA_HILLS": 421,
    "WOODHAVEN": 422, "RICHMOND_HILL": 423, "KEW_GARDENS": 424, "HOWARD_BEACH": 425,
    "OZONE_PARK": 426, "SOUTH_OZONE_PARK": 427, "BAYSIDE": 428, "DOUGLASTON": 429,
    "LITTLE_NECK": 430, "AUBURNDALE": 431, "JAMAICA": 432, "SOUTH_JAMAICA": 433, "HOLLIS": 434,
    "ST_ALBANS": 435, "LAURELTON": 436, "CAMBRIA_HEIGHTS": 437, "QUEENS_VILLAGE": 438,
    "GLEN_OAKS": 439, "FAR_ROCKAWAY": 440, "BROAD_CHANNEL": 441, "FLORAL_PARK": 442,
    "BELLEROSE": 443, "ROSEDALE": 444, "SPRINGFIELD_GARDENS": 445, "BRIARWOOD": 446,
    "JAMAICA_ESTATES": 447, "ARVERNE": 448, "NEW_HYDE_PARK": 449, "SOUTH_RICHMOND_HILL": 450,
    "OAKLAND_GARDENS": 451, "ROCKAWAY_PARK": 452, "HILLCREST": 453, "POMONOK": 454,
    "UTOPIA": 455, "EAST_FLUSHING": 456, "MURRAY_HILL_QUEENS": 457, "CLEARVIEW": 459,
    "MALBA": 460, "BEECHHURST": 461, "BAYS_WATER": 462, "BELLE_HARBOR": 463,
    "BREEZY_POINT": 464, "NEPONSIT": 465, "EDGEMERE": 466, "HAMILTON_BEACH": 467,
    "RAMBLERSVILLE": 468, "ROCKWOOD_PARK": 469, "LINDENWOOD": 470, "OLD_HOWARD_BEACH": 471,
    "HAMMELS": 473, "DITMARS_STEINWAY": 474, "ROCKAWAY_ALL": 477, "HUNTERS_POINT": 478,
    "BROOKVILLE": 479, "BAY_TERRACE_QUEENS": 480,
    # Staten Island (500s)
    "STATEN_ISLAND": 500, "NORTH_SHORE": 501, "SOUTH_SHORE": 502, "EAST_SHORE": 503,
    "WEST_SHORE": 504, "MID_ISLAND": 505, "ANNADALE": 507, "ARDEN_HEIGHTS": 508,
    "ARLINGTON": 509, "ARROCHAR": 510, "BAY_TERRACE": 511, "BLOOMFIELD": 512,
    "BULLS_HEAD": 514, "CASTLETON_CORNERS": 516, "CHARLESTON": 517, "CHELSEA_STATEN_ISLAND": 518,
    "CLIFTON": 519, "DONGAN_HILLS": 522, "EGBERTVILLE": 523, "ELM_PARK": 524,
    "ELTINGVILLE": 525, "EMERSON_HILL": 526, "FORT_WADSWORTH": 527, "GRANITEVILLE": 528,
    "GRANT_CITY": 529, "GRASMERE": 530, "GREAT_KILLS": 531, "GREENRIDGE": 532,
    "GRYMES_HILL": 533, "HOWLAND_HOOK": 537, "HUGUENOT": 538, "LIGHTHOUSE_HILL": 540,
    "MANOR_HEIGHTS": 543, "MARINERS_HARBOR": 544, "MEIERS_CORNERS": 545, "MIDLAND_BEACH": 546,
    "NEW_BRIGHTON": 547, "NEW_DORP": 548, "NEW_SPRINGVILLE": 549, "OAKWOOD": 550,
    "OCEAN_BREEZE": 551, "PARK_HILL": 553, "PLEASANT_PLAINS": 554, "PORT_RICHMOND": 556,
    "PRINCES_BAY": 557, "RICHMOND_VALLEY": 560, "RICHMONDTOWN": 561, "ROSEBANK": 562,
    "ROSSVILLE": 563, "SHORE_ACRES": 565, "SILVER_LAKE": 566, "SOUTH_BEACH": 568,
    "SAINT_GEORGE": 569, "STAPLETON": 571, "SUNNYSIDE_STATEN_ISLAND": 573, "TODT_HILL": 575,
    "TOMPKINSVILLE": 576, "TOTTENVILLE": 577, "TRAVIS": 578, "WEST_BRIGHTON": 580,
    "WESTERLEIGH": 582, "WILLOWBROOK": 583, "WOODROW": 584, "NEW_DORP_BEACH": 591,
    "OAKWOOD_BEACH": 592,
}

# code -> name (first wins)
AREA_NAMES: dict[int, str] = {}
for _name, _code in AREAS.items():
    AREA_NAMES.setdefault(_code, _name)


def neighborhoods_for_borough(borough_code: int) -> list[int]:
    """Leaf neighborhood codes within a borough (for adaptive sharding).

    Filters out the borough root and ``ALL_*`` rollups (which overlap leaves).
    Cross-listed oddities like MARBLE_HILL are harmless — enumeration de-dupes
    by listing id across shards.
    """
    lo = borough_code
    hi = borough_code + 99
    out = []
    for name, code in AREAS.items():
        if code == borough_code or name.startswith("ALL_") or code == ALL_NYC_AND_NJ:
            continue
        if lo <= code <= hi:
            out.append(code)
    return sorted(out)


# --- GraphQL API identity (verbatim from the reference clients) -------------
GRAPHQL_ENDPOINT = "https://api-v6.streeteasy.com/"

# NOTE: the Apollo client-version string contains a literal DOUBLE space after
# "version" — kept verbatim because that is what the real frontend sends.
GRAPHQL_HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://streeteasy.com",
    "Referer": "https://streeteasy.com/",
    "Apollographql-Client-Name": "srp-frontend-service",
    "Apollographql-Client-Version": "version  50bef71ef923e981bdcb7c781851c3bfdb12a0c1",
    "Os": "web",
    "App-Version": "1.0.0",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    ),
    "Sec-Ch-Ua": '"Chromium";v="133", "Not(A:Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Accept-Language": "en-US,en;q=0.9",
    "Dnt": "1",
}

# Strings that indicate a PerimeterX/HUMAN block. The first group is the
# "Press & Hold" HTML wall (web pages); the second is the PerimeterX JSON
# challenge body that api-v6 returns (e.g. {"appId":"PX...","jsClientSrc":...}).
BLOCK_MARKERS = (
    "Press & Hold",
    "Access to this page has been denied",
    "px-captcha",
    "_pxCaptcha",
    "jsClientSrc",
    "firstPartyEnabled",
)

# --- Image CDN --------------------------------------------------------------
# A media `key` (32-hex hash) renders as photos.zillowstatic.com/fp/{key}-{size}.{ext}.
# The same hash serves every size; only the tail changes. Verified live:
#   cc_ft_1536 (largest, ~hi-res) > p_h > p_e (medium) > p_d (small)
PHOTO_CDN_TEMPLATE = "https://photos.zillowstatic.com/fp/{key}-{size}.{ext}"
DEFAULT_IMAGE_SIZE = "cc_ft_1536"   # best resolution for a floor-plan dataset
DEFAULT_IMAGE_EXT = "webp"
