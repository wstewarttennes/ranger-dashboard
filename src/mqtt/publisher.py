"""Publish vehicle state to Home Assistant over MQTT.

Design goals:
- **Last-known survives offline.** State is published *retained*, and the data
  sensors carry NO availability topic, so HA keeps showing the last reading
  (SoC, charge, temps) even after the Pi/truck powers off. A separate
  `binary_sensor.ranger_online` (driven by the MQTT last-will) tells you whether
  it's live, and `sensor.ranger_last_seen` gives an "as of" timestamp.
- **Zero HA config.** Entities are created via MQTT discovery on connect.

paho-mqtt runs its own network thread (loop_start); `publish()` is thread-safe,
so we call it straight from the asyncio publish loop.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

# key in VehicleState.to_dict()  ->  (Friendly name, unit, device_class, state_class, icon)
SENSORS: list[tuple[str, str, str | None, str | None, str | None, str | None]] = [
    ("soc_pct",          "Battery",        "%",   "battery",     "measurement", None),
    ("dc_bus_voltage",   "Bus Voltage",    "V",   "voltage",     "measurement", None),
    ("dc_bus_current",   "Bus Current",    "A",   "current",     "measurement", None),
    ("pack_voltage",     "Pack Voltage",   "V",   "voltage",     "measurement", None),
    ("pack_current",     "Pack Current",   "A",   "current",     "measurement", None),
    ("power_kw",         "Power",          "kW",  None,          "measurement", "mdi:flash"),
    ("pack_temperature", "Pack Temp",      "°C",  "temperature", "measurement", None),
    ("motor_temp_c",     "Motor Temp",     "°C",  "temperature", "measurement", None),
    ("inverter_temp_c",  "Inverter Temp",  "°C",  "temperature", "measurement", None),
    ("charger_temp_c",   "Charger Temp",   "°C",  "temperature", "measurement", None),
    ("charge_watts",     "Charge Power",   "W",   "power",       "measurement", None),
    ("charge_current",   "Charge Current", "A",   "current",     "measurement", None),
    ("cell_delta_mv",    "Cell Delta",     "mV",  None,          "measurement", "mdi:scale-balance"),
    ("min_cell_v",       "Min Cell",       "V",   "voltage",     "measurement", None),
    ("max_cell_v",       "Max Cell",       "V",   "voltage",     "measurement", None),
    ("speed_mph",        "Speed",          "mph", "speed",       "measurement", "mdi:speedometer"),
    ("motor_rpm",        "Motor RPM",      "rpm", None,          "measurement", "mdi:engine"),
    ("throttle_pct",     "Throttle",       "%",   None,          "measurement", "mdi:gauge"),
    ("gear",             "Gear",           None,  None,          None,          "mdi:car-shift-pattern"),
    ("fault_level_str",  "Fault Level",    None,  None,          None,          "mdi:alert-circle-outline"),
    ("key_switch_voltage","12V Supply",    "V",   "voltage",     "measurement", "mdi:car-battery"),
    # Deep diagnostics (already present in to_dict(); exposed for full HA history)
    ("charge_voltage",         "Charge Voltage",    "V", "voltage", "measurement", None),
    ("motor_current",          "Motor Current",     "A", "current", "measurement", None),
    ("motor_torque_pct",       "Motor Torque",      "%", None,      "measurement", "mdi:cog-outline"),
    ("fault_code",             "Fault Code",        None, None,     "measurement", "mdi:alert"),
    ("charge_voltage_limit",   "Charge V Limit",    "V", "voltage", "measurement", None),
    ("charge_current_limit",   "Charge A Limit",    "A", "current", "measurement", None),
    ("discharge_current_limit","Discharge A Limit", "A", "current", "measurement", None),
    ("discharge_voltage_limit","Discharge V Limit", "V", "voltage", "measurement", None),
    ("bms_fault_flags",        "BMS Fault Flags",   None, None,     "measurement", "mdi:flag-remove-outline"),
    ("bms_status_flags",       "BMS Status Flags",  None, None,     "measurement", "mdi:flag-outline"),
    ("system_flags_raw",       "System Flags",      None, None,     "measurement", "mdi:flag-triangle"),
    ("openpilot_state",        "openpilot",         None, None,     None,          "mdi:steering"),
    # Trip / energy telemetry (flattened into the payload by the publish loop)
    ("trip_miles",         "Trip Distance",     "mi",     "distance", "measurement", "mdi:map-marker-distance"),
    ("trip_kwh",           "Trip Energy",       "kWh",    "energy",   "measurement", None),
    ("trip_efficiency",    "Trip Efficiency",   "mi/kWh", None,       "measurement", "mdi:leaf"),
    ("since_charge_miles", "Since Charge Dist", "mi",     "distance", "measurement", "mdi:map-marker-distance"),
    ("since_charge_kwh",   "Since Charge Energy","kWh",   "energy",   "measurement", None),
    ("charge_session_kwh", "Charge Session",    "kWh",    "energy",   "measurement", "mdi:ev-station"),
    # X1 life/odometer (configurable TPDOs 0x482/0x483 — 0 until mapped in SmartView)
    ("odometer_mi",        "Odometer",          "mi",     "distance", "total_increasing", "mdi:counter"),
    ("key_on_hours",       "Key-On Hours",      "h",      "duration", "total_increasing", "mdi:clock-outline"),
    ("service_hours",      "Time To Service",   "h",      "duration", "measurement", "mdi:wrench-clock"),
    ("motor_op_hours",     "Motor Hours",       "h",      "duration", "total_increasing", "mdi:engine-outline"),
    # Motor / node internals + secondary flags (completeness)
    ("motor_iq",           "Motor Iq Current",  "A",   "current", "measurement", None),
    ("node_dc_current",    "Node DC Current",   "A",   "current", "measurement", None),
    ("motor_speed_ref",    "Motor Speed Ref",   "rpm", None,      "measurement", "mdi:speedometer-medium"),
    ("motor_flags",        "Motor Flags",       None,  None,      "measurement", "mdi:flag-outline"),
    ("fault_level",        "Fault Level Num",   None,  None,      "measurement", "mdi:numeric"),
    ("bms_fault_flags_2",  "BMS Fault Flags 2", None,  None,      "measurement", "mdi:flag-remove-outline"),
    ("bms_status_flags_2", "BMS Status Flags 2",None,  None,      "measurement", "mdi:flag-outline"),
]

# key -> (Friendly name, device_class, icon)
BINARY_SENSORS: list[tuple[str, str, str | None, str | None]] = [
    ("charging",         "Charging",         "battery_charging", "mdi:ev-station"),
    ("vehicle_running",  "Running",          "power",            "mdi:power"),
    ("park_brake",       "Park Brake",       None,               "mdi:car-brake-parking"),
    # Alerting flags — wire HA automations to these for phone notifications
    ("has_fault",        "Fault Active",     "problem",          "mdi:alert-circle"),
    ("key_undervoltage", "Key Undervoltage", "problem",          "mdi:car-battery"),
    ("overtemp",         "Overtemp",         "problem",          "mdi:thermometer-alert"),
    # State flags
    ("precharging",      "Precharging",      None,               "mdi:flash-alert"),
    ("traction_enabled", "Traction Enabled", "running",          "mdi:car-traction-control"),
    ("comma_connected",  "comma Connected",  "connectivity",     "mdi:radio-tower"),
    ("openpilot_enabled","openpilot Engaged",None,               "mdi:steering"),
    ("key_voltage_live", "Key Voltage Live", "power",            "mdi:car-battery"),
]

# Tidy entity_id slugs where the raw json key is verbose. entity_id becomes
# sensor.ranger_<slug>; the value_template still reads the real json key.
SLUG_OVERRIDES = {
    "min_cell_v": "min_cell",
    "max_cell_v": "max_cell",
    "cell_delta_mv": "cell_delta",
    "speed_mph": "speed",
    "throttle_pct": "throttle",
    "vehicle_running": "running",
}


def _slug(key: str) -> str:
    return SLUG_OVERRIDES.get(key, key)


class MqttPublisher:
    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: str = "",
        password: str = "",
        base_topic: str = "ranger",
        discovery_prefix: str = "homeassistant",
        device_name: str = "Ranger EV",
        client_id: str = "ranger-dashboard",
    ):
        self.host = host
        self.port = port
        self.base_topic = base_topic.rstrip("/")
        self.discovery_prefix = discovery_prefix.rstrip("/")
        self.device_name = device_name
        self.state_topic = f"{self.base_topic}/state"
        self.avail_topic = f"{self.base_topic}/availability"

        # paho-mqtt < 2 callback API (classic on_connect signature)
        self._client = mqtt.Client(client_id=client_id, clean_session=True)
        if username:
            self._client.username_pw_set(username, password)
        # Last will: broker marks us offline (retained) if we drop.
        self._client.will_set(self.avail_topic, "offline", qos=1, retain=True)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    # ---- lifecycle ----
    def start(self) -> None:
        logger.info("MQTT connecting to %s:%s", self.host, self.port)
        self._client.connect_async(self.host, self.port, keepalive=30)
        self._client.loop_start()

    def stop(self) -> None:
        try:
            self._client.publish(self.avail_topic, "offline", qos=1, retain=True)
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:  # pragma: no cover - best effort on shutdown
            logger.debug("MQTT stop error", exc_info=True)

    # ---- callbacks ----
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("MQTT connected — publishing discovery")
            self._publish_discovery()
            client.publish(self.avail_topic, "online", qos=1, retain=True)
        else:
            logger.error("MQTT connect failed (rc=%s)", rc)

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            logger.warning("MQTT unexpectedly disconnected (rc=%s); auto-reconnecting", rc)

    # ---- discovery ----
    def _device(self) -> dict:
        return {
            "identifiers": ["ranger_ev"],
            "name": self.device_name,
            "manufacturer": "Ford",
            "model": "Ranger EV conversion",
        }

    def _publish_discovery(self) -> None:
        dev = self._device()

        def cfg(component: str, uid: str, payload: dict) -> None:
            topic = f"{self.discovery_prefix}/{component}/{uid}/config"
            payload.update({"unique_id": uid, "object_id": uid, "device": dev})
            self._client.publish(topic, json.dumps(payload), qos=1, retain=True)

        # numeric / text sensors — NO availability topic, so last value persists offline
        for key, name, unit, dclass, sclass, icon in SENSORS:
            p: dict = {
                "name": name,
                "state_topic": self.state_topic,
                "value_template": "{{ value_json.%s }}" % key,
            }
            if unit:
                p["unit_of_measurement"] = unit
            if dclass:
                p["device_class"] = dclass
            if sclass:
                p["state_class"] = sclass
            if icon:
                p["icon"] = icon
            cfg("sensor", f"ranger_{_slug(key)}", p)

        # binary sensors from booleans in the state json
        for key, name, dclass, icon in BINARY_SENSORS:
            p = {
                "name": name,
                "state_topic": self.state_topic,
                "value_template": "{{ 'ON' if value_json.%s else 'OFF' }}" % key,
                "payload_on": "ON",
                "payload_off": "OFF",
            }
            if dclass:
                p["device_class"] = dclass
            if icon:
                p["icon"] = icon
            cfg("binary_sensor", f"ranger_{_slug(key)}", p)

        # connectivity — this one DOES use the availability topic (LWT)
        cfg("binary_sensor", "ranger_online", {
            "name": "Online",
            "state_topic": self.avail_topic,
            "payload_on": "online",
            "payload_off": "offline",
            "device_class": "connectivity",
        })

        # last-seen timestamp (from the augmented state payload)
        cfg("sensor", "ranger_last_seen", {
            "name": "Last Seen",
            "state_topic": self.state_topic,
            "value_template": "{{ value_json.last_seen }}",
            "device_class": "timestamp",
            "icon": "mdi:clock-outline",
        })

    # ---- state ----
    def publish(self, state: dict) -> None:
        """Publish the vehicle state (retained) with an ISO 'last_seen' stamp."""
        payload = {**state, "last_seen": datetime.now(timezone.utc).isoformat()}
        self._client.publish(self.state_topic, json.dumps(payload), qos=0, retain=True)
