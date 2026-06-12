"""GraphQL query building + response parsing (no network)."""

from streeteasy_floorplans import graphql


def test_search_query_inlines_enums_no_variables() -> None:
    q = graphql.build_search_query(
        area_codes=[100, 300], bucket="studio", page=1, per_page=50, user_search_token="tok123"
    )
    assert "areas: [100, 300]" in q
    assert "rentalStatus: ACTIVE" in q
    assert "attribute: RECOMMENDED" in q
    assert "adStrategy: NONE" in q
    # studio = exact 0 bedrooms
    assert "bedrooms: { lowerBound: 0, upperBound: 0 }" in q
    # enums must be bare tokens, token is a quoted string
    assert 'userSearchToken: "tok123"' in q
    # input is inlined: query must not declare GraphQL variables
    assert "query SearchRentalsFederated {" in q
    assert "$input" not in q


def test_search_query_open_ended_4plus_and_price() -> None:
    q = graphql.build_search_query(
        area_codes=[400], bucket="4plus", page=2, per_page=30, user_search_token="t",
        price_min=2000, price_max=4000,
    )
    assert "bedrooms: { lowerBound: 4 }" in q          # no upperBound
    assert "price: { lowerBound: 2000, upperBound: 4000 }" in q
    assert "page: 2" in q and "perPage: 30" in q


def test_detail_request_uses_variable() -> None:
    query, variables = graphql.build_detail_request(5037855)
    assert "$listingID: ID!" in query
    assert "media.floorPlans" not in query  # it's a selection, not a literal path
    assert "floorPlans { __typename key }" in query
    assert variables == {"listingID": "5037855"}


def _search_payload() -> dict:
    return {
        "searchRentals": {
            "totalCount": 3,
            "edges": [
                {
                    "__typename": "OrganicRentalEdge",
                    "node": {
                        "id": "111", "areaName": "Chelsea", "bedroomCount": 0,
                        "buildingType": "RENTAL", "livingAreaSize": 525, "price": 4908,
                        "street": "777 6th Avenue", "unit": "20B", "urlPath": "/building/x/20b",
                        "isNewDevelopment": False,
                        "leadMedia": {"photo": {"key": "pkey1"}, "floorPlan": {"key": "fpkey1"}},
                        "photos": [{"key": "pkey1"}, {"key": "pkey2"}],
                    },
                },
                {
                    "__typename": "OrganicRentalEdge",
                    "node": {
                        "id": "222", "areaName": "LES", "bedroomCount": 2, "price": 6350,
                        "urlPath": "/building/y/1413",
                        "leadMedia": {"photo": {"key": "pk"}, "floorPlan": None},
                        "photos": [{"key": "pk"}],
                    },
                },
                {  # sponsored -> excluded
                    "__typename": "SponsoredRentalEdge",
                    "node": {"id": "999", "bedroomCount": 1, "leadMedia": {"floorPlan": {"key": "x"}}},
                },
            ],
        }
    }


def test_parse_search_detects_floorplan_and_skips_sponsored() -> None:
    records, total = graphql.parse_search_response(_search_payload(), "studio")
    assert total == 3
    ids = [r.id for r in records]
    assert ids == ["111", "222"]            # 999 sponsored dropped

    r1 = records[0]
    assert r1.has_floor_plan is True
    assert r1.floor_plan_keys == ["fpkey1"]
    assert r1.photo_keys == ["pkey1", "pkey2"]
    assert r1.url == "https://streeteasy.com/building/x/20b"

    r2 = records[1]
    assert r2.has_floor_plan is False
    assert r2.floor_plan_keys == []


def test_parse_detail_response() -> None:
    data = {
        "rentalByListingId": {
            "id": "5037855", "status": "ACTIVE",
            "media": {
                "photos": [{"key": "p1"}, {"key": "p2"}],
                "floorPlans": [{"key": "fp1"}, {"key": "fp2"}],
                "assetCount": 14,
            },
            "propertyDetails": {"bedroomCount": 2, "livingAreaSize": 900},
        }
    }
    info = graphql.parse_detail_response(data)
    assert info["has_floor_plan"] is True
    assert info["floor_plan_keys"] == ["fp1", "fp2"]
    assert info["photo_keys"] == ["p1", "p2"]
    assert info["bedroom_count"] == 2
