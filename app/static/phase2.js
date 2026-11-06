/* AstroBuild Phase 2: NASA PDS numerical terrain browser and Earthdata discovery. */
(() => {
  'use strict';
  const one = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const btn = one('#pds-load');
  if (btn) btn.addEventListener('click', async () => {
    const error = one('#pds-error');
    const output = one('#pds-result');
    error.hidden = true; output.hidden = true;
    const body = one('#pds-body').value;
    const latitude = Number(one('#pds-lat').value);
    const longitude = Number(one('#pds-lon').value);
    const span_deg = Number(one('#pds-span').value);
    if (![latitude,longitude,span_deg].every(Number.isFinite)) { error.textContent = 'Enter valid latitude, longitude and span.'; error.hidden = false; return; }
    btn.disabled = true;
    btn.textContent = 'Retrieving official NASA elevation data...';
    try {
      const query = new URLSearchParams({body,latitude,longitude,span_deg});
      const response = await fetch(`/api/nasa/planetary-profile?${query}`, {headers:{'Accept':'application/json'}});
      const json = await response.json();
      if (!response.ok) throw new Error(typeof json.detail==='string' ? json.detail : `HTTP ${response.status}`);
      const p = json.profile;
      output.innerHTML = `<strong>${esc(json.name)}</strong><p>NASA PDS numeric grid · ${esc(json.product_id)} · centered ${Number(json.center.latitude).toFixed(2)}°, ${Number(json.center.longitude_east).toFixed(2)}°E</p><div class="phase2-metrics"><div><small>Local relief</small><strong>${Number(p.relief_m).toFixed(1)} m</strong></div><div><small>Median slope</small><strong>${Number(p.slope_median_deg).toFixed(2)}°</strong></div><div><small>Ground spacing</small><strong>${(Number(p.pixel_spacing_m)/1000).toFixed(2)} km</strong></div></div><p class="phase2-note">${json.limitations.map(esc).join(' ')} This is a real NASA-derived gridded measurement, not an Earth analog ranking.</p><a class="phase2-link" href="${esc(json.source_url)}" target="_blank" rel="noopener noreferrer">Official raster source ↗</a>`;
      output.hidden = false;
      const earth = one('#earth-file')?.files?.[0];
      if (earth) {
        const compare = new FormData();
        compare.append('earth_file', earth);
        compare.append('body', body);
        compare.append('latitude', latitude);
        compare.append('longitude', longitude);
        compare.append('span_deg', span_deg);
        const spacing = one('#earth-spacing')?.value.trim();
        if (spacing) compare.append('earth_pixel_spacing_m', spacing);
        const cmpResponse = await fetch('/api/nasa/compare-earth-with-pds', {method:'POST',body:compare});
        const comparison = await cmpResponse.json();
        if (!cmpResponse.ok) throw new Error(typeof comparison.detail === 'string' ? comparison.detail : `Comparison HTTP ${cmpResponse.status}`);
        if (typeof displayComparison === 'function') displayComparison(comparison);
      }
    } catch (e) { error.textContent = e.message; error.hidden = false; }
    finally { btn.disabled = false; btn.textContent = 'Load official NASA elevation profile'; }
  });
  const siteDetail = one('#site-detail');
  if (siteDetail) siteDetail.addEventListener('click', async e => {
    if (!e.target.closest('#earthdata-discover')) return;
    const selected = (typeof state !== 'undefined') ? state.selectedSite : null;
    if (!selected) return;
    const box = one('#earthdata-results');
    const output = one('#earthdata-content');
    box.hidden = false; output.textContent = 'Searching NASA Earthdata CMR...';
    try {
      const res = await fetch(`/api/nasa/earth-granules/${encodeURIComponent(selected)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `CMR HTTP ${res.status}`);
      if (data.status === 'outside_coverage') { output.textContent = data.message; return; }
      if (!data.granules.length) { output.textContent = 'No NASADEM tiles returned for the selected sample box. Try NASA Earthdata Search directly.'; return; }
      output.innerHTML = `<p>${data.granules.length} catalog result(s) from NASADEM_HGT.001. Downloads may require Earthdata Login.</p>` + data.granules.map(g => `<div class="granule-item"><strong>${esc(g.title)}</strong>${g.links.map(url=>`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">NASA file link ↗</a>`).join('')}</div>`).join('');
    } catch (e) { output.textContent = `NASA CMR lookup failed: ${e.message}`; }
  });
  const delay = one('#delay-range');
  if (delay) delay.addEventListener('input', () => one('#delay-value').textContent = `${delay.value} min`);
  const missionForm = one('#mission-form');
  if (missionForm) missionForm.addEventListener('submit', () => {
    const output = one('#communications-result');
    // Read the actual server response through the existing renderMission callback, never infer success from a click.
    if (output) output.textContent = 'Recalculating the communications scenario...';
  });
  // Extend the existing global renderMission function without replacing task scheduling.
  if (typeof renderMission === 'function') {
    const original = renderMission;
    renderMission = function (result) {
      original(result);
      const output = one('#communications-result');
      if (!output) return;
      if (!result.ready || !result.communications) { output.textContent = 'Mission configuration not feasible.'; return; }
      const c = result.communications;
      output.innerHTML = `<strong>${c.mode === 'local_autonomy' ? 'Locally autonomous' : 'Earth-supervised'} coordination</strong><div class="phase2-metrics"><div><small>Round-trip delay</small><strong>${Number(c.round_trip_min).toFixed(0)} min</strong></div><div><small>Modeled review hold</small><strong>${Number(c.review_hold_h).toFixed(2)} h</strong></div><div><small>Latency avoided</small><strong>${Number(c.estimated_latency_avoided_h).toFixed(2)} h</strong></div></div><p class="phase2-note">Communication reviews are hypothetical. Any hazard outside validated robot controls must trigger a safe stop and human investigation. No autonomous construction robots are controlled by this demonstration.</p>`;
    };
  }
})();
