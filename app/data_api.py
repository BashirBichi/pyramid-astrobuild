"""NASA-derived research endpoints with explicit provenance and safe upstream errors."""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from .nasa_data import NASADataClient, NASAUpstreamError, profile_global_grid
from .terrain import MAX_INPUT_BYTES, TerrainInputError, compare_profiles, profile_geotiff

router = APIRouter(prefix="/api", tags=["NASA datasets"])


def nasa_client(request: Request) -> NASADataClient:
    return request.app.state.nasa


@router.get("/nasa/planetary-profile")
async def planetary_profile(
    client: Annotated[NASADataClient, Depends(nasa_client)],
    body: Annotated[str, Query(pattern=r"^(mars|moon)$")] = "mars",
    latitude: Annotated[float, Query(ge=-80, le=80)] = 0.0,
    longitude: Annotated[float, Query(ge=-180, le=360)] = 0.0,
    span_deg: Annotated[float, Query(ge=4, le=20)] = 8.0,
) -> dict:
    try:
        raster = await client.raster(body)
        return await run_in_threadpool(profile_global_grid, raster, body, latitude, longitude, span_deg)
    except NASAUpstreamError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (TerrainInputError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/nasa/earth-granules/{site_id}")
async def earth_granules(site_id: str, client: Annotated[NASADataClient, Depends(nasa_client)]) -> dict:
    from .main import SITES

    site = next((site for site in SITES if site["id"] == site_id), None)
    if site is None:
        raise HTTPException(404, "Unknown Earth analog candidate")
    try:
        result = await client.granules(site["lat"], site["lng"])
        return {"site_id": site_id, "site_name": site["name"], **result}
    except NASAUpstreamError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/nasa/compare-earth-with-pds")
async def compare_earth_with_pds(
    client: Annotated[NASADataClient, Depends(nasa_client)],
    earth_file: Annotated[UploadFile, File()],
    body: Annotated[str, Form(pattern=r"^(mars|moon)$")] = "mars",
    latitude: Annotated[float, Form(ge=-80, le=80)] = 0.0,
    longitude: Annotated[float, Form(ge=-180, le=360)] = 0.0,
    span_deg: Annotated[float, Form(ge=4, le=20)] = 8.0,
    earth_pixel_spacing_m: Annotated[float | None, Form(ge=0.1, le=100000)] = None,
) -> dict:
    try:
        blob = await earth_file.read(MAX_INPUT_BYTES + 1)
    finally:
        await earth_file.close()
    if len(blob) > MAX_INPUT_BYTES:
        raise HTTPException(413, "Earth GeoTIFF must be at most 12 MB")
    try:
        raster = await client.raster(body)
        planet = await run_in_threadpool(profile_global_grid, raster, body, latitude, longitude, span_deg)
        earth = await run_in_threadpool(profile_geotiff, blob, "earth", earth_pixel_spacing_m)
        from .terrain import TerrainProfile
        comparison = compare_profiles(earth, TerrainProfile(**planet["profile"]))
    except NASAUpstreamError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (TerrainInputError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    comparison["provenance"] = "NASA_PDS_PLANETARY_PLUS_USER_EARTH_RASTER"
    comparison["source"] = {"planetary": planet, "earth_file_name": (earth_file.filename or "")[:160], "earth_verified_nasa": False}
    comparison["warnings"].insert(0, "Planetary topography comes from NASA PDS. Earth raster is user-supplied and has not been independently verified as NASA data.")
    return comparison
