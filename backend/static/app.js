// Courtside dashboard — Record / Sessions / Summary.
const $ = (id) => document.getElementById(id);
const fmt = (v, d = 1) => (v == null || Number.isNaN(v)) ? '–' : Number(v).toFixed(d);
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));

// ---------- tabs ----------
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    $(btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'sessions') loadSessions();
    if (btn.dataset.tab === 'summary') loadSummary();
  });
});

// ---------- canvas helper (DPR-crisp) ----------
function prep(canvas, h = 56) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 300;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}
function drawSpark(canvas, values, color) {
  const { ctx, w, h } = prep(canvas);
  ctx.clearRect(0, 0, w, h);
  const v = values.filter(x => x != null && !Number.isNaN(x));
  if (v.length < 2) return;
  const max = Math.max(...v), min = Math.min(...v), span = (max - min) || 1, pad = 4;
  const pt = (val, i) => [pad + (i / (v.length - 1)) * (w - 2 * pad),
    h - pad - ((val - min) / span) * (h - 2 * pad)];
  ctx.beginPath(); ctx.moveTo(pad, h - pad);
  v.forEach((val, i) => ctx.lineTo(...pt(val, i)));
  ctx.lineTo(w - pad, h - pad); ctx.closePath();
  ctx.fillStyle = color + '22'; ctx.fill();
  ctx.beginPath();
  v.forEach((val, i) => { const [x, y] = pt(val, i); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();
}

// ---------- live polling ----------
function setRing(sand) {
  const f = $('ringFill');
  if (sand == null || Number.isNaN(sand)) { f.style.strokeDashoffset = 100; return; }
  f.style.strokeDashoffset = 100 - clamp((sand - 15) / 40 * 100, 0, 100);
}
function setupBanner(online, d) {
  const el = $('setupBanner');
  if (!online || !d) { el.className = 'banner err'; el.textContent = '● Node offline — check power / hotspot.'; return; }
  const issues = [];
  if (d.temp_c == null) issues.push('Air sensor (DHT11) not reading — reseat GPIO2.');
  if (d.sound_pp != null && d.sound_pp >= 4000) issues.push('Mic pegged at max — OUT wire floating/shorted.');
  if (d.ir_object_c == null) issues.push('IR not reading — check MLX wiring (0x5A).');
  else if (d.ir_ambient_c != null && Math.abs(d.ir_object_c - d.ir_ambient_c) < 1.5)
    issues.push('IR ≈ air temp — aim it DOWN at the sand (tripod may be too high).');
  else if (d.ir_object_c < 5 || d.ir_object_c > 70)
    issues.push('Sand IR out of expected range — check aim.');
  if (!issues.length) { el.className = 'banner ok'; el.textContent = '✓ Setup looks good — IR aimed at the sand, all sensors live.'; }
  else { el.className = 'banner warn'; el.innerHTML = 'Setup check:<ul>' + issues.map(i => `<li>${i}</li>`).join('') + '</ul>'; }
}
async function pollLive() {
  const status = $('status'), st = $('statusText');
  try {
    const j = await (await fetch('/api/live')).json();
    const online = j.online && j.reading;
    st.textContent = online ? `online · ${j.age_s}s` : (j.reading ? `stale · ${j.age_s}s` : 'no data yet');
    status.className = 'status ' + (online ? 'online' : (j.reading ? 'stale' : 'offline'));
    const d = j.reading || {};
    $('heroVal').textContent = fmt(d.ir_object_c); setRing(d.ir_object_c);
    $('v_sand').textContent = fmt(d.ir_object_c);
    $('v_air').textContent = fmt(d.temp_c);
    $('v_hum').textContent = fmt(d.humidity_pct, 0);
    $('v_wind').textContent = fmt(d.sound_pp, 0);
    setupBanner(online, j.reading);
  } catch (e) { st.textContent = 'disconnected'; status.className = 'status offline'; }
}
async function pollPlots() {
  try {
    const j = await (await fetch('/api/court/recent?minutes=2')).json();
    const r = j.readings || [];
    document.querySelectorAll('canvas.spark').forEach(c =>
      drawSpark(c, r.map(x => x[c.dataset.key]), c.dataset.color));
  } catch (e) { /* ignore */ }
}

// ---------- recording ----------
let timerInt = null;
function fmtElapsed(ms) {
  const s = Math.floor(ms / 1000); return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}
function setRecordingUI(on) {
  const btn = $('recBtn'), t = $('recTimer');
  if (on) {
    btn.textContent = '■ Stop & evaluate'; btn.classList.add('recording'); t.style.display = 'block';
    const start = Number(localStorage.getItem('activeStart')) || Date.now();
    clearInterval(timerInt);
    timerInt = setInterval(() => { t.textContent = fmtElapsed(Date.now() - start); }, 500);
    t.textContent = fmtElapsed(Date.now() - start);
  } else {
    btn.textContent = '● Start recording'; btn.classList.remove('recording'); t.style.display = 'none';
    clearInterval(timerInt);
  }
}
$('recBtn').addEventListener('click', async () => {
  const active = localStorage.getItem('activeSessionId');
  if (!active) {
    try {
      const j = await (await fetch('/api/sessions/start', { method: 'POST' })).json();
      localStorage.setItem('activeSessionId', j.session_id);
      localStorage.setItem('activeStart', String(Date.now()));
      setRecordingUI(true);
    } catch (e) { alert('Could not start recording: ' + e.message); }
  } else {
    try {
      await fetch(`/api/sessions/${active}/stop`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
      });
      $('evalForm').dataset.sid = active;
      localStorage.removeItem('activeSessionId'); localStorage.removeItem('activeStart');
      setRecordingUI(false);
      $('evalForm').style.display = 'block';
      $('evalForm').scrollIntoView({ behavior: 'smooth' });
    } catch (e) { alert('Could not stop: ' + e.message); }
  }
});

// ---------- eval form ----------
const ef = $('evalForm');
const bindSlider = (name, label, zeroDash) => {
  const i = ef.querySelector(`[name="${name}"]`);
  i.addEventListener('input', () => { $(label).textContent = (zeroDash && i.value === '0') ? '–' : i.value; });
};
bindSlider('subjective_rating_1_10', 'selfVal', false);
bindSlider('peer_rating_1_10', 'peerVal', true);
bindSlider('coach_rating_1_10', 'coachVal', true);
$('windSeg').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  $('windSeg').querySelectorAll('button').forEach(x => x.classList.remove('on'));
  b.classList.add('on'); ef.querySelector('[name="wind_self_report"]').value = b.dataset.v;
});
$('geoBtn').addEventListener('click', () => {
  const s = $('geoStatus');
  if (!navigator.geolocation) { s.textContent = 'Geolocation not supported.'; return; }
  s.textContent = 'locating…';
  navigator.geolocation.getCurrentPosition(p => {
    ef.querySelector('[name="lat"]').value = p.coords.latitude.toFixed(6);
    ef.querySelector('[name="lon"]').value = p.coords.longitude.toFixed(6);
    s.textContent = `📍 ${p.coords.latitude.toFixed(4)}, ${p.coords.longitude.toFixed(4)}`;
  }, err => { s.textContent = 'Location failed: ' + err.message; }, { enableHighAccuracy: true, timeout: 10000 });
});

const INT_F = ['kills', 'errors', 'sets_won', 'sets_lost', 'wind_self_report'];
const FLOAT_F = ['subjective_rating_1_10', 'peer_rating_1_10', 'coach_rating_1_10', 'lat', 'lon'];
function formBody(form) {
  const body = {};
  for (const [k, v] of new FormData(form).entries()) {
    if (v === '') continue;
    if ((k === 'peer_rating_1_10' || k === 'coach_rating_1_10') && Number(v) === 0) continue; // 0 = not rated
    body[k] = INT_F.includes(k) ? parseInt(v, 10) : FLOAT_F.includes(k) ? parseFloat(v) : v;
  }
  return body;
}
ef.addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = $('evalMsg'), sid = ef.dataset.sid;
  try {
    const r = await fetch(`/api/sessions/${sid}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formBody(ef))
    });
    if (!r.ok) throw new Error(await r.text());
    msg.textContent = 'Saved ✓'; msg.className = 'formmsg ok';
    setTimeout(() => { ef.reset(); ef.style.display = 'none'; msg.textContent = ''; }, 900);
  } catch (err) { msg.textContent = 'Error: ' + err.message; msg.className = 'formmsg err'; }
});

// ---------- sessions list + detail/edit ----------
async function loadSessions() {
  $('sessionList').style.display = '';   // reset full-page detail
  $('detail').style.display = 'none';
  try {
    const rows = await (await fetch('/api/sessions')).json();
    const ul = $('sessionList');
    if (!rows.length) { ul.innerHTML = '<li><span class="sub">No sessions yet — record one on the Record tab.</span></li>'; return; }
    ul.innerHTML = '';
    rows.forEach(s => {
      const li = document.createElement('li'); li.className = 'tap';
      const rec = s.status === 'recording' ? '<span class="recdot">● REC</span>' :
        (s.subjective_rating_1_10 != null ? `<span class="rate">${s.subjective_rating_1_10}/10</span>` : '<span class="sub">unrated</span>');
      const sub = [s.partner, s.location].filter(Boolean).join(' · ') || '—';
      li.innerHTML = `<span>${s.day}<br><span class="sub">${sub}</span></span>${rec}`;
      li.addEventListener('click', () => showDetail(s.session_id));
      ul.appendChild(li);
    });
  } catch (e) { /* ignore */ }
}

const EDIT = [
  ['subjective_rating_1_10', 'Self rating', 'number'], ['peer_rating_1_10', 'Peer rating', 'number'],
  ['coach_rating_1_10', 'Coach rating', 'number'], ['wind_self_report', 'Wind (0-5)', 'number'],
  ['kills', 'Kills', 'number'], ['errors', 'Errors', 'number'],
  ['sets_won', 'Sets won', 'number'], ['sets_lost', 'Sets lost', 'number'],
  ['partner', 'Partner', 'text'], ['opponent_level', 'Opponent level', 'text'],
  ['location', 'Location', 'text'], ['felt_state', 'Felt state', 'text'], ['notes', 'Notes', 'text'],
];
async function showDetail(sid) {
  const d = await (await fetch(`/api/sessions/${encodeURIComponent(sid)}`)).json();
  const s = d.sensors || {};
  const mm = (o, u) => o ? `${o.mean}${u} <span class="sub">(${o.min}–${o.max})</span>` : '–';
  const fields = EDIT.map(([k, label, type]) =>
    `<label class="fld">${label}<input name="${k}" type="${type}" ${type === 'number' ? 'inputmode="numeric"' : ''} value="${d[k] != null ? d[k] : ''}"></label>`).join('');
  const el = $('detail');
  $('sessionList').style.display = 'none';   // full-page detail
  el.style.display = 'block';
  el.innerHTML = `
    <button type="button" id="backBtn" class="ghost" style="margin-top:0;width:100%">← Back to sessions</button>
    <h2>${d.day} · ${d.status}${d.n_readings ? ` · ${d.n_readings} sensor samples` : ''}</h2>
    <div class="det-sensors">
      <div class="tile"><div class="card-label">Sand IR</div><div class="tile-val">${mm(s.sand_temp, '°')}</div></div>
      <div class="tile"><div class="card-label">Air</div><div class="tile-val">${mm(s.air_temp, '°')}</div></div>
      <div class="tile"><div class="card-label">Humidity</div><div class="tile-val">${mm(s.humidity, '%')}</div></div>
      <div class="tile"><div class="card-label">Wind/sound</div><div class="tile-val">${mm(s.wind_sound, '')}</div></div>
    </div>
    <form id="editForm">${fields}
      <div class="btnrow"><button type="submit" class="primary">Save changes</button>
      <button type="button" id="delBtn" class="danger">Delete</button></div>
      <div id="editMsg" class="formmsg"></div>
    </form>`;
  window.scrollTo(0, 0);
  const showList = () => { el.style.display = 'none'; $('sessionList').style.display = ''; };
  $('backBtn').addEventListener('click', showList);
  $('editForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = {};
    for (const [k, v] of new FormData(e.target).entries())
      body[k] = v === '' ? null : (INT_F.includes(k) || FLOAT_F.includes(k) ? Number(v) : v);
    const r = await fetch(`/api/sessions/${encodeURIComponent(sid)}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    });
    $('editMsg').textContent = r.ok ? 'Saved ✓' : 'Error'; $('editMsg').className = 'formmsg ' + (r.ok ? 'ok' : 'err');
    loadSessions();
  });
  $('delBtn').addEventListener('click', async () => {
    if (!confirm('Delete this session?')) return;
    await fetch(`/api/sessions/${encodeURIComponent(sid)}`, { method: 'DELETE' });
    el.style.display = 'none'; loadSessions();
  });
}

// ---------- summary ----------
async function loadSummary() {
  try {
    const j = await (await fetch('/api/summary')).json();
    $('s_n').textContent = j.n_sessions;
    $('s_avg').textContent = j.avg_rating != null ? j.avg_rating : '–';
    $('s_best').textContent = j.best_rating != null ? j.best_rating : '–';
    drawHist(j.history || []);
    const ul = $('summaryList');
    ul.innerHTML = (j.history || []).length ? '' : '<li><span class="sub">No rated sessions yet.</span></li>';
    (j.history || []).slice().reverse().forEach(h => {
      const li = document.createElement('li');
      const extra = [h.peer != null ? `peer ${h.peer}` : '', h.coach != null ? `coach ${h.coach}` : ''].filter(Boolean).join(' · ');
      li.innerHTML = `<span>${h.day}<br><span class="sub">${extra || '—'}</span></span><span class="rate">${h.rating}/10</span>`;
      ul.appendChild(li);
    });
  } catch (e) { /* ignore */ }
}
function drawHist(hist) {
  const c = $('histChart'), { ctx, w, h } = prep(c, 170);
  ctx.clearRect(0, 0, w, h);
  const pad = 24, n = hist.length;
  // gridlines 0..10
  ctx.strokeStyle = 'rgba(255,255,255,0.07)'; ctx.fillStyle = '#8b97ab'; ctx.font = '10px -apple-system';
  for (let g = 0; g <= 10; g += 2) {
    const y = h - pad - (g / 10) * (h - 2 * pad);
    ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(w - 6, y); ctx.stroke(); ctx.fillText(g, 4, y + 3);
  }
  if (!n) return;
  const X = i => pad + (n === 1 ? 0.5 : i / (n - 1)) * (w - pad - 10);
  const Y = v => h - pad - (v / 10) * (h - 2 * pad);
  const series = (key, color) => {
    const pts = hist.map((d, i) => [X(i), d[key]]).filter(p => p[1] != null);
    if (!pts.length) return;
    ctx.beginPath(); pts.forEach(([x, v], i) => { const y = Y(v); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();
    pts.forEach(([x, v]) => { ctx.beginPath(); ctx.arc(x, Y(v), 3, 0, 7); ctx.fillStyle = color; ctx.fill(); });
  };
  series('rating', '#f2935a'); series('peer', '#76d6c0'); series('coach', '#5ad19a');
}

// ---------- boot ----------
if (localStorage.getItem('activeSessionId')) setRecordingUI(true);
pollLive(); pollPlots();
setInterval(pollLive, 1000);
setInterval(pollPlots, 2500);
