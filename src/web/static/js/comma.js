/**
 * Comma 4 WebRTC integration.
 * Establishes a WebRTC connection via the Pi's proxy endpoint to get:
 * - Road camera video stream
 * - Cereal data channel (openpilot state messages)
 *
 * Pattern adapted from: openpilot/tools/bodyteleop/static/js/webrtc.js
 */

let pc = null;
let dc = null;
let commaConnected = false;
let commaRetryTimer = null;

async function connectComma() {
    // Check if comma 4 is reachable first
    try {
        const statusResp = await fetch("/api/comma/status");
        const status = await statusResp.json();
        if (!status.connected) {
            setCommaStatus("offline", "Comma 4: Offline");
            scheduleCommaRetry();
            return;
        }
    } catch (e) {
        setCommaStatus("offline", "Comma 4: Offline");
        scheduleCommaRetry();
        return;
    }

    setCommaStatus("connecting", "Comma 4: Connecting...");

    try {
        pc = new RTCPeerConnection({ sdpSemantics: "unified-plan" });

        // Handle incoming video track
        pc.addEventListener("track", (evt) => {
            if (evt.track.kind === "video") {
                document.getElementById("comma-video").srcObject = evt.streams[0];
                setCommaStatus("connected", "Comma 4: Live");
            }
        });

        pc.addEventListener("connectionstatechange", () => {
            if (pc.connectionState === "disconnected" || pc.connectionState === "failed") {
                setCommaStatus("offline", "Comma 4: Disconnected");
                cleanupComma();
                scheduleCommaRetry();
            }
        });

        // Create data channel for cereal messages
        dc = pc.createDataChannel("data", { ordered: true });
        dc.onmessage = onCommaDataMessage;
        dc.onclose = () => {
            commaConnected = false;
        };
        dc.onopen = () => {
            commaConnected = true;
        };

        // Create and send offer
        const offer = await pc.createOffer({
            offerToReceiveVideo: true,
            offerToReceiveAudio: false,
        });
        await pc.setLocalDescription(offer);

        // Wait for ICE gathering
        await new Promise((resolve) => {
            if (pc.iceGatheringState === "complete") {
                resolve();
            } else {
                pc.addEventListener("icegatheringstatechange", function check() {
                    if (pc.iceGatheringState === "complete") {
                        pc.removeEventListener("icegatheringstatechange", check);
                        resolve();
                    }
                });
            }
        });

        // Send offer to proxy
        const response = await fetch("/api/comma/offer", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sdp: pc.localDescription.sdp }),
        });

        if (!response.ok) {
            throw new Error(`Proxy returned ${response.status}`);
        }

        const answer = await response.json();
        if (answer.error) {
            throw new Error(answer.error);
        }

        await pc.setRemoteDescription(answer);
        commaConnected = true;

    } catch (e) {
        console.error("Comma WebRTC error:", e);
        setCommaStatus("offline", "Comma 4: Error");
        cleanupComma();
        scheduleCommaRetry();
    }
}

function onCommaDataMessage(evt) {
    try {
        const text = typeof evt.data === "string" ? evt.data : new TextDecoder().decode(evt.data);
        const msg = JSON.parse(text);

        if (msg.type === "selfdriveState" && msg.data) {
            updateOpenpilotState(msg.data);
        }
    } catch (e) {
        // Ignore malformed messages
    }
}

function updateOpenpilotState(data) {
    const opState = document.getElementById("op-state");
    const state = data.state || "disabled";

    // Map selfdriveState.state enum to display string
    let displayState = "disabled";
    if (state === "enabled" || data.enabled === true) {
        displayState = "engaged";
    } else if (state === "softDisabling" || state === "overriding") {
        displayState = "overriding";
    } else if (state === "preEnabled") {
        displayState = "ready";
    }

    opState.textContent = displayState;
    opState.className = "stat-value op-" + displayState;
}

function setCommaStatus(state, text) {
    const overlay = document.getElementById("camera-overlay");
    const statusEl = document.getElementById("comma-status");
    statusEl.textContent = text;
    overlay.className = "camera-overlay" + (state === "connected" ? " connected" : "");
}

function cleanupComma() {
    if (dc) { try { dc.close(); } catch (e) {} dc = null; }
    if (pc) { try { pc.close(); } catch (e) {} pc = null; }
    commaConnected = false;
}

function scheduleCommaRetry() {
    if (!commaRetryTimer) {
        commaRetryTimer = setTimeout(() => {
            commaRetryTimer = null;
            connectComma();
        }, 5000);
    }
}

// Connect on load
document.addEventListener("DOMContentLoaded", () => {
    // Delay slightly to let WebSocket connect first
    setTimeout(connectComma, 1000);
});
