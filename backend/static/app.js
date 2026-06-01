// Courtside dashboard — drives the Oura-style UI in index.html / style.css.

const $ = (id) => document.getElementById(id);
const fmt = (v, d = 1) =>
  (v === null || v === undefined || Number.isNaN(v)) ? '–' : Number(v).toFixed(d);
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));

// ---- tabs ----
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    $(btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'log') loadSessions();
  });
});

// ---- hero ring (sand surface temp, mapped 15–55 °C) ----
function setRing(sand) {
  const fill = $('ringFill');
  if (sand === null || sand === undefined || Number.isNaN(sand)) {
    fill.style.strokeDashoffset = 100;
    return;
  }
  const pct = clamp((sand - 15) / (55 - 15) * 100, 0, 100);
  fill.style.strokeDashoffset = 100 - pct;  // dasharray is 100 (r=15.915)
}

// ---- live polling ----
async function pollLive() {
  const status = $('status'), statusText = $('statusText');
  try {
    const j = await (await fetch('/api/live')).json();
    if (j.online && j.reading) {
      statusText.textContent = `online · ${j.age_s}s`;
      status.className = 'status online';
    } else if (j.reading) {
      statusText.textContent = `stale · ${j.age_s}s`;
      status.className = 'status stale';
    } else {
      statusText.textContent = 'no data yet';
      status.className = 'status offline';
    }
    const d = j.reading || {};
    $('heroVal').textContent = fmt(d.ir_object_c);
    setRing(d.ir_object_c);
    $('sound').textContent = fmt(d.sound_pp, 0);
    $('temp').textContent = fmt(d.temp_c);
    $('humidity').textContent = fmt(d.humidity_pct);
    $('ir_ambient').textContent = fmt(d.ir_ambient_c);
  } catch (e) {
    statusText.textContent = 'disconnected';
    status.className = 'status offline';
  }
}

// ---- wind sparkline ----
const canvas = $('sparkline'), ctx = canvas.getContext('2d');
function drawSpark(values) {
  const w = canvas.width, h = canvas.height, pad = 6;
  ctx.clearRect(0, 0, w, h);
  if (values.length < 2) return;
  const max = Math.max(...values, 1), min = Math.min(...values, 0);
  const span = (max - min) || 1;
  const pt = (v, i) => [
    pad + (i / (values.length - 1)) * (w - 2 * pad),
    h - pad - ((v - min) / span) * (h - 2 * pad),
  ];
  // fill under the line
  ctx.beginPath();
  ctx.moveTo(pad, h - pad);
  values.forEach((v, i) => ctx.lineTo(...pt(v, i)));
  ctx.lineTo(w - pad, h - pad);
  ctx.closePath();
  ctx.fillStyle = 'rgba(118, 214, 192, 0.12)';
  ctx.fill();
  // the line
  ctx.beginPath();
  values.forEach((v, i) => { const [x, y] = pt(v, i); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.strokeStyle = '#76d6c0';
  ctx.lineWidth = 2;
  ctx.stroke();
}
async function pollRecent() {
  try {
    const j = await (await fetch('/api/court/recent?minutes=5')).json();
    drawSpark((j.readings || []).map(x => x.sound_pp).filter(v => v != null && !Number.isNaN(v)));
  } catch (e) { /* ignore */ }
}

// ---- session form ----
const form = $('sessionForm');
const ratingInput = form.querySelector('input[name="subjective_rating_1_10"]');
ratingInput.addEventListener('input', () => { $('ratingVal').textContent = ratingInput.value; });
form.querySelector('input[name="day"]').value = new Date().toISOString().slice(0, 10);

// segmented wind selector -> hidden input
const windSeg = $('windSeg');
const windInput = form.querySelector('input[name="wind_self_report"]');
windSeg.addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  windSeg.querySelectorAll('button').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  windInput.value = b.dataset.v;
});

// geolocation -> hidden lat/lon
$('geoBtn').addEventListener('click', () => {
  const st = $('geoStatus');
  if (!navigator.geolocation) { st.textContent = 'Geolocation not supported on this device.'; return; }
  st.textContent = 'locating…';
  navigator.geolocation.getCurrentPosition(
    pos => {
      const { latitude, longitude, accuracy } = pos.coords;
      form.querySelector('input[name="lat"]').value = latitude.toFixed(6);
      form.querySelector('input[name="lon"]').value = longitude.toFixed(6);
      st.textContent = `📍 ${latitude.toFixed(4)}, ${longitude.toFixed(4)} (±${Math.round(accuracy)} m)`;
    },
    err => { st.textContent = `Location failed: ${err.message}. (Needs HTTPS or localhost.)`; },
    { enableHighAccuracy: true, timeout: 10000 }
  );
});

const INT_FIELDS = ['kills', 'errors', 'sets_won', 'sets_lost', 'wind_self_report'];
const FLOAT_FIELDS = ['subjective_rating_1_10', 'lat', 'lon'];

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = $('formMsg');
  const body = {};
  for (const [k, v] of new FormData(form).entries()) {
    if (v === '') continue;
    body[k] = INT_FIELDS.includes(k) ? parseInt(v, 10)
            : FLOAT_FIELDS.includes(k) ? parseFloat(v)
            : v;
  }
  try {
    const r = await fetch('/api/sessions', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await r.text());
    msg.textContent = 'Saved ✓'; msg.className = 'formmsg ok';
    loadSessions();
  } catch (err) {
    msg.textContent = 'Error: ' + err.message; msg.className = 'formmsg err';
  }
});

async function loadSessions() {
  try {
    const rows = await (await fetch('/api/sessions')).json();
    const ul = $('sessionList');
    if (!rows.length) { ul.innerHTML = '<li><span class="sub">No sessions yet.</span></li>'; return; }
    ul.innerHTML = '';
    rows.forEach(s => {
      const li = document.createElement('li');
      const rate = s.subjective_rating_1_10 != null ? `<span class="rate">${s.subjective_rating_1_10}/10</span>` : '';
      const sub = [s.partner, s.location].filter(Boolean).join(' · ') || '—';
      li.innerHTML = `<span>${s.day}<br><span class="sub">${sub}</span></span>${rate}`;
      ul.appendChild(li);
    });
  } catch (e) { /* ignore */ }
}

pollLive(); pollRecent();
setInterval(pollLive, 1000);
setInterval(pollRecent, 3000);
