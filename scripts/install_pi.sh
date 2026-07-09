#!/bin/bash
# Ranger Dashboard - Raspberry Pi Setup Script
# Run as: sudo bash install_pi.sh
#
# This script:
# 1. Enables SPI for CAN HAT
# 2. Configures SocketCAN overlay
# 3. Installs Python dependencies
# 4. Installs systemd services for auto-start
# 5. Configures Chromium kiosk mode

set -e

DASHBOARD_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DASHBOARD_USER="${SUDO_USER:-pi}"

echo "=== Ranger Dashboard Pi Setup ==="
echo "Dashboard dir: $DASHBOARD_DIR"
echo "User: $DASHBOARD_USER"
echo ""

# 1. System packages
echo "--- Installing system packages ---"
apt-get update
apt-get install -y \
    can-utils \
    chromium-browser \
    unclutter \
    python3-pip \
    python3-venv

# 2. Enable SPI (required for MCP2515/MCP2518FD CAN HATs)
echo "--- Enabling SPI ---"
raspi-config nonint do_spi 0

# 3. Configure CAN HAT overlay in /boot/config.txt
echo "--- Configuring CAN HAT overlay ---"
BOOT_CONFIG="/boot/firmware/config.txt"
if [ ! -f "$BOOT_CONFIG" ]; then
    BOOT_CONFIG="/boot/config.txt"
fi

# Waveshare 2-CH CAN FD HAT (MCP2518FD)
# If using MCP2515 single-channel, replace with:
#   dtoverlay=mcp2515-can0,oscillator=12000000,interrupt=25,spimaxfrequency=2000000
if ! grep -q "mcp251xfd" "$BOOT_CONFIG"; then
    echo "" >> "$BOOT_CONFIG"
    echo "# Ranger Dashboard - CAN HAT" >> "$BOOT_CONFIG"
    echo "dtoverlay=mcp251xfd,spi0-0,oscillator=40000000,interrupt=25" >> "$BOOT_CONFIG"
    echo "# Uncomment for second CAN channel:" >> "$BOOT_CONFIG"
    echo "#dtoverlay=mcp251xfd,spi0-1,oscillator=40000000,interrupt=24" >> "$BOOT_CONFIG"
    echo "CAN overlay added to $BOOT_CONFIG"
else
    echo "CAN overlay already configured"
fi

# 4. Auto-bring-up CAN interface on boot
echo "--- Configuring CAN interface auto-start ---"
cat > /etc/network/interfaces.d/can0 << 'EOF'
auto can0
iface can0 inet manual
    pre-up /sbin/ip link set can0 type can bitrate 500000 restart-ms 100
    up /sbin/ip link set up can0
    down /sbin/ip link set down can0
EOF

# 5. Create Python venv and install dashboard
echo "--- Setting up Python environment ---"
cd "$DASHBOARD_DIR"
sudo -u "$DASHBOARD_USER" python3 -m venv .venv
sudo -u "$DASHBOARD_USER" .venv/bin/pip install --upgrade pip
sudo -u "$DASHBOARD_USER" .venv/bin/pip install -e .

# 6. Update config for real CAN
echo "--- Updating config for Pi ---"
sed -i 's/interface: "virtual"/interface: "can0"/' "$DASHBOARD_DIR/config.yaml"

# 7. Install systemd services
echo "--- Installing systemd services ---"

cat > /etc/systemd/system/ranger-dashboard.service << EOF
[Unit]
Description=Ranger EV Dashboard Backend
After=network.target can0.service
Wants=network.target

[Service]
Type=simple
User=$DASHBOARD_USER
WorkingDirectory=$DASHBOARD_DIR
ExecStart=$DASHBOARD_DIR/.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8088
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/ranger-kiosk.service << EOF
[Unit]
Description=Ranger EV Dashboard Kiosk
After=graphical.target ranger-dashboard.service
Wants=ranger-dashboard.service

[Service]
Type=simple
User=$DASHBOARD_USER
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/$DASHBOARD_USER/.Xauthority
ExecStartPre=/bin/sleep 5
ExecStart=$DASHBOARD_DIR/scripts/kiosk.sh
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
EOF

# 8. Enable services
systemctl daemon-reload
systemctl enable ranger-dashboard.service
systemctl enable ranger-kiosk.service

# 9. Disable screen blanking
echo "--- Disabling screen blanking ---"
mkdir -p /etc/xdg/lxsession/LXDE-pi
cat > /etc/xdg/lxsession/LXDE-pi/autostart << 'EOF'
@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
@xset s off
@xset -dpms
@xset s noblank
EOF

# 10. Configure for fast boot
echo "--- Optimizing boot time ---"
# Disable splash screen for faster boot
if ! grep -q "disable_splash=1" "$BOOT_CONFIG"; then
    echo "disable_splash=1" >> "$BOOT_CONFIG"
fi

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit $DASHBOARD_DIR/config.yaml:"
echo "     - Set comma.host to your comma 4's IP address"
echo "     - Verify can.interface is 'can0'"
echo "  2. Reboot: sudo reboot"
echo "  3. Dashboard will auto-start on boot at http://localhost:8088"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status ranger-dashboard  # Check backend status"
echo "  sudo systemctl status ranger-kiosk      # Check kiosk status"
echo "  sudo journalctl -u ranger-dashboard -f  # View backend logs"
echo "  candump can0                            # View raw CAN traffic"
echo ""
