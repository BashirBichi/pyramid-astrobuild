"""NASA PDS binary byte order, scaling, bounds, upstream isolation and CMR metadata."""
from __future__ import annotations

import asyncio
import json

import httpx
import numpy as np
import pytest

from app.nasa_data import NASADataClient, NASAUpstreamError, RASTER_BYTES, RASTER_HEIGHT, RASTER_WIDTH, profile_global_grid
from app.mission import MissionRequest, simulate_mission


def make_raster(body: str) -> bytes:
    yy, xx = np.mgrid[0:RASTER_HEIGHT, 0:RASTER_WIDTH]
    # Both bodies use correct native endianness; moon grid is scaled by 0.5.
    data = 100 + yy * 2 + xx // 4
    dtype = '>i2' if body == 'mars' else '<i2'
    return data.astype(dtype).tobytes()


def test_global_grid_endianness_and_lunar_scale() -> None:
    mars = profile_global_grid(make_raster('mars'), 'mars', 0, 0, 4)
    moon = profile_global_grid(make_raster('moon'), 'moon', 0, 0, 4)
    assert moon['profile']['relief_m'] == pytest.approx(mars['profile']['relief_m'] * 0.5, abs=0.6)
    assert mars['provenance'] == 'NASA_PDS_NUMERIC_GRID'
    assert mars['profile']['sampled_pixels'] == 256
    assert moon['profile']['pixel_spacing_m'] < mars['profile']['pixel_spacing_m']


def test_longitude_wrap_and_input_limits() -> None:
    blob = make_raster('mars')
    a = profile_global_grid(blob, 'mars', 10, 359, 4)
    b = profile_global_grid(blob, 'mars', 10, -1, 4)
    assert a['profile'] == b['profile']
    for lat, lon, span in [(81,10,4), (0, 10, 2), (0,361, 8), (0,float('nan'),8)]:
        with pytest.raises(ValueError):
            profile_global_grid(blob, 'mars', lat, lon, span)
    with pytest.raises(NASAUpstreamError):
        profile_global_grid(b'bad', 'mars', 0, 0)


def test_remote_pds_cache_is_singleflight() -> None:
    requests = []
    blob = make_raster('mars')

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, content=blob)

    async def run() -> None:
        client = NASADataClient(httpx.MockTransport(handler))
        try:
            first, second = await asyncio.gather(client.raster('mars'), client.raster('mars'))
            assert first == blob and second == blob
            assert len(requests) == 1
        finally:
            await client.close()

    asyncio.run(run())


def test_bad_remote_grid_rejected_not_cached() -> None:
    async def run() -> None:
        client = NASADataClient(httpx.MockTransport(lambda req: httpx.Response(200, content=b'BAD')))
        try:
            with pytest.raises(NASAUpstreamError):
                await client.raster('moon')
        finally:
            await client.close()
    asyncio.run(run())


def test_cmr_discovery_data_provenance() -> None:
    urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        payload = {'feed': {'entry': [{'id':'G123', 'title':'NASADEM_HGT tile', 'links':[{'href':'https://data.earthdata.nasa.gov/file.hgt'}]}]}}
        return httpx.Response(200, content=json.dumps(payload).encode())

    async def run() -> None:
        client = NASADataClient(httpx.MockTransport(handler))
        try:
            result = await client.granules(17.92, 10.9)
            assert result['collection'] == 'NASADEM_HGT.001'
            assert len(result['granules']) == 1
            assert 'NASADEM_HGT' in urls[0]
            assert (await client.granules(75.38,-89.67))['status'] == 'outside_coverage'
        finally:
            await client.close()
    asyncio.run(run())


def test_autonomy_reduces_hypothetical_approval_delay_only() -> None:
    autonomous = simulate_mission(MissionRequest(autonomous=True, communication_delay_min=24, review_events=3))
    supervised = simulate_mission(MissionRequest(autonomous=False, communication_delay_min=24, review_events=3))
    assert supervised['ready'] and autonomous['ready']
    assert supervised['duration_h'] > autonomous['duration_h']
    assert supervised['energy_kwh'] == autonomous['energy_kwh']
    assert autonomous['communications']['estimated_latency_avoided_h'] > 0
    assert simulate_mission(MissionRequest(autonomous=False, communication_delay_min=4)) == simulate_mission(MissionRequest(autonomous=False, communication_delay_min=4))
