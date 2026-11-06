# Pyramid AstroBuild

Planetary Construction Intelligence | NASA Space Apps Challenge 2026, Kano | Pyramid City Devs.

FastAPI proof of concept for Earth analog terrain research, geospatial elevation profile comparison, and constrained robotic mission planning.

## Research integrity

Candidate terrestrial regions are research leads, not verified Moon/Mars analog sites. Synthetic examples are clearly marked. Numeric comparisons require compatible elevation models and must not be presented as scientifically validated analog rankings.

## Deployment

A GitHub Actions workflow imports the prepared application source from a compressed bundle. Render builds the included Dockerfile and serves `GET /api/health` for readiness. The application is stateless and does not store uploaded rasters.
