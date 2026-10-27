(() => {
  if (location.origin !== globalThis.PF_CONFIG.webOrigin || location.pathname !== "/extension/connect" || window !== window.top) return;
  const api = globalThis.browser || globalThis.chrome;
  let connecting = false;
  const reply = (requestId, value) => window.postMessage({ source: "profligator-extension", requestId, ...value }, location.origin);

  async function issueGrant() {
    // Requests use the existing HttpOnly app session at the fixed configured API.
    const options = { method: "POST", credentials: "include", cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: navigator.userAgent.includes("Firefox/") ? "Firefox extension" : "Chromium extension" }) };
    let response = await fetch(globalThis.PF_CONFIG.apiOrigin + "/api/v1/extension/sessions", options);
    if (response.status === 401) {
      const refresh = await fetch(globalThis.PF_CONFIG.apiOrigin + "/api/v1/auth/refresh", { method: "POST", credentials: "include" });
      if (refresh.ok) response = await fetch(globalThis.PF_CONFIG.apiOrigin + "/api/v1/extension/sessions", options);
    }
    if (!response.ok) throw new Error(response.status === 401 ? "Sign in to Profligator first, then reconnect." :
      response.status === 403 ? "A signed-in candidate account is required." : "Could not connect the extension.");
    return response.json();
  }

  window.addEventListener("message", async (event) => {
    const message = event.data;
    if (event.source !== window || event.origin !== location.origin || message?.source !== "profligator-app" ||
        typeof message.requestId !== "string" || message.requestId.length > 100) return;
    if (message.type === "PF_PING") { reply(message.requestId, { available: true }); return; }
    if (message.type === "PF_REVOKED") {
      await api.runtime.sendMessage({ type: "PF_STATE" }).catch(() => {});
      return;
    }
    if (message.type !== "PF_AUTHORIZE" || connecting) return;
    connecting = true;
    let grant;
    try {
      grant = await issueGrant();
      const response = await api.runtime.sendMessage({ type: "PF_CONNECT", grant });
      if (!response?.ok) throw new Error(response?.error || "Could not connect the extension.");
      // Return public connection status only; the bearer never enters the web page's JS world.
      reply(message.requestId, { connected: true, handle: response.value.handle });
    } catch (error) {
      if (grant) await fetch(globalThis.PF_CONFIG.apiOrigin + `/api/v1/extension/sessions/${encodeURIComponent(grant.session.id)}`,
        { method: "DELETE", credentials: "include" }).catch(() => {});
      reply(message.requestId, { error: error.message || "Connection failed." });
    } finally { connecting = false; }
  });
})();
