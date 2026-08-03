/**
 * Battery cell grid visualization.
 * Shows 42 cells (7 modules x 6 cells) as a color-coded heatmap.
 */

let cellElements = [];
let gridInitialized = false;

function initBatteryGrid() {
    const grid = document.getElementById("cell-grid");
    grid.innerHTML = "";
    cellElements = [];

    // 7 modules x 6 cells = 42 cells
    for (let i = 0; i < 42; i++) {
        const cell = document.createElement("div");
        cell.className = "cell";
        cell.textContent = "--";
        grid.appendChild(cell);
        cellElements.push(cell);
    }
    gridInitialized = true;
}

function updateBattery(state) {
    const grid = document.getElementById("cell-grid");
    if (!grid) return;   // cell grid removed from the main dashboard (no per-cell data)
    const summary = document.getElementById("battery-summary");
    const voltages = state.cell_voltages || [];
    const delta = state.cell_delta_mv;
    const activeCount = voltages.filter(v => v > 0).length;

    // No per-cell data on the CAN bus \u2014 show a graceful pack-level view instead
    // of 42 empty boxes (per-cell voltages live on the MCU serial console).
    if (activeCount === 0) {
        summary.textContent = "per-cell not on CAN";
        grid.classList.add("no-cells");
        grid.innerHTML =
            '<div class="cell-placeholder">' +
              '<div class="cell-ph-soc">' + (state.soc_pct > 0 ? Math.round(state.soc_pct) + '%' : '--') + '</div>' +
              '<div class="cell-ph-label">STATE OF CHARGE</div>' +
              (state.pack_voltage > 0 ? '<div class="cell-ph-sub">Pack ' + state.pack_voltage.toFixed(1) + ' V</div>' : '') +
              '<div class="cell-ph-note">Individual cell voltages aren\u2019t broadcast on CAN &mdash; ' +
              'view in the MCU console (<code>show cells</code>) or enable a cell-broadcast service.</div>' +
            '</div>';
        gridInitialized = false;   // re-init the grid if cells ever start arriving
        return;
    }

    if (!gridInitialized || grid.classList.contains("no-cells")) {
        grid.classList.remove("no-cells");
        initBatteryGrid();
    }

    // Update summary
    document.getElementById("battery-summary").textContent =
        `${activeCount} cells | \u0394 ${delta.toFixed(0)}mV`;

    // Update each cell
    for (let i = 0; i < 42; i++) {
        const v = voltages[i];
        const el = cellElements[i];

        if (v <= 0) {
            el.textContent = "--";
            el.className = "cell";
            continue;
        }

        el.textContent = v.toFixed(2);

        // Color based on voltage health
        if (v < 3.2 || v > 4.15) {
            el.className = "cell bad";
        } else if (v < 3.4 || v > 4.1) {
            el.className = "cell warn";
        } else {
            el.className = "cell good";
        }
    }
}

// Initialize on load
document.addEventListener("DOMContentLoaded", initBatteryGrid);
