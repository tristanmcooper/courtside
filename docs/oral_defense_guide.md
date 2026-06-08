# Courtside — Oral Defense Study Guide

Everything you need to explain and defend the project. Read top-to-bottom once,
then drill the **Q&A** section.

---

## 1. The 30-second pitch
> "Beach volleyball performance varies a lot day to day, and no single tool
> explains why — wearables only see overnight recovery, weather apps miss the
> court's microclimate, and you can't fill out surveys mid-match. **Courtside** is
> a multi-modal instrument I built and deployed that fuses four streams — a custom
> courtside sensor node, wearable recovery data, regional weather, and my own
> session ratings — into one per-session table, then runs a factor-ranking
> analysis to surface *what likely explained how I played*. It's a working,
> deployed system validated on a small personal pilot; I'm honest that the sample
> is too small for statistical claims yet."

**The one-line product promise:** *"How did I play, what were the conditions, how
was my body, and what probably mattered?"*

---

## 2. Problem → Gap → Contribution
- **Problem:** recovery, environment, and mindset interact, but existing tools each
  measure one dimension alone.
- **Three blind spots:** wearables ignore same-day environment/subjective state;
  weather apps are city-grid (miss court microclimate — wind reshaped by terrain,
  sand temp driven by sun/grain/moisture); in-match self-report is impractical.
- **Gap:** no system *fuses* recovery + environment + subjective state + performance
  for an individual beach athlete.
- **Contribution:** a working multi-modal **instrument + pipeline** (not a
  finished study) that does this fusion at low cost, plus a needs survey (N=20)
  that validated the design. Methods generalize to other heat-exposed, individually-
  variable settings.

---

## 3. Architecture — be able to draw this
```
[ESP32-S3 node]  --WiFi(hotspot)-->  [Cloud backend: FastAPI + PostgreSQL on Render]
  DHT11 (air T/RH)                         |   ^                         ^
  MLX90614 (sand IR)                       |   |                         |
  electret mic (wind/audio)                v   |                         |
                                   [mobile web app]              [Apple Watch]
                                   live view / record / log     via Health Auto Export
                                                                 [Oura API] [Open-Meteo]
                                            |
                                            v
                          [build_features.py] -> per-session feature table
                                            |
                                            v
                          [analysis.py: 4-stage] -> factor_rankings
```
**Data flow in words:** node samples at 1 Hz → POSTs JSON to the cloud → you open
the app on your phone to see live readings and **record** a session (start/stop
bookmarks the sensor window) → after playing you **log** the rating/outcomes →
Apple Watch + Oura + weather attach by date/time → the pipeline builds one row per
session and ranks factors.

---

## 4. Components & the "why" behind each
**Node (ESP32-S3 + DHT11 + MLX90614 + mic).**
- *DHT11* = air temp + humidity (one-wire, GPIO2). *MLX90614* = **non-contact IR
  thermometer** reading **sand surface** temp (I²C, addr 0x5A) — measures emitted
  infrared, no contact needed. *Mic* = peak-to-peak amplitude as a cheap wind/audio
  proxy (GPIO4, an ADC1 pin so it works with WiFi on).
- *Why ESP32-S3:* cheap, WiFi built-in, enough ADC/I²C. *Why hotspot→cloud:* the
  beach has no WiFi and you didn't want a laptop in the sun, so the node joins your
  iPhone Personal Hotspot and posts to a fixed cloud URL.

**Cloud backend (FastAPI + PostgreSQL, Render).**
- One service ingests node + wearable data and serves the app. Postgres persists
  data; SQLite is used locally. *Why cloud:* fixed URL reachable from any beach with
  cell signal; no laptop dependency; same endpoint serves the node, the watch, and
  the dashboard.

**App (mobile web).** Live setup view (per-sensor plots + a heuristic setup-check),
**recording** (start/stop → captures the session's sensor time-series), and an
**evaluation** form (self-rating, peer/coach, felt-wind, kills/errors, notes, GPS).

**Wearables.** Apple Watch auto-syncs via **Health Auto Export** (HRV, resting HR,
sleep, respiratory rate, workouts). Oura via API as a **second** recovery source.
*Why both:* Apple HRV is **SDNN**, Oura is **RMSSD** — two independent estimates →
cross-validation. Workouts give **in-session HR/intensity** + **prior-7-day load**.

**Weather (Open-Meteo).** Coarse (~1–3 km grid) regional reference, kept *separate*
from on-court sensors. *Why:* lets you show the node captures microclimate the
regional model can't — which is the whole thesis.

---

## 5. The ML pipeline (4 stages) — explain each
Outcome = subjective 1–10 self-rating (primary). For each candidate feature:
1. **Correlation screen** — Pearson (linear) + Spearman (rank/monotonic) of each
   feature vs the rating. Cheap, first look.
2. **Sparse linear selection** — **Lasso** (L1-penalized regression) with
   **leave-one-out CV** to pick the penalty. Lasso zeroes out weak features →
   sparse, appropriate for small N. LOOCV because every data point counts when N is tiny.
3. **Nonlinear importance** — **Random Forest + Gradient Boosting** feature
   importances to catch interactions a linear model misses.
4. **SHAP** — Shapley values from the gradient-boosting model: a game-theory method
   attributing each prediction to each feature → per-factor importance + direction.
- Plus **leave-one-session-out stability**: refit dropping each session, see if the
  top-3 factors stay stable. **No p-values as confirmatory. No deployed model.**

---

## 6. The data you actually have (pilot)
- First instrumented beach day: **2 recorded sessions**, ~1,380 and ~2,255 one-Hz
  samples, **sand 40–43 °C vs air ~26 °C** (the microclimate gap, live).
- Apple Watch recovery (HRV/RHR) auto-arrived for the window.
- Survey: **N=20** players; **wind ranked #1** (4.05/5); 85% interested.

---

## 7. Key design decisions & trade-offs (examiners love these)
| Decision | Why | Honest trade-off |
|---|---|---|
| DHT11 (not BME280) | what I had working reliably | low-res (±2°C/±5%RH), no pressure |
| Acoustic mic as wind proxy | cheap, no extra hardware | qualitative only, not a calibrated anemometer |
| Cloud (not SD card / laptop) | no laptop in sun; fixed URL anywhere | depends on cell signal; free-tier cold starts |
| Apple Watch via Health Auto Export | automated, no iOS dev | runs only when phone unlocked |
| Subjective rating = primary outcome | reliable, low-burden, valid in sport psych | subjective |
| Kills/errors = secondary | objective | **confounded by partner & opponent in 2v2** |
| Oura + Apple both | cross-validate HRV (RMSSD vs SDNN) | two devices |

---

## 8. Limitations (lead with these — it's a strength to be honest)
1. **Small N is the dominant limitation.** A factor ranking on ~2–4 sessions is not
   statistically interpretable (a 4-point correlation can exceed 0.8 by chance).
   Everything is framed descriptively; the pipeline reports its own instability.
2. **Ground truth:** kills/errors are partner/opponent-confounded → added optional
   **peer/coach ratings** as better external truth; per-own-contact stats = future.
3. **Sensor fidelity:** DHT11 low-res; mic uncalibrated; weather coarse (by design).
4. **Scope cuts:** voice EMA and CV kill/error extraction were de-scoped to keep the
   core instrument robust.

---

## 9. Validation / evaluation (what you CAN claim)
- **Sensor responsiveness (bench):** breath → coupled temp/humidity spike; blow →
  mic transient; IR jumps ~10 °C aimed at skin.
- **End-to-end pipeline runs** on real pilot data → 42-column fused table.
- **Need validation:** N=20 survey shaped the feature set.
- Evaluation *criteria* (data completeness, time alignment, ranking stability, face
  validity) are defined; stability/face-validity need ≥15 sessions to be meaningful.

---

## 10. Anticipated questions + crisp answers
**Q: With N so small, what can you actually conclude?**
A: Nothing statistically — and I say so. The deliverable is the working instrument
and pipeline; the factor ranking is its *output format*, shown to demonstrate the
analysis runs and self-reports instability. Real conclusions need ~15+ sessions,
which the system now collects at near-zero marginal effort.

**Q: Kills/errors depend on your partner — how is that a valid outcome?**
A: Correct, that's why the **subjective 1–10 is the primary outcome** and kills/
errors are secondary/exploratory. I added **peer and coach ratings** as
less-confounded external ground truth, and splitting stats by my own contacts is
future work. (This is exactly the TA's feedback, addressed.)

**Q: Your mic isn't an anemometer — is the wind data meaningful?**
A: It's a *qualitative* wind/audio proxy, not calibrated wind speed. I validate it
two ways: against my **felt-wind** rating and against **Open-Meteo** regional wind.
A true anemometer is the obvious hardware upgrade.

**Q: Why measure sand temp — isn't air temp enough?**
A: No — surface temp diverged from air by ~15 °C in the pilot (40 vs 26). Sand temp
drives foot comfort, push-off, and heat load, and weather/air data can't see it.
It's the novel, hard-to-get signal.

**Q: SHAP/Lasso on 4 points — isn't that overfitting?**
A: Yes, which is why it's labeled exploratory and paired with leave-one-out
stability. The methods are the *pipeline*; they become valid at higher N.

**Q: How do you align streams in time?**
A: Sensor rows carry server-receive timestamps; a session has an explicit
start/stop recording window; wearable data joins by date; workouts by time overlap.

**Q: Apple SDNN vs Oura RMSSD — why both / are they comparable?**
A: Both estimate HRV but with different math (SDNN = SD of all RR intervals; RMSSD =
short-term beat-to-beat). They're correlated but not identical — having both lets me
cross-check and fill gaps; I never average them blindly.

**Q: How is missing data handled?**
A: Pipeline imputes feature means for models, drops all-NaN/constant features, and
skips model stages entirely below the sample threshold.

**Q: Privacy / why a web app, not native?**
A: Health data lives in a private repo + private backend; secrets are gitignored. A
web app avoids the App Store and works cross-device; native HealthKit would need an
iOS app I didn't have time/justification to build.

**Q: What's novel vs just using Oura?**
A: Oura tells you your recovery. It can't tell you the sand was 43 °C, the wind was
gusting, and you still rated the session a 7. The fusion + court microclimate is new.

---

## 11. Glossary (say these confidently)
- **HRV / SDNN / RMSSD** — heart-rate variability; SDNN = std-dev of RR intervals
  (Apple), RMSSD = root-mean-square of successive differences (Oura). Higher ≈ more
  recovered/parasympathetic.
- **MLX90614** — non-contact IR thermometer; reads surface temp from emitted infrared.
- **Lasso** — linear regression with L1 penalty; shrinks weak coefficients to zero.
- **LOOCV** — leave-one-out cross-validation; train on N−1, test on 1, repeat.
- **Random Forest / Gradient Boosting** — tree ensembles; capture nonlinear
  interactions; report feature importances.
- **SHAP** — Shapley additive explanations; per-feature contribution to a prediction.
- **Peak-to-peak** — max minus min of the mic signal in a 50 ms window (amplitude).
- **WBGT** — wet-bulb globe temperature; standard heat-stress index in sport.
- **EMA** — ecological momentary assessment (in-the-moment self-report).
