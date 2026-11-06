"""Pyramid AstroBuild API. No user information, files or credentials are persisted."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from .mission import MissionRequest, simulate_mission
from .nasa_data import NASADataClient
from .data_api import router as nasa_router
from .terrain import MAX_INPUT_BYTES, TerrainInputError, compare_profiles, profile_geotiff, synthetic_comparison

BASE = Path(__file__).resolve().parent
@asynccontextmanager
async def lifespan(instance: FastAPI):
    client = NASADataClient()
    instance.state.nasa = client
    try:
        yield
    finally:
        await client.close()


app = FastAPI(title="Pyramid AstroBuild", version="0.2.0", docs_url="/api/docs", redoc_url=None, lifespan=lifespan)
app.include_router(nasa_router)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
_ANALYSES = asyncio.Semaphore(2)

SITES = [
    {"id":"tenere","name":"Ténéré Desert","country":"Niger","region":"Sahara","lat":17.92,"lng":10.9,"category":"Arid terrain","status":"Research candidate","description":"Large arid plains and dunes; investigate substrate, climate and relief with DEM and satellite products.","research":"Study terrain stability, dune movement, and similarity to specific Mars surface classes.","tag":"Dune fields"},
    {"id":"danakil","name":"Danakil Depression","country":"Ethiopia","region":"Afar","lat":14.24,"lng":40.3,"category":"Volcanic","status":"Research candidate","description":"Arid, volcanically active depression with unusual mineral deposits and harsh conditions.","research":"Compare volcanic geomorphology and mineral signatures; field safety constraints are substantial.","tag":"Volcanic basin"},
    {"id":"namib","name":"Namib Desert","country":"Namibia","region":"Southern Africa","lat":-24.73,"lng":15.35,"category":"Arid terrain","status":"Research candidate","description":"Dry coastal desert containing large dune systems and exposed rocky surfaces.","research":"Separate dune and rocky candidate areas; assess dune mobility, slope and surface texture.","tag":"Hyper-arid"},
    {"id":"wadi-rum","name":"Wadi Rum","country":"Jordan","region":"Middle East","lat":29.58,"lng":35.42,"category":"Rocky desert","status":"Research candidate","description":"Sandstone valleys, ridges and desert plains with potential analog features.","research":"Study bedrock landforms and slopes for rover mobility training scenarios.","tag":"Rock formations"},
    {"id":"teide","name":"Teide Volcanic Landscape","country":"Spain","region":"Tenerife","lat":28.27,"lng":-16.64,"category":"Volcanic","status":"Research candidate","description":"High-elevation volcanic terrain and lava formations.","research":"Evaluate lava field roughness and geological comparability to selected planetary volcanic units.","tag":"Lava field"},
    {"id":"atacama","name":"Atacama Desert","country":"Chile","region":"South America","lat":-23.5,"lng":-68.3,"category":"Established analog","status":"Reference example","description":"An arid Earth analog frequently used in planetary research; included as a benchmark, not a newly discovered site.","research":"Use as a control against potential new candidates. Sites within this desert vary widely.","tag":"Reference"},
    {"id":"haughton","name":"Haughton Crater","country":"Canada","region":"Devon Island","lat":75.38,"lng":-89.67,"category":"Impact terrain","status":"Reference example","description":"Meteorite impact structure used for planetary analog field research.","research":"Use crater relief and geology as a comparison control, with polar data limitations noted.","tag":"Reference"},
    {"id":"death-valley","name":"Death Valley","country":"United States","region":"California","lat":36.44,"lng":-116.83,"category":"Arid terrain","status":"Reference example","description":"Arid basin and ranges historically discussed as terrestrial planetary analog environments.","research":"Benchmark arid surface conditions; avoid comparing environments without matching local scale.","tag":"Reference"},
]

DATASETS = [
    {"id":"srtm","name":"NASA SRTM Global 1 arc-second","body":"Earth","kind":"Elevation DEM","url":"https://www.earthdata.nasa.gov/data/catalog/lpcloud-srtmgl1-003","access":"Earthdata account may be required","detail":"~30 m elevation, 60°N to 56°S. Suitable for slope and local relief analysis."},
    {"id":"nasadem","name":"NASADEM Merged DEM","body":"Earth","kind":"Elevation DEM","url":"https://search.earthdata.nasa.gov/search?q=NASADEM_HGT","access":"Earthdata account may be required","detail":"SRTM-derived global DEM with additional processing and void filling."},
    {"id":"mola","name":"Mars Orbiter Laser Altimeter (MOLA)","body":"Mars","kind":"Elevation DEM","url":"https://pds-geosciences.wustl.edu/missions/mgs/megdr.html","access":"Public PDS DEM source","detail":"NASA Mars Global Surveyor topography. Download actual numeric DEM for comparison, not shaded-relief imagery."},
    {"id":"lola","name":"Lunar Orbiter Laser Altimeter (LOLA)","body":"Moon","kind":"Elevation DEM","url":"https://pds-geosciences.wustl.edu/missions/lro/lola.htm","access":"Public planetary archive","detail":"LRO laser altimetry for lunar elevation and terrain studies."},
    {"id":"earthdata","name":"NASA Earthdata GIS","body":"Earth","kind":"Discovery","url":"https://gis.earthdata.nasa.gov/portal/home/","access":"Public catalog","detail":"Find NASA GIS-ready datasets and map services."},
]


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": "0.2.0", "mode": "prototype"}


@app.get("/api/catalog")
def catalog() -> dict:
    return {"sites": SITES, "datasets": DATASETS, "verification": "Candidate regions are research leads, not measured or validated analog sites. No site ranking is implied."}


@app.post("/api/mission")
def mission(request: MissionRequest) -> dict:
    return simulate_mission(request)


@app.get("/api/demo-comparison")
def demo_comparison() -> dict:
    return synthetic_comparison()


async def _read_limit(upload: UploadFile) -> bytes:
    try:
        blob = await upload.read(MAX_INPUT_BYTES + 1)
        if len(blob) > MAX_INPUT_BYTES:
            raise HTTPException(413, "Each GeoTIFF must be at most 12 MB")
        return blob
    finally:
        await upload.close()


@app.post("/api/terrain/compare")
async def terrain_compare(
    earth_file: Annotated[UploadFile, File()],
    reference_file: Annotated[UploadFile, File()],
    reference_body: Annotated[str, Form()] = "mars",
    earth_pixel_spacing_m: Annotated[float | None, Form(ge=0.1, le=100000)] = None,
    reference_pixel_spacing_m: Annotated[float | None, Form(ge=0.1, le=100000)] = None,
) -> dict:
    if reference_body not in {"mars", "moon"}:
        raise HTTPException(422, "Reference body must be mars or moon")
    # A single request cannot monopolize the service with arbitrarily many large rasters.
    async with _ANALYSES:
        earth = await _read_limit(earth_file)
        reference = await _read_limit(reference_file)
        try:
            result = await run_in_threadpool(
                lambda: compare_profiles(
                    profile_geotiff(earth, "earth", earth_pixel_spacing_m),
                    profile_geotiff(reference, reference_body, reference_pixel_spacing_m),
                )
            )
        except TerrainInputError as exc:
            raise HTTPException(422, str(exc)) from exc
        is_synthetic_example = any(
            (name or "").upper().startswith("SYNTHETIC_")
            for name in (earth_file.filename, reference_file.filename)
        )
        result["provenance"] = "SYNTHETIC_SAMPLE_RASTERS" if is_synthetic_example else "USER_UPLOADED_RASTERS"
        if is_synthetic_example:
            result["warnings"].insert(0, "Sample filenames indicate synthetic rasters. These measurements are not NASA observations.")
        result["reference_body"] = reference_body
        return result


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(BASE / "static" / "index.html")
