# Pyramid AstroBuild

Planetary Construction Intelligence | NASA Space Apps Challenge 2026, Kano | Pyramid City Devs.

FastAPI proof of concept for Earth analog research, NASA planetary elevation profiling, evidence-aware analog screening, geospatial terrain comparison, and constrained robotic mission planning.

## Research integrity

Candidate terrestrial regions are research leads, not verified Moon/Mars analog sites. The analog ranking is a transparent research-priority heuristic, not a construction, habitability, safety, or site-selection score. Synthetic examples are clearly marked. Numeric terrain comparisons require compatible elevation models and provenance.

## Phase 3 intelligence core

Analog Explorer can:

- Anchor a Mars or Moon comparison to a NASA PDS planetary terrain profile.
- Score transparent terrain, climate, geology and robotic-operations context.
- Check NASA Earthdata CMR for nearby NASADEM catalog coverage.
- Keep measured Earth-to-planet terrain matching in a pending state until comparable DEMs are actually processed.

## Deployment

GitHub Actions validates Python compilation, backend tests, and frontend JavaScript syntax. Render builds the included Dockerfile and serves the FastAPI application. The application is stateless and does not store uploaded rasters.
