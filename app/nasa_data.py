"""Official NASA metadata discovery and bounded PDS global DEM readers.

No API credentials are required for the chosen public PDS raster files or CMR
metadata requests. All remote addresses are constants to prevent URL injection.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import math
from typing import Any

import httpx
import numpy as np

from .terrain import PLANET_RADII_M, TerrainProfile, profile_from_array

PIXELS_PER_DEGREE = 4
RASTER_WIDTH = 360 * PIXELS_PER_DEGREE
RASTER_HEIGHT = 180 * PIXELS_PER_DEGREE
RASTER_BYTES = RASTER_WIDTH * RASTER_HEIGHT * 2
CMR_ENDPOINT = "https://cmr.earthdata.nasa.gov/search/granules.json"


@dataclass(frozen=True, slots=True)
class Grid:
    name: str
    url: str
    dtype: str
    scale: float
    product_id: str


GRIDS: dict[str, Grid] = {
    "mars": Grid(
        "NASA MGS / MOLA MEGDR, global topography 4 pixels/degree",
        "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg004/megt90n000cb.img",
        ">i2", 1.0, "MEGT90N000CB / v2.0",
    ),
    "moon": Grid(
        "NASA LRO / LOLA LDEM, global elevation 4 pixels/degree",
        "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/ldem_4.img",
        "<i2", 0.5, "LDEM_4 / v3.0",
    ),
}


class NASAUpstreamError(RuntimeError):
    """Official NASA dataset endpoint could not be read or validated."""


class NASADataClient:
    """Pooled HTTP client with per-process bounded immutable raster cache."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.http = httpx.AsyncClient(
            timeout=httpx.Timeout(24.0, connect=7.0),
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
            follow_redirects=False,
            transport=transport,
            headers={"User-Agent": "PyramidAstroBuild/0.2 (+NASA Space Apps research)"},
        )
        self._cached: dict[str, bytes] = {}
        self._locks = {body: asyncio.Lock() for body in GRIDS}

    async def close(self) -> None:
        await self.http.aclose()

    async def raster(self, body: str) -> bytes:
        if body not in GRIDS:
            raise ValueError("Planet must be mars or moon")
        if body in self._cached:
            return self._cached[body]
        async with self._locks[body]:
            if body in self._cached:
                return self._cached[body]
            try:
                async with self.http.stream("GET", GRIDS[body].url) as response:
                    response.raise_for_status()
                    if response.headers.get("content-length") and int(response.headers["content-length"]) != RASTER_BYTES:
                        raise NASAUpstreamError("PDS grid file size does not match its published label")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        size += len(chunk)
                        if size > RASTER_BYTES:
                            raise NASAUpstreamError("PDS response exceeds documented raster size")
                        chunks.append(chunk)
            except (httpx.HTTPError, ValueError) as exc:
                raise NASAUpstreamError("NASA PDS data service is currently unavailable") from exc
            data = b"".join(chunks)
            if len(data) != RASTER_BYTES:
                raise NASAUpstreamError("NASA PDS returned an incomplete elevation grid")
            self._cached[body] = data
            return data

    async def granules(self, latitude: float, longitude: float) -> dict[str, Any]:
        """Discover NASADEM_HGT granules for a given Earth location, without downloading them."""
        if not (-56 <= latitude <= 60 and -180 <= longitude <= 180):
            return {"granules": [], "status": "outside_coverage", "message": "NASADEM SRTM coverage is approximately 56°S to 60°N."}
        # Clamped box avoids crossing dateline and keeps CMR search selective.
        west, east = max(-180, longitude - 0.4), min(180, longitude + 0.4)
        south, north = max(-56, latitude - 0.4), min(60, latitude + 0.4)
        bbox = f"{west:.4f},{south:.4f},{east:.4f},{north:.4f}"
        params = {"short_name": "NASADEM_HGT", "version": "001", "bounding_box": bbox, "page_size": "6"}
        try:
            response = await self.http.get(CMR_ENDPOINT, params=params)
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise NASAUpstreamError("NASA CMR metadata response was too large")
            entries = response.json().get("feed", {}).get("entry", [])
        except (httpx.HTTPError, ValueError, AttributeError, TypeError) as exc:
            raise NASAUpstreamError("NASA Earthdata CMR catalog is temporarily unavailable") from exc
        if not isinstance(entries, list):
            raise NASAUpstreamError("NASA CMR returned an invalid granule list")
        found = []
        for item in entries[:6]:
            if not isinstance(item, dict):
                continue
            links = []
            for link in item.get("links", []):
                url = link.get("href", "") if isinstance(link, dict) else ""
                if isinstance(url, str) and url.startswith("https://") and not link.get("inherited", False):
                    links.append(url)
            found.append({
                "id": str(item.get("id", ""))[:100],
                "title": str(item.get("title", "NASADEM granule"))[:180],
                "updated": str(item.get("updated", ""))[:40],
                "links": links[:3],
            })
        return {"status": "ok", "granules": found, "bbox": bbox, "collection": "NASADEM_HGT.001", "provider": "NASA Earthdata CMR", "download_note": "Granule download generally requires a free NASA Earthdata Login. Results are discovery metadata, not processed elevations."}


def profile_global_grid(payload: bytes, body: str, latitude: float, longitude: float, span_deg: float = 8) -> dict[str, Any]:
    """Extract a local patch from a published NASA 4 px/degree raster grid.

    PDS MOLA is big-endian signed int16 meters. LOLA LDEM_4 is little-endian
    signed int16 digital numbers with 0.5-meter elevation scale.
    """
    if body not in GRIDS:
        raise ValueError("Planet must be mars or moon")
    if not all(math.isfinite(v) for v in (latitude, longitude, span_deg)):
        raise ValueError("Coordinates and span must be finite")
    if not (-80 <= latitude <= 80 and -180 <= longitude <= 360 and 4 <= span_deg <= 20):
        raise ValueError("Supported latitude: -80 to 80°, longitude: -180 to 360°, span: 4 to 20°")
    if len(payload) != RASTER_BYTES:
        raise NASAUpstreamError("Unexpected length for published NASA PDS grid")
    grid = GRIDS[body]
    raw = np.frombuffer(payload, dtype=grid.dtype).reshape(RASTER_HEIGHT, RASTER_WIDTH)
    n = int(round(span_deg * PIXELS_PER_DEGREE))
    row = int(math.floor((90 - latitude) * PIXELS_PER_DEGREE))
    col = int(math.floor((longitude % 360) * PIXELS_PER_DEGREE))
    rows = np.arange(row - n // 2, row - n // 2 + n, dtype=np.intp)
    cols = np.arange(col - n // 2, col - n // 2 + n, dtype=np.intp) % RASTER_WIDTH
    if rows.min() < 0 or rows.max() >= RASTER_HEIGHT:
        raise ValueError("Selected region extends beyond the planetary grid")
    selected = raw[np.ix_(rows, cols)]
    good = selected != -32768
    elevations = selected.astype(np.float64) * grid.scale
    unit_m = math.pi / 180.0 * PLANET_RADII_M[body] / PIXELS_PER_DEGREE
    profile: TerrainProfile = profile_from_array(elevations, unit_m * math.cos(math.radians(latitude)), unit_m, good)
    return {
        "body": body,
        "provenance": "NASA_PDS_NUMERIC_GRID",
        "name": grid.name,
        "product_id": grid.product_id,
        "source_url": grid.url,
        "center": {"latitude": latitude, "longitude_east": longitude % 360},
        "span_deg": span_deg,
        "grid_resolution_deg": 1 / PIXELS_PER_DEGREE,
        "profile": asdict(profile),
        "limitations": [
            "Coarse 4 pixel/degree planetary grid. Cannot assess individual construction footprints.",
            "Published gridded values may be interpolated; not every cell is a direct altimeter measurement.",
            "Terrain relief alone cannot validate surface material, radiation, environmental or construction suitability.",
        ],
    }
