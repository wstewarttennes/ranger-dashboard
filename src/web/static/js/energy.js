/**
 * Energy tab — trip/efficiency (live from ws telemetry), charge session log,
 * and time-series graphs (polled from /api/history). Self-contained SVG charts,
 * no external libs (kiosk-friendly).
 */

let energySub = "trip";
let historyTimer = null;

function switchEnergy(sub) {
    energySub = sub;
    document.querySelectorAll("#view-energy .subtab").forEach(t =>
        t.classList.toggle("active", t.dataset.esub === sub));
    document.querySelectorAll("#view-energy .subview").forEach(v => v.classList.remove("active"));
    document.getElementById("esub-" + sub).classList.add("active");

    if (sub === "charges") loadChargeLog();
    if (sub === "graphs") { loadHistory(); }

    // graphs refresh periodically only while visible
    if (historyTimer) { clearInterval(historyTimer); historyTimer = null; }
    if (sub === "graphs") historyTimer = setInterval(loadHistory, 15000);
}

/** live trip/efficiency from the ws payload (state.telemetry) */
function updateEnergy(state) {
    const view = document.getElementById("view-energy");
    if (!view || !view.classList.contains("active")) return;
    if (energySub !== "trip" || !state.telemetry) return;
    const t = state.telemetry;

    const grid = (el, s, extra) => {
        el.innerHTML =
            diagRow("Distance", s.miles.toFixed(1) + " mi") +
            diagRow("Energy Used", s.kwh.toFixed(2) + " kWh") +
            diagRow("Efficiency", s.efficiency > 0 ? s.efficiency.toFixed(1) + " mi/kWh" : "--") +
            diagRow("Regen", s.regen_kwh.toFixed(2) + " kWh", "ok") +
            diagRow("Drive Time", s.hours.toFixed(1) + " h") + (extra || "");
    };
    let cur = "";
    if (t.current_charge) {
        cur = diagRow("⚡ Charging now", "+" + t.current_charge.kwh.toFixed(2) + " kWh (" +
              t.current_charge.minutes.toFixed(0) + " min)", "ok");
    }
    grid(document.getElementById("energy-trip-grid"), t.trip);
    grid(document.getElementById("energy-since-grid"), t.since_charge, cur);
}

function resetTrip() {
    fetch("/api/trip/reset", {method: "POST"}).catch(() => {});
}

/* ---- Charge log ---- */
async function loadChargeLog() {
    try {
        const r = await fetch("/api/charge_sessions");
        const d = await r.json();
        const el = document.getElementById("charge-log");
        if (!d.sessions || !d.sessions.length) {
            el.innerHTML = '<div class="diag-row"><span class="diag-k">No charge sessions yet</span></div>';
            return;
        }
        el.innerHTML = d.sessions.map(s => {
            const dt = new Date(s.start * 1000);
            const when = dt.toLocaleString([], {month: "short", day: "numeric",
                hour: "numeric", minute: "2-digit"});
            return '<div class="charge-card">' +
                '<div class="charge-card-top"><b>' + when + '</b>' +
                '<span class="charge-kwh">' + (s.kwh || 0).toFixed(2) + ' kWh</span></div>' +
                '<div class="charge-card-row">' +
                '<span>SOC ' + s.start_soc + '% → ' + s.end_soc + '%</span>' +
                '<span>' + (s.minutes || 0).toFixed(0) + ' min</span>' +
                '<span>$' + (s.cost || 0).toFixed(2) + '</span>' +
                '<span>peak ' + (s.peak_w || 0) + ' W</span>' +
                '</div></div>';
        }).join("");
    } catch (e) { /* transient */ }
}

/* ---- Graphs (inline SVG) ---- */
async function loadHistory() {
    try {
        const r = await fetch("/api/history");
        const d = await r.json();
        const h = d.history || [];
        if (!h.length) return;
        const ts = h.map(p => p.t);
        drawGraph("graph-soc", ts, [{data: h.map(p => p.soc), color: "#00e676"}], 0, 100);
        drawGraph("graph-power", ts, [{data: h.map(p => p.power_kw), color: "#448aff"}]);
        drawGraph("graph-temps", ts, [
            {data: h.map(p => p.motor_c), color: "#ff9100"},
            {data: h.map(p => p.inv_c), color: "#ffd600"},
            {data: h.map(p => p.chg_c), color: "#ff1744"},
        ]);
    } catch (e) { /* transient */ }
}

function drawGraph(elId, ts, series, forceMin, forceMax) {
    const el = document.getElementById(elId);
    const W = 800, H = 160, pad = 24;
    let lo = forceMin, hi = forceMax;
    if (lo === undefined || hi === undefined) {
        const all = series.flatMap(s => s.data).filter(v => v !== null && !isNaN(v));
        lo = Math.min(...all); hi = Math.max(...all);
        if (lo === hi) { lo -= 1; hi += 1; }
    }
    const t0 = ts[0], t1 = ts[ts.length - 1] || t0 + 1;
    const x = t => pad + (t - t0) / Math.max(1, t1 - t0) * (W - 2 * pad);
    const y = v => H - pad - (v - lo) / (hi - lo) * (H - 2 * pad);
    const lines = series.map(s => {
        const pts = s.data.map((v, i) => (v === null || isNaN(v)) ? null : x(ts[i]) + "," + y(v))
                          .filter(Boolean).join(" ");
        return '<polyline fill="none" stroke="' + s.color + '" stroke-width="2" points="' + pts + '"/>';
    }).join("");
    // y-axis labels (min/max)
    const labels = '<text x="2" y="' + (pad + 4) + '" fill="#8888aa" font-size="11">' + hi.toFixed(0) + '</text>' +
                   '<text x="2" y="' + (H - pad) + '" fill="#8888aa" font-size="11">' + lo.toFixed(0) + '</text>';
    el.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" width="100%" height="' + H + '">' +
        '<line x1="' + pad + '" y1="' + (H - pad) + '" x2="' + (W - pad) + '" y2="' + (H - pad) + '" stroke="#2a2a3a"/>' +
        labels + lines + '</svg>';
}
