"""Deterministic DEM feature extraction for comparing terrain, not habitability.

Never use these values as evidence of planetary environmental equivalence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
import math

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.io import MemoryFile

MAX_DIMENSION = 512
MAX_INPUT_BYTES = 12 * 1024 * 1024
PLANET_RADII_M = {"earth": 6_371_000.0, "mars": 3_389_500.0, "moon": 1_737_400.0}


class TerrainInputError(ValueError):
    """Invalid, unsupported, or insufficient DEM data."""


@dataclass(frozen=True, slots=True)
class TerrainProfile:
    elevation_p05_m: float
    elevation_p95_m: float
    relief_m: float
    elevation_std_m: float
    slope_median_deg: float
    slope_p90_deg: float
    gentle_slope_pct: float
    pixel_spacing_m: float
    valid_pixel_pct: float
    sampled_pixels: int


def _finite_float(value: float) -> float:
    if not math.isfinite(value):
        raise TerrainInputError("DEM statistics produced a non-finite value")
    return round(float(value), 3)


def profile_from_array(elevation: np.ndarray, pixel_x_m: float, pixel_y_m: float, mask: np.ndarray | None = None) -> TerrainProfile:
    if elevation.ndim != 2 or min(elevation.shape) < 16:
        raise TerrainInputError("DEM must contain at least a 16x16 pixel area")
    if not all(math.isfinite(v) and v > 0 for v in (pixel_x_m, pixel_y_m)):
        raise TerrainInputError("Pixel spacing must be positive finite meters")
    matrix = np.asarray(elevation, dtype=np.float64)
    good = np.isfinite(matrix)
    if mask is not None:
        good &= np.asarray(mask, dtype=np.bool_)
    valid_pct = 100.0 * good.mean()
    if valid_pct < 70 or good.sum() < 256:
        raise TerrainInputError("DEM has too few valid elevation pixels (minimum 70%)")
    samples = matrix[good]
    # Bad pixels are not scored. Filling only permits finite numerical differentiation.
    filled = np.where(good, matrix, np.median(samples))
    gy, gx = np.gradient(filled, pixel_y_m, pixel_x_m)
    adjacent_good = good.copy()
    adjacent_good[1:, :] &= good[:-1, :]
    adjacent_good[:-1, :] &= good[1:, :]
    adjacent_good[:, 1:] &= good[:, :-1]
    adjacent_good[:, :-1] &= good[:, 1:]
    slopes = np.degrees(np.arctan(np.hypot(gx, gy)))[adjacent_good]
    if slopes.size < 128:
        raise TerrainInputError("DEM has insufficient neighboring valid pixels to measure slope")
    p05, p95 = np.percentile(samples, [5, 95])
    return TerrainProfile(
        elevation_p05_m=_finite_float(p05),
        elevation_p95_m=_finite_float(p95),
        relief_m=_finite_float(p95 - p05),
        elevation_std_m=_finite_float(np.std(samples)),
        slope_median_deg=_finite_float(np.median(slopes)),
        slope_p90_deg=_finite_float(np.percentile(slopes, 90)),
        gentle_slope_pct=_finite_float(np.mean(slopes <= 5.0) * 100),
        pixel_spacing_m=_finite_float(math.sqrt(pixel_x_m * pixel_y_m)),
        valid_pixel_pct=_finite_float(valid_pct),
        sampled_pixels=int(samples.size),
    )


def profile_geotiff(blob: bytes, body: str, spacing_override_m: float | None = None) -> TerrainProfile:
    if not blob or len(blob) > MAX_INPUT_BYTES:
        raise TerrainInputError("GeoTIFF must be non-empty and no larger than 12 MB")
    if body not in PLANET_RADII_M:
        raise TerrainInputError("Planet must be earth, moon, or mars")
    if spacing_override_m is not None and (not math.isfinite(spacing_override_m) or not (0.1 <= spacing_override_m <= 100_000)):
        raise TerrainInputError("Manual pixel spacing must be 0.1 to 100,000 meters")
    try:
        with MemoryFile(blob) as mem, mem.open() as ds:
            if ds.count != 1 or ds.width < 16 or ds.height < 16:
                raise TerrainInputError("Upload one-band elevation GeoTIFF with at least 16x16 pixels")
            if ds.width > 60_000 or ds.height > 60_000:
                raise TerrainInputError("DEM dimensions exceed processing limit")
            if abs(ds.transform.b) > 1e-10 or abs(ds.transform.d) > 1e-10:
                raise TerrainInputError("Rotated raster transforms are unsupported; reproject before uploading")
            sample_w = min(MAX_DIMENSION, ds.width)
            sample_h = min(MAX_DIMENSION, ds.height)
            data = ds.read(1, masked=True, out_shape=(sample_h, sample_w), resampling=Resampling.average)
            if spacing_override_m is not None:
                x_m = y_m = spacing_override_m * math.sqrt((ds.width / sample_w) * (ds.height / sample_h))
            elif ds.crs and ds.crs.is_geographic:
                latitude = ds.transform.f + ds.transform.e * ds.height * .5
                if abs(latitude) > 88:
                    raise TerrainInputError("Geographic DEM too close to a pole; project to meters or supply spacing")
                radius = PLANET_RADII_M[body]
                x_m = abs(ds.transform.a) * (ds.width / sample_w) * math.pi / 180 * radius * math.cos(math.radians(latitude))
                y_m = abs(ds.transform.e) * (ds.height / sample_h) * math.pi / 180 * radius
            elif ds.crs and ds.crs.is_projected:
                # Rasterio returns (unit name, meters per unit) for linear units.
                factor = ds.crs.linear_units_factor[1]
                x_m = abs(ds.transform.a) * (ds.width / sample_w) * factor
                y_m = abs(ds.transform.e) * (ds.height / sample_h) * factor
            else:
                raise TerrainInputError("DEM CRS is unknown; specify pixel spacing in meters")
            valid = ~np.ma.getmaskarray(data)
            return profile_from_array(np.asarray(data.filled(np.nan), dtype=np.float64), x_m, y_m, valid)
    except TerrainInputError:
        raise
    except (rasterio.errors.RasterioError, ValueError, OSError, TypeError) as exc:
        raise TerrainInputError("Could not read elevation raster as a valid GeoTIFF") from exc


def compare_profiles(earth: TerrainProfile, reference: TerrainProfile) -> dict:
    """Heuristic topography-only comparison, without absolute elevation comparison.

    Absolute height uses different geodetic datums across celestial bodies, so
    elevation above a reference datum must never be directly compared.
    """
    features = (
        ("relief_m", 0.25, 0.9),
        ("elevation_std_m", 0.20, 0.9),
        ("slope_median_deg", 0.20, 12.0),
        ("slope_p90_deg", 0.25, 18.0),
        ("gentle_slope_pct", 0.10, 40.0),
    )
    differences: dict[str, float] = {}
    distance = 0.0
    for name, weight, scale in features:
        a, b = getattr(earth, name), getattr(reference, name)
        error = abs(math.log1p(a) - math.log1p(b)) / scale if name in {"relief_m", "elevation_std_m"} else abs(a-b) / scale
        differences[name] = round(error, 3)
        distance += weight * min(error, 5.0)
    ratio = max(earth.pixel_spacing_m, reference.pixel_spacing_m) / max(0.1, min(earth.pixel_spacing_m, reference.pixel_spacing_m))
    warnings = ["This index compares topography only, not geology, atmosphere, temperature, radiation, resources, or construction safety."]
    if ratio > 3:
        warnings.append("Resolution differs by more than 3x. Reproject/resample both DEMs to comparable ground resolution before interpreting results.")
    if earth.valid_pixel_pct < 95 or reference.valid_pixel_pct < 95:
        warnings.append("Some elevation cells were missing; check nodata coverage and raster quality.")
    return {
        "similarity_index": round(100 * math.exp(-distance), 1),
        "measure": "Experimental terrain-pattern similarity index (0–100; not scientifically calibrated)",
        "earth": asdict(earth),
        "reference": asdict(reference),
        "feature_differences": differences,
        "warnings": warnings,
    }


def synthetic_comparison() -> dict:
    """Explicitly synthetic demo, NOT sourced from Earth/Moon/Mars observations."""
    yy, xx = np.mgrid[0:256, 0:256]
    earth = 910 + 34 * np.sin(xx / 34) + 17 * np.cos(yy / 41) + 0.14 * xx
    mars = 300 + 37 * np.sin(xx / 36) + 21 * np.cos(yy / 37) + 0.17 * xx
    result = compare_profiles(profile_from_array(earth, 30, 30), profile_from_array(mars, 30, 30))
    result["provenance"] = "SYNTHETIC_DEMO_ONLY"
    result["warnings"].insert(0, "Both surfaces are mathematically generated examples. This is not NASA observational data.")
    return result
