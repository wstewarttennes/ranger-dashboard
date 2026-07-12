/**
 * Gauge rendering - updates speed, power, RPM, temps, and stats.
 */

function updateGauges(state) {
    // Speed (use imperial by default, configurable later)
    const speedEl = document.getElementById("speed");
    const speedUnit = document.getElementById("speed-unit");
    speedEl.textContent = Math.round(state.speed_mph);
    speedUnit.textContent = "MPH";

    // Gear
    const gearEl = document.getElementById("gear");
    gearEl.textContent = state.gear;
    gearEl.style.color = state.gear === "R" ? "var(--accent-orange)" :
                          state.gear === "D" ? "var(--accent-green)" :
                          "var(--text-secondary)";

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
    if (state.charging) {
        chgStatus.textContent = "⚡ Charging";
        chgStatus.style.color = "#00e676";
        document.getElementById("charge-power").textContent = state.charge_watts + "W";
        document.getElementById("charger-temp").textContent = state.charger_temp_c.toFixed(0) + "°C";
    } else {
        chgStatus.textContent = "Idle";
        chgStatus.style.color = "";
        document.getElementById("charge-power").textContent = "--W";
        document.getElementById("charger-temp").textContent = "--°C";
    }

    // Throttle
    document.getElementById("throttle").textContent = state.throttle_pct.toFixed(0) + "%";

    // Openpilot state
    const opState = document.getElementById("op-state");
    opState.textContent = state.openpilot_state;
    opState.className = "stat-value op-" + state.openpilot_state;
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
