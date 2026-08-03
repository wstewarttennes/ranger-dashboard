/**
 * Gauge rendering - updates speed, power, RPM, temps, and stats.
 */

function updateGauges(state) {
    // Speed (use imperial by default, configurable later)
    const speedEl = document.getElementById("speed");
    const speedUnit = document.getElementById("speed-unit");
    speedEl.textContent = Math.round(state.speed_mph);
    speedUnit.textContent = "MPH";

    // Gear selector — slide the knob to the active gear (R / N / D).
    // While charging the drivetrain is locked out, so show a LOCKED state.
    const selector = document.getElementById("gear-selector");
    const lock = document.getElementById("gear-lock");
    if (selector) selector.classList.toggle("locked", !!state.charging);
    if (lock) lock.classList.toggle("hidden", !state.charging);

    if (!state.charging) {
        const gearOrder = ["R", "N", "D"];
        const gearIdx = gearOrder.indexOf(state.gear);
        const knob = document.getElementById("gear-knob");
        if (knob && gearIdx >= 0) {
            knob.style.transform = "translateX(" + (gearIdx * 100) + "%)";
            knob.style.background = state.gear === "R" ? "var(--accent-orange)" :
                                    state.gear === "D" ? "var(--accent-green)" :
                                    "var(--text-secondary)";
        }
        document.querySelectorAll(".gear-opt").forEach(o =>
            o.classList.toggle("active", o.dataset.gear === state.gear));
    } else {
        document.querySelectorAll(".gear-opt").forEach(o => o.classList.remove("active"));
    }

    // Power
    const powerEl = document.getElementById("power");
    const powerBar = document.getElementById("power-bar");
    const powerKw = state.power_kw;
    powerEl.textContent = powerKw.toFixed(1);

    if (powerKw >= 0) {
        powerEl.style.color = "var(--accent-green)";
        powerBar.style.width = Math.min(100, (powerKw / 80) * 100) + "%";
        powerBar.classList.remove("regen");
    } else {
        powerEl.style.color = "var(--accent-blue)";
        powerBar.style.width = Math.min(100, (Math.abs(powerKw) / 30) * 100) + "%";
        powerBar.classList.add("regen");
    }

    // RPM
    document.getElementById("rpm").textContent = state.motor_rpm;

    // Temperatures with color coding
    const motorTemp = document.getElementById("motor-temp");
    motorTemp.textContent = state.motor_temp_c.toFixed(0) + "\u00B0C";
    motorTemp.className = "stat-value " + getTempClass(state.motor_temp_c, 80, 100);

    const invTemp = document.getElementById("inverter-temp");
    invTemp.textContent = state.inverter_temp_c.toFixed(0) + "\u00B0C";
    invTemp.className = "stat-value " + getTempClass(state.inverter_temp_c, 70, 90);

    // Electrical — while charging, show live charge V/A (from the TSM2500);
    // otherwise show the X1 motor-bus values.
    if (state.charging) {
        document.getElementById("voltage").textContent = state.charge_voltage.toFixed(1) + "V";
        document.getElementById("current").textContent = state.charge_current.toFixed(0) + "A";
    } else {
        document.getElementById("voltage").textContent = state.dc_bus_voltage.toFixed(1) + "V";
        document.getElementById("current").textContent = state.dc_bus_current.toFixed(1) + "A";
    }
    document.getElementById("soc").textContent = state.soc_pct > 0 ? state.soc_pct.toFixed(0) + "%" : "--%";

    // Charging panel
    const chgStatus = document.getElementById("charge-status");
    const chgProgress = document.getElementById("charge-progress");
    const chgBar = document.getElementById("charge-progress-bar");
    if (state.charging) {
        chgStatus.textContent = "⚡ Charging";
        chgStatus.style.color = "#00e676";
        document.getElementById("charge-power").textContent = state.charge_watts + "W";
        document.getElementById("charger-temp").textContent = state.charger_temp_c.toFixed(0) + "°C";
        if (chgProgress) chgProgress.classList.add("active");
        if (chgBar) chgBar.style.width = (state.soc_pct > 0 ? state.soc_pct : 0) + "%";
    } else {
        chgStatus.textContent = "Idle";
        chgStatus.style.color = "";
        document.getElementById("charge-power").textContent = "--W";
        document.getElementById("charger-temp").textContent = "--°C";
        if (chgProgress) chgProgress.classList.remove("active");
    }

    // Throttle
    document.getElementById("throttle").textContent = state.throttle_pct.toFixed(0) + "%";

    // Openpilot state
    const opState = document.getElementById("op-state");
    opState.textContent = state.openpilot_state;
    opState.className = "stat-value op-" + state.openpilot_state;

    // DC-DC / 12V health — from the key-undervoltage flag (until a real 12V TPDO
    // is enabled in SmartView). LOW = the DC-DC isn't holding the 12V rail up.
    const dcdc = document.getElementById("dcdc-badge");
    if (dcdc) {
        if (state.key_voltage_live) {
            // Real 12V number from the mapped TPDO
            const v = state.key_switch_voltage;
            dcdc.textContent = "12V: " + v.toFixed(1) + "V";
            dcdc.className = "dcdc-badge " + (v < 12.0 ? "low" : v < 13.0 ? "" : "ok");
        } else if (state.key_undervoltage) {
            dcdc.textContent = "DC-DC 12V: LOW ⚠";
            dcdc.className = "dcdc-badge low";
        } else if (state.vehicle_running || state.charging) {
            dcdc.textContent = "DC-DC 12V: OK";
            dcdc.className = "dcdc-badge ok";
        } else {
            dcdc.textContent = "DC-DC 12V: --";
            dcdc.className = "dcdc-badge";
        }
    }
}

function getTempClass(temp, warnThreshold, critThreshold) {
    if (temp >= critThreshold) return "temp-crit";
    if (temp >= warnThreshold) return "temp-warn";
    return "";
}

function updateFaultOverlay(state) {
    const overlay = document.getElementById("fault-overlay");
    const message = document.getElementById("fault-message");

    if (state.fault_level > 0 && state.fault_level <= 2) {
        overlay.classList.remove("hidden");
        message.textContent = `FAULT: ${state.fault_level_str} (Code ${state.fault_code})`;
    } else {
        overlay.classList.add("hidden");
    }
}
