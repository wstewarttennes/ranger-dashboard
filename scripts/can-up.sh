#!/usr/bin/env bash
# Bring up both Ranger CAN interfaces at their bus bitrates.
# Run on the Pi HOST (not in the container): sudo bash scripts/can-up.sh
#
# Because the dashboard container runs with network_mode: host, whatever we
# bring up here is immediately visible inside the container.
#
# Override bitrates via env if needed, e.g.:
#   CAN1_BITRATE=250000 sudo -E bash scripts/can-up.sh
set -euo pipefail

CAN0_BITRATE="${CAN0_BITRATE:-250000}"   # Thunderstruck battery/charge bus (MCU + TSM2500)
CAN1_BITRATE="${CAN1_BITRATE:-500000}"   # X1 / Hyper9 motor bus — VERIFY baud in SmartView

bring_up() {
  local iface="$1" br="$2"
  if ! ip link show "$iface" >/dev/null 2>&1; then
    echo "!! $iface does not exist (check CAN HAT overlays in /boot/firmware/config.txt)"
    return 1
  fi
  ip link set "$iface" down 2>/dev/null || true
  ip link set "$iface" type can bitrate "$br" restart-ms 100
  ip link set "$iface" up
  echo "   $iface up @ ${br} bps"
}

echo "Bringing up CAN interfaces..."
bring_up can0 "$CAN0_BITRATE" || true
bring_up can1 "$CAN1_BITRATE" || true
echo
ip -brief -details link show | grep -A0 can || true
echo
echo "Test each bus (Ctrl-C to stop):"
echo "  candump can0     # expect Thunderstruck 0x351-0x35B (battery)"
echo "  candump can1     # expect Hyper9 0x181-0x184 (motor)"
