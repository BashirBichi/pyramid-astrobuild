from __future__ import annotations

import asyncio

from app.analog import TARGET_PROFILES, _site_screening, rank_sites


def site(**overrides):
    base = {
        "id": "x", "name": "Test", "country": "Earth", "region": "Test",
        "lat": 10.0, "lng": 10.0, "status": "Research candidate", "tag": "test",
        "analog_profile": {
            "terrain": ["arid", "rocky", "volcanic"],
            "climate": ["hyper_arid", "dust"],
            "geology": ["basaltic", "volcanic"],
            "operations": ["rover", "remote"],
        },
    }
    base.update(overrides)
    return base


def test_target_profiles_are_bounded_and_distinct() -> None:
    assert set(TARGET_PROFILES) == {"mars", "moon"}
    assert TARGET_PROFILES["mars"].terrain != TARGET_PROFILES["moon"].terrain


def test_screening_score_is_deterministic_and_bounded() -> None:
    result = _site_screening(site(), TARGET_PROFILES["mars"])
    assert 0 <= result["analog_screening_score"] <= 100
    assert result == _site_screening(site(), TARGET_PROFILES["mars"])


def test_empty_profile_gets_zero_context() -> None:
    result = _site_screening(site(analog_profile={}), TARGET_PROFILES["moon"])
    assert result["analog_screening_score"] == 0


class FakeNASA:
    async def raster(self, body: str) -> bytes:
        return b"raster"

    async def granules(self, latitude: float, longitude: float) -> dict:
        if latitude > 60:
            return {"status": "outside_coverage", "granules": []}
        return {"status": "ok", "granules": [{"id": "demo"}], "bbox": "x"}


def fake_profile(*args, **kwargs):
    return {
        "body": args[1],
        "profile": {
            "relief_m": 10, "elevation_p05_m": 0, "elevation_p95_m": 10,
            "elevation_std_m": 2, "slope_median_deg": 2, "slope_p90_deg": 5,
            "gentle_slope_pct": 90, "pixel_spacing_m": 1000,
            "valid_pixel_pct": 100, "sampled_pixels": 256,
        },
        "provenance": "NASA_PDS_NUMERIC_GRID", "product_id": "TEST",
        "source_url": "https://example.test",
        "center": {"latitude": 0, "longitude_east": 0}, "span_deg": 8,
    }


def test_rank_sites_combines_context_and_nasadem_discoverability(monkeypatch) -> None:
    monkeypatch.setattr("app.analog.profile_global_grid", fake_profile)
    result = asyncio.run(rank_sites(
        FakeNASA(),
        [site(name="A", id="a"), site(name="B", id="b", lat=75.0)],
        "mars", 0, 0, 8,
    ))
    assert result["ranking"][0]["rank"] == 1
    assert result["ranking"][0]["nasadem"]["readiness"] == 100
    assert result["ranking"][1]["nasadem"]["status"] == "outside_coverage"
    assert all(item["measured_terrain_match"]["status"] == "pending" for item in result["ranking"])
