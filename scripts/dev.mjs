import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const apiOnly = process.argv.includes("--api-only");
const children = [];
let stopping = false;

function stopAll(signal = "SIGTERM") {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (child.exitCode !== null || child.pid === undefined) continue;
    try {
      if (process.platform === "win32") child.kill(signal);
      else process.kill(-child.pid, signal);
    } catch (error) {
      if (error.code !== "ESRCH") console.error(error);
    }
  }
}

process.on("SIGINT", () => stopAll("SIGINT"));
process.on("SIGTERM", () => stopAll());

function start(command, args, options = {}) {
  const child = spawn(command, args, {
    cwd: root,
    stdio: "inherit",
    detached: process.platform !== "win32",
    ...options,
  });
  children.push(child);
  child.on("error", (error) => {
    console.error(`Could not start ${command}: ${error.message}`);
    process.exitCode = 1;
    stopAll();
  });
  child.on("exit", (code, signal) => {
    if (stopping) return;
    process.exitCode = code ?? (signal ? 1 : 0);
    stopAll();
  });
  return child;
}

function listen(port) {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolvePort(address.port));
    });
  });
}

async function apiPort() {
  if (process.env.PROFLIGATOR_API_PORT) {
    const port = Number(process.env.PROFLIGATOR_API_PORT);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      throw new Error("PROFLIGATOR_API_PORT must be a port number from 1 to 65535.");
    }
    return port;
  }
  try {
    return await listen(8000);
  } catch (error) {
    if (error.code !== "EADDRINUSE") throw error;
    return listen(0);
  }
}

async function waitForApi(port, child) {
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline && child.exitCode === null && !stopping) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`, {
        signal: AbortSignal.timeout(1000),
      });
      const health = await response.json();
      if (response.ok && health.service === "Profligator API" && health.database === "ok") {
        return;
      }
    } catch {
      // Uvicorn may still be starting.
    }
    await new Promise((resolveSleep) => setTimeout(resolveSleep, 250));
  }
  throw new Error(`API did not become healthy on port ${port}. Check its output above.`);
}

try {
  const port = await apiPort();
  const uv = spawnSync("uv", ["--version"], { stdio: "ignore" }).status === 0;
  const python = join(
    root,
    "apps/api/.venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
  if (!uv && !existsSync(python)) {
    throw new Error("Install uv and run `uv sync --project apps/api --dev` to set up the API.");
  }

  const argumentsForUvicorn = [
    "profligator_api.main:app",
    "--app-dir", "apps/api/src",
    "--reload", "--host", "127.0.0.1", "--port", String(port),
  ];
  const api = uv
    ? start("uv", ["run", "--project", "apps/api", "uvicorn", ...argumentsForUvicorn])
    : start(python, ["-m", "uvicorn", ...argumentsForUvicorn]);

  await waitForApi(port, api);
  console.log(`Profligator API ready at http://127.0.0.1:${port}`);

  if (!apiOnly) {
    const vite = join(root, "node_modules/vite/bin/vite.js");
    if (!existsSync(vite)) throw new Error("Run `npm install` to set up the web app.");
    start(process.execPath, [vite, "--host", "0.0.0.0"], {
      cwd: join(root, "apps/web"),
      env: { ...process.env, PROFLIGATOR_API_PORT: String(port) },
    });
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
  stopAll();
}
