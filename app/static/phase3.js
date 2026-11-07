/* AstroBuild Phase 3: evidence-aware analog intelligence. */
(() => {
  'use strict';
  const one = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const button = one('#analog-rank');
  const output = one('#analog-ranking');
  const status = one('#analog-status');
  if (!button || !output) return;
  const setStatus = (message, error = false) => { status.textContent = message; status.style.color = error ? '#9a5d12' : ''; };
  const render = (data) => {
    const target = data.target;
    const p = target.profile;
    one('#analog-target-summary').textContent = target.environment_summary;
    one('#analog-target-relief').textContent = `${Number(p.relief_m).toFixed(1)} m`;
    one('#analog-target-slope').textContent = `${Number(p.slope_median_deg).toFixed(2)}°`;
    one('#analog-target-resolution').textContent = `${(Number(p.pixel_spacing_m) / 1000).toFixed(2)} km`;
    one('#analog-target-provenance').textContent = `${data.body.toUpperCase()} · ${target.source.product_id}`;
    output.innerHTML = data.ranking.map(item => {
      const score = Number(item.research_priority_score);
      const dataReady = item.nasadem?.readiness >= 100;
      return `<article class="analog-result">
        <span class="analog-rank">${item.rank}</span>
        <div class="analog-name"><strong>${esc(item.name)}</strong><span>${esc(item.country)} · ${esc(item.tag)}</span></div>
        <div class="analog-score"><strong>${score.toFixed(1)}</strong><small>priority</small><div class="analog-bar"><i style="width:${Math.max(0,Math.min(100,score))}%"></i></div></div>
        <div class="analog-metric"><small>Terrain</small><strong>${Number(item.terrain_context).toFixed(0)}%</strong></div>
        <div class="analog-metric"><small>Climate</small><strong>${Number(item.climate_context).toFixed(0)}%</strong></div>
        <div class="analog-metric"><small>Geology</small><strong>${Number(item.geology_context).toFixed(0)}%</strong></div>
        <div class="analog-metric"><small>NASA DEM</small><strong>${Number(item.nasadem?.granules ?? 0)}</strong></div>
        <span class="analog-data ${dataReady ? '' : 'pending'}">${dataReady ? 'CATALOG READY' : 'MEASURE PENDING'}</span>
      </article>`;
    }).join('') || '<div class="analog-empty">No candidates matched the selected filters.</div>';
    one('#analog-limitations').innerHTML = `<strong>How to interpret this ranking</strong>${data.limitations.map(esc).join(' ')}`;
  };
  button.addEventListener('click', async () => {
    const body = one('#analog-body').value;
    const latitude = Number(one('#analog-lat').value);
    const longitude = Number(one('#analog-lon').value);
    const span = Number(one('#analog-span').value);
    if (![latitude, longitude, span].every(Number.isFinite)) { setStatus('Enter valid target coordinates and window size.', true); return; }
    button.disabled = true;
    button.textContent = 'Building evidence ranking...';
    output.innerHTML = '<div class="analog-empty">Retrieving NASA planetary terrain and checking Earthdata coverage...</div>';
    setStatus('NASA PDS terrain anchor + NASADEM catalog discovery in progress.');
    try {
      const query = new URLSearchParams({body, latitude, longitude, span_deg: span});
      const response = await fetch(`/api/analog/rank?${query}`, {headers:{Accept:'application/json'}});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${response.status}`);
      render(data);
      setStatus(`Ranked ${data.ranking.length} Earth research regions against the ${body === 'mars' ? 'Mars' : 'Moon'} context. Measured terrain matching remains pending until comparable Earth DEMs are processed.`);
    } catch (error) {
      output.innerHTML = '<div class="analog-empty">Ranking unavailable. The rest of Analog Explorer remains usable.</div>';
      setStatus(error.message, true);
    } finally {
      button.disabled = false;
      button.textContent = 'Rank Earth analogs';
    }
  });
})();
