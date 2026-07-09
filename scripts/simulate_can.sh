#!/bin/bash
# Set up virtual CAN interface for desktop testing (Linux only)
# Usage: sudo bash simulate_can.sh

set -e

echo "Setting up virtual CAN interface..."
modprobe vcan
ip link add dev vcan0 type vcan 2>/dev/null || true
ip link set up vcan0

echo "vcan0 is up. Starting CAN simulator..."
echo "Press Ctrl+C to stop."
echo ""

cd "$(dirname "$0")/.."
python -m src.can.simulator --interface vcan0
