"""Evidence-aware Earth analog screening for Mars and Moon research.

The ranking is a research-priority screen, not a construction-suitability score.
Terrain similarity remains measured only when a real Earth DEM is supplied.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .nasa_data import NASADataClient, NASAUpstreamError, profile_global_grid


@dataclass(frozen=True, slots=True)
class TargetProfile:
    body: str
    terrain: frozenset[str]
    climate: frozenset[str]
    geology: frozenset[str]
    operations: frozenset[str]
    environment_summary: str
    evidence: tuple[str, ...]


TARGET_PROFILES: dict[str, TargetProfile] = {
    "mars": TargetProfile(
        "mars",
        frozenset({"arid", "rocky", "volcanic", "dune", "basin", "crater"}),
        frozenset({"hyper_arid", "cold", "dust", "thin_atmosphere"}),
        frozenset({"basaltic", "volcanic", "sedimentary", "impact"}),
        frozenset({"rover", "dust", "remote", "extreme_environment"}),
        "Cold, dusty desert conditions with a very thin atmosphere and diverse rocky terrain.",
        (
            "NASA describes Mars as a cold, dusty desert world with a very thin atmosphere.",
            "Mars has volcanoes, canyons, craters and other diverse surface environments.",
            "Dust activity is an operational consideration for surface exploration.",
        ),
    ),
    "moon": TargetProfile(
        "moon",
        frozenset({"crater", "rocky", "basin", "volcanic", "regolith"}),
        frozenset({"airless", "extreme_heat", "radiation", "dust"}),
        frozenset({"basaltic", "volcanic", "impact"}),
        frozenset({"rover", "remote", "extreme_environment", "dust"}),
        "Airless, radiation-exposed terrain dominated by impact features, rocky material and regolith.",
        (
            "NASA describes the Moon as having a very thin exosphere and a heavily cratered rocky surface.",
            "Lunar regolith is fragmented rock and dust produced largely by impacts.",
            "Extreme temperature swings and rugged terrain matter for surface operations.",
        ),
    ),
}


def _overlap_score(values: Iterable[str], target: frozenset[str]) -> float:
    source = frozenset(values)
    if not source or not target:
        return 0.0
    return round(100.0 * len(source & target) / len(target), 1)


def _site_screening(site: Mapping[str, Any], target: TargetProfile) -> dict[str, float]:
    profile = site.get("analog_profile") or {}
    terrain = _overlap_score(profile.get("terrain", ()), target.terrain)
    climate = _overlap_score(profile.get("climate", ()), target.climate)
    geology = _overlap_score(profile.get("geology", ()), target.geology)
    operations = _overlap_score(profile.get("operations", ()), target.operations)
    screening = round(
        terrain * 0.35
        + climate * 0.30
        + geology * 0.20
        + operations * 0.15,
        1,
    )
    return {
        "terrain_context": terrain,
        "climate_context": climate,
        "geology_context": geology,
        "operations_context": operations,
        "analog_screening_score": screening,
    }


async def rank_sites(
    client: NASADataClient,
    sites: Sequence[Mapping[str, Any]],
    body: str,
    latitude: float,
    longitude: float,
    span_deg: float,
    candidate_ids: set[str] | None = None,
) -> dict[str, Any]:
    if body not in TARGET_PROFILES:
        raise ValueError("Target body must be mars or moon")
    target = TARGET_PROFILES[body]
    planet = await client.raster(body)
    target_profile = await asyncio.to_thread(
        profile_global_grid,
        planet,
        body,
        latitude,
        longitude,
        span_deg,
    )

    selected = [site for site in sites if candidate_ids is None or site["id"] in candidate_ids]
    semaphore = asyncio.Semaphore(4)

    async def discover(site: Mapping[str, Any]) -> dict[str, Any]:
        async with semaphore:
            try:
                metadata = await client.granules(float(site["lat"]), float(site["lng"]))
                status = metadata.get("status", "unknown")
                count = len(metadata.get("granules", []))
                readiness = 100.0 if status == "ok" and count > 0 else 0.0
                if status == "ok" and count == 0:
                    readiness = 25.0
                return {"status": status, "granules": count, "readiness": readiness, "bbox": metadata.get("bbox")}
            except NASAUpstreamError as exc:
                return {"status": "unavailable", "granules": 0, "readiness": 0.0, "error": str(exc)}

    discoveries = await asyncio.gather(*(discover(site) for site in selected))
    ranked: list[dict[str, Any]] = []
    for site, discovery in zip(selected, discoveries, strict=True):
        screening = _site_screening(site, target)
        priority = round(
            screening["analog_screening_score"] * 0.75
            + discovery["readiness"] * 0.25,
            1,
        )
        ranked.append({
            "rank": 0,
            "site_id": site["id"],
            "name": site["name"],
            "country": site["country"],
            "region": site["region"],
            "lat": site["lat"],
            "lng": site["lng"],
            "status": site["status"],
            "tag": site["tag"],
            **screening,
            "nasadem": discovery,
            "measured_terrain_match": {
                "status": "pending",
                "score": None,
                "message": "Upload or acquire a NASADEM Earth DEM for this site before assigning a measured terrain similarity score.",
            },
            "research_priority_score": priority,
            "interpretation": (
                "Higher score means stronger contextual analog evidence plus better NASADEM data discoverability. "
                "It does not mean safer, cheaper, more habitable, or construction-ready."
            ),
        })
    ranked.sort(key=lambda item: (-item["research_priority_score"], item["name"]))
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index

    return {
        "body": body,
        "target": {
            "environment_summary": target.environment_summary,
            "evidence": list(target.evidence),
            "profile": target_profile["profile"],
            "source": {
                "provenance": target_profile["provenance"],
                "product_id": target_profile["product_id"],
                "source_url": target_profile["source_url"],
                "center": target_profile["center"],
                "span_deg": target_profile["span_deg"],
            },
        },
        "ranking": ranked,
        "method": {
            "name": "AstroBuild Evidence-Aware Analog Screening v1",
            "weights": {
                "terrain_context": 0.35,
                "climate_context": 0.30,
                "geology_context": 0.20,
                "operations_context": 0.15,
                "nasadem_discoverability": 0.25,
            },
            "note": "The contextual score is a transparent screening heuristic. Measured terrain similarity requires comparable Earth and planetary DEM profiles.",
        },
        "limitations": [
            "NASADEM CMR results prove catalog discoverability, not that the DEM tile has been downloaded or processed.",
            "Context classes are research descriptors, not quantitative environmental measurements.",
            "The planetary topography profile is real NASA PDS data, but its coarse resolution is not a construction-footprint assessment.",
            "No ranking output should be interpreted as a site-selection, habitability, safety, or engineering decision.",
        ],
    }
