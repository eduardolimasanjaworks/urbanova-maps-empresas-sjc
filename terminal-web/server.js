const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const express = require("express");
const bcrypt = require("bcryptjs");
const dotenv = require("dotenv");
const WebSocket = require("ws");

dotenv.config();

const app = express();
const HOST = process.env.HOST || "0.0.0.0";
const PORT = Number(process.env.PORT || 8787);
const TOOL_DIR = process.env.TOOL_DIR || path.resolve(__dirname, "..");
const USERNAME = process.env.TERMINAL_USERNAME || "admin";
const PASSWORD_HASH = process.env.TERMINAL_PASSWORD_HASH || "";

if (!PASSWORD_HASH) {
  console.error("ERRO: defina TERMINAL_PASSWORD_HASH no .env");
  process.exit(1);
}

const activeProcesses = new Map();
const authSessions = new Set();

function wsSend(ws, message) {
  if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message));
}

function getMenu() {
  return {
    title: "Escolha uma opcao",
    options: [
      { id: "start_capture", label: "Capturar todas as empresas do Urbanova (modo maximo)" },
      { id: "show_status", label: "Ver status da ultima execucao" },
      { id: "consult_balance", label: "Consultar saldo/uso estimado" },
      { id: "explain_algorithm", label: "Como o algoritmo funciona (modo leigo)" },
      { id: "download_csv", label: "Baixar CSV final" },
      { id: "show_key_help", label: "Como criar API Key no Google Cloud" },
      { id: "show_failures", label: "Por que a ferramenta pode falhar e fallback" },
      { id: "run_test", label: "Rodar teste rapido da API Key" },
      { id: "logout", label: "Sair" },
    ],
  };
}

function fallbackMessage(stderr) {
  const s = (stderr || "").toLowerCase();
  if (s.includes("api_key_invalid") || s.includes("invalid api key")) {
    return "Nao funcionou: aparentemente sua API key esta invalida.";
  }
  if (s.includes("billing") || s.includes("payment")) {
    return "Falhou: billing do Google Cloud parece nao estar ativo.";
  }
  if (s.includes("permission_denied") || s.includes("forbidden")) {
    return "Falhou: permissao negada na API. Verifique restricao da key para Places API.";
  }
  if (s.includes("quota") || s.includes("rate limit")) {
    return "Falhou: limite de quota/rate da API foi atingido.";
  }
  return "A ferramenta falhou por um erro tecnico. Veja o log e tente novamente.";
}

function summarizeStatus() {
  const statusPath = path.join(TOOL_DIR, "output", "resumo_execucao.json");
  if (!fs.existsSync(statusPath)) {
    return "Sem execucao anterior. Escolha a opcao de captura.";
  }
  const data = JSON.parse(fs.readFileSync(statusPath, "utf8"));
  return [
    "Ultima execucao:",
    `- Empresas unicas encontradas: ${data.total_unique_places || 0}`,
    `- Cobertura com telefone: ${data?.coverage?.with_phone_pct ?? 0}%`,
    `- Cobertura com horario: ${data?.coverage?.with_hours_pct ?? 0}%`,
    `- Cobertura com website: ${data?.coverage?.with_website_pct ?? 0}%`,
    `- Vias sem cobertura: ${data?.coverage?.uncovered_roads_count ?? 0}`,
  ].join("\n");
}

function keyHelpText() {
  return [
    "Como criar API Key (Google Cloud):",
    "1) Acesse console.cloud.google.com",
    "2) Crie um projeto",
    "3) Ative Billing",
    "4) Library > habilite Places API",
    "5) Credentials > Create API key",
    "6) Restrinja para Places API",
    "7) Coloque no arquivo terminal-web/.env:",
    "   MAPS_SERVER_API_KEY=AIza...",
  ].join("\n");
}

function failureHelpText() {
  return [
    "Falhas comuns e fallback:",
    "- API key invalida: gere outra key e teste novamente",
    "- Billing inativo: habilite faturamento no projeto",
    "- Quota estourada: aguarde ou reduza frequencia",
    "- Cobertura incompleta: rode nova varredura (fallback automatico por ruas/tipos ja ativo)",
  ].join("\n");
}

function parseLastJsonBlock(text) {
  const t = String(text || "").trim();
  const idx = t.lastIndexOf("{");
  if (idx < 0) return null;
  const candidate = t.slice(idx);
  try {
    return JSON.parse(candidate);
  } catch (_err) {
    return null;
  }
}

function countJsonlLines(filePath) {
  if (!fs.existsSync(filePath)) return 0;
  const content = fs.readFileSync(filePath, "utf8");
  if (!content.trim()) return 0;
  return content.split("\n").filter((l) => l.trim()).length;
}

function estimateUsageAndCost() {
  const discoveryN = countJsonlLines(path.join(TOOL_DIR, "output", "places_descoberta.jsonl"));
  const detailsN = countJsonlLines(path.join(TOOL_DIR, "output", "places_detalhes.jsonl"));
  const nearbyCap = 5000;
  const textCap = 5000;
  const detailsCap = 1000;
  // Estimativa simples: discovery dividido em nearby/text.
  const nearApprox = Math.floor(discoveryN * 0.7);
  const textApprox = discoveryN - nearApprox;
  const billedNear = Math.max(0, nearApprox - nearbyCap);
  const billedText = Math.max(0, textApprox - textCap);
  const billedDetails = Math.max(0, detailsN - detailsCap);
  const cost = (billedNear / 1000) * 32 + (billedText / 1000) * 32 + (billedDetails / 1000) * 20;
  return {
    discoveryN,
    detailsN,
    estimatedUSD: Math.round(cost * 100) / 100,
  };
}

function algorithmForLaymanText() {
  return [
    "Como tentamos pegar 'todas' as empresas do Urbanova:",
    "1) Dividimos o bairro em varios pontos (grade).",
    "2) Em cada ponto, consultamos a API oficial do Google Maps.",
    "3) Repetimos por tipos de negocio (clinica, restaurante, farmacia, etc.).",
    "4) Repetimos por ruas/avenidas importantes para reduzir buracos.",
    "5) Juntamos tudo e removemos duplicadas.",
    "6) Pedimos detalhes (telefone, horario, site).",
    "7) Geramos CSV final.",
    "",
    "Observacao: o Google pode nao listar 100% absoluto, mas este modo busca cobertura maxima.",
  ].join("\n");
}

app.get("/health", (_req, res) => res.json({ ok: true }));
app.get("/download/csv", (req, res) => {
  const sid = String(req.query.sid || "");
  if (!sid || !authSessions.has(sid)) return res.status(401).json({ error: "nao autenticado" });
  const csvPath = path.join(TOOL_DIR, "output", "empresas_urbanova.csv");
  if (!fs.existsSync(csvPath)) return res.status(404).json({ error: "CSV ainda nao gerado" });
  return res.download(csvPath, "empresas_urbanova.csv");
});
app.use(express.static(path.join(__dirname, "public")));

const server = app.listen(PORT, HOST, () => {
  console.log(`Servidor pronto em http://${HOST}:${PORT}`);
});

const wss = new WebSocket.Server({ server, path: "/ws" });
wss.on("connection", (ws) => {
  const sid = Math.random().toString(36).slice(2);
  let authed = false;
  wsSend(ws, { type: "line", data: "Bem-vindo ao terminal Urbanova.\n" });
  wsSend(ws, { type: "line", data: "Digite usuario e senha para continuar.\n" });
  wsSend(ws, { type: "ready" });

  ws.on("message", async (raw) => {
    let msg;
    try {
      msg = JSON.parse(raw.toString("utf8"));
    } catch (_err) {
      wsSend(ws, { type: "line", data: "Entrada invalida.\n" });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (msg.type === "auth") {
      const username = String(msg.username || "");
      const password = String(msg.password || "");
      if (username !== USERNAME || !(await bcrypt.compare(password, PASSWORD_HASH))) {
        wsSend(ws, { type: "line", data: "Usuario ou senha invalidos.\n" });
        wsSend(ws, { type: "auth_fail" });
        wsSend(ws, { type: "ready" });
        return;
      }
      authed = true;
      authSessions.add(sid);
      wsSend(ws, { type: "auth_ok", sid });
      wsSend(ws, { type: "line", data: "Login efetuado.\n" });
      wsSend(ws, { type: "menu", ...getMenu() });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (!authed) {
      wsSend(ws, { type: "line", data: "Nao autenticado.\n" });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (msg.type !== "action") return;
    const action = String(msg.action || "");

    if (action === "show_status") {
      wsSend(ws, { type: "line", data: `${summarizeStatus()}\n` });
      wsSend(ws, { type: "menu", ...getMenu() });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (action === "consult_balance") {
      const est = estimateUsageAndCost();
      wsSend(
        ws,
        {
          type: "line",
          data:
            [
              "Saldo real da conta Google:",
              "- Abra: Google Cloud Console > Billing > Reports",
              "",
              "Estimativa local com base no ultimo processamento:",
              `- Eventos de descoberta: ${est.discoveryN}`,
              `- Eventos de detalhes: ${est.detailsN}`,
              `- Custo estimado: US$ ${est.estimatedUSD}`,
            ].join("\n") + "\n",
        },
      );
      wsSend(ws, { type: "menu", ...getMenu() });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (action === "explain_algorithm") {
      wsSend(ws, { type: "line", data: `${algorithmForLaymanText()}\n` });
      wsSend(ws, { type: "menu", ...getMenu() });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (action === "download_csv") {
      const csvPath = path.join(TOOL_DIR, "output", "empresas_urbanova.csv");
      if (!fs.existsSync(csvPath)) {
        wsSend(ws, { type: "line", data: "CSV ainda nao foi gerado. Rode a captura primeiro.\n" });
        wsSend(ws, { type: "menu", ...getMenu() });
        wsSend(ws, { type: "ready" });
        return;
      }
      wsSend(ws, { type: "download", url: `/download/csv?sid=${sid}` });
      wsSend(ws, { type: "line", data: "Download iniciado.\n" });
      wsSend(ws, { type: "menu", ...getMenu() });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (action === "show_key_help") {
      wsSend(ws, { type: "line", data: `${keyHelpText()}\n` });
      wsSend(ws, { type: "menu", ...getMenu() });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (action === "show_failures") {
      wsSend(ws, { type: "line", data: `${failureHelpText()}\n` });
      wsSend(ws, { type: "menu", ...getMenu() });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (action === "logout") {
      authed = false;
      authSessions.delete(sid);
      wsSend(ws, { type: "line", data: "Sessao encerrada.\n" });
      wsSend(ws, { type: "auth_fail" });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (action === "run_test" || action === "start_capture") {
      const key = process.env.MAPS_SERVER_API_KEY || "";
      if (!key) {
        wsSend(ws, { type: "line", data: "Nao funcionou: falta MAPS_SERVER_API_KEY no .env.\n" });
        wsSend(ws, { type: "menu", ...getMenu() });
        wsSend(ws, { type: "ready" });
        return;
      }
      const active = activeProcesses.get(ws);
      if (active) {
        wsSend(ws, { type: "line", data: "Ja existe um processo em execucao.\n" });
        wsSend(ws, { type: "ready" });
        return;
      }

      const cmd = process.platform === "win32" ? "python" : "python3";
      const args =
        action === "run_test"
          ? ["validar_maps_key.py", "--api-key", key]
          : ["pipeline_full_urbanova.py", "--api-key", key, "--passes", "3", "--step", "220", "--radius", "280"];
      const apiName =
        action === "run_test"
          ? "Google Places API (validação real de credencial)"
          : "Google Places API + Overpass (execucao full)";
      wsSend(ws, { type: "line", data: `Estou indo consultar a API do Maps: ${apiName}\n` });

      const proc = spawn(cmd, args, { cwd: TOOL_DIR, env: process.env, shell: false });
      activeProcesses.set(ws, proc);
      let stdoutBuffer = "";
      let stderrBuffer = "";
      proc.stdout.on("data", (c) => {
        stdoutBuffer += c.toString("utf8");
      });
      proc.stderr.on("data", (c) => {
        const s = c.toString("utf8");
        stderrBuffer += s;
      });
      proc.on("close", (code) => {
        if (code === 0) {
          if (action === "run_test") {
            const parsed = parseLastJsonBlock(stdoutBuffer);
            if (parsed?.ok) {
              wsSend(ws, { type: "line", data: "Teste concluido: API key valida e pronta para captura.\n" });
            } else {
              wsSend(ws, { type: "line", data: "Teste executado, mas a chave nao foi validada.\n" });
            }
          } else {
            const statusPath = path.join(TOOL_DIR, "output", "resumo_execucao.json");
            if (fs.existsSync(statusPath)) {
              const data = JSON.parse(fs.readFileSync(statusPath, "utf8"));
              wsSend(
                ws,
                {
                  type: "line",
                  data:
                    [
                      "Captura concluida.",
                      `- Empresas encontradas: ${data.total_unique_places || 0}`,
                      `- Com telefone: ${data?.coverage?.with_phone_pct ?? 0}%`,
                      `- Com horario: ${data?.coverage?.with_hours_pct ?? 0}%`,
                      "Use a opcao 'Baixar CSV final'.",
                    ].join("\n") + "\n",
                },
              );
            } else {
              wsSend(ws, { type: "line", data: "Captura concluida. Use a opcao 'Baixar CSV final'.\n" });
            }
          }
        } else {
          wsSend(ws, { type: "line", data: `${fallbackMessage(stderrBuffer)}\n` });
        }
        wsSend(ws, { type: "menu", ...getMenu() });
        wsSend(ws, { type: "ready" });
        activeProcesses.delete(ws);
      });
    }
  });

  ws.on("close", () => {
    authSessions.delete(sid);
    const proc = activeProcesses.get(ws);
    if (proc && !proc.killed) proc.kill();
    activeProcesses.delete(ws);
  });
});
