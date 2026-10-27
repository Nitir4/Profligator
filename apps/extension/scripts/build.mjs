import { mkdir, writeFile, copyFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { execFileSync } from "node:child_process";

const root = fileURLToPath(new URL("../", import.meta.url));
function origin(value) {
  const url = new URL(value);
  if (url.username || url.password || url.search || url.hash || url.pathname !== "/" ||
      !(url.protocol === "https:" || (url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname)))) {
    throw new Error("Extension origins must be HTTPS origins or localhost HTTP origins.");
  }
  return url.origin;
}
const webOrigin = origin(process.env.PROFLIGATOR_EXTENSION_WEB_ORIGIN || "http://localhost:5173");
const apiOrigin = origin(process.env.PROFLIGATOR_EXTENSION_API_ORIGIN || webOrigin);
// WebExtension match patterns have a host, not a port. Exact trusted origins are
// enforced separately by the bridge and background worker.
function hostPattern(value, path = "/*") {
  const url = new URL(value);
  return `${url.protocol}//${url.hostname}${path}`;
}
const platformPatterns = ["https://leetcode.com/*", "https://www.leetcode.com/*",
  "https://www.geeksforgeeks.org/*", "https://geeksforgeeks.org/*", "https://practice.geeksforgeeks.org/*",
  "https://codeforces.com/*", "https://www.codeforces.com/*", "https://mirror.codeforces.com/*"];
const config = { webOrigin, apiOrigin, platformPatterns };
for (const browser of ["chrome", "firefox"]) {
  const output = resolve(process.env.PROFLIGATOR_EXTENSION_OUTPUT_DIR || resolve(root, "dist"), browser);
  await mkdir(output, { recursive: true });
  const manifest = {
    manifest_version: 3, name: "Profligator", version: "0.1.0",
    description: "Check coding questions against your connected Profligator history.",
    permissions: ["storage", "alarms"], host_permissions: [...new Set([...platformPatterns, hostPattern(webOrigin), hostPattern(apiOrigin)])],
    action: { default_title: "Profligator", default_popup: "popup.html" },
    background: browser === "chrome" ? { service_worker: "background.js" } :
      { scripts: ["config.js", "core.js", "background.js"] },
    content_scripts: [
      { matches: platformPatterns, js: ["config.js", "core.js", "history.js", "content.js"], run_at: "document_idle" },
      { matches: [hostPattern(webOrigin, "/extension/connect*")], js: ["config.js", "bridge.js"], run_at: "document_idle" },
    ],
    content_security_policy: { extension_pages: "script-src 'self'; object-src 'self'" },
  };
  if (browser === "firefox") {
    manifest.browser_specific_settings = {
      gecko: { id: "profligator@profligator.local", strict_min_version: "140.0",
        data_collection_permissions: { required: ["websiteContent", "browsingActivity", "authenticationInfo"] } },
      gecko_android: { strict_min_version: "142.0" },
    };
  }
  await writeFile(resolve(output, "config.js"), `globalThis.PF_CONFIG = ${JSON.stringify(config)};\n`);
  for (const name of ["core.js", "history.js", "background.js", "content.js", "bridge.js", "popup.js", "popup.html", "popup.css"]) {
    await copyFile(resolve(root, "src", name), resolve(output, name));
  }
  // Reuse original Figma exports and the web application's local fonts.
  // Flat paths keep both browser packages and ZIPs self-contained.
  for (const name of ["profligator-mark", "close", "duplicate", "arrow-right", "synced"]) {
    await copyFile(resolve(root, "../web/src/assets/extension", `${name}.svg`), resolve(output, `${name}.svg`));
  }
  for (const weight of [400, 500, 600, 700]) {
    await copyFile(resolve(root, "../../node_modules/@fontsource/inter/files", `inter-latin-${weight}-normal.woff2`),
      resolve(output, `inter-${weight}.woff2`));
  }
  manifest.web_accessible_resources = [{ resources: ["profligator-mark.svg", "close.svg", "duplicate.svg", "arrow-right.svg", "synced.svg",
    "inter-400.woff2", "inter-500.woff2", "inter-600.woff2", "inter-700.woff2"], matches: platformPatterns }];
  await writeFile(resolve(output, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
  // Check the shipped classic scripts as well as the source; no remote/bundled code dependencies.
  for (const name of ["config.js", "core.js", "history.js", "background.js", "content.js", "bridge.js", "popup.js"]) {
    execFileSync(process.execPath, ["--check", resolve(output, name)]);
  }
  execFileSync("python3", [resolve(root, "scripts/package.py"), output, `${output}.zip`]);
  if (browser === "firefox") {
    await copyFile(`${output}.zip`, resolve(output, "../firefox-unsigned.xpi"));
  }
  console.log(`${browser}: ${output} (${webOrigin})`);
}
