(() => {
  const api = globalThis.browser || globalThis.chrome;
  const core = globalThis.PF_CORE;
  const $ = (id) => document.getElementById(id);
  let activeTab = null;
  let historyTimer = null;
  const names = { leetcode: "LeetCode", geeksforgeeks: "GeeksforGeeks", codeforces: "Codeforces" };
  const send = async (type, values = {}) => {
    const response = await api.runtime.sendMessage({ type, ...values });
    if (!response?.ok) throw new Error(response?.error || "Extension request failed");
    return response.value;
  };
  function historyDescription(result, profile) {
    if (result?.status === "running") return "Importing… You can close the popup; keep your LeetCode tab open.";
    if (result?.status === "failed") return result.error || "Import failed. Saved questions are retained.";
    const value = result?.questions != null ? result : profile;
    let description = `${value.questions} ${value.questions === 1 ? "question" : "questions"} · ${value.timestamped_questions} with dated acceptances`;
    if (value.source_local_question_times) description += ` · ${value.source_local_question_times} with source dates (time zone unspecified)`;
    if (value.questions_with_statements != null) description += ` · ${value.questions_with_statements} with statements`;
    if (value.questions_with_difficulty != null) description += ` · ${value.questions_with_difficulty} with difficulty`;
    if (value.source_total_solved !== null) description += ` · ${value.source_total_solved} reported solved`;
    if (value.history_complete === false || result?.next_cursor != null) description += " · Partial history";
    if (result?.status === "cooldown") description += " · Refresh recently attempted; try again shortly.";
    if (result?.status === "not_found") description += " · Acceptance not visible yet.";
    if (result?.warning) description += ` · ${result.warning}`;
    if (result?.dated_history_checked) description += ` · ${result.dated_history_checked} available submission histories checked`;
    if (result?.enrichment_status === "partial") description += " · Some metadata is unavailable; saved questions are retained.";
    return description;
  }
  async function refreshHistory() {
    const state = await send("PF_HISTORY_STATE");
    $("history").hidden = false;
    $("history-empty").hidden = state.profiles.length !== 0;
    const container = $("history-accounts");
    container.replaceChildren();
    let running = false;
    for (const profile of state.profiles) {
      const row = document.createElement("article"); row.className = "history-account";
      const heading = document.createElement("h3"); heading.textContent = `${names[profile.platform]} · @${profile.handle}`;
      const description = document.createElement("p"); description.setAttribute("role", "status");
      const result = state.results[profile.profile_id];
      description.textContent = historyDescription(result, profile);
      const button = document.createElement("button");
      const busy = result?.status === "running";
      running ||= busy;
      button.disabled = busy;
      button.textContent = busy ? "Importing…" : result?.next_cursor != null ? "Continue history import" : "Import solved history";
      button.addEventListener("click", async () => {
        button.disabled = true; description.textContent = "Importing solved questions…";
        try {
          [activeTab] = await api.tabs.query({ active: true, lastFocusedWindow: true });
          const imported = await send("PF_HISTORY_IMPORT", { profile_id: profile.profile_id, tab_id: activeTab?.id });
          description.textContent = historyDescription(imported, profile);
          await refreshHistory();
        } catch (error) { report(error); description.textContent = error.message; }
        finally { button.disabled = false; }
      });
      const label = document.createElement("label"); label.className = "tracking-toggle";
      const toggle = document.createElement("input"); toggle.type = "checkbox";
      toggle.checked = state.tracking[profile.platform]?.profile_id === profile.profile_id;
      toggle.addEventListener("change", async () => {
        toggle.disabled = true;
        try { await send("PF_TRACK", { profile_id: profile.profile_id, enabled: toggle.checked }); await refreshHistory(); }
        catch (error) { toggle.checked = !toggle.checked; report(error); }
        finally { toggle.disabled = false; }
      });
      label.append(toggle, document.createTextNode("Track accepted submissions"));
      row.append(heading, description, button, label); container.append(row);
    }
    if (historyTimer) clearTimeout(historyTimer);
    if (running) historyTimer = setTimeout(() => void refreshHistory().catch(report), 2000);
  }
  function show(snapshot) {
    const problem = snapshot?.problem;
    const result = snapshot?.result || { status: "loading" };
    $("question").textContent = problem?.title || "Current question";
    $("platform").textContent = problem?.platform || "";
    $("status").textContent = core.describe(result);
    const url = result.duplicate ? core.attemptUrl(result.previous_attempt) : null;
    $("attempt").hidden = !url;
    if (url) { $("attempt").href = url; $("attempt").textContent = result.previous_attempt.submission_url === url ? "View previous submission" : "View previous problem"; }
  }
  async function check(force) {
    $("error").hidden = true;
    $("check").disabled = true;
    try {
      if (!activeTab?.id || !core.identify(activeTab.url)) { show({ result: { status: "unsupported" } }); return; }
      show(await api.tabs.sendMessage(activeTab.id, { type: force ? "PF_RECHECK" : "PF_SNAPSHOT" }));
    } catch { $("status").textContent = "Reload this question tab after installing the extension, then try again."; }
    finally { $("check").disabled = false; }
  }
  async function initialize() {
    const state = await send("PF_STATE");
    $("connection").textContent = state.connected ? `Connected as ${state.handle}${state.offline ? " · App unavailable" : ""}` : "Connect your existing Profligator account.";
    $("connect").hidden = state.connected;
    $("disconnect").hidden = !state.connected;
    [activeTab] = await api.tabs.query({ active: true, lastFocusedWindow: true });
    $("check").hidden = !state.connected || !core.identify(activeTab?.url);
    $("history").hidden = !state.connected;
    if (state.connected && !state.offline) await refreshHistory();
    await check(false);
  }
  function report(error) { $("error").textContent = error.message; $("error").hidden = false; }
  $("connect").addEventListener("click", () => void api.tabs.create({ url: globalThis.PF_CONFIG.webOrigin + "/extension/connect" }));
  $("dashboard").addEventListener("click", () => void api.tabs.create({ url: globalThis.PF_CONFIG.webOrigin + "/dashboard" }));
  $("check").addEventListener("click", () => void check(true));
  $("disconnect").addEventListener("click", async () => {
    $("disconnect").disabled = true;
    try { await send("PF_DISCONNECT"); await initialize(); } catch (error) { report(error); }
    finally { $("disconnect").disabled = false; }
  });
  void initialize().catch(report);
})();
