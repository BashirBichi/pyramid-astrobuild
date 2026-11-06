## Phase 2: Official NASA catalog and PDS data (v0.2)

The application can retrieve **actual planetary numerical grids on demand** from NASA's Planetary Data System. No spacecraft data is bundled, and NASA endpoint failures are reported rather than silently substituting synthetic values.

- `GET /api/nasa/planetary-profile?body=mars&latitude=0&longitude=137&span_deg=8` uses the **MOLA MEGT90N000CB** 4 pixels/degree global topography file. Its PDS label documents 1440×720 samples, signed big-endian 16-bit meters.
- `GET /api/nasa/planetary-profile?body=moon&latitude=0&longitude=137&span_deg=8` uses the **LOLA LDEM_4** global gridded elevation file. Its PDS label documents 1440×720 little-endian 16-bit samples with 0.5-meter scaling to height relative to the lunar reference radius.
- `GET /api/nasa/earth-granules/tenere` queries NASA Earthdata's CMR for **NASADEM_HGT.001** tiles near a curated region. Downloads may require NASA Earthdata Login; this endpoint returns only metadata and links.
- `POST /api/nasa/compare-earth-with-pds` accepts a user-supplied Earth GeoTIFF and retrieves the official reference terrain grid; its output explicitly states the Earth upload is **not independently provenance-verified**.
- Mission simulation supports `communication_delay_min` (one-way minutes), `autonomous` mode, and illustrative `review_events` to demonstrate the impact of Earth supervision latency. This models neither real hardware behavior nor flight safety.

### Official science provenance

- [NASA PDS MOLA MEGDR catalog](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html)
- [MOLA MEGT90N000CB label](https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg004/megt90n000cb.lbl)
- [NASA PDS LOLA GDR catalog](https://pds-geosciences.wustl.edu/missions/lro/lola.htm)
- [LOLA LDEM_4 label](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/ldem_4.lbl)
- [NASA Earthdata CMR search API](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html)

**Resolution warning:** 4 pixels/degree corresponds to approximately 14.8 km at the Martian equator and 7.6 km at the lunar equator. Such data cannot resolve a building site. The app reports coarse grid ground sampling and warns when the Earth raster differs in scale. Do not treat the heuristic terrain index as a construction suitability assessment.

**Runtime constraints:** A pooled HTTP client retrieves only fixed allowlisted NASA PDS grid URLs, enforces their published lengths, and caches 2 MB per planetary body per process. A pooled CMR client performs metadata-only lookup for a fixed collection; the app does not accept arbitrary remote fetch URLs. Uploaded DEMs remain memory-only. NASA PDS/CMR Internet connectivity is required for new data loads, and service restarts clear the cache.
