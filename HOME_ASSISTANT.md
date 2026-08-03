# Ranger → Home Assistant (MQTT)

The dashboard publishes live vehicle state to Home Assistant over MQTT, so the
Ranger shows up on the HA dashboard (SoC, charging, power, temps, cells, drive
state). State is published **retained**, so HA keeps showing the **last-known**
reading even after the truck powers off; `binary_sensor.ranger_online` tracks
whether it's live and `sensor.ranger_last_seen` gives the "as of" time.

## How it works
- `src/mqtt/publisher.py` connects to the HA Mosquitto broker, publishes MQTT
  **discovery** configs (entities auto-create under a "Ranger EV" device), then
  pushes `VehicleState.to_dict()` to `ranger/state` at `mqtt.publish_rate` Hz
  (retained). Last-will sets `ranger/availability` = offline on disconnect.
- Config lives under `mqtt:` in `config.yaml`. The **password** comes from the
  `RANGER_MQTT_PASSWORD` env var (kept out of git via `.env`).

## One-time setup
1. **HA broker login** — Settings → Add-ons → *Mosquitto broker* → Configuration,
   add under `logins:`
   ```yaml
   logins:
     - username: ranger
       password: <pick-a-password>
   ```
   Save → **Restart** the add-on. (The MQTT integration is already configured.)
2. **Pi secret** — on the Pi, in the dashboard dir:
   ```bash
   cp .env.example .env
   # edit .env: RANGER_MQTT_PASSWORD=<same password>
   ```

## Deploy
From the Mac (truck on / Pi reachable):
```bash
./deploy.sh                 # rsync + rebuild + restart (keeps .env)
# or on the Pi directly:
cd ranger-dashboard && docker compose -f docker-compose.pi.yml up --build -d
```

## Verify
- Pi logs: `docker compose -f docker-compose.pi.yml logs -f` → "MQTT connected — publishing discovery".
- HA → Settings → Devices → **Ranger EV** appears with ~23 entities.
- HA dashboard "Home" → the **Ranger** tile populates; tap it for the full popup.

## Entities (prefix `sensor.ranger_` / `binary_sensor.ranger_`)
soc_pct, power_kw, pack_voltage, pack_current, pack_temperature, motor_temp_c,
inverter_temp_c, charger_temp_c, charge_watts, charge_current, min_cell, max_cell,
cell_delta, speed, motor_rpm, throttle, gear, fault_level_str, last_seen ·
binary: charging, running, park_brake, online

## Offline history backfill (HA long-term statistics)

Live MQTT only reaches HA on home wifi — drives with no wifi leave a gap, and HA
won't accept back-dated *state* over MQTT (it stamps everything with receive
time). So we buffer locally and backfill via the recorder's statistics import.

**How it works** (`src/state/history_db.py` + `src/ha/stats_sync.py`):
- Every 10 s the dashboard appends a full-resolution sample to `data/history.db`
  (SQLite, WAL). This runs off the CAN loop — **no wifi needed** — and never
  rolls off (unlike the ~24 h `history.json` that backs the live Graphs view).
- A background task aggregates complete hours to mean/min/max and pushes them via
  the `recorder/import_statistics` websocket command as **external statistics**
  (`ranger:soc`, `ranger:power_kw`, …, ~18 metrics). It runs every 10 min and on
  startup, is **idempotent**, and only advances a high-water mark on success — so
  a drive logged offline is backfilled, correctly time-stamped, once you're home.
- External stats don't collide with the live `sensor.ranger_*` MQTT entities;
  they appear in the **Statistics** graph card and the **Energy dashboard**.

**One-time setup**
1. **HA token** — HA → your profile → **Security** → *Long-lived access tokens* →
   **Create token** ("ranger-pi"). Copy it (shown once).
2. **Pi secret** — on the Pi, in `/home/weston/dashboard/.env`, add:
   ```bash
   RANGER_HA_TOKEN=<paste the long-lived token>
   ```
3. Restart: `docker compose -f docker-compose.pi.yml up -d` (no rebuild needed —
   `.env` is read at container start).

Config lives under `ha_stats:` in `config.yaml` (url, sync interval, retention).
Set `retention_days` > 0 to prune the SQLite log; `0` keeps it forever.

**Verify** — Pi logs show `HA stats backfill enabled -> http://192.168.1.153:8123`
then `HA stats: synced ~N h across M metrics`. In HA → Developer Tools →
Statistics, search `ranger:` — the metrics appear and can be added to a History/
Statistics card.

## Notes
- **Away connectivity:** the broker is `192.168.1.153:1883` (LAN). The Pi reaches
  it on home wifi. Driving on cellular won't reach it unless HA is exposed over
  Tailscale/VPN — fine for a home dashboard (retained last value persists).
- **Live-while-parked** SoC needs the Pi on standby power on the CAN bus with the
  truck off; otherwise you get last-known + charging-session updates.
