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
    if (!gridInitialized) {
        initBatteryGrid();
    }

    const voltages = state.cell_voltages;
    const minV = state.min_cell_v;
    const maxV = state.max_cell_v;
    const delta = state.cell_delta_mv;

    // Update summary
    const activeCount = voltages.filter(v => v > 0).length;
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
