if (typeof importScripts === "function") importScripts("config.js", "core.js");
(() => {
  const api = globalThis.browser || globalThis.chrome;
  const config = globalThis.PF_CONFIG;
  const core = globalThis.PF_CORE;
  const key = "profligatorSession";
  const historyKey = "profligatorHistory";
  // Chrome otherwise allows extension content scripts to read storage.local.
  const storageReady = api.storage.local.setAccessLevel ?
    api.storage.local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" }) : Promise.resolve();
  let generation = 0;
  const inFlight = new Map();
  const historyJobs = new Map();
  let historyWrites = Promise.resolve();

  const saved = async () => { await storageReady; return (await api.storage.local.get(key))[key] || null; };
  const publicState = (session) => ({ connected: !!session, handle: session?.handle || null, expires_at: session?.expires_at || null,
    webOrigin: config.webOrigin });
  const internal = (sender) => sender.id === api.runtime.id && sender.url === api.runtime.getURL("popup.html");
  function pairingPage(sender) {
    try { const url = new URL(sender.url); return sender.id === api.runtime.id && sender.frameId === 0 &&
      url.origin === config.webOrigin && url.pathname === "/extension/connect"; } catch { return false; }
  }

  async function notifyTabs() {
    const tabs = await api.tabs.query({ url: config.platformPatterns });
    await Promise.all(tabs.map((tab) => api.tabs.sendMessage(tab.id, { type: "PF_SESSION_CHANGED" }).catch(() => {})));
  }

  async function request(path, session, options = {}) {
    const controller = new AbortController();
    // Provider history (120s), optional metadata (60s), matching (60s), plus response overhead.
    const timer = setTimeout(() => controller.abort(), path.startsWith("/api/v1/extension/history/") ? 250000 : 15000);
    try {
      const response = await fetch(config.apiOrigin + path, { ...options, credentials: "omit", cache: "no-store",
        redirect: "error", signal: controller.signal,
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.token}` } });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const error = new Error(typeof payload?.detail === "string" ? payload.detail : "Extension request failed");
        error.status = response.status;
        throw error;
      }
      return payload;
    } finally { clearTimeout(timer); }
  }

  async function forget(session) {
    const current = await saved();
    if (current?.token !== session?.token) return;
    generation++;
    await api.storage.local.remove(key);
    await api.storage.local.remove(historyKey);
    await notifyTabs();
  }

  async function requireSession() {
    const session = await saved();
    if (!session || Date.parse(session.expires_at) <= Date.now()) {
      if (session) await forget(session);
      throw new Error("Connect your Profligator account first.");
    }
    return session;
  }

  async function sameSession(session) {
    if ((await saved())?.token !== session.token) throw new Error("Browser connection changed. Import stopped.");
  }

  async function historyState(session) {
    await storageReady;
    const state = (await api.storage.local.get(historyKey))[historyKey];
    return state?.session_id === session.session_id ? state : { session_id: session.session_id, tracking: {}, progress: {}, results: {}, pending: {} };
  }

  async function updateHistory(session, update) {
    const pending = historyWrites.then(async () => {
      await sameSession(session);
      const state = await historyState(session);
      update(state);
      await api.storage.local.set({ [historyKey]: state });
    });
    historyWrites = pending.catch(() => {});
    return pending;
  }

  async function linkedProfile(session, id) {
    const profiles = await request("/api/v1/extension/history/profiles", session);
    const profile = profiles.find(value => value.profile_id === id);
    if (!profile) throw new Error("Link this platform account in Profligator first.");
    return profile;
  }

  async function platformSender(sender) {
    if (sender.id !== api.runtime.id || sender.frameId !== 0 || !sender.tab?.id || !core.platform(sender.url)) {
      throw new Error("Invalid platform request");
    }
    const tab = await api.tabs.get(sender.tab.id);
    if (new URL(sender.url).origin !== new URL(tab.url).origin) throw new Error("Platform tab changed");
    return { tab, platform: core.platform(tab.url) };
  }

  async function saveBrowserQuestions(session, profile, data) {
    if (data?.handle?.toLowerCase() !== profile.handle.toLowerCase() || !Array.isArray(data.questions) || data.questions.length > 2000) {
      throw new Error("Unexpected signed-in history response.");
    }
    let result;
    for (let start = 0; start < Math.max(1, data.questions.length); start += 100) {
      await sameSession(session);
      const questions = data.questions.slice(start, start + 100).map(item => ({
        source_id: item.source_id, title: item.title, solved_at: item.solved_at ?? null, submission_id: item.submission_id ?? null,
        difficulty: ["Easy", "Medium", "Hard"].includes(item.difficulty) ? item.difficulty : null,
        topics: Array.isArray(item.topics) ? item.topics.filter(topic => typeof topic === "string" && topic.length > 0 && topic.length <= 128).slice(0, 50) : [],
        ...(item.public_statement === true && typeof item.statement === "string" && item.statement.length > 0 && item.statement.length <= 50000
          ? { statement: item.statement, public_statement: true } : {}),
      }));
      result = await request("/api/v1/extension/history/browser", session, { method: "POST", body: JSON.stringify({
        profile_id: profile.profile_id, handle: profile.handle, questions, source_total_solved: data.source_total_solved ?? null,
        final_batch: start + 100 >= data.questions.length,
      }) });
    }
    return result;
  }

  async function importHistory(message) {
    const session = await requireSession();
    const profile = await linkedProfile(session, message.profile_id);
    const jobKey = `${session.session_id}:${profile.profile_id}`;
    if (historyJobs.has(jobKey)) return historyJobs.get(jobKey);
    const job = (async () => {
      await updateHistory(session, state => { state.results[profile.profile_id] = { status: "running" }; });
      let result;
      if (profile.platform === "leetcode") {
        const tab = await api.tabs.get(message.tab_id);
        if (core.platform(tab.url) !== "leetcode") throw new Error("Open a signed-in LeetCode tab to import this account.");
        const state = await historyState(session);
        const progress = state.progress[profile.profile_id] || { cursor: 0, dateOffset: 0 };
        const collected = await api.tabs.sendMessage(tab.id, { type: "PF_COLLECT_HISTORY", handle: profile.handle, ...progress });
        if (!collected?.ok) throw new Error(collected?.error || "Reload your LeetCode tab, then retry the import.");
        await sameSession(session);
        if (core.platform((await api.tabs.get(tab.id)).url) !== "leetcode") throw new Error("LeetCode tab changed during import.");
        result = await saveBrowserQuestions(session, profile, collected.value);
        result.next_cursor = collected.value.next_cursor;
        result.warning = collected.value.warning;
        result.dated_history_checked = collected.value.dated_history_checked;
        await updateHistory(session, state => {
          state.progress[profile.profile_id] = { cursor: collected.value.next_cursor ?? 0, dateOffset: collected.value.date_offset,
            dateProgress: collected.value.date_progress || {}, metadataOffset: collected.value.metadata_offset || 0 };
        });
      } else {
        result = await request("/api/v1/extension/history/provider", session,
          { method: "POST", body: JSON.stringify({ profile_id: profile.profile_id }) });
      }
      await updateHistory(session, state => { state.results[profile.profile_id] = result; });
      return result;
    })().catch(async error => {
      if ([401, 403].includes(error.status)) await forget(session);
      else await updateHistory(session, state => { state.results[profile.profile_id] = { status: "failed", error: error.message }; }).catch(() => {});
      throw error;
    }).finally(() => historyJobs.delete(jobKey));
    historyJobs.set(jobKey, job);
    return job;
  }

  async function armTracking(message, sender) {
    const { tab, platform } = await platformSender(sender);
    const actual = core.identify(tab.url);
    const session = await requireSession();
    const state = await historyState(session);
    const binding = state.tracking[platform];
    const problem = message.problem;
    if (!binding) return { enabled: false };
    if (!actual || problem?.source_id !== actual.source_id || problem.platform !== platform ||
        problem.canonical_url !== actual.canonical_url || typeof problem.title !== "string" ||
        !problem.title.length || problem.title.length > 512) throw new Error("Invalid submission request.");
    const eventKey = `${platform}:${actual.source_id}`;
    const pending = { profile_id: binding.profile_id, platform, tab_id: tab.id, origin: new URL(tab.url).origin,
      problem: { ...actual, title: problem.title,
        statement: typeof problem.statement === "string" && problem.statement.length <= 50000 ? problem.statement : null,
        topics: Array.isArray(problem.topics) ? problem.topics.filter(topic => typeof topic === "string" && topic.length > 0 && topic.length <= 128).slice(0, 50) : [] },
      since: Date.now(), attempts: 0, when: Date.now() + 30000 };
    await updateHistory(session, current => { (current.pending ||= {})[eventKey] = pending; });
    await api.alarms.create(`pf-acceptance:${eventKey}`, { when: pending.when });
    return { enabled: true };
  }

  async function capturePending(eventKey) {
    const session = await saved();
    if (!session || Date.parse(session.expires_at) <= Date.now()) return;
    const state = await historyState(session);
    const pending = state.pending?.[eventKey];
    if (!pending) return;
    const stillEnabled = current => current.tracking[pending.platform]?.profile_id === pending.profile_id;
    const remove = () => updateHistory(session, current => {
      if (current.pending?.[eventKey]?.since === pending.since) delete current.pending[eventKey];
    });
    if (!stillEnabled(state) || Date.now() - pending.since > 600000) { await remove(); return; }
    const jobKey = `capture:${session.session_id}:${eventKey}`;
    if (inFlight.has(jobKey)) return inFlight.get(jobKey);
    const job = (async () => {
      let result;
      const profile = await linkedProfile(session, pending.profile_id);
      if (profile.platform !== pending.platform) throw new Error("Linked platform changed.");
      if (pending.platform === "leetcode") {
        const tab = await api.tabs.get(pending.tab_id);
        if (new URL(tab.url).origin !== pending.origin) throw new Error("Keep your signed-in LeetCode tab open to record this submission.");
        const response = await api.tabs.sendMessage(tab.id, { type: "PF_READ_ACCEPTANCE", handle: profile.handle,
          problem: pending.problem, since: pending.since });
        if (!response?.ok) throw new Error(response?.error || "LeetCode acceptance could not be read.");
        if (!response.value) return false;
        if (response.value.questions?.length !== 1 || response.value.questions[0].source_id !== pending.problem.source_id) {
          throw new Error("Invalid accepted-submission evidence.");
        }
        if (!stillEnabled(await historyState(session))) { await remove(); return true; }
        result = await saveBrowserQuestions(session, profile, response.value);
      } else {
        if (!stillEnabled(await historyState(session))) { await remove(); return true; }
        result = await request("/api/v1/extension/history/provider", session, { method: "POST",
          body: JSON.stringify({ profile_id: profile.profile_id, source_id: pending.problem.source_id }) });
        if (result.status === "succeeded") {
          await saveVisibleMetadata(session, pending.problem);
          const current = await linkedProfile(session, pending.profile_id);
          result = { ...result, ...current, status: result.status };
        }
      }
      await updateHistory(session, current => { current.results[profile.profile_id] = result; });
      if (result.status === "succeeded") { await remove(); return true; }
      return false;
    })().catch(async error => {
      if ([401, 403].includes(error.status)) { await forget(session); return true; }
      await updateHistory(session, current => { current.results[pending.profile_id] = { status: "failed", error: error.message }; }).catch(() => {});
      return false;
    }).finally(() => inFlight.delete(jobKey));
    inFlight.set(jobKey, job);
    const done = await job;
    if (!done) {
      let next;
      await updateHistory(session, current => {
        const item = current.pending?.[eventKey];
        if (item?.since !== pending.since) return;
        item.attempts++;
        if (item.attempts >= 3 || !stillEnabled(current)) delete current.pending[eventKey];
        else { item.when = Date.now() + 65000; next = item.when; }
      }).catch(() => {});
      if (next) await api.alarms.create(`pf-acceptance:${eventKey}`, { when: next });
    }
  }

  async function saveVisibleMetadata(session, problem) {
    if (!["geeksforgeeks", "codeforces"].includes(problem.platform) || !problem.statement) return;
    await sameSession(session);
    return request("/api/v1/extension/history/metadata", session, { method: "POST", body: JSON.stringify({
      platform: problem.platform, source_id: problem.source_id, statement: problem.statement,
      topics: problem.topics, public_statement: true,
    }) });
  }

  async function check(message, sender) {
    // Chromium's MessageSender.url can retain the document's initial URL after
    // pushState. Read the tab's current URL while still verifying the script's host.
    if (sender.id !== api.runtime.id || sender.frameId !== 0 || !sender.tab?.id ||
        !config.platformPatterns.some(pattern => new URL(pattern).origin === new URL(sender.url).origin)) {
      throw new Error("Invalid question request");
    }
    const tab = await api.tabs.get(sender.tab.id);
    const actual = core.identify(tab.url);
    if (new URL(sender.url).origin !== new URL(tab.url).origin) throw new Error("Question page changed");
    const problem = message.problem;
    if (!actual || !problem ||
        problem.platform !== actual.platform || problem.source_id !== actual.source_id ||
        problem.canonical_url !== actual.canonical_url || typeof problem.title !== "string" ||
        !problem.title.length || problem.title.length > 512 ||
        (problem.statement != null && (typeof problem.statement !== "string" || problem.statement.length > 50000)) ||
        !Array.isArray(problem.topics) || problem.topics.length > 50 || problem.topics.some((topic) => typeof topic !== "string" || topic.length > 128)) {
      throw new Error("Invalid question request");
    }
    const session = await saved();
    if (!session || Date.parse(session.expires_at) <= Date.now()) {
      if (session) await forget(session);
      return { duplicate: false, status: "sign_in_required" };
    }
    const requestGeneration = generation;
    // Visiting a public GFG/Codeforces question can fill text for an existing solve.
    // The server cannot create a solve or acceptance date through this endpoint.
    await saveVisibleMetadata(session, problem).catch(() => {});
    const cacheKey = `${sender.tab.id}:${requestGeneration}:${JSON.stringify(problem)}`;
    if (!inFlight.has(cacheKey)) {
      const promise = request("/api/v1/extension/check", session, { method: "POST", body: JSON.stringify(problem) })
        .then((result) => generation === requestGeneration ? result : { duplicate: false, status: "sign_in_required" })
        .catch(async (error) => {
          if ([401, 403].includes(error.status)) { await forget(session); return { duplicate: false, status: "sign_in_required" }; }
          return { duplicate: false, status: "api_unavailable" };
        }).finally(() => inFlight.delete(cacheKey));
      inFlight.set(cacheKey, promise);
    }
    return inFlight.get(cacheKey);
  }

  async function handle(message, sender) {
    if (message.type === "PF_CHECK") return check(message, sender);
    if (message.type === "PF_HISTORY_IMPORT" && internal(sender)) return importHistory(message);
    if (message.type === "PF_HISTORY_STATE" && internal(sender)) {
      const session = await requireSession();
      const profiles = await request("/api/v1/extension/history/profiles", session);
      const state = await historyState(session);
      return { profiles, tracking: state.tracking, results: state.results, progress: state.progress };
    }
    if (message.type === "PF_TRACK" && internal(sender)) {
      const session = await requireSession();
      const profile = await linkedProfile(session, message.profile_id);
      if (typeof message.enabled !== "boolean") throw new Error("Invalid tracking preference.");
      await updateHistory(session, state => {
        if (message.enabled) state.tracking[profile.platform] = { profile_id: profile.profile_id, handle: profile.handle };
        else if (state.tracking[profile.platform]?.profile_id === profile.profile_id) {
          delete state.tracking[profile.platform];
          for (const [eventKey, event] of Object.entries(state.pending || {})) {
            if (event.profile_id === profile.profile_id) delete state.pending[eventKey];
          }
        }
      });
      return { enabled: message.enabled };
    }
    if (message.type === "PF_TRACKING") {
      const { platform } = await platformSender(sender);
      const session = await saved();
      if (!session || Date.parse(session.expires_at) <= Date.now()) return null;
      return (await historyState(session)).tracking[platform] || null;
    }
    if (message.type === "PF_ARM_TRACKING") return armTracking(message, sender);
    if (message.type === "PF_CONNECT" && pairingPage(sender)) {
      const grant = message.grant;
      if (typeof grant?.token !== "string" || !/^pfext_[A-Za-z0-9_-]{64}$/.test(grant.token)) throw new Error("Invalid connection");
      const identity = await request("/api/v1/extension/session", grant);
      const previous = await saved();
      // Reconnecting in one browser replaces its old device grant.
      if (previous && previous.token !== grant.token) await request("/api/v1/extension/session", previous, { method: "DELETE" }).catch(() => {});
      generation++;
      if (previous?.token !== grant.token) await api.storage.local.remove(historyKey);
      const session = { token: grant.token, handle: identity.handle, expires_at: identity.expires_at, session_id: identity.session_id };
      await api.storage.local.set({ [key]: session });
      await notifyTabs();
      return publicState(session);
    }
    if (message.type === "PF_STATE" && (internal(sender) || pairingPage(sender))) {
      let session = await saved();
      if (session) {
        try { await request("/api/v1/extension/session", session); }
        catch (error) {
          if ([401, 403].includes(error.status)) { await forget(session); session = null; }
          else return { ...publicState(session), offline: true };
        }
      }
      return publicState(session);
    }
    if (message.type === "PF_DISCONNECT" && internal(sender)) {
      const session = await saved();
      if (session) {
        try { await request("/api/v1/extension/session", session, { method: "DELETE" }); }
        catch (error) { if (![401, 403].includes(error.status)) throw new Error("Could not revoke this connection. Start Profligator and try again."); }
        await forget(session);
      }
      return publicState(null);
    }
    throw new Error("Unsupported extension message");
  }

  api.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message?.type?.startsWith("PF_")) return false;
    boot.then(() => handle(message, sender)).then((value) => sendResponse({ ok: true, value }),
      (error) => sendResponse({ ok: false, error: error.message || "Extension request failed" }));
    return true;
  });
  api.alarms.onAlarm.addListener(alarm => {
    if (alarm.name.startsWith("pf-acceptance:")) void capturePending(alarm.name.slice(14));
  });
  // Restore pending provider confirmations when the MV3 worker or browser restarts.
  const boot = (async () => {
    const session = await saved();
    if (!session) return;
    const state = await historyState(session);
    await updateHistory(session, current => {
      for (const result of Object.values(current.results)) {
        if (result.status === "running") {
          result.status = "failed";
          result.error = "Import was interrupted. Saved questions are retained; import again to continue.";
        }
      }
    });
    for (const [eventKey, pending] of Object.entries(state.pending || {})) {
      await api.alarms.create(`pf-acceptance:${eventKey}`, { when: Math.max(Date.now() + 30000, pending.when) });
    }
  })();
})();
