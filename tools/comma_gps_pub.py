#!/usr/bin/env python3
"""Ranger — comma-side GPS speed pusher.

Reads the comma's GPS (`gpsLocationExternal.speed`, gear-independent) and POSTs
it to the Ranger dashboard's `/api/gps` a couple times a second. The dashboard
prefers this over its rpm-derived speed, which is only correct in ONE gear on
the manual gearbox (see config.yaml `rpm_to_kmh`).

Run on the comma with openpilot's python env:
    PYTHONPATH=/data/openpilot /usr/local/venv/bin/python tools/comma_gps_pub.py

Target dashboard URL via env RANGER_DASH_URL
(default http://ranger.local:8088/api/gps — set to the Pi's IP if mDNS doesn't
resolve on the comma; a DHCP reservation for the Pi makes this stable).
"""
import json
import os
import time
import urllib.request

import cereal.messaging as messaging

DASH_URL = os.environ.get("RANGER_DASH_URL", "http://ranger.local:8088/api/gps")


def main() -> None:
    sm = messaging.SubMaster(["gpsLocationExternal"])
    while True:
        sm.update(1000)
        if sm.updated["gpsLocationExternal"]:
            g = sm["gpsLocationExternal"]
            body = json.dumps({"speed_ms": float(g.speed), "fix": bool(g.hasFix)}).encode()
            req = urllib.request.Request(
                DASH_URL, data=body, headers={"Content-Type": "application/json"}
            )
            try:
                urllib.request.urlopen(req, timeout=2)
            except Exception:
                pass  # dashboard may be unreachable (out of wifi range) — keep going
        time.sleep(0.5)


if __name__ == "__main__":
    main()
