// AgentX-Kit VS Code extension.
// Thin wrapper over the `agentx` CLI + MCP registration for Copilot/agent mode.
// Pure JS (no build step). Requires `pip install agentx-kit` on PATH.
const vscode = require("vscode");
const fs = require("fs");
const path = require("path");

function cli() {
  return vscode.workspace.getConfiguration("agentx").get("command", "agentx");
}

function runInTerminal(name, commandLine) {
  const term = vscode.window.createTerminal({ name });
  term.show();
  term.sendText(commandLine);
}

function workspaceRoot() {
  const folders = vscode.workspace.workspaceFolders;
  return folders && folders.length ? folders[0].uri.fsPath : process.cwd();
}

async function newProject() {
  const name = await vscode.window.showInputBox({
    prompt: "Project name", value: "my-agent",
  });
  if (!name) return;
  const problem = await vscode.window.showInputBox({
    prompt: "Describe the use case (optional — seeds the agent's prompt)", value: "",
  });
  const enterprise = await vscode.window.showQuickPick(["No", "Yes (tracing, guardrails, FastAPI, Docker, CI, evals, cache)"], {
    placeHolder: "Enterprise pack?",
  });
  let cmd = `${cli()} new --yes --name ${JSON.stringify(name)}`;
  if (problem) cmd += ` --prompt ${JSON.stringify(problem)}`;
  if (enterprise && enterprise.startsWith("Yes")) cmd += " --enterprise";
  runInTerminal("AgentX: new", cmd);
}

function dashboard() {
  runInTerminal("AgentX: dashboard", `${cli()} dashboard`);
}

async function addPrompt() {
  const agent = await vscode.window.showInputBox({ prompt: "Agent name", value: "assistant" });
  if (!agent) return;
  const text = await vscode.window.showInputBox({ prompt: "System prompt" });
  if (text === undefined) return;
  runInTerminal("AgentX: prompt", `${cli()} prompt set ${JSON.stringify(agent)} --text ${JSON.stringify(text)} -d`);
}

function cacheStats() {
  runInTerminal("AgentX: cache", `${cli()} cache stats`);
}

// Write .vscode/mcp.json so GitHub Copilot (agent mode) / VS Code can use AgentX-Kit's MCP server.
async function registerMcp() {
  const root = workspaceRoot();
  const dir = path.join(root, ".vscode");
  const file = path.join(dir, "mcp.json");
  let config = { servers: {} };
  try {
    if (fs.existsSync(file)) config = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (e) { /* start fresh on parse error */ }
  config.servers = config.servers || {};
  config.servers["agentx-kit"] = { command: cli(), args: ["mcp"] };
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(file, JSON.stringify(config, null, 2));
  vscode.window.showInformationMessage(
    "AgentX-Kit MCP server registered in .vscode/mcp.json. Open Copilot Chat (Agent mode) and ask it to build an agent from a problem statement."
  );
  const doc = await vscode.workspace.openTextDocument(file);
  vscode.window.showTextDocument(doc);
}

function activate(context) {
  const reg = (id, fn) => context.subscriptions.push(vscode.commands.registerCommand(id, fn));
  reg("agentx.newProject", newProject);
  reg("agentx.dashboard", dashboard);
  reg("agentx.addPrompt", addPrompt);
  reg("agentx.cacheStats", cacheStats);
  reg("agentx.registerMcp", registerMcp);
}

function deactivate() {}

module.exports = { activate, deactivate };
