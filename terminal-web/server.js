const path = require("path");
const fs = require("fs");
const { spawn, spawnSync } = require("child_process");
const express = require("express");
const bcrypt = require("bcryptjs");
const dotenv = require("dotenv");
const WebSocket = require("ws");

dotenv.config();

const app = express();
const HOST = process.env.HOST || "0.0.0.0";
const PORT = Number(process.env.PORT || 8787);
const TOOL_DIR = path.resolve(process.env.TOOL_DIR || path.join(__dirname, ".."));
const PYTHON_BIN =
  process.env.PYTHON_BIN || (process.platform === "win32" ? "python" : "python3");
const USERNAME = process.env.TERMINAL_USERNAME || "admin";
const PASSWORD_HASH = process.env.TERMINAL_PASSWORD_HASH || "";

if (!PASSWORD_HASH) {
  console.error("ERRO: defina TERMINAL_PASSWORD_HASH no .env");
  process.exit(1);
}

function buscasConfigPath() {
  return path.join(TOOL_DIR, "config", "buscas_urbanova.json");
}

function writeBuscasConfig(data) {
  const p = buscasConfigPath();
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(data, null, 2) + "\n", "utf8");
}

function ensureBuscasConfig() {
  const p = buscasConfigPath();
  if (fs.existsSync(p)) return true;
  fs.mkdirSync(path.dirname(p), { recursive: true });
  spawnSync(PYTHON_BIN, ["gerenciar_buscas.py", "init"], {
    cwd: TOOL_DIR,
    env: process.env,
    encoding: "utf8",
  });
  if (!fs.existsSync(p)) {
    writeBuscasConfig({
      bairro: "Urbanova",
      cidade: "São José dos Campos",
      incluir_buscas_amplas: true,
      segmentos: [],
    });
  }
  return true;
}

/** @returns {object} */
function readBuscasConfig() {
  ensureBuscasConfig();
  const p = buscasConfigPath();
  return JSON.parse(fs.readFileSync(p, "utf8"));
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
      { id: "start_free_capture", label: "🆓 Capturar empresas GRATIS (scraper + OSM)" },
      { id: "start_free_osm_only", label: "🗺️  Capturar apenas via OpenStreetMap (mais rapido)" },
      { id: "start_free_scraper_only", label: "🕷️  Capturar apenas via Google Maps scraping" },
      {
        id: "merge_only",
        label: "🧩 Só gerar CSV final (merge, sem re-scrapar — use se o download veio velho)",
      },
      { id: "show_status", label: "📊 Ver status da ultima execucao" },
      { id: "explain_algorithm", label: "❓ Como o algoritmo funciona (modo leigo)" },
      { id: "download_csv", label: "📥 Baixar CSV final" },
      { id: "show_failures", label: "⚠️  Por que a ferramenta pode falhar e fallback" },
      { id: "start_capture", label: "💳 Capturar via API paga Google (requer API Key)" },
      { id: "run_test", label: "🔑 Testar API Key Google (modo pago)" },
      { id: "buscas_list", label: "📋 Ver termos de busca (config)" },
      { id: "buscas_add", label: "➕ Adicionar termos de busca" },
      { id: "buscas_remove", label: "➖ Remover termo(s) de busca" },
      { id: "buscas_amplas", label: "🔀 Ligar/desligar buscas amplas" },
      { id: "buscas_bairro", label: "📍 Definir bairro" },
      { id: "buscas_cidade", label: "🏙 Definir cidade" },
      { id: "logout", label: "🚪 Sair" },
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
  // Check free pipeline first
  const freePath = path.join(TOOL_DIR, "output", "resumo_pipeline_gratuito.json");
  const paidPath = path.join(TOOL_DIR, "output", "resumo_execucao.json");

  const lines = [];

  if (fs.existsSync(freePath)) {
    const data = JSON.parse(fs.readFileSync(freePath, "utf8"));
    lines.push(
      "🆓 Pipeline Gratuito (ultima execucao):",
      `- Custo: ${data.custo_total || "R$ 0,00"}`,
      `- Total empresas encontradas: ${data?.resultados?.total_unificado ?? 0}`,
      `- Confirmadas Urbanova: ${data?.resultados?.confirmados_urbanova ?? 0}`,
      `- Com telefone: ${data?.cobertura?.com_telefone_pct ?? 0}%`,
      `- Com horario: ${data?.cobertura?.com_horario_pct ?? 0}%`,
      `- Com website: ${data?.cobertura?.com_website_pct ?? 0}%`,
      `- Com email: ${data?.cobertura?.com_email_pct ?? 0}%`,
      `- Tempo: ${data.tempo_execucao_segundos ?? 0}s`,
      `- Fontes: Google Maps Scraper (${data?.fontes?.google_maps_scraper ?? 0}) + OSM (${data?.fontes?.osm_overpass ?? 0})`,
    );
  }

  if (fs.existsSync(paidPath)) {
    const data = JSON.parse(fs.readFileSync(paidPath, "utf8"));
    if (lines.length) lines.push("");
    lines.push(
      "💳 Pipeline Pago (ultima execucao):",
      `- Empresas: ${data.total_unique_places || 0}`,
      `- Com telefone: ${data?.coverage?.with_phone_pct ?? 0}%`,
      `- Com horario: ${data?.coverage?.with_hours_pct ?? 0}%`,
      `- Com website: ${data?.coverage?.with_website_pct ?? 0}%`,
    );
  }

  if (!lines.length) {
    return "Sem execucao anterior. Escolha uma opcao de captura.";
  }
  return lines.join("\n");
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
    "",
    "🆓 MODO GRATUITO (recomendado):",
    "1) Abrimos o Google Maps no navegador automatico (como voce faria).",
    "2) Buscamos por cada tipo de negocio: restaurante, farmacia, clinica, etc.",
    "3) Rolamos todos os resultados para capturar o maximo possivel.",
    "4) Entramos em cada empresa para pegar telefone, horario, site, etc.",
    "5) Consultamos o OpenStreetMap (mapa livre) para pegar mais dados.",
    "6) Juntamos tudo, removemos duplicados, e geramos o CSV final.",
    "7) Custo: R$ 0,00!",
    "",
    "💳 MODO PAGO (API Google):",
    "1) Dividimos o bairro em varios pontos (grade).",
    "2) Consultamos a API oficial do Google Maps (paga).",
    "3) Repetimos por tipos de negocio e ruas.",
    "4) Pedimos detalhes de cada empresa.",
    "5) Custo: ~US$ 10-50 dependendo da quantidade.",
    "",
    "Observacao: ambos os modos buscam cobertura maxima.",
  ].join("\n");
}

app.get("/health", (_req, res) => res.json({ ok: true }));
app.get("/download/csv", (req, res) => {
  const sid = String(req.query.sid || "");
  if (!sid || !authSessions.has(sid)) return res.status(401).json({ error: "nao autenticado" });
  // Prefer the free pipeline final CSV, fallback to legacy
  const freeCsv = path.join(TOOL_DIR, "output", "empresas_urbanova_FINAL.csv");
  const legacyCsv = path.join(TOOL_DIR, "output", "empresas_urbanova.csv");
  const csvPath = fs.existsSync(freeCsv) ? freeCsv : legacyCsv;
  if (!fs.existsSync(csvPath)) return res.status(404).json({ error: "CSV ainda nao gerado" });
  return res.download(csvPath, "empresas_urbanova_FINAL.csv");
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

    if (msg.type === "input_cancel") {
      wsSend(ws, { type: "line", data: "Operacao cancelada.\n" });
      wsSend(ws, { type: "menu", ...getMenu() });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (msg.type === "input") {
      const exp = String(msg.expect || "");
      const raw = String(msg.value || "");
      try {
        const data = readBuscasConfig();
        if (!Array.isArray(data.segmentos)) data.segmentos = [];

        if (exp === "buscas_add") {
          const parts = raw
            .split(/[,;]+/)
            .map((s) => s.trim())
            .filter(Boolean);
          const seen = new Set(data.segmentos);
          let n = 0;
          for (const p of parts) {
            if (!seen.has(p)) {
              data.segmentos.push(p);
              seen.add(p);
              n += 1;
            }
          }
          writeBuscasConfig(data);
          wsSend(ws, {
            type: "line",
            data: `Adicionados ${n} termo(s) novo(s). Total: ${data.segmentos.length}\n`,
          });
        } else if (exp === "buscas_remove") {
          const toRemove = new Set(
            raw
              .split(/[,;]+/)
              .map((s) => s.trim())
              .filter(Boolean),
          );
          const before = data.segmentos.length;
          data.segmentos = data.segmentos.filter((s) => !toRemove.has(s));
          writeBuscasConfig(data);
          wsSend(ws, {
            type: "line",
            data: `Removidos ${before - data.segmentos.length} termo(s). Restam ${data.segmentos.length}\n`,
          });
        } else if (exp === "buscas_bairro") {
          const v = raw.trim();
          if (!v) throw new Error("Bairro vazio");
          data.bairro = v;
          writeBuscasConfig(data);
          wsSend(ws, { type: "line", data: `Bairro salvo: ${v}\n` });
        } else if (exp === "buscas_cidade") {
          const v = raw.trim();
          if (!v) throw new Error("Cidade vazia");
          data.cidade = v;
          writeBuscasConfig(data);
          wsSend(ws, { type: "line", data: `Cidade salva: ${v}\n` });
        } else {
          wsSend(ws, { type: "line", data: "Entrada desconhecida.\n" });
        }
      } catch (err) {
        wsSend(ws, {
          type: "line",
          data: `Erro ao salvar config: ${err.message || err}\n`,
        });
      }
      wsSend(ws, { type: "menu", ...getMenu() });
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
      const freeCsv = path.join(TOOL_DIR, "output", "empresas_urbanova_FINAL.csv");
      const legacyCsv = path.join(TOOL_DIR, "output", "empresas_urbanova.csv");
      const csvPath = fs.existsSync(freeCsv) ? freeCsv : legacyCsv;
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

    if (action === "buscas_list") {
      try {
        const data = readBuscasConfig();
        const segs = Array.isArray(data.segmentos) ? data.segmentos : [];
        const lines = [
          "--- config/buscas_urbanova.json ---",
          `bairro: ${data.bairro}`,
          `cidade: ${data.cidade}`,
          `buscas amplas: ${data.incluir_buscas_amplas ? "sim" : "nao"}`,
          "",
          `segmentos (${segs.length}):`,
          ...segs.map((s, i) => `  ${i + 1}. ${s}`),
          "",
        ];
        wsSend(ws, { type: "line", data: lines.join("\n") + "\n" });
      } catch (err) {
        wsSend(ws, {
          type: "line",
          data: `Erro ao ler buscas: ${err.message || err}\n`,
        });
      }
      wsSend(ws, { type: "menu", ...getMenu() });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (action === "buscas_add") {
      wsSend(ws, {
        type: "expect_input",
        expect: "buscas_add",
        prompt:
          "Digite termos separados por VIRGULA (ex: chaveiro, serralheria).\nLinha vazia = cancelar.",
      });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (action === "buscas_remove") {
      wsSend(ws, {
        type: "expect_input",
        expect: "buscas_remove",
        prompt:
          "Digite o(s) termo(s) exatos a remover (virgula = varios).\nLinha vazia = cancelar.",
      });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (action === "buscas_bairro") {
      wsSend(ws, {
        type: "expect_input",
        expect: "buscas_bairro",
        prompt: "Novo bairro (texto livre).\nLinha vazia = cancelar.",
      });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (action === "buscas_cidade") {
      wsSend(ws, {
        type: "expect_input",
        expect: "buscas_cidade",
        prompt: "Nova cidade.\nLinha vazia = cancelar.",
      });
      wsSend(ws, { type: "ready" });
      return;
    }

    if (action === "buscas_amplas") {
      try {
        const data = readBuscasConfig();
        data.incluir_buscas_amplas = !Boolean(data.incluir_buscas_amplas);
        writeBuscasConfig(data);
        wsSend(ws, {
          type: "line",
          data: `Buscas amplas (empresas/comercio/servicos/lojas): ${data.incluir_buscas_amplas ? "LIGADAS" : "DESLIGADAS"}\n`,
        });
      } catch (err) {
        wsSend(ws, {
          type: "line",
          data: `Erro: ${err.message || err}\n`,
        });
      }
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

    // ─── Free pipeline actions ───────────────────────────────
    if (
      action === "start_free_capture" ||
      action === "start_free_osm_only" ||
      action === "start_free_scraper_only" ||
      action === "merge_only"
    ) {
      const active = activeProcesses.get(ws);
      if (active) {
        wsSend(ws, { type: "line", data: "Ja existe um processo em execucao.\n" });
        wsSend(ws, { type: "ready" });
        return;
      }

      let args = ["pipeline_gratuito.py"];
      let modeLabel = "completo (Scraper + OSM)";

      if (action === "merge_only") {
        args.push("--merge-only");
        modeLabel = "merge apenas (CSV final)";
      } else if (action === "start_free_osm_only") {
        args.push("--skip-scraper");
        modeLabel = "apenas OpenStreetMap (rapido)";
      } else if (action === "start_free_scraper_only") {
        args.push("--skip-osm");
        modeLabel = "apenas Google Maps Scraping";
      }

      if (action !== "merge_only") {
        const buscasJson = path.join(TOOL_DIR, "config", "buscas_urbanova.json");
        if (fs.existsSync(buscasJson)) {
          args.push("--buscas-config", buscasJson);
        }
      }

      if (action === "merge_only") {
        wsSend(ws, {
          type: "line",
          data: `🧩 Gerando CSV final (${modeLabel}) a partir dos arquivos em output/...\n`,
        });
        wsSend(ws, { type: "line", data: "Leva poucos segundos.\n" });
      } else {
        wsSend(ws, { type: "line", data: `🆓 Iniciando captura GRATUITA - modo ${modeLabel}\n` });
        wsSend(ws, { type: "line", data: "Isso pode levar alguns minutos. Aguarde...\n" });
      }

      const proc = spawn(PYTHON_BIN, args, { cwd: TOOL_DIR, env: process.env, shell: false });
      activeProcesses.set(ws, proc);
      let stdoutBuffer = "";
      let stderrBuffer = "";
      proc.stdout.on("data", (c) => {
        const s = c.toString("utf8");
        stdoutBuffer += s;
        // Stream progress to user
        wsSend(ws, { type: "line", data: s });
      });
      proc.stderr.on("data", (c) => {
        stderrBuffer += c.toString("utf8");
      });
      proc.on("close", (code) => {
        if (code === 0) {
          const statusPath = path.join(TOOL_DIR, "output", "resumo_pipeline_gratuito.json");
          if (fs.existsSync(statusPath)) {
            const data = JSON.parse(fs.readFileSync(statusPath, "utf8"));
            wsSend(ws, {
              type: "line",
              data: [
                "",
                "✅ Captura GRATUITA concluida!",
                `- Custo: ${data.custo_total || "R$ 0,00"}`,
                `- Empresas encontradas: ${data?.resultados?.total_unificado ?? 0}`,
                `- Confirmadas Urbanova: ${data?.resultados?.confirmados_urbanova ?? 0}`,
                `- Com telefone: ${data?.cobertura?.com_telefone_pct ?? 0}%`,
                `- Com website: ${data?.cobertura?.com_website_pct ?? 0}%`,
                "Use a opcao 'Baixar CSV final'.",
              ].join("\n") + "\n",
            });
          } else {
            wsSend(ws, { type: "line", data: "✅ Captura concluida! Use 'Baixar CSV final'.\n" });
          }
        } else {
          wsSend(ws, { type: "line", data: `❌ ${fallbackMessage(stderrBuffer)}\n` });
          if (stderrBuffer) {
            wsSend(ws, { type: "line", data: `Detalhes: ${stderrBuffer.slice(0, 500)}\n` });
          }
        }
        wsSend(ws, { type: "menu", ...getMenu() });
        wsSend(ws, { type: "ready" });
        activeProcesses.delete(ws);
      });
      return;
    }

    // ─── Paid pipeline actions (legacy) ───────────────────────
    if (action === "run_test" || action === "start_capture") {
      const key = process.env.MAPS_SERVER_API_KEY || "";
      if (!key) {
        wsSend(ws, { type: "line", data: "Nao funcionou: falta MAPS_SERVER_API_KEY no .env.\nDica: use o modo GRATUITO que nao precisa de API key!\n" });
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

      const args =
        action === "run_test"
          ? ["validar_maps_key.py", "--api-key", key]
          : ["pipeline_full_urbanova.py", "--api-key", key, "--passes", "3", "--step", "220", "--radius", "280"];
      const apiName =
        action === "run_test"
          ? "Google Places API (validação real de credencial)"
          : "Google Places API + Overpass (execucao full)";
      wsSend(ws, { type: "line", data: `💳 Estou indo consultar a API paga: ${apiName}\n` });

      const proc = spawn(PYTHON_BIN, args, { cwd: TOOL_DIR, env: process.env, shell: false });
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
    // Nao matar o pipeline ao fechar a aba: o scrape pode levar horas e a Fase 4 (CSV final)
    // so roda depois; matar aqui deixava empresas_urbanova_scraper.csv novo e FINAL antigo.
    if (proc && !proc.killed) {
      try {
        proc.unref();
      } catch (_e) {
        /* ignore */
      }
    }
    activeProcesses.delete(ws);
  });
});
