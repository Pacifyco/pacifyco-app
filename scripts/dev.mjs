// Starts local Postgres, the API and the web app together: `npm run dev` from the repo root.
// Ctrl+C stops the API and web app; the database keeps running (`npm run db:stop` stops it).
import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const isWindows = process.platform === "win32";

const python = isWindows
  ? join(root, "api", ".venv", "Scripts", "python.exe")
  : join(root, "api", ".venv", "bin", "python");

function fail(message) {
  console.error(`\n${message}\n`);
  process.exit(1);
}

if (!existsSync(python)) {
  fail("API virtual environment not found. Set it up first (README, step 2).");
}
if (!existsSync(join(root, "web", "node_modules"))) {
  fail("Web dependencies not installed. Run `npm install` in /web first (README, step 3).");
}

console.log("Starting Postgres (docker compose)...");
const db = spawnSync("docker", ["compose", "up", "-d", "--wait"], { cwd: root, stdio: "inherit" });
if (db.status !== 0) {
  fail("Couldn't start Postgres. Is Docker Desktop running?");
}

const colours = { api: "\x1b[36m", web: "\x1b[35m" };
const reset = "\x1b[0m";
const children = [];

function run(name, command, args, cwd) {
  const child = spawn(command, args, { cwd, shell: isWindows, env: { ...process.env, FORCE_COLOR: "1" } });
  const prefix = `${colours[name]}[${name}]${reset} `;
  for (const stream of [child.stdout, child.stderr]) {
    let buffered = "";
    stream.on("data", (chunk) => {
      buffered += chunk.toString();
      const lines = buffered.split(/\r?\n/);
      buffered = lines.pop();
      for (const line of lines) process.stdout.write(prefix + line + "\n");
    });
  }
  child.on("exit", (code) => {
    process.stdout.write(`${prefix}exited (${code ?? "signal"})\n`);
    stopAll(code ?? 0);
  });
  children.push(child);
}

let stopping = false;
function stopAll(code) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (child.exitCode !== null) continue;
    if (isWindows) {
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      child.kill("SIGTERM");
    }
  }
  process.exit(code);
}

process.on("SIGINT", () => stopAll(0));
process.on("SIGTERM", () => stopAll(0));

run("api", python, ["-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"], join(root, "api"));
run("web", "npm", ["run", "dev"], join(root, "web"));

console.log("API: http://localhost:8000/docs   Web: http://localhost:5173   (Ctrl+C to stop)");
