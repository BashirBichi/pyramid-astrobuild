'use strict';

const PAGES = new Set(['overview', 'explorer', 'terrain', 'mission', 'sources']);
const state = {sites: [], datasets: [], selectedSite: null, map: null, markers: new Map(), toastTimer: null};
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const icon = (name) => `<svg class="i" aria-hidden="true"><use href="#ic-${name}"/></svg>`;
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (s) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));

async function request(path, options = {}) {
  let response;
  try { response = await fetch(path, {cache: 'no-store', ...options}); }
  catch { throw new Error('Network unavailable. Confirm the server is running and try again.'); }
  let data;
  try { data = await response.json(); }
  catch { throw new Error(`Server returned invalid JSON (HTTP ${response.status}).`); }
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(Array.isArray(detail) ? detail.map(item => item.msg).join('; ') : String(detail || `HTTP ${response.status}`));
  }
  return data;
}

function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => el.classList.remove('show'), 4000);
}

function showError(id, message) {
  const el = $(id);
  if (!el) return;
  el.textContent = message;
  el.hidden = !message;
}

function pageName(page) {
  return {overview:'Overview', explorer:'Analog Explorer', terrain:'Terrain Lab', mission:'Robotics Simulator', sources:'Data Sources'}[page];
}

function navigate(page, updateHash = true) {
  if (!PAGES.has(page)) page = 'overview';
  $$('.page').forEach(el => el.classList.toggle('visible', el.id === `page-${page}`));
  $$('[data-page]').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
    if (el.dataset.page === page) el.setAttribute('aria-current', 'page');
    else el.removeAttribute('aria-current');
  });
  $('#breadcrumb-current').textContent = pageName(page);
  if (updateHash && location.hash !== `#${page}`) history.replaceState(null, '', `#${page}`);
  closeSidebar();
  window.scrollTo({top: 0, behavior: 'instant'});
  if (page === 'explorer') setTimeout(initMap, 30);
}

function closeSidebar() {
  $('#sidebar').classList.remove('open');
  $('#sidebar-screen').classList.remove('open');
}

function siteIsReference(site) { return site.status === 'Reference example'; }

function matchingSites() {
  const q = $('#site-search').value.trim().toLowerCase();
  const filter = $('#site-filter').value;
  return state.sites.filter(site => {
    if (filter === 'candidate' && siteIsReference(site)) return false;
    if (filter === 'reference' && !siteIsReference(site)) return false;
    return [site.name, site.country, site.category, site.region].join(' ').toLowerCase().includes(q);
  });
}

function renderSites() {
  syncMapMarkers();
  const results = matchingSites();
  $('#site-count').textContent = `${results.length} location${results.length === 1 ? '' : 's'}`;
  $('#site-list').innerHTML = results.length ? results.map(site => `
    <button type="button" class="site-item ${state.selectedSite === site.id ? 'active' : ''}" data-site="${escapeHtml(site.id)}">
      <span class="site-marker ${siteIsReference(site) ? 'ref' : ''}">${icon('pin')}</span>
      <span class="site-text"><strong>${escapeHtml(site.name)}</strong><small>${escapeHtml(site.country)} · ${escapeHtml(site.region)}</small><span class="site-tag">${escapeHtml(site.tag)} · ${siteIsReference(site) ? 'Benchmark reference' : 'Requires validation'}</span></span>
      ${icon('chevron')}
    </button>`).join('') : '<div class="empty-state">No sites match these filters.</div>';
  $$('[data-site]').forEach(button => button.addEventListener('click', () => selectSite(button.dataset.site)));
  state.markers.forEach((marker, id) => {
    if (state.map) {
      if (results.some(site => site.id === id)) marker.addTo(state.map);
      else state.map.removeLayer(marker);
    }
  });
}

function selectSite(id) {
  const site = state.sites.find(item => item.id === id);
  if (!site) return;
  state.selectedSite = id;
  renderSites();
  $('#site-detail').innerHTML = `
    <div class="detail-upper"><span class="eyebrow">SITE INTELLIGENCE / ${escapeHtml(site.category.toUpperCase())}</span><span class="detail-status">${escapeHtml(site.status)}</span></div>
    <h3>${escapeHtml(site.name)}, ${escapeHtml(site.country)}</h3>
    <p>${escapeHtml(site.description)}</p>
    <div class="detail-metadata"><span>${icon('pin')} ${site.lat.toFixed(2)}°, ${site.lng.toFixed(2)}°</span><span>${escapeHtml(site.tag)}</span><span>Unscored</span></div>
    <div class="research-focus"><small>RESEARCH HYPOTHESIS</small><p>${escapeHtml(site.research)}</p></div>
    <div class="action-row"><button class="btn btn-outline" id="site-analyze">Compare with a NASA DEM ${icon('arrow')}</button></div>`;
  $('#site-analyze').addEventListener('click', () => navigate('terrain'));
  const marker = state.markers.get(id);
  if (marker && state.map) state.map.setView([site.lat, site.lng], Math.max(5, state.map.getZoom()), {animate: true});
}

function syncMapMarkers() {
  if (!state.map) return;
  state.sites.forEach(site => {
    if (state.markers.has(site.id)) return;
    const markerIcon = L.divIcon({className:'', html:`<span class="map-pin ${siteIsReference(site) ? 'ref' : ''}" style="display:block"></span>`, iconSize:[17,17], iconAnchor:[8,8]});
    const marker = L.marker([site.lat, site.lng], {icon: markerIcon})
      .bindPopup(`<b>${escapeHtml(site.name)}</b><br>${escapeHtml(site.country)} · ${escapeHtml(site.status)}`)
      .on('click', () => selectSite(site.id));
    marker.addTo(state.map);
    state.markers.set(site.id, marker);
  });
}

function initMap() {
  if (state.map || !$('#analog-map')) return;
  if (!window.L) {
    $('#analog-map').innerHTML = '<div class="map-unavailable">Map tiles could not load. The research site list remains fully accessible. Refresh with an internet connection to view the map.</div>';
    return;
  }
  const map = L.map('analog-map', {zoomControl: false, scrollWheelZoom: false}).setView([14, 13], 2);
  state.map = map;
  L.control.zoom({position: 'bottomright'}).addTo(map);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
    maxZoom: 17, minZoom: 2, detectRetina: false,
  }).addTo(map);
  syncMapMarkers();
  setTimeout(() => {map.invalidateSize(); if(state.selectedSite) selectSite(state.selectedSite);}, 120);
}

function renderSources() {
  $('#sources-grid').innerHTML = state.datasets.map(dataset => `
    <article class="card source-card">
      <div class="source-body"><span>${escapeHtml(dataset.body.toUpperCase())}</span>${icon('database')}</div>
      <h3>${escapeHtml(dataset.name)}</h3><p>${escapeHtml(dataset.detail)}</p><small>${escapeHtml(dataset.access)} · ${escapeHtml(dataset.kind)}</small>
      <a href="${escapeHtml(dataset.url)}" target="_blank" rel="noopener noreferrer">Open source catalog ${icon('external')}</a>
    </article>`).join('');
}

function displayComparison(result) {
  $('#terrain-results').hidden = false;
  $('#similarity-score').textContent = Number(result.similarity_index).toFixed(1);
  const synthetic = String(result.provenance).startsWith('SYNTHETIC_');
  $('#result-provenance').textContent = synthetic ? 'SYNTHETIC DEMO' : 'USER UPLOADED DEMs';
  $('#result-provenance').style.color = synthetic ? '#f4c783' : '#a2eec8';
  const fields = [
    ['relief_m','Local relief','m',0],
    ['elevation_std_m','Elevation spread','m',0],
    ['slope_median_deg','Median terrain slope','°',1],
    ['slope_p90_deg','90th percentile slope','°',1],
    ['gentle_slope_pct','Gentle surface area','%',1],
  ];
  $('#metric-bars').innerHTML = fields.map(([key,label,units,dp]) => {
    const a = Number(result.earth[key]);
    const b = Number(result.reference[key]);
    const comparison = key === 'gentle_slope_pct' ? 100 : Math.max(a,b,1);
    return `<div class="metric-item"><div class="metric-label">${label}</div><div class="metric-values"><span>Earth <strong>${a.toFixed(dp)}${units}</strong></span><span>Reference <strong>${b.toFixed(dp)}${units}</strong></span></div><div class="bar-track"><div class="bar-fill" style="width:${Math.max(1,Math.min(100,100 * a / comparison))}%"></div></div><div class="bar-track" style="margin-top:5px"><div class="bar-fill" style="background:linear-gradient(90deg,#6684ce,#b0acfb);width:${Math.max(1,Math.min(100,100 * b / comparison))}%"></div></div></div>`;
  }).join('');
  $('#result-warnings').innerHTML = result.warnings.map(warning => `<div class="warning-item">${icon('info')} ${escapeHtml(warning)}</div>`).join('');
  $('#terrain-results').scrollIntoView({behavior:'smooth',block:'start'});
}

async function submitTerrain(event) {
  event.preventDefault();
  const button = $('#terrain-form button[type="submit"]');
  showError('#terrain-error', '');
  const earth = $('#earth-file').files?.[0];
  const reference = $('#reference-file').files?.[0];
  if (!earth || !reference) return showError('#terrain-error', 'Both elevation GeoTIFF files are required.');
  if (earth.size > 12*1024*1024 || reference.size > 12*1024*1024) return showError('#terrain-error', 'Each GeoTIFF must be at most 12 MB. Crop a smaller geographic area first.');
  const body = new FormData();
  body.append('earth_file', earth);
  body.append('reference_file', reference);
  body.append('reference_body', $('#target-body').value);
  if ($('#earth-spacing').value.trim()) body.append('earth_pixel_spacing_m', $('#earth-spacing').value);
  if ($('#reference-spacing').value.trim()) body.append('reference_pixel_spacing_m', $('#reference-spacing').value);
  button.disabled = true;
  button.textContent = 'Analyzing terrain...';
  try { displayComparison(await request('/api/terrain/compare', {method:'POST', body})); }
  catch (error) { showError('#terrain-error', error.message); }
  finally { button.disabled = false; button.innerHTML = `${icon('spark')} Analyze uploaded DEMs`; }
}

function renderMission(result) {
  if (!result.ready) {
    $('#mission-days').textContent = '--';
    $('#mission-energy').textContent = '--';
    $('#timeline').innerHTML = `<div class="empty-state">${escapeHtml(result.reason)}. ${result.missing_roles ? `Add: ${escapeHtml(result.missing_roles.join(', '))}` : `Required: ${escapeHtml(result.required_power_kw || 0)} kW`}.</div>`;
    return;
  }
  $('#mission-days').textContent = result.duration_days;
  $('#mission-energy').textContent = Number(result.energy_kwh).toLocaleString('en-US', {maximumFractionDigits:0});
  $('#timeline').innerHTML = result.timeline.map(task => {
    const left = Math.max(0, Math.min(100, 100 * task.start_h / result.duration_h));
    const width = Math.min(100-left, 100 * task.duration_h / result.duration_h);
    return `<div class="timeline-item"><div class="timeline-title"><strong>${escapeHtml(task.label)}</strong><span>${task.start_h}h → ${task.end_h}h</span></div><div class="timeline-track"><div class="timeline-segment" style="left:${left}%;width:${width}%"></div></div></div>`;
  }).join('');
  $('#mission-assumptions').innerHTML = `<strong>Assumptions and limitations</strong><ul>${result.assumptions.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
}

async function submitMission(event) {
  if (event) event.preventDefault();
  showError('#mission-error','');
  const form = $('#mission-form');
  const body = Object.fromEntries(new FormData(form).entries());
  Object.keys(body).forEach(key => body[key] = Number(body[key]));
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try { renderMission(await request('/api/mission', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})); }
  catch (error) { showError('#mission-error',error.message); }
  finally { button.disabled = false; }
}

function initEventHandlers() {
  $$('[data-page]').forEach(el => el.addEventListener('click', () => navigate(el.dataset.page)));
  $$('[data-go]').forEach(el => el.addEventListener('click', () => navigate(el.dataset.go)));
  $('#menu-button').addEventListener('click', () => { $('#sidebar').classList.toggle('open'); $('#sidebar-screen').classList.toggle('open'); });
  $('#sidebar-screen').addEventListener('click', closeSidebar);
  $('#site-search').addEventListener('input', renderSites);
  $('#site-filter').addEventListener('change', renderSites);
  $('#terrain-form').addEventListener('submit', submitTerrain);
  $('#earth-file').addEventListener('change', (event) => $('#earth-file-label').textContent = event.target.files?.[0]?.name ?? 'Choose a GeoTIFF');
  $('#reference-file').addEventListener('change', (event) => $('#reference-file-label').textContent = event.target.files?.[0]?.name ?? 'Choose a GeoTIFF');
  $('#demo-button').addEventListener('click', async () => {
    showError('#terrain-error','');
    const button = $('#demo-button');
    button.disabled = true;
    try { displayComparison(await request('/api/demo-comparison')); toast('Synthetic demonstration loaded. Not NASA measurements.'); }
    catch (error) { showError('#terrain-error', error.message); }
    finally { button.disabled = false; }
  });
  $('#power-range').addEventListener('input', (event) => $('#power-value').textContent = `${event.target.value} kW`);
  $('#mission-form').addEventListener('submit', submitMission);
  window.addEventListener('hashchange', () => navigate(location.hash.slice(1),false));
}

async function start() {
  initEventHandlers();
  navigate(location.hash.slice(1), false);
  try {
    const catalog = await request('/api/catalog');
    state.sites = catalog.sites;
    state.datasets = catalog.datasets;
    $('#stat-sites').textContent = String(state.sites.length).padStart(2,'0');
    renderSites();
    renderSources();
    if (location.hash === '#explorer') initMap();
  } catch (error) {
    toast(`Unable to load location catalog: ${error.message}`);
    $('#site-list').innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
  await submitMission();
}

document.addEventListener('DOMContentLoaded', start);
