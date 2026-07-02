// AgentX VS Code extension — a thin wrapper over the `agentx` CLI.
// No build step: plain CommonJS so it runs as-is.
const vscode = require("vscode");
const cp = require("child_process");
const fs = require("fs");
const path = require("path");

/** Resolve the agentx executable: user setting → workspace .venv → PATH. */
function agentxCli() {
  const cfg = vscode.workspace.getConfiguration("agentx").get("cliPath");
  if (cfg) return cfg;
  const ws = workspaceRoot();
  if (ws) {
    for (const rel of [".venv/bin/agentx", ".venv/Scripts/agentx.exe"]) {
      const p = path.join(ws, rel);
      if (fs.existsSync(p)) return p;
    }
  }
  return "agentx"; // fall back to PATH
}

function workspaceRoot() {
  const folders = vscode.workspace.workspaceFolders;
  return folders && folders.length ? folders[0].uri.fsPath : undefined;
}

/** Run a command in a reusable integrated terminal. */
function runInTerminal(name, cmd) {
  const term = vscode.window.terminals.find((t) => t.name === name) || vscode.window.createTerminal(name);
  term.show();
  term.sendText(cmd);
}

/** Run a command and capture stdout (for graph/providers). */
function runCapture(cmd, cwd) {
  return new Promise((resolve, reject) => {
    cp.exec(cmd, { cwd, maxBuffer: 4 * 1024 * 1024 }, (err, stdout, stderr) => {
      if (err) reject(new Error(stderr || err.message));
      else resolve(stdout);
    });
  });
}

async function cmdNew() {
  const name = await vscode.window.showInputBox({ prompt: "Project name", value: "my-agent" });
  if (!name) return;
  const framework = await vscode.window.showQuickPick(["langgraph", "crewai"], { placeHolder: "Framework" });
  if (!framework) return;
  const provider = await vscode.window.showQuickPick(
    ["openai", "anthropic", "gemini", "groq", "ollama", "huggingface", "cohere", "mistral"],
    { placeHolder: "LLM provider" }
  );
  if (!provider) return;
  const rag = (await vscode.window.showQuickPick(["no", "yes"], { placeHolder: "Add RAG?" })) === "yes";
  const serve = (await vscode.window.showQuickPick(["no", "yes"], { placeHolder: "FastAPI server?" })) === "yes";

  const cli = agentxCli();
  const flags = [`--yes`, `--name ${name}`, `--framework ${framework}`, `--provider ${provider}`];
  if (rag) flags.push("--rag");
  if (serve) flags.push("--serve");
  runInTerminal("AgentX", `${cli} new ${flags.join(" ")}`);
}

async function cmdGraph() {
  const cli = agentxCli();
  const ws = workspaceRoot();
  try {
    const mermaid = await runCapture(`${cli} graph --format mermaid`, ws);
    const panel = vscode.window.createWebviewPanel(
      "agentxGraph", "AgentX Graph", vscode.ViewColumn.Beside, { enableScripts: true }
    );
    panel.webview.html = graphHtml(mermaid);
  } catch (e) {
    vscode.window.showErrorMessage(`agentx graph failed: ${e.message}`);
  }
}

function graphHtml(mermaidText) {
  const safe = String(mermaidText).replace(/`/g, "\\`");
  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
</head><body style="background:#fff">
<pre class="mermaid">${safe}</pre>
<script>mermaid.initialize({ startOnLoad: true });</script>
</body></html>`;
}

function cmdDashboard() {
  const cli = agentxCli();
  runInTerminal("AgentX Dashboard", `${cli} dashboard`);
  vscode.window.showInformationMessage("Launching AgentX dashboard at http://localhost:8501");
}

function cmdRun() {
  const ws = workspaceRoot();
  let slug = "";
  try {
    const mf = JSON.parse(fs.readFileSync(path.join(ws, "agentx.json"), "utf-8"));
    slug = mf.name || "";
  } catch (_) {}
  if (!slug) {
    vscode.window.showErrorMessage("No agentx.json found in the workspace root.");
    return;
  }
  runInTerminal("AgentX Run", `uv run ${slug}`);
}

async function cmdProviders() {
  const cli = agentxCli();
  try {
    const out = await runCapture(`${cli} providers`, workspaceRoot());
    const ch = vscode.window.createOutputChannel("AgentX Providers");
    ch.clear();
    ch.append(out);
    ch.show();
  } catch (e) {
    vscode.window.showErrorMessage(`agentx providers failed: ${e.message}`);
  }
}

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("agentx.new", cmdNew),
    vscode.commands.registerCommand("agentx.graph", cmdGraph),
    vscode.commands.registerCommand("agentx.dashboard", cmdDashboard),
    vscode.commands.registerCommand("agentx.run", cmdRun),
    vscode.commands.registerCommand("agentx.providers", cmdProviders)
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
