(() => {
  const api = globalThis.browser || globalThis.chrome;
  const core = globalThis.PF_CORE;
  const history = globalThis.PF_HISTORY.createClient();
  let historyTail = Promise.resolve();
  const readHistory = operation => {
    const pending = historyTail.then(operation);
    historyTail = pending.catch(() => {});
    return pending;
  };
  let pageIdentity = null;
  let lastKey = null;
  let generation = 0;
  let timer = null;
  let alertHost = null;
  let dismissedKey = null;
  let state = { problem: null, result: { duplicate: false, status: "loading" } };

  function clearAlert() { alertHost?.remove(); alertHost = null; }

  // Use the same local Inter files as the Figma-based web screens. Font faces
  // belong to the document font set, even when the card is in a shadow root.
  for (const weight of [400, 500, 600, 700]) {
    const face = new FontFace("Profligator Inter", `url(${api.runtime.getURL(`inter-${weight}.woff2`)})`, { weight: String(weight) });
    face.load().then(loaded => document.fonts.add(loaded)).catch(() => {});
  }

  function icon(name) {
    const image = document.createElement("img");
    image.src = api.runtime.getURL(`${name}.svg`);
    image.alt = "";
    return image;
  }

  function render(result, key) {
    clearAlert();
    const href = core.attemptUrl(result.previous_attempt);
    if (!result.duplicate || !href || dismissedKey === key) return;
    alertHost = document.createElement("div");
    alertHost.id = "profligator-duplicate-alert";
    // Keep private history references out of the coding site's DOM and JavaScript.
    const root = alertHost.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    // Figma 2603:1342 / report Figure 11.10. Keep the original card palette,
    // assets, spacing and top-right placement; all attempt details stay dynamic.
    style.textContent = `
      :host{all:initial;position:fixed;top:80px;right:32px;z-index:2147483647;width:min(384px,calc(100vw - 32px));font:12px/18px "Profligator Inter",Inter,sans-serif;color:#0f172a;color-scheme:light}
      *{box-sizing:border-box}img{display:block}p,h2,h3{margin:0}button,a{font:inherit}button{cursor:pointer}
      section{background:#fff;border:1px solid rgba(226,232,240,.9);border-radius:12px;overflow:hidden;box-shadow:0 0 0 1px rgba(15,23,42,.05),0 12px 32px -4px rgba(15,23,42,.18),0 4px 12px -2px rgba(15,23,42,.08)}
      .accent{height:4px;background:linear-gradient(90deg,#4f46e5,#6366f1,#818cf8)}
      .body{display:flex;flex-direction:column;gap:14px;padding:20px}
      header{display:flex;align-items:flex-start;justify-content:space-between}
      .brand{display:flex;align-items:center;gap:10px}.brand-mark{display:grid;place-items:center;width:28px;height:28px;border-radius:8px;background:#4f46e5;box-shadow:0 1px 1px rgba(0,0,0,.05)}
      .brand strong{font-size:12px;font-weight:600;letter-spacing:-.3px;line-height:16px}.badge{margin-left:-4px;border:1px solid #e0e7ff;border-radius:4px;padding:3px 7px;background:#eef2ff;color:#4338ca;font-size:10px;font-weight:700;letter-spacing:.5px;line-height:15px}
      .close{display:grid;place-items:center;border:0;background:transparent;border-radius:6px;padding:4px;width:22px;height:22px;margin-top:-4px}
      h2{display:flex;align-items:center;gap:8px;font-size:15px;font-weight:600;letter-spacing:-.375px;line-height:22.5px}.summary p{margin-top:4px;color:#475569}
      .previous{display:flex;flex-direction:column;gap:8px;padding:13px;background:#f8fafc;border:1px solid rgba(226,232,240,.8);border-radius:8px}
      .labels{display:flex;align-items:center;justify-content:space-between;gap:6px}.label{font-size:11px;font-weight:500;letter-spacing:.55px;line-height:16.5px;color:#64748b}
      .solved{display:flex;align-items:center;gap:4px;padding:3px 9px;background:#ecfdf5;border:1px solid rgba(167,243,208,.6);border-radius:9999px;color:#047857;font-size:11px;font-weight:500;letter-spacing:.55px;line-height:16.5px;white-space:nowrap}.solved i{width:6px;height:6px;border-radius:50%;background:#059669}
      h3{font-size:14px;font-weight:600;line-height:19.25px}.platform{display:flex;align-items:center;gap:4px;color:#334155;font-size:12px;font-weight:500;line-height:16px;margin-top:3.5px}.platform i{width:8px;height:8px;border-radius:50%;background:#f59e0b}
      .actions{display:flex;align-items:center;justify-content:space-between;padding-top:2px;gap:8px}.dismiss{border:0;background:transparent;color:#475569;padding:8px 12px;border-radius:8px;font-size:12px;font-weight:500;line-height:16px}
      .attempt{display:flex;align-items:center;justify-content:center;gap:6px;padding:8px 16px;background:#4f46e5;color:#fff;border-radius:8px;text-decoration:none;font-size:12px;font-weight:600;line-height:16px;box-shadow:0 1px 1px rgba(0,0,0,.05)}
      footer{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 20px;border-top:1px solid #f1f5f9;background:rgba(248,250,252,.8);font-size:11px;line-height:16.5px;color:#64748b}footer span{display:flex;align-items:center;gap:4px}footer a{color:#94a3b8;text-decoration:none}
      button:focus-visible,a:focus-visible{outline:2px solid #818cf8;outline-offset:2px}
      @media(max-width:440px){:host{right:16px}.labels{flex-wrap:wrap}}
    `;
    const section = document.createElement("section");
    section.setAttribute("role", "status");
    section.setAttribute("aria-live", "polite");
    const header = document.createElement("header");
    const brand = document.createElement("div"); brand.className = "brand";
    const mark = document.createElement("span"); mark.className = "brand-mark"; mark.append(icon("profligator-mark"));
    const name = document.createElement("strong"); name.textContent = "Profligator";
    const badge = document.createElement("span"); badge.className = "badge"; badge.textContent = "EXTENSION";
    brand.append(mark, name, badge);
    const close = () => { dismissedKey = key; clearAlert(); };
    const dismiss = document.createElement("button"); dismiss.className = "close"; dismiss.append(icon("close"));
    dismiss.type = "button";
    dismiss.setAttribute("aria-label", "Dismiss Profligator alert");
    dismiss.addEventListener("click", close);
    header.append(brand, dismiss);
    const summary = document.createElement("div"); summary.className = "summary";
    const title = document.createElement("h2"); title.append(icon("duplicate"), document.createTextNode("Duplicate Problem Detected"));
    const description = document.createElement("p");
    description.textContent = "You have previously attempted a similar problem in your connected coding accounts.";
    summary.append(title, description);
    const previous = document.createElement("div"); previous.className = "previous";
    const labels = document.createElement("div"); labels.className = "labels";
    const label = document.createElement("span"); label.className = "label"; label.textContent = "YOUR PREVIOUS ATTEMPT";
    const solved = document.createElement("span"); solved.className = "solved";
    const date = result.previous_attempt.solved_at ? new Date(result.previous_attempt.solved_at) : null;
    const dateText = date && !Number.isNaN(date.getTime()) ? new Intl.DateTimeFormat("en", { month: "short", year: "numeric", timeZone: "UTC" }).format(date).toUpperCase() : null;
    solved.append(document.createElement("i"), document.createTextNode(dateText ? `SOLVED • ${dateText}` : "SOLVED"));
    labels.append(label, solved);
    const details = document.createElement("div");
    const previousTitle = document.createElement("h3"); previousTitle.textContent = result.previous_attempt.title;
    const platform = document.createElement("p"); platform.className = "platform";
    const names = { leetcode: "LeetCode", geeksforgeeks: "GeeksforGeeks", codeforces: "Codeforces" };
    platform.append(document.createElement("i"), document.createTextNode(names[result.previous_attempt.platform] || result.previous_attempt.platform));
    details.append(previousTitle, platform); previous.append(labels, details);
    const actions = document.createElement("div"); actions.className = "actions";
    const dismissAction = document.createElement("button"); dismissAction.type = "button"; dismissAction.className = "dismiss";
    dismissAction.textContent = "Dismiss"; dismissAction.addEventListener("click", close);
    const link = document.createElement("a"); link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer";
    link.className = "attempt"; link.append(document.createTextNode("View Previous Attempt"), icon("arrow-right"));
    actions.append(dismissAction, link);
    const body = document.createElement("div"); body.className = "body"; body.append(header, summary, previous, actions);
    const footer = document.createElement("footer");
    const synced = document.createElement("span"); synced.append(icon("synced"), document.createTextNode("Synced with your Unified Portfolio"));
    const settings = document.createElement("a"); settings.href = globalThis.PF_CONFIG.webOrigin + "/extension/connect";
    settings.textContent = "Settings"; settings.target = "_blank"; settings.rel = "noopener noreferrer";
    footer.append(synced, settings);
    const accent = document.createElement("div"); accent.className = "accent";
    section.append(accent, body, footer);
    root.append(style, section);
    document.documentElement.append(alertHost);
  }

  async function scan(force = false) {
    const identity = core.identify(location.href);
    const identityKey = identity ? `${identity.platform}:${identity.source_id}` : null;
    if (pageIdentity !== identityKey) {
      pageIdentity = identityKey;
      generation++;
      lastKey = null;
      dismissedKey = null;
      clearAlert();
      state = { problem: null, result: { duplicate: false, status: identity ? "loading" : "unsupported" } };
    }
    if (!identity) return state;
    const problem = core.extract(document, location.href);
    if (!problem) {
      if (state.problem) { generation++; lastKey = null; clearAlert(); }
      state = { problem: null, result: { duplicate: false, status: "loading" } };
      return state;
    }
    const key = JSON.stringify(problem);
    if (!force && lastKey === key) return state;
    lastKey = key;
    const requestGeneration = ++generation;
    if (force) dismissedKey = null;
    clearAlert();
    state = { problem, result: { duplicate: false, status: "checking" } };
    try {
      const response = await api.runtime.sendMessage({ type: "PF_CHECK", problem });
      const result = response?.ok ? response.value : { duplicate: false, status: "api_unavailable" };
      if (generation !== requestGeneration || core.identify(location.href)?.canonical_url !== problem.canonical_url) return state;
      state = { problem, result };
      render(result, key);
    } catch {
      if (generation === requestGeneration) state = { problem, result: { duplicate: false, status: "api_unavailable" } };
    }
    return state;
  }

  function schedule() {
    if (timer) return;
    timer = setTimeout(() => { timer = null; if (!document.hidden) void scan(); }, 400);
  }
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  // History navigation may change the URL before React replaces the statement.
  setInterval(() => {
    const identity = core.identify(location.href);
    if ((identity ? `${identity.platform}:${identity.source_id}` : null) !== pageIdentity) schedule();
  }, 1000);
  addEventListener("popstate", schedule);
  document.addEventListener("visibilitychange", schedule);
  api.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (sender.id !== api.runtime.id) return false;
    if (["PF_COLLECT_HISTORY", "PF_READ_ACCEPTANCE"].includes(message?.type)) {
      if (core.platform(location.href) !== "leetcode") { sendResponse({ ok: false, error: "Open a LeetCode tab first." }); return false; }
      readHistory(() => message.type === "PF_COLLECT_HISTORY" ? history.collect(message) : history.capture(message))
        .then(value => sendResponse({ ok: true, value }), error => sendResponse({ ok: false, error: error.message }));
      return true;
    }
    if (message?.type === "PF_SESSION_CHANGED") {
      generation++; lastKey = null; dismissedKey = null; clearAlert(); schedule(); return false;
    }
    if (["PF_SNAPSHOT", "PF_RECHECK"].includes(message?.type)) {
      scan(message.type === "PF_RECHECK").then((value) => sendResponse(value));
      return true;
    }
    return false;
  });
  // A submission arms a later provider check. Clicking Submit or opening a page
  // never establishes an acceptance, and Run/Test buttons do not arm tracking.
  let lastSubmit = 0;
  function submitted() {
    const problem = core.extract(document, location.href);
    if (!problem || Date.now() - lastSubmit < 1500) return;
    lastSubmit = Date.now();
    void api.runtime.sendMessage({ type: "PF_ARM_TRACKING", problem }).catch(() => {});
  }
  document.addEventListener("click", event => {
    const button = event.target?.closest?.('button,input[type="submit"],[role="button"]');
    if (!button || button.disabled) return;
    const label = (button.textContent || button.value || button.getAttribute("aria-label") || "").trim();
    if (/^submit(?:\s+(?:solution|code))?$/i.test(label) || button.getAttribute("data-e2e-locator") === "console-submit-button") submitted();
  }, true);
  document.addEventListener("submit", submitted, true);
  void scan();
})();
