#!/bin/bash
# Launch Chromium in kiosk mode for the Ranger Dashboard
# Called by ranger-kiosk.service on boot

DASHBOARD_URL="http://localhost:8088"

# Wait for the dashboard backend to be ready
for i in $(seq 1 30); do
    if curl -s "$DASHBOARD_URL/api/health" > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Hide the mouse cursor after 3 seconds of inactivity
unclutter -idle 3 -root &

# Launch Chromium in kiosk mode
exec chromium-browser \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-translate \
    --disable-features=TranslateUI \
    --no-first-run \
    --check-for-update-interval=31536000 \
    --disable-session-crashed-bubble \
    --disable-component-update \
    --autoplay-policy=no-user-gesture-required \
    --start-fullscreen \
    --window-size=800,480 \
    --window-position=0,0 \
    "$DASHBOARD_URL"
