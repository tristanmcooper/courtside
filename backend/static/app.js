// Courtside dashboard — Record / Sessions / Summary
const $ = (id) => document.getElementById(id);
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
const fmt = (v, d = 1) => (v == null || Number.isNaN(v)) ? '–' : Number(v).toFixed(d);

// ---------- icons (Lucide-style) ----------
const S = (p) => `<svg viewBox="0 0 24 24">${p}</svg>`;
const ICONS = {
  logo: S('<circle cx="12" cy="12" r="9"/><path d="M4 14c2 1.4 4 1.4 8 0s4-1.4 8 0"/>'),
  record: S('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3" fill="currentColor" stroke="none"/>'),
  sessions: S('<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>'),
  summary: S('<path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/>'),
  sand: S('<path d="M14 9.5V4a2 2 0 0 0-4 0v5.5a4 4 0 1 0 4 0Z"/><path d="M12 4v8"/>'),
  air: S('<path d="M14 9.5V4a2 2 0 0 0-4 0v5.5a4 4 0 1 0 4 0Z"/>'),
  humidity: S('<path d="M12 2.7S5 9 5 14a7 7 0 0 0 14 0c0-5-7-11.3-7-11.3Z"/>'),
  wind: S('<path d="M3 8h11a2.5 2.5 0 1 0-2.5-2.5"/><path d="M3 12h15a2.5 2.5 0 1 1-2.5 2.5"/><path d="M3 16h8"/>'),
  location: S('<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>'),
  save: S('<path d="M20 6 9 17l-5-5"/>'),
  notes: S('<path d="M12 20H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v6"/><path d="M18.5 14.5 21 17l-3.7 3.7L14 21l.5-3.7Z"/>'),
  trash: S('<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>'),
  back: S('<path d="M19 12H5"/><path d="m12 19-7-7 7-7"/>'),
  bulb: S('<path d="M9 18h6M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12c.6.6 1 1.5 1 3h6c0-1.5.4-2.4 1-3a7 7 0 0 0-4-12Z"/>'),
};
const drawIcons = (root = document) =>
  root.querySelectorAll('[data-icon]').forEach(e => { e.innerHTML = ICONS[e.dataset.icon] || ''; });

// ---------- formatters ----------
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function fmtDate(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return `${MON[m - 1]} ${d}, ${y}`;
}
function humanAge(s) {
  if (s == null) return '';
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}
const ratingClass = (v) => v == null ? 'none' : v >= 7 ? 'good' : v >= 4 ? 'mid' : 'low';
function interp(sand) {
  if (sand == null) return '—';
  if (sand < 25) return 'Cool';
  if (sand < 35) return 'Comfortable';
  if (sand < 45) return 'Warm';
  return 'Hot';
}

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

// ---------- canvas ----------
function prep(c, h) {
  const dpr = window.devicePixelRatio || 1, w = c.clientWidth || 300;
  c.width = w * dpr; c.height = h * dpr;
  const ctx = c.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}
function drawSpark(c, values, color) {
  const { ctx, w, h } = prep(c, 52), pad = 4;
  ctx.clearRect(0, 0, w, h);
  const v = values.filter(x => x != null && !Number.isNaN(x));
  if (v.length < 2) return;
  const max = Math.max(...v), min = Math.min(...v), span = (max - min) || 1;
  const pt = (val, i) => [pad + (i / (v.length - 1)) * (w - 2 * pad), h - pad - ((val - min) / span) * (h - 2 * pad)];
  ctx.beginPath(); ctx.moveTo(pad, h - pad);
  v.forEach((val, i) => ctx.lineTo(...pt(val, i)));
  ctx.lineTo(w - pad, h - pad); ctx.closePath();
  ctx.fillStyle = color + '22'; ctx.fill();
  ctx.beginPath(); v.forEach((val, i) => { const [x, y] = pt(val, i); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();
}

// ---------- live ----------
function setRing(sand) {
  const f = $('ringFill');
  f.style.strokeDashoffset = (sand == null || Number.isNaN(sand)) ? 100 : 100 - clamp((sand - 15) / 40 * 100, 0, 100);
}
async function pollLive() {
  const status = $('status'), st = $('statusText');
  try {
    const j = await (await fetch('/api/live')).json();
    const d = j.reading || {};
    if (j.online && j.reading) { status.className = 'status online'; st.textContent = `Live · ${humanAge(j.age_s)}`; }
    else if (j.reading && j.age_s < 120) { status.className = 'status stale'; st.textContent = `Last reading ${humanAge(j.age_s)}`; }
    else if (j.reading) { status.className = 'status offline'; st.textContent = `Offline · last seen ${humanAge(j.age_s)}`; }
    else { status.className = 'status offline'; st.textContent = 'Offline · no data yet'; }
    $('heroVal').textContent = fmt(d.ir_object_c); setRing(d.ir_object_c);
    $('interp').textContent = interp(d.ir_object_c);
    $('v_sand').textContent = fmt(d.ir_object_c);
    $('v_air').textContent = fmt(d.temp_c);
    $('v_hum').textContent = fmt(d.humidity_pct, 0);
    $('v_wind').textContent = fmt(d.sound_pp, 0);
  } catch (e) { status.className = 'status offline'; st.textContent = 'Disconnected'; }
}
async function pollPlots() {
  try {
    const j = await (await fetch('/api/court/recent?minutes=2')).json();
    const r = j.readings || [];
    document.querySelectorAll('canvas.spark').forEach(c => drawSpark(c, r.map(x => x[c.dataset.key]), c.dataset.color));
  } catch (e) { /* ignore */ }
}

// ---------- recording ----------
let timerInt = null;
const fmtElapsed = (ms) => { const s = Math.floor(ms / 1000); return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`; };
function setRecordingUI(on) {
  const btn = $('recBtn'), t = $('recTimer');
  if (on) {
    btn.innerHTML = `<span class="ic">${ICONS.record}</span>Stop &amp; evaluate`; btn.classList.add('recording'); t.style.display = 'block';
    const start = Number(localStorage.getItem('activeStart')) || Date.now();
    clearInterval(timerInt);
    const tick = () => { t.textContent = fmtElapsed(Date.now() - start); };
    tick(); timerInt = setInterval(tick, 500);
  } else {
    btn.innerHTML = `<span class="ic">${ICONS.record}</span>Start recording`; btn.classList.remove('recording'); t.style.display = 'none';
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
      await fetch(`/api/sessions/${active}/stop`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
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
const bindSlider = (name, label, dash) => {
  const i = ef.querySelector(`[name="${name}"]`), el = $(label);
  i.addEventListener('input', () => {
    const z = dash && i.value === '0';
    el.textContent = z ? '—' : i.value; el.classList.toggle('dim', z);
  });
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
ef.addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = $('evalMsg'), body = {};
  for (const [k, v] of new FormData(ef).entries()) {
    if (v === '') continue;
    if ((k === 'peer_rating_1_10' || k === 'coach_rating_1_10') && Number(v) === 0) continue;
    body[k] = INT_F.includes(k) ? parseInt(v, 10) : FLOAT_F.includes(k) ? parseFloat(v) : v;
  }
  try {
    const r = await fetch(`/api/sessions/${ef.dataset.sid}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await r.text());
    msg.textContent = 'Saved ✓'; msg.className = 'formmsg ok';
    setTimeout(() => { ef.reset(); ef.style.display = 'none'; msg.textContent = ''; }, 900);
  } catch (err) { msg.textContent = 'Error: ' + err.message; msg.className = 'formmsg err'; }
});

// ---------- sessions ----------
const condStr = (s) => {
  if (!s) return '';
  const bits = [];
  if (s.sand_temp) bits.push(`Sand ${s.sand_temp.mean}°`);
  if (s.air_temp) bits.push(`Air ${s.air_temp.mean}°`);
  if (s.wind_sound) bits.push(`Wind ${Math.round(s.wind_sound.mean)}`);
  return bits.join(' · ');
};
async function loadSessions() {
  $('sessionList').style.display = ''; $('detail').style.display = 'none';
  try {
    const rows = await (await fetch('/api/sessions')).json();
    const ul = $('sessionList');
    if (!rows.length) { ul.innerHTML = '<li class="empty">No sessions yet.<br>Hit <b>Start recording</b> on the Record tab to log your first one.</li>'; return; }
    ul.innerHTML = '';
    rows.forEach(s => {
      const li = document.createElement('li'); li.className = 'scard';
      const rec = s.status === 'recording';
      const badge = rec ? '<span class="badge rec">● REC</span>'
        : s.subjective_rating_1_10 != null ? `<span class="badge ${ratingClass(s.subjective_rating_1_10)}">${s.subjective_rating_1_10}/10</span>`
          : '<span class="badge none">Unrated</span>';
      const meta = [s.partner, s.location].filter(Boolean).join(' · ') || 'No notes';
      const cond = condStr(s.sensors);
      li.innerHTML = `<div><div class="s-date">${fmtDate(s.day)}</div><div class="s-meta">${meta}</div>${cond ? `<div class="s-cond">${cond}</div>` : ''}</div>${badge}`;
      li.addEventListener('click', () => showDetail(s.session_id));
      ul.appendChild(li);
    });
  } catch (e) { /* ignore */ }
}

const PERF = [['subjective_rating_1_10', 'Self (0–10)'], ['peer_rating_1_10', 'Peer'], ['coach_rating_1_10', 'Coach'],
['kills', 'Kills'], ['errors', 'Errors'], ['sets_won', 'Sets won'], ['sets_lost', 'Sets lost']];
const CTX = [['partner', 'Partner'], ['opponent_level', 'Opponent'], ['location', 'Location'], ['felt_state', 'Felt state']];
const val = (d, k) => (d[k] != null ? d[k] : '');
async function showDetail(sid) {
  const d = await (await fetch(`/api/sessions/${encodeURIComponent(sid)}`)).json();
  const s = d.sensors || {};
  const tile = (lbl, o, u) => `<div class="tile"><div class="card-label">${lbl}</div><div class="tile-val">${o ? `${o.mean}${u} <span class="sub">${o.min}–${o.max}</span>` : '–'}</div></div>`;
  const num = ([k, lbl]) => `<label class="fld">${lbl}<input name="${k}" type="number" inputmode="numeric" value="${val(d, k)}"></label>`;
  const txt = ([k, lbl]) => `<label class="fld">${lbl}<input name="${k}" type="text" value="${val(d, k)}"></label>`;
  const el = $('detail');
  $('sessionList').style.display = 'none'; el.style.display = 'block';
  el.innerHTML = `
    <button type="button" id="backBtn" class="btn secondary" style="margin-bottom:14px"><span class="ic">${ICONS.back}</span>Back to sessions</button>
    <h2 class="eyebrow" style="margin:0 2px 8px">${fmtDate(d.day)}${d.n_readings ? ` · ${d.n_readings} sensor samples` : ''}</h2>
    <div class="section-title" style="margin-top:6px"><span class="ic">${ICONS.sand}</span>Conditions</div>
    <div class="det-sensors">
      ${tile('Sand IR', s.sand_temp, '°')}${tile('Air', s.air_temp, '°')}
      ${tile('Humidity', s.humidity, '%')}${tile('Wind/audio', s.wind_sound, '')}
    </div>
    <form id="editForm">
      <div class="section-title"><span class="ic">${ICONS.summary}</span>Performance</div>
      <div class="grid2">${PERF.map(num).join('')}</div>
      <div class="section-title"><span class="ic">${ICONS.notes}</span>Context</div>
      ${CTX.map(txt).join('')}
      <label class="fld">Notes<textarea name="notes" rows="2">${val(d, 'notes')}</textarea></label>
      <div class="btnrow">
        <button type="submit" class="btn primary"><span class="ic">${ICONS.save}</span>Save</button>
        <button type="button" id="delBtn" class="btn danger"><span class="ic">${ICONS.trash}</span>Delete</button>
      </div>
      <div id="editMsg" class="formmsg"></div>
    </form>`;
  window.scrollTo(0, 0);
  $('backBtn').addEventListener('click', () => { el.style.display = 'none'; $('sessionList').style.display = ''; });
  $('editForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = {};
    for (const [k, v] of new FormData(e.target).entries())
      body[k] = v === '' ? null : (INT_F.includes(k) || FLOAT_F.includes(k) ? Number(v) : v);
    const r = await fetch(`/api/sessions/${encodeURIComponent(sid)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    $('editMsg').textContent = r.ok ? 'Saved ✓' : 'Error'; $('editMsg').className = 'formmsg ' + (r.ok ? 'ok' : 'err');
  });
  $('delBtn').addEventListener('click', async () => {
    if (!confirm('Delete this session?')) return;
    await fetch(`/api/sessions/${encodeURIComponent(sid)}`, { method: 'DELETE' });
    el.style.display = 'none'; loadSessions();
  });
}

// ---------- summary ----------
function pearson(xs, ys) {
  const n = xs.length; if (n < 3) return null;
  const mx = xs.reduce((a, b) => a + b) / n, my = ys.reduce((a, b) => a + b) / n;
  let num = 0, dx = 0, dy = 0;
  for (let i = 0; i < n; i++) { num += (xs[i] - mx) * (ys[i] - my); dx += (xs[i] - mx) ** 2; dy += (ys[i] - my) ** 2; }
  return (dx && dy) ? num / Math.sqrt(dx * dy) : null;
}
async function loadSummary() {
  try {
    const j = await (await fetch('/api/summary')).json();
    $('s_n').textContent = j.n_sessions;
    $('s_avg').textContent = j.avg_rating != null ? j.avg_rating : '–';
    $('s_best').textContent = j.best_rating != null ? j.best_rating : '–';
    const hist = j.history || [];
    // trend
    const tc = $('trendCard'), tv = $('trendVal');
    if (hist.length >= 2) {
      const r = hist.map(h => h.rating), slope = r[r.length - 1] - r[0];
      const dir = slope > 0.5 ? 'up' : slope < -0.5 ? 'down' : 'flat';
      tc.className = 'card trend ' + dir;
      tv.textContent = dir === 'up' ? 'Improving ↑' : dir === 'down' ? 'Declining ↓' : 'Steady →';
    } else { tc.className = 'card trend flat'; tv.textContent = 'Need ≥2 sessions'; }
    drawHist(hist);
    loadRecovery();
    // insights from sessions (sensors + rating)
    insights();
    const ul = $('summaryList');
    ul.innerHTML = hist.length ? '' : '<li class="empty">No rated sessions yet.</li>';
    hist.slice().reverse().forEach(h => {
      const li = document.createElement('li'); li.className = 'scard'; li.style.cursor = 'default';
      const extra = [h.peer != null ? `peer ${h.peer}` : '', h.coach != null ? `coach ${h.coach}` : ''].filter(Boolean).join(' · ') || '—';
      li.innerHTML = `<div><div class="s-date">${fmtDate(h.day)}</div><div class="s-meta">${extra}</div></div><span class="badge ${ratingClass(h.rating)}">${h.rating}/10</span>`;
      ul.appendChild(li);
    });
  } catch (e) { /* ignore */ }
}
async function loadRecovery() {
  const cell = (k, o, u = '') => o
    ? `<div class="r"><div class="k">${k}</div><div class="v">${o.value}${u}</div><div class="s">${o.source} · ${fmtDate(o.day)}</div></div>`
    : `<div class="r"><div class="k">${k}</div><div class="v">–</div><div class="s">no data yet</div></div>`;
  try {
    const r = await (await fetch('/api/recovery')).json();
    let html = cell('HRV (SDNN)', r.hrv, ' ms') + cell('Resting HR', r.resting_hr) + cell('Sleep', r.sleep_hours, ' h');
    const w = r.last_workout;
    if (w) {
      html += `<div class="r"><div class="k">In-session HR</div><div class="v">${w.avg_hr ? Math.round(w.avg_hr) : '–'}</div><div class="s">${w.name || 'workout'} · max ${w.max_hr ? Math.round(w.max_hr) : '–'}</div></div>`;
      html += `<div class="r"><div class="k">Active energy</div><div class="v">${w.active_energy ? Math.round(w.active_energy) : '–'}</div><div class="s">kcal · ${w.duration_min ? Math.round(w.duration_min) : '–'} min</div></div>`;
    }
    html += cell('Resp. rate', r.respiratory_rate);
    $('recGrid').innerHTML = html;
  } catch (e) { $('recGrid').innerHTML = '<div class="r"><div class="k">Recovery</div><div class="v">–</div><div class="s">unavailable</div></div>'; }
}

async function insights() {
  const box = $('insights'); box.innerHTML = '';
  try {
    const rows = await (await fetch('/api/sessions')).json();
    const rated = rows.filter(s => s.subjective_rating_1_10 != null);
    const card = (msg) => `<div class="insight"><span class="ic">${ICONS.bulb}</span><p>${msg}</p></div>`;
    if (rated.length < 3) { box.innerHTML = card(`Log ${3 - rated.length} more rated session${3 - rated.length > 1 ? 's' : ''} to unlock condition insights.`); return; }
    const out = [];
    const corr = (pick, label) => {
      const pts = rated.filter(s => s.sensors && pick(s.sensors) != null);
      if (pts.length < 3) return;
      const r = pearson(pts.map(s => pick(s.sensors)), pts.map(s => s.subjective_rating_1_10));
      if (r != null && Math.abs(r) >= 0.4)
        out.push(`${label} ${r < 0 ? 'tended to go with <b>lower</b>' : 'tended to go with <b>higher</b>'} self-ratings (r=${r.toFixed(2)}).`);
    };
    corr(s => s.sand_temp && s.sand_temp.mean, 'Warmer sand');
    corr(s => s.wind_sound && s.wind_sound.mean, 'More wind/noise');
    box.innerHTML = (out.length ? out : ['No strong condition patterns yet — keep collecting.']).map(card).join('');
  } catch (e) { /* ignore */ }
}
function drawHist(hist) {
  const { ctx, w, h } = prep($('histChart'), 170), pad = 24, n = hist.length;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = 'rgba(255,255,255,0.06)'; ctx.fillStyle = '#6f7c91'; ctx.font = '10px Inter, sans-serif';
  for (let g = 0; g <= 10; g += 2) { const y = h - pad - (g / 10) * (h - 2 * pad); ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(w - 6, y); ctx.stroke(); ctx.fillText(g, 6, y + 3); }
  if (!n) return;
  const X = i => pad + (n === 1 ? 0.5 : i / (n - 1)) * (w - pad - 10), Y = v => h - pad - (v / 10) * (h - 2 * pad);
  const series = (key, color) => {
    const pts = hist.map((d, i) => [X(i), d[key]]).filter(p => p[1] != null);
    if (!pts.length) return;
    ctx.beginPath(); pts.forEach(([x, v], i) => { const y = Y(v); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    ctx.strokeStyle = color; ctx.lineWidth = 2.4; ctx.stroke();
    pts.forEach(([x, v]) => { ctx.beginPath(); ctx.arc(x, Y(v), 3, 0, 7); ctx.fillStyle = color; ctx.fill(); });
  };
  series('rating', '#f6b26b'); series('peer', '#67e8d1'); series('coach', '#5ad19a');
}

// ---------- boot ----------
drawIcons();
if (localStorage.getItem('activeSessionId')) setRecordingUI(true);
pollLive(); pollPlots();
setInterval(pollLive, 1000);
setInterval(pollPlots, 2500);
