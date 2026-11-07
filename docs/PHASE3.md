# AstroBuild Phase 3: Analog Intelligence

## Purpose

Analog Explorer now provides an evidence-aware research-priority screen for Earth regions that may be useful as terrestrial analog environments for Mars or Moon surface robotics research.

The system deliberately separates three evidence layers:

1. **NASA planetary anchor** - a local topographic profile extracted from the public NASA PDS MOLA or LOLA global elevation grid.
2. **Earth analog context** - transparent categorical descriptors covering terrain, climate, geology and robotic field operations.
3. **Earth data readiness** - NASA Earthdata CMR discovery of NASADEM granules near each candidate location.

## Ranking model

The contextual analog screen uses:

- Terrain context: 35%
- Climate context: 30%
- Geology context: 20%
- Operations context: 15%

The final research-priority score combines that contextual screen at 75% with NASADEM catalog discoverability at 25%.

This is **not** a suitability score. It does not estimate habitability, construction cost, safety, geological equivalence, resource availability or engineering feasibility.

## Measured terrain matching

AstroBuild does not invent a measured terrain score for a candidate whose Earth DEM has not been processed.

A future measured-match pipeline can use:

- NASADEM or another documented Earth DEM
- MOLA for Mars
- LOLA for the Moon
- compatible spatial resolution and coordinate reference
- the existing deterministic terrain feature engine

The measured comparison already supports relief, elevation spread, median slope, high-percentile slope and gentle-surface fraction.

## NASA data boundaries

NASADEM is distributed as 1° x 1° tiles and covers land between approximately 60°N and 56°S. NASA Earthdata CMR discovery therefore cannot establish DEM availability for every candidate region. A catalog result also does not mean the file has been downloaded or processed.

The planetary profile uses a coarse global PDS grid and is intended as a regional research anchor, not a construction-footprint model.

## Safety and scientific integrity

AstroBuild is a research prototype. Its output must not be interpreted as:

- a real construction site recommendation
- a habitability assessment
- a robotic safety authorization
- an autonomous construction command
- a validated planetary engineering model

Every future scoring layer should preserve provenance, resolution, uncertainty and limitations.
