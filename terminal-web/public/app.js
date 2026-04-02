/* global Terminal */
const terminalEl = document.getElementById("terminal");

let term = null;
let ws = null;
let currentLine = "";
let busy = false;
let authState = "username";
let pendingUsername = "";
let authenticated = false;
let menuOptions = [];
let menuIndex = 0;
let sid = "";
let outputLog = "";
let inMenu = false;
let menuRendered = false;

function setBusy(v) {
  busy = v;
}

function printPrompt() {
  if (term) term.write("\r\n$ ");
}

function appendLog(s) {
  outputLog += s;
}

function renderMenu(fullRender = false) {
  if (!menuOptions.length) return;
  if (!menuRendered || fullRender) {
    term.write("\r\n\r\nUse ↑/↓ e Enter.\r\n");
    for (let i = 0; i < menuOptions.length; i += 1) {
      const marker = i === menuIndex ? "➤" : " ";
      term.writeln(`${marker} ${menuOptions[i].label}`);
    }
    menuRendered = true;
    return;
  }

  // Move o cursor para o inicio do bloco de opcoes e atualiza in-place.
  for (let i = 0; i < menuOptions.length; i += 1) {
    term.write("\x1b[1A");
  }
  for (let i = 0; i < menuOptions.length; i += 1) {
    const marker = i === menuIndex ? "➤" : " ";
    term.write("\r\x1b[2K");
    term.write(`${marker} ${menuOptions[i].label}`);
    if (i < menuOptions.length - 1) term.write("\r\n");
  }
  term.write("\r\n");
}

function redrawMenu() {
  renderMenu(false);
}

function connectSocket() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "line") {
      const text = msg.data.replace(/\n/g, "\r\n");
      term.write(text);
      appendLog(msg.data);
    }
    if (msg.type === "download" && msg.url) {
      // Inicia o download usando o comportamento padrão do navegador
      const a = document.createElement("a");
      a.href = msg.url;
      a.download = "empresas_urbanova.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
    if (msg.type === "auth_ok") {
      authenticated = true;
      authState = "done";
      sid = msg.sid || "";
    }
    if (msg.type === "auth_fail") {
      authenticated = false;
      authState = "username";
      pendingUsername = "";
      inMenu = false;
      menuRendered = false;
      menuOptions = [];
      menuIndex = 0;
      term.write("\r\nusuario> ");
    }
    if (msg.type === "menu") {
      inMenu = true;
      menuRendered = false;
      menuOptions = msg.options || [];
      menuIndex = 0;
      renderMenu(true);
    }
    if (msg.type === "ready") {
      setBusy(false);
      if (!authenticated && authState === "username") {
        // ja imprime no auth_fail/boot
      } else if (!inMenu) {
        printPrompt();
      }
    }
  });
  ws.addEventListener("close", () => {
    term.write("\r\n[conexao encerrada]\r\n");
    setBusy(false);
  });
}

function setupTerminal() {
  term = new Terminal({
    cols: 120,
    rows: 35,
    cursorBlink: true,
    theme: {
      background: "#0f1115",
      foreground: "#d7dbe3",
    },
  });
  term.open(terminalEl);
  term.writeln("Urbanova Terminal");
  term.writeln("Acesso via terminal.");
  term.writeln("Informe usuario:");
  term.writeln("");
  term.write("usuario> ");
  term.focus();

  term.onData((data) => {
    if (busy) return;
    if (inMenu && authenticated) {
      if (data === "\u001b[A") {
        menuIndex = (menuIndex - 1 + menuOptions.length) % menuOptions.length;
        redrawMenu();
        return;
      }
      if (data === "\u001b[B") {
        menuIndex = (menuIndex + 1) % menuOptions.length;
        redrawMenu();
        return;
      }
      if (data === "\r") {
        const selected = menuOptions[menuIndex];
        if (selected && ws && ws.readyState === 1) {
          term.write(`\r\nSelecionado: ${selected.label}\r\n`);
          appendLog(`Selecionado: ${selected.label}\n`);
          inMenu = false;
          menuRendered = false;
          ws.send(JSON.stringify({ type: "action", action: selected.id }));
          setBusy(true);
        }
        return;
      }
      return;
    }

    if (data === "\r") {
      const cmd = currentLine.trim();
      if (ws && ws.readyState === 1) {
        if (!authenticated) {
          if (authState === "username") {
            pendingUsername = cmd;
            authState = "password";
            term.write("\r\nsenha> ");
          } else if (authState === "password") {
            ws.send(JSON.stringify({ type: "auth", username: pendingUsername, password: cmd }));
            setBusy(true);
          }
        }
      }
      currentLine = "";
      return;
    }
    if (data === "\u007f") {
      if (currentLine.length > 0) {
        currentLine = currentLine.slice(0, -1);
        term.write("\b \b");
      }
      return;
    }
    if (/[\x20-\x7E]/.test(data)) {
      currentLine += data;
      if (!authenticated && authState === "password") {
        term.write("*");
      } else {
        term.write(data);
      }
    }
  });
}

setupTerminal();
connectSocket();

window.addEventListener("keydown", async (e) => {
  // Copiar saída completa com Ctrl+Shift+C
  if (e.ctrlKey && e.shiftKey && (e.key === "C" || e.key === "c")) {
    e.preventDefault();
    await navigator.clipboard.writeText(outputLog);
    term.write("\r\n[saida copiada para area de transferencia]\r\n");
    if (inMenu) {
      redrawMenu();
    } else {
      printPrompt();
    }
  }
  // Atalho rápido para baixar CSV autenticado.
  if (e.ctrlKey && e.shiftKey && (e.key === "D" || e.key === "d")) {
    e.preventDefault();
    if (sid) {
      window.open(`/download/csv?sid=${encodeURIComponent(sid)}`, "_blank");
    }
  }
});
