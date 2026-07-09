/**
 * WebSocket client for real-time vehicle state updates.
 * Connects to the FastAPI backend and dispatches state to UI components.
 */

let ws = null;
let reconnectTimer = null;
let lastUpdate = 0;

const WS_URL = `ws://${window.location.host}/ws`;

function connectWebSocket() {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        console.log("WebSocket connected");
        setConnectionStatus(true);
        if (reconnectTimer) {
            clearInterval(reconnectTimer);
            reconnectTimer = null;
        }
        // Send a keepalive ping every 30s
        setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send("ping");
            }
        }, 30000);
    };

    ws.onmessage = (event) => {
        const state = JSON.parse(event.data);
        lastUpdate = Date.now();
        onVehicleState(state);
    };

    ws.onclose = () => {
        console.log("WebSocket disconnected");
        setConnectionStatus(false);
        scheduleReconnect();
    };

    ws.onerror = (err) => {
        console.error("WebSocket error:", err);
        ws.close();
    };
}

function scheduleReconnect() {
    if (!reconnectTimer) {
        reconnectTimer = setInterval(() => {
            console.log("Attempting WebSocket reconnect...");
            connectWebSocket();
        }, 2000);
    }
}

function setConnectionStatus(connected) {
    const dot = document.getElementById("status-indicator");
    const text = document.getElementById("status-text");
    if (connected) {
        dot.classList.add("connected");
        text.textContent = "Connected";
    } else {
        dot.classList.remove("connected");
        text.textContent = "Disconnected";
    }
}

/**
 * Called on each state update. Delegates to gauge/battery/comma modules.
 */
function onVehicleState(state) {
    updateGauges(state);
    updateBattery(state);
    updateFaultOverlay(state);
    updateTabStatus(state);
}

// Start connection on load
document.addEventListener("DOMContentLoaded", connectWebSocket);
