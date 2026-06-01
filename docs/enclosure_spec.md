# Courtside Node — Enclosure Spec (for CAD)

A 3D-printed housing for a beach-volleyball courtside sensor node. It mounts on a
camera/phone tripod and holds a microcontroller + 3 environmental sensors + a
WiFi antenna. Used outdoors on sand in direct sun.

---

## Components to enclose

| # | Part | Function | Nominal size (CONFIRM) | Notes for housing |
|---|------|----------|------------------------|-------------------|
| 1 | ESP32-S3 dev board ("Lonely Binary Gold") | brain + WiFi | ~70 × 26 × 6 mm (board); headers add ~10 mm height | USB-C on one short end must be accessible |
| 2 | **DHT11** module (blue) | air temp / humidity | ~22 × 28 mm board, sensor ~12 × 6 mm | blue sensor face must see open air; vented + shaded |
| 3 | MLX90614 IR thermometer (GY-906) | sand surface temp | ~13 × 17 mm board; metal can ~9 mm Ø, ~6 mm tall | **needs an open hole aimed down at sand** |
| 4 | Electret mic module | sound / wind proxy | ~10–15 × 15–33 mm (measure) | needs a port + foam windscreen |
| 5 | External WiFi antenna | range | flexible adhesive strip *or* SMA rod + pigtail | mount on outer/upper wall, away from metal |
| 6 | (Power) USB-C power bank | power | external | NOT enclosed — connects by USB-C cable |

Wiring is currently jumper wires; assume a small protoboard (~50 × 70 mm) or the
breadboard will sit at the bottom of the housing. Leave room + cable slack.

---

## Functional requirements (priority order)

### 1. Tripod mount — MOST IMPORTANT
- The tripod (VIMOSE 66") uses a standard **1/4"-20 UNC** screw (the male stud).
- The housing **base needs a 1/4"-20 female socket** to screw down onto it.
- **Do not print bare threads — they strip.** Use a **brass heat-set threaded
  insert (1/4"-20)** or a captured/recessed 1/4"-20 hex nut in a boss.
- Base should be flat and stable; ~6–8 mm thread engagement depth.

### 2. IR sensor aimed at the sand (MLX90614)
- The IR sensor reads surface temp by *line of sight*. **Plastic blocks IR — there
  must be an OPEN hole in front of it (no window/lens).**
- Because the node sits up on a tripod, the IR must point **down and out toward the
  sand at an angle** (e.g., a port on a lower / angled face).
- Make it **aim-able**: mount the MLX on a small adjustable bracket (tilt) or give
  2–3 alternate mounting positions, so Tristan can point it at the sand patch.
- Standard MLX90614 sees a ~90° cone — keep that cone unobstructed.

### 3. Mic / wind port
- The mic is the node's **only** wind sensor (no anemometer), used as a *qualitative*
  acoustic wind proxy — so the **foam windscreen is important**: it cuts direct-gust
  clipping so the signal tracks turbulence instead of pegging.
- A small **side port with a foam windscreen** (also a sand/spray shield, lets air in).
- A mic is *not* aimed like a directional sensor — wind noise is turbulence over the
  port, so exposure + the foam shield matter more than orientation.
- If adjustability is wanted, mount the mic on a rotatable plug.
- (The proxy is validated in software against self-reported wind + an Open-Meteo
  regional reference, not against an onboard anemometer.)

### 4. Temp/humidity chamber — must be vented + shaded
- A sealed sunlit box reads **falsely hot/dry**. The temp/humidity sensor needs a
  **vented, shaded sub-chamber** (radiation-shield / "Stevenson screen" idea):
  louvered vents on a **shaded** face (e.g., underside), airflow but no direct sun.
- This is why the whole housing should be **light/white** colored.

### 5. WiFi antenna
- Mount on an **outer or upper wall, away from the board and other metal** (metal
  shadows WiFi).
- If **SMA rod**: a ~6.5 mm bulkhead hole for the SMA connector.
- If **flexible adhesive antenna**: a flat exterior patch to stick it + a small
  slot to route the thin coax (U.FL) out from the board.

### 6. USB-C access
- A side cutout (~12 × 8 mm, position TBD by board) aligned with the ESP32's USB-C
  port, for power (power bank) and re-flashing without opening the case.

### 7. Access + assembly
- A **removable lid** (snap-fit or 4 screws) to get at the electronics.
- Internal **screw bosses or a slotted rail** so sensors can be repositioned.
- Cable strain-relief for the antenna coax and USB cable.

---

## Material & environment
- **PETG or ASA**, *not PLA* — PLA sags in beach heat / direct sun. ASA is best for
  UV; PETG is fine and easier to print.
- **Light/white color** — reflects sun, keeps the temp sensor honest.
- Sand-resistant (not waterproof): vents face down, no large top openings.
- Keep it compact but leave ~10–15 mm clearance around the board for cables/heat.

---

## Summary for a quick start
A light-colored vented box that **screws onto a 1/4"-20 tripod stud**, with: an
**open downward-angled hole** for the IR (sand) sensor, a **foam-screened side
port** for the mic, a **louvered shaded vent** for the temp/humidity sensor, an
**antenna mount** on an outer wall, and a **USB-C cutout**. Removable lid, internal
adjustable sensor mounts. Print in PETG/ASA, white.
