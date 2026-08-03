/**
 * Diagnostics view — renders the full firehose of decoded CAN data across
 * Motor / Battery / Charger / Flags subtabs, plus a live raw-CAN sniffer.
 * Panels render from the same 20 Hz websocket state; the CAN Raw table polls
 * /api/can/raw only while that subtab is visible.
 */

let diagSubtab = "motor";
let canRawTimer = null;

function diagRow(label, value, cls) {
    return '<div class="diag-row"><span class="diag-k">' + label +
           '</span><span class="diag-v ' + (cls || "") + '">' + value + '</span></div>';
}

function hex(n, width) {
    let s = (n >>> 0).toString(16).toUpperCase();
    while (width && s.length < width) s = "0" + s;
    return "0x" + s;
}

function tempClass(t) {
    if (t >= 90) return "temp-crit";
    if (t >= 70) return "temp-warn";
    return "";
}

/** Called every websocket frame. Only does work when Diagnostics is visible. */
function updateDiagnostics(state) {
    const view = document.getElementById("view-diagnostics");
    if (!view || !view.classList.contains("active")) return;

    if (diagSubtab === "motor") renderMotor(state);
    else if (diagSubtab === "battery") renderBattery(state);
    else if (diagSubtab === "charger") renderCharger(state);
    else if (diagSubtab === "flags") renderFlags(state);
    // canraw renders on its own poll timer
}

function renderMotor(s) {
    const g = document.getElementById("diag-motor-grid");
    g.innerHTML =
        diagRow("Gear", s.gear) +
        diagRow("Speed", s.speed_mph.toFixed(1) + " mph") +
        diagRow("Motor RPM", s.motor_rpm) +
        diagRow("Power", s.power_kw.toFixed(2) + " kW") +
        diagRow("Throttle", s.throttle_pct.toFixed(0) + " %") +
        diagRow("Torque", s.motor_torque_pct.toFixed(0) + " %") +
        diagRow("Motor Temp", s.motor_temp_c.toFixed(1) + " °C", tempClass(s.motor_temp_c)) +
        diagRow("Inverter Temp", s.inverter_temp_c.toFixed(1) + " °C", tempClass(s.inverter_temp_c)) +
        diagRow("DC Bus Voltage", s.dc_bus_voltage.toFixed(1) + " V") +
        diagRow("DC Bus Current", s.dc_bus_current.toFixed(1) + " A") +
        diagRow("Motor Current", s.motor_current.toFixed(1) + " A") +
        diagRow("Fault Level", s.fault_level_str, s.fault_level > 0 ? "temp-warn" : "") +
        diagRow("Fault Code", s.fault_code) +
        // From configurable TPDOs (show only once mapped in SmartView / non-zero)
        (s.key_voltage_live ? diagRow("12V Supply", s.key_switch_voltage.toFixed(2) + " V",
            s.key_switch_voltage < 12 ? "temp-warn" : "ok") : "") +
        (s.odometer_mi > 0 ? diagRow("Odometer", s.odometer_mi.toFixed(1) + " mi") : "") +
        (s.key_on_hours > 0 ? diagRow("Key-On Hours", s.key_on_hours + " h") : "") +
        (s.service_hours > 0 ? diagRow("Time To Service", s.service_hours + " h") : "") +
        (s.motor_op_hours > 0 ? diagRow("Motor Hours", s.motor_op_hours + " h") : "");
}

function renderBattery(s) {
    const g = document.getElementById("diag-battery-grid");
    const active = (s.cell_voltages || []).filter(v => v > 0).length;
    // zevccs (BMS pack broadcast) is disabled, so pack_voltage/current read 0.
    // Fall back to the X1's DC-bus values — same bus when the contactor's closed.
    const packV = s.pack_voltage > 0 ? s.pack_voltage : s.dc_bus_voltage;
    const packVsrc = s.pack_voltage > 0 ? "" : " (bus)";
    const packA = s.pack_current !== 0 ? s.pack_current
                : s.charging ? s.charge_current : s.dc_bus_current;
    const packAsrc = s.pack_current !== 0 ? "" : s.charging ? " (chg)" : " (bus)";
    let rows =
        diagRow("SOC", s.soc_pct > 0 ? s.soc_pct.toFixed(1) + " %" : "--") +
        diagRow("Pack Voltage", packV.toFixed(1) + " V" + packVsrc) +
        diagRow("Pack Current", packA.toFixed(1) + " A" + packAsrc);
    // Pack temp only when the BMS actually broadcasts it (zevccs)
    if (s.pack_temperature > 0)
        rows += diagRow("Pack Temp", s.pack_temperature.toFixed(1) + " °C", tempClass(s.pack_temperature));
    // Per-cell rows only if cell data is present on the bus
    if (active > 0) {
        rows += diagRow("Cells Reporting", active) +
                diagRow("Min Cell", s.min_cell_v.toFixed(3) + " V") +
                diagRow("Max Cell", s.max_cell_v.toFixed(3) + " V") +
                diagRow("Cell Delta", s.cell_delta_mv.toFixed(0) + " mV", s.cell_delta_mv > 100 ? "temp-warn" : "");
    }
    // BMS limits only when broadcast — hide the all-zero rows when zevccs is off
    if (s.charge_voltage_limit > 0 || s.charge_current_limit > 0) {
        rows += diagRow("Charge V Limit", s.charge_voltage_limit.toFixed(1) + " V") +
                diagRow("Charge A Limit", s.charge_current_limit.toFixed(1) + " A") +
                diagRow("Discharge A Limit", s.discharge_current_limit.toFixed(1) + " A") +
                diagRow("Discharge V Limit", s.discharge_voltage_limit.toFixed(1) + " V");
    }
    g.innerHTML = rows;

    // Cell temperatures section — hidden entirely when there's no data
    const ct = document.getElementById("diag-celltemp-grid");
    const title = document.getElementById("celltemp-title");
    const temps = (s.cell_temps || []).filter(t => t > 0);
    if (temps.length === 0) {
        ct.innerHTML = "";
        ct.style.display = "none";
        if (title) title.style.display = "none";
    } else {
        ct.style.display = "";
        if (title) title.style.display = "";
        ct.innerHTML = (s.cell_temps || []).map((t, i) =>
            '<div class="celltemp ' + tempClass(t) + '"><span>T' + (i + 1) +
            '</span><b>' + (t > 0 ? t.toFixed(0) + "°" : "--") + '</b></div>'
        ).join("");
    }
}

function renderCharger(s) {
    document.getElementById("diag-charge-status").textContent = s.charging ? "⚡ Charging" : "Idle";
    document.getElementById("diag-charge-status").className =
        "charge-hero-status" + (s.charging ? " charging" : "");
    document.getElementById("diag-charge-power").textContent =
        s.charging ? s.charge_watts + " W" : "-- W";
    const soc = s.soc_pct > 0 ? s.soc_pct : 0;
    document.getElementById("diag-charge-soc-bar").style.width = soc + "%";
    document.getElementById("diag-charge-soc-label").textContent =
        s.soc_pct > 0 ? s.soc_pct.toFixed(0) + "%" : "--%";

    const g = document.getElementById("diag-charger-grid");
    g.innerHTML =
        diagRow("Status", s.charging ? "Charging" : "Idle", s.charging ? "ok" : "") +
        diagRow("Charge Voltage", s.charge_voltage.toFixed(1) + " V") +
        diagRow("Charge Current", s.charge_current.toFixed(1) + " A") +
        diagRow("Charge Power", s.charge_watts + " W") +
        diagRow("Charger Temp", s.charger_temp_c.toFixed(1) + " °C", tempClass(s.charger_temp_c)) +
        diagRow("BMS Charge V Limit", s.charge_voltage_limit.toFixed(1) + " V") +
        diagRow("BMS Charge A Limit", s.charge_current_limit.toFixed(1) + " A");
}

function renderFlags(s) {
    const f = document.getElementById("diag-fault-grid");
    f.innerHTML =
        diagRow("Fault Level", s.fault_level_str, s.fault_level > 0 ? "temp-warn" : "ok") +
        diagRow("Fault Code", s.fault_code, s.fault_code ? "temp-warn" : "") +
        diagRow("System Flags", hex(s.system_flags_raw, 4)) +
        diagRow("Motor Flags", hex(s.motor_flags, 4));

    const chips = document.getElementById("diag-sysflags");
    const decoded = s.system_flags_decoded || [];
    chips.innerHTML = decoded.map(fl => {
        const on = fl.active ? "on " + fl.severity : "off";
        return '<span class="chip ' + on + '">' + fl.label + '</span>';
    }).join("");

    const b = document.getElementById("diag-bmsflags-grid");
    b.innerHTML =
        diagRow("Fault Flags", hex(s.bms_fault_flags, 4), s.bms_fault_flags ? "temp-warn" : "") +
        diagRow("Status Flags", hex(s.bms_status_flags, 4)) +
        diagRow("Fault Flags 2", hex(s.bms_fault_flags_2, 4), s.bms_fault_flags_2 ? "temp-warn" : "") +
        diagRow("Status Flags 2", hex(s.bms_status_flags_2, 4));
}

/* ---- Raw CAN sniffer (polls only while its subtab is active) ---- */

function startCanRaw() {
    if (canRawTimer) return;
    pollCanRaw();
    canRawTimer = setInterval(pollCanRaw, 200); // 5 Hz
}

function stopCanRaw() {
    if (canRawTimer) { clearInterval(canRawTimer); canRawTimer = null; }
}

async function pollCanRaw() {
    try {
        const r = await fetch("/api/can/raw");
        const data = await r.json();
        renderCanRaw(data);
    } catch (e) { /* transient */ }
}

function renderCanRaw(data) {
    const buses = data.buses || {};
    const bar = document.getElementById("canraw-buses");
    bar.innerHTML = Object.keys(buses).sort().map(name => {
        const b = buses[name];
        return '<span class="canraw-bus">' + name + ': <b>' + b.live + '</b> ids, <b>' +
               b.hz + '</b> Hz</span>';
    }).join("") || '<span class="canraw-bus">waiting for frames&hellip;</span>';

    const rows = data.frames || [];
    const tb = document.getElementById("canraw-tbody");
    tb.innerHTML = rows.map(f =>
        '<tr class="' + (f.stale ? "stale" : "") + '">' +
        '<td>' + f.bus + '</td>' +
        '<td class="mono">' + f.id_hex + (f.extended ? '<span class="ext">x</span>' : '') + '</td>' +
        '<td>' + f.dlc + '</td>' +
        '<td class="mono data">' + f.data + '</td>' +
        '<td>' + f.hz + '</td>' +
        '<td>' + f.count + '</td>' +
        '<td>' + f.age_ms + 'ms</td>' +
        '</tr>'
    ).join("");
}
