/**
 * Terminal view — xterm.js connected to server PTY via WebSocket.
 */

let term = null;
let termSocket = null;
let termInitialized = false;

function initTerminal() {
    if (termInitialized) return;
    termInitialized = true;

    const container = document.getElementById("terminal-container");
    if (!container) return;

    term = new Terminal({
        cursorBlink: true,
        fontSize: 14,
        fontFamily: "'Fira Code', 'Cascadia Code', 'SF Mono', Menlo, monospace",
        theme: {
            background: "#0a0a0f",
            foreground: "#e8e8f0",
            cursor: "#448aff",
            cursorAccent: "#0a0a0f",
            selectionBackground: "rgba(68, 138, 255, 0.3)",
            black: "#0a0a0f",
            red: "#ff1744",
            green: "#00e676",
            yellow: "#ffd600",
            blue: "#448aff",
            magenta: "#d500f9",
            cyan: "#00e5ff",
            white: "#e8e8f0",
            brightBlack: "#4a4a6a",
            brightRed: "#ff5252",
            brightGreen: "#69f0ae",
            brightYellow: "#ffff00",
            brightBlue: "#82b1ff",
            brightMagenta: "#ea80fc",
            brightCyan: "#84ffff",
            brightWhite: "#ffffff",
        },
        allowProposedApi: true,
    });

    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);

    term.open(container);
    fitAddon.fit();

    // Connect WebSocket
    connectTerminal(fitAddon);

    // Refit on resize
    window.addEventListener("resize", () => {
        if (currentTab === "terminal") {
            fitAddon.fit();
            sendResize();
        }
    });

    // Refit when terminal tab becomes visible
    const observer = new MutationObserver(() => {
        if (document.getElementById("view-terminal").classList.contains("active")) {
            setTimeout(() => {
                fitAddon.fit();
                sendResize();
                term.focus();
            }, 50);
        }
    });
    observer.observe(document.getElementById("view-terminal"), {
        attributes: true,
        attributeFilter: ["class"],
    });
}

function connectTerminal(fitAddon) {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}/ws/terminal`;

    termSocket = new WebSocket(url);

    termSocket.onopen = () => {
        term.writeln("\x1b[32mConnected to Ranger terminal\x1b[0m\r\n");
        sendResize();
    };

    termSocket.onmessage = (event) => {
        term.write(event.data);
    };

    termSocket.onclose = () => {
        term.writeln("\r\n\x1b[31mTerminal disconnected. Switching tabs will reconnect.\x1b[0m");
        termInitialized = false;
    };

    termSocket.onerror = () => {
        term.writeln("\r\n\x1b[31mConnection error\x1b[0m");
    };

    // Send keystrokes to server
    term.onData((data) => {
        if (termSocket && termSocket.readyState === WebSocket.OPEN) {
            termSocket.send(data);
        }
    });
}

function sendResize() {
    if (term && termSocket && termSocket.readyState === WebSocket.OPEN) {
        termSocket.send(`\x1b[resize:${term.rows}:${term.cols}`);
    }
}

// Hook into tab switching — lazy-init terminal on first visit
const origSwitchTab = window.switchTab;
window.switchTab = function (tab) {
    origSwitchTab(tab);
    if (tab === "terminal") {
        if (!termInitialized) {
            initTerminal();
        } else if (term) {
            term.focus();
        }
    }
};
