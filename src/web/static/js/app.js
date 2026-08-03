/**
 * Main application - handles tab switching and embedded browser.
 */

let currentTab = "dashboard";

// Web apps that get their own tab — loaded lazily into an iframe on first view.
const APP_URLS = {
    goblin: "https://hellogobl.in/goblin",
    cityflavor: "https://cityflavor.com/portal/dashboard",
};

function switchTab(tab) {
    currentTab = tab;

    // Update tab buttons
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.getElementById("tab-" + tab).classList.add("active");

    // Update views
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    document.getElementById("view-" + tab).classList.add("active");

    // Lazy-load app iframes the first time their tab is opened
    if (APP_URLS[tab]) {
        const frame = document.getElementById(tab + "-frame");
        if (frame && !frame.src) frame.src = APP_URLS[tab];
    }

    // Raw-CAN polling only runs while the Diagnostics > CAN Raw subtab is showing
    if (tab === "diagnostics" && diagSubtab === "canraw") startCanRaw();
    else stopCanRaw();

    // Energy tab: refresh current subview on open, stop history polling on leave
    if (tab === "energy") switchEnergy(energySub);
    else if (typeof historyTimer !== "undefined" && historyTimer) {
        clearInterval(historyTimer); historyTimer = null;
    }
}

function switchSubtab(sub) {
    diagSubtab = sub;
    document.querySelectorAll(".subtab").forEach(t =>
        t.classList.toggle("active", t.dataset.sub === sub));
    document.querySelectorAll(".subview").forEach(v => v.classList.remove("active"));
    document.getElementById("sub-" + sub).classList.add("active");

    if (sub === "canraw") startCanRaw();
    else stopCanRaw();
}

function reloadApp(tab) {
    const frame = document.getElementById(tab + "-frame");
    if (frame) frame.src = APP_URLS[tab];  // reassign to force a reload
}

function loadHomeAssistant() {
    const input = document.getElementById("ha-url");
    let url = input.value.trim();
    if (!url) return;
    if (!url.startsWith("http")) url = "http://" + url;
    const frame = document.getElementById("ha-frame");
    frame.src = url;
    frame.classList.remove("hidden");
    document.getElementById("ha-placeholder").classList.add("hidden");
}

function loadUrl(url) {
    if (!url.startsWith("http")) url = "https://" + url;
    const frame = document.getElementById("browser-frame");
    frame.src = url;
    frame.classList.remove("hidden");
    document.getElementById("browser-placeholder").classList.add("hidden");
}

function openUrl() {
    const input = document.getElementById("browser-url");
    let url = input.value.trim();
    if (!url) return;
    loadUrl(url);
    input.value = "";
}

function browserHome() {
    const frame = document.getElementById("browser-frame");
    frame.src = "about:blank";
    frame.classList.add("hidden");
    document.getElementById("browser-placeholder").classList.remove("hidden");
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
