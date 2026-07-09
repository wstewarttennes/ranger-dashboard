/**
 * Main application - handles tab switching and embedded browser.
 */

let currentTab = "dashboard";

function switchTab(tab) {
    currentTab = tab;

    // Update tab buttons
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.getElementById("tab-" + tab).classList.add("active");

    // Update views
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    document.getElementById("view-" + tab).classList.add("active");
}

function openUrl() {
    const input = document.getElementById("browser-url");
    let url = input.value.trim();
    if (!url) return;
    if (!url.startsWith("http")) url = "https://" + url;
    window.open(url, "_blank");
    input.value = "";
}

/**
 * Update the mini status in the tab bar (visible from browser tab too).
 */
function updateTabStatus(state) {
    document.getElementById("tab-speed").textContent = Math.round(state.speed_mph) + " MPH";
    const socText = state.soc_pct > 0 ? state.soc_pct.toFixed(0) + "%" : "--%";
    document.getElementById("tab-soc").textContent = socText;
}

// Prevent accidental zooming on touchscreen
document.addEventListener("gesturestart", (e) => e.preventDefault());

// Keep screen awake (where supported)
async function requestWakeLock() {
    try {
        if ("wakeLock" in navigator) {
            await navigator.wakeLock.request("screen");
        }
    } catch (e) {
        // Not supported or permission denied
    }
}

document.addEventListener("DOMContentLoaded", requestWakeLock);
document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
        requestWakeLock();
    }
});
