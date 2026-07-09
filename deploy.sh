#!/bin/bash
# Ranger Dashboard - Deploy to Pi
#
# Usage:
#   ./deploy.sh              # Deploy using hostname 'ranger' (default)
#   ./deploy.sh pi@10.0.0.5  # Deploy to specific host
#   ./deploy.sh pi@ranger    # Deploy using custom hostname
#
# First-time setup on Pi:
#   1. Flash Raspberry Pi OS Desktop (64-bit) with Raspberry Pi Imager
#   2. Enable SSH, set WiFi in Imager settings
#   3. Boot the Pi, then run: ./deploy.sh
#   The script handles Docker install, dashboard setup, and auto-start.

set -e

PI_HOST="${1:-weston@ranger}"
REMOTE_DIR="/home/weston/dashboard"
SSH_OPTS="-i ~/.ssh/id_ed25519"
export RSYNC_RSH="ssh $SSH_OPTS"

echo "=== Ranger Dashboard Deploy ==="
echo "Target: $PI_HOST"
echo "Remote dir: $REMOTE_DIR"
echo ""

# 1. Check SSH connectivity
echo "--- Checking SSH connection ---"
if ! ssh $SSH_OPTS -o ConnectTimeout=5 "$PI_HOST" "echo 'connected'" 2>/dev/null; then
    echo "ERROR: Cannot SSH to $PI_HOST"
    echo "Make sure the Pi is on and SSH is enabled."
    echo "Try: ssh $PI_HOST"
    exit 1
fi
echo "SSH OK"

# 2. Install Docker on Pi if not present
echo "--- Checking Docker on Pi ---"
ssh $SSH_OPTS "$PI_HOST" "command -v docker" >/dev/null 2>&1 || {
    echo "Installing Docker on Pi..."
    ssh $SSH_OPTS "$PI_HOST" "curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker \$USER"
    echo "Docker installed. You may need to log out/in on the Pi, then re-run this script."
    echo "Run: ssh $PI_HOST 'logout' then ./deploy.sh"
    exit 0
}
echo "Docker OK"

# 3. Sync dashboard files to Pi
echo "--- Syncing files to Pi ---"
rsync -avz --delete \
    --exclude '.pytest_cache' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    --exclude 'ranger_dashboard.egg-info' \
    --exclude '.venv' \
    --exclude 'node_modules' \
    "$(dirname "$0")/" \
    "$PI_HOST:$REMOTE_DIR/"
echo "Files synced"

# 4. Make sure config is set for real CAN
echo "--- Updating config for Pi ---"
ssh $SSH_OPTS "$PI_HOST" "sed -i 's/interface: \"virtual\"/interface: \"can0\"/' $REMOTE_DIR/config.yaml"

# 5. Set up CAN interface (if not already configured)
echo "--- Configuring CAN interface ---"
ssh $SSH_OPTS "$PI_HOST" "sudo bash -c '
    # Enable SPI
    raspi-config nonint do_spi 0 2>/dev/null || true

    # Add CAN HAT overlay if not present
    BOOT_CONFIG=\"/boot/firmware/config.txt\"
    [ ! -f \"\$BOOT_CONFIG\" ] && BOOT_CONFIG=\"/boot/config.txt\"
    if ! grep -q \"mcp251xfd\" \"\$BOOT_CONFIG\" 2>/dev/null; then
        echo \"\" >> \"\$BOOT_CONFIG\"
        echo \"# Ranger Dashboard - CAN HAT\" >> \"\$BOOT_CONFIG\"
        echo \"dtoverlay=mcp251xfd,spi0-0,oscillator=40000000,interrupt=25\" >> \"\$BOOT_CONFIG\"
        echo \"CAN overlay added\"
    fi

    # Auto-bring-up CAN on boot
    cat > /etc/network/interfaces.d/can0 << CANEOF
auto can0
iface can0 inet manual
    pre-up /sbin/ip link set can0 type can bitrate 500000 restart-ms 100
    up /sbin/ip link set up can0
    down /sbin/ip link set down can0
CANEOF
'"

# 6. Build and start the dashboard
echo "--- Building and starting dashboard ---"
ssh $SSH_OPTS "$PI_HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.pi.yml up --build -d"

# 7. Set up kiosk auto-start (Chromium opens dashboard on boot)
echo "--- Configuring kiosk auto-start ---"
ssh $SSH_OPTS "$PI_HOST" "
    mkdir -p ~/.config/autostart
    cat > ~/.config/autostart/dashboard-kiosk.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=Ranger Dashboard
Exec=bash -c \"sleep 8 && chromium-browser --kiosk --noerrdialogs --disable-infobars --disable-translate --no-first-run --check-for-update-interval=31536000 --start-fullscreen --window-size=800,480 http://localhost:8088\"
X-GNOME-Autostart-enabled=true
EOF
"

# 8. Disable screen blanking
echo "--- Disabling screen blanking ---"
ssh $SSH_OPTS "$PI_HOST" "sudo bash -c '
    mkdir -p /etc/xdg/lxsession/LXDE-pi
    cat > /etc/xdg/lxsession/LXDE-pi/autostart << XEOF
@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
@xset s off
@xset -dpms
@xset s noblank
XEOF
'" 2>/dev/null || true

echo ""
echo "=== Deploy complete! ==="
echo ""
echo "Dashboard is running at http://$PI_HOST:8088"
echo "Reboot the Pi for kiosk mode + CAN HAT: ssh $PI_HOST 'sudo reboot'"
echo ""
echo "Commands:"
echo "  ssh $PI_HOST 'cd $REMOTE_DIR && docker compose -f docker-compose.pi.yml logs -f'  # View logs"
echo "  ssh $PI_HOST 'cd $REMOTE_DIR && docker compose -f docker-compose.pi.yml restart'  # Restart"
echo "  ./deploy.sh                                                                        # Re-deploy"
