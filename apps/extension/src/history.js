/* Signed-in LeetCode history. Session credentials stay in the provider tab. */
(() => {
  const statusFields = "userStatus { isSignedIn username }";
  const profileQuery = `query OwnerHistory($username: String!) {
    ${statusFields}
    matchedUser(username: $username) { username submitStatsGlobal { acSubmissionNum { difficulty count } } }
  }`;
  const questionsQuery = `query OwnerQuestions($filters: UserProgressQuestionListInput) {
    ${statusFields}
    userProgressQuestionList(filters: $filters) { questions { title titleSlug questionStatus } }
  }`;
  const submissionsQuery = `query OwnerAcceptances($questionSlug: String!, $offset: Int!, $limit: Int!, $lastKey: String) {
    ${statusFields}
    questionSubmissionList(questionSlug: $questionSlug, offset: $offset, limit: $limit, lastKey: $lastKey, status: 10) {
      lastKey hasNext submissions { id title titleSlug statusDisplay timestamp isPending }
    }
  }`;
  const metadataQuery = `query OwnerPublicProblem($titleSlug: String!) {
    ${statusFields}
    question(titleSlug: $titleSlug) { titleSlug difficulty isPaidOnly content topicTags { name } }
  }`;

  function account(data, handle) {
    if (data?.userStatus?.isSignedIn !== true || typeof data.userStatus.username !== "string") {
      throw new Error("Sign in to LeetCode in this tab, then import again.");
    }
    if (data.userStatus.username.toLowerCase() !== handle.toLowerCase()) {
      throw new Error(`This LeetCode tab is signed in as ${data.userStatus.username}. Select its linked account in Profligator.`);
    }
  }

  function accepted(row, sourceId) {
    if (!row || row.isPending === true || row.statusDisplay !== "Accepted" ||
        (row.titleSlug && row.titleSlug !== sourceId)) return null;
    if (!/^[1-9][0-9]{0,24}$/.test(String(row.id)) || !/^[0-9]+$/.test(String(row.timestamp))) return null;
    const milliseconds = Number(row.timestamp) * 1000;
    if (!Number.isSafeInteger(milliseconds) || milliseconds < Date.UTC(2010, 0, 1) || milliseconds > Date.now() + 300000) return null;
    return { source_id: sourceId, solved_at: new Date(milliseconds).toISOString(), submission_id: String(row.id) };
  }

  function question(row) {
    if (row?.questionStatus !== "SOLVED" || typeof row.title !== "string" || !row.title.trim() || row.title.length > 512 ||
        !/^[a-z0-9-]{1,160}$/.test(row.titleSlug)) throw new Error("LeetCode returned an unexpected solved question.");
    return { source_id: row.titleSlug, title: row.title.trim(), solved_at: null, submission_id: null };
  }

  function createClient(options = {}) {
    const fetcher = options.fetch || globalThis.fetch;
    const pause = options.pause || (milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds)));
    const cookie = options.cookie || (() => globalThis.document?.cookie || "");
    const parseStatement = options.parseStatement || (html => globalThis.PF_CORE?.fromHtml(html) || null);
    let lastRequest = 0;
    let providerStopped = false;
    async function query(queryText, variables, handle) {
      const remaining = 2100 - (Date.now() - lastRequest);
      if (remaining > 0) await pause(remaining);
      lastRequest = Date.now();
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 20000);
      try {
        // This CSRF value is used locally only; the browser sends its session cookie.
        const csrf = cookie().split(";").map(value => value.trim()).find(value => value.startsWith("csrftoken="))?.slice(10);
        const response = await fetcher("/graphql/", { method: "POST", credentials: "include", redirect: "error",
          cache: "no-store", signal: controller.signal,
          headers: { "Content-Type": "application/json", ...(csrf ? { "x-csrftoken": csrf } : {}) },
          body: JSON.stringify({ query: queryText, variables }) });
        if (!response.ok) {
          providerStopped = [403, 429].includes(response.status);
          throw new Error(response.status === 401 ? "Sign in to LeetCode again before importing."
            : `LeetCode history is unavailable (HTTP ${response.status}). Try again later.`);
        }
        const raw = await response.text();
        if (raw.length > 5000000) throw new Error("LeetCode returned too much history in one response.");
        const payload = JSON.parse(raw);
        if (payload.errors?.length || !payload.data) throw new Error("LeetCode could not return this history query.");
        account(payload.data, handle);
        return payload.data;
      } finally { clearTimeout(timer); }
    }

    async function acceptances(handle, sourceId, minimumTime = null, progress = null) {
      let offset = minimumTime === null ? progress?.offset || 0 : 0;
      let lastKey = minimumTime === null ? progress?.lastKey || null : null;
      let earliest = minimumTime === null ? progress?.earliest || null : null;
      if (progress?.complete && minimumTime === null) return { evidence: earliest, progress };
      const cursors = new Set();
      if (lastKey) cursors.add(lastKey);
      let complete = false;
      let warning = null;
      // Later imports resume this question's older pages instead of repeating its first two.
      for (let page = 0; page < 2; page++) {
        let data;
        try { data = await query(submissionsQuery, { questionSlug: sourceId, offset, limit: 20, lastKey }, handle); }
        catch (error) {
          if (page === 0 || /signed in|Sign in|different profile/.test(error.message)) throw error;
          warning = "Some older submission pages could not be read. Earlier observed acceptances are retained.";
          break;
        }
        const history = data.questionSubmissionList;
        if (!Array.isArray(history?.submissions) || typeof history.hasNext !== "boolean") throw new Error("LeetCode submission history changed.");
        for (const row of history.submissions) {
          const evidence = accepted(row, sourceId);
          if (evidence && (minimumTime === null || Date.parse(evidence.solved_at) >= minimumTime) &&
              (!earliest || evidence.solved_at < earliest.solved_at)) earliest = evidence;
        }
        if (!history.hasNext || minimumTime !== null) { complete = !history.hasNext; break; }
        if (!history.submissions.length || (history.lastKey && cursors.has(history.lastKey))) throw new Error("LeetCode repeated a submission cursor.");
        if (history.lastKey) cursors.add(history.lastKey);
        offset += history.submissions.length;
        lastKey = history.lastKey || null;
      }
      return { evidence: earliest, progress: { offset, lastKey, earliest, complete }, warning };
    }

    async function publicMetadata(handle, sourceId) {
      const data = await query(metadataQuery, { titleSlug: sourceId }, handle);
      const value = data.question;
      if (value == null) return null;
      if (value.titleSlug !== sourceId || !Array.isArray(value.topicTags)) throw new Error("LeetCode returned unexpected question metadata.");
      const statement = value.isPaidOnly === false ? parseStatement(value.content) : null;
      return { difficulty: ["Easy", "Medium", "Hard"].includes(value.difficulty) ? value.difficulty : null,
        topics: [...new Set(value.topicTags.map(tag => tag.name).filter(name => typeof name === "string" && name.length > 0 && name.length <= 128))].slice(0, 50),
        statement, ...(statement ? { public_statement: true } : {}) };
    }

    function savedDates(value) {
      if (!value || typeof value !== "object" || Array.isArray(value)) return {};
      const result = {};
      for (const [key, progress] of Object.entries(value).slice(-5000)) {
        if (!/^[a-z0-9-]{1,160}$/.test(key) || !Number.isSafeInteger(progress?.offset) || progress.offset < 0 ||
            progress.offset > 1000000 || typeof progress.complete !== "boolean" ||
            (progress.lastKey != null && (typeof progress.lastKey !== "string" || progress.lastKey.length > 1024))) continue;
        let earliest = null;
        const instant = Date.parse(progress.earliest?.solved_at);
        if (progress.earliest?.source_id === key && /^[1-9][0-9]{0,24}$/.test(progress.earliest.submission_id) &&
            typeof progress.earliest.solved_at === "string" && /Z$/.test(progress.earliest.solved_at) &&
            Number.isFinite(instant) && instant >= Date.UTC(2010, 0, 1) && instant <= Date.now() + 300000) {
          earliest = { source_id: key, submission_id: progress.earliest.submission_id, solved_at: progress.earliest.solved_at };
        }
        result[key] = { offset: progress.offset, lastKey: progress.lastKey || null, complete: progress.complete, earliest };
      }
      return result;
    }

    async function collect({ handle, cursor = 0, dateOffset = 0, dateProgress = {}, metadataOffset = 0 }) {
      providerStopped = false;
      if (typeof handle !== "string" || !/^[A-Za-z0-9_.-]{2,64}$/.test(handle) ||
          !Number.isSafeInteger(cursor) || cursor < 0 || !Number.isSafeInteger(dateOffset) || dateOffset < 0 ||
          !Number.isSafeInteger(metadataOffset) || metadataOffset < 0) {
        throw new Error("Invalid linked account or import cursor.");
      }
      const profile = await query(profileQuery, { username: handle }, handle);
      if (profile.matchedUser?.username?.toLowerCase() !== handle.toLowerCase()) throw new Error("LeetCode returned a different profile.");
      const total = profile.matchedUser.submitStatsGlobal?.acSubmissionNum?.find(item => item.difficulty === "All")?.count;
      if (!Number.isSafeInteger(total) || total < 0) throw new Error("LeetCode solved totals are unavailable.");
      const records = new Map();
      let exhausted = false, nextCursor = cursor;
      for (let page = 0; page < 20; page++) {
        const data = await query(questionsQuery, { filters: { questionStatus: "SOLVED", skip: nextCursor, limit: 100 } }, handle);
        const rows = data.userProgressQuestionList?.questions;
        if (!Array.isArray(rows) || rows.length > 100) throw new Error("LeetCode solved-question history changed.");
        for (const row of rows) {
          const item = question(row);
          if (records.has(item.source_id)) throw new Error("LeetCode repeated a solved-question page. Retry from the start.");
          records.set(item.source_id, item);
        }
        nextCursor += rows.length;
        if (rows.length < 100) { exhausted = true; break; }
      }
      const items = [...records.values()];
      const dates = savedDates(dateProgress);
      let dateChecks = 0;
      let dateWarning = null;
      // Repeated imports advance date enrichment rather than querying only the first questions.
      for (let index = 0; index < Math.min(20, items.length); index++) {
        const item = items[(dateOffset + index) % items.length];
        try {
          const { evidence, progress, warning } = await acceptances(handle, item.source_id, null, dates[item.source_id]);
          dates[item.source_id] = progress;
          dateChecks++;
          if (evidence) Object.assign(item, evidence);
          if (warning) { dateWarning = warning; break; }
        } catch (error) {
          // A changed/logged-out account must never attach another user's dates.
          if (/signed in|Sign in|different profile/.test(error.message)) throw error;
          dateWarning = "Some submission dates could not be read. Question names are still imported.";
          break;
        }
      }
      let metadataChecks = 0, metadataWarning = null;
      for (let index = 0; !providerStopped && index < Math.min(20, items.length); index++) {
        const item = items[(metadataOffset + index) % items.length];
        try {
          const metadata = await publicMetadata(handle, item.source_id);
          if (metadata) Object.assign(item, metadata);
          metadataChecks++;
        } catch (error) {
          if (/signed in|Sign in|different profile/.test(error.message)) throw error;
          metadataWarning = "Some public question text could not be read. Saved names and dates are retained.";
          break;
        }
      }
      // Check identity once more after a long import before handing any data to the app.
      if (!providerStopped) await query(`query OwnerIdentity { ${statusFields} }`, {}, handle);
      return { handle, questions: items, source_total_solved: total, next_cursor: exhausted ? null : nextCursor,
        date_offset: dateOffset + dateChecks, date_progress: Object.fromEntries(Object.entries(dates).slice(-5000)),
        metadata_offset: metadataOffset + metadataChecks,
        dated_history_checked: Object.values(dates).filter(value => value.complete).length,
        warning: [dateWarning, metadataWarning].filter(Boolean).join(" ") || null };
    }

    async function capture({ handle, problem, since }) {
      providerStopped = false;
      if (problem?.platform !== "leetcode" || !/^[a-z0-9-]{1,160}$/.test(problem.source_id) ||
          !Number.isFinite(since) || typeof problem.title !== "string") throw new Error("Invalid acceptance request.");
      const { evidence } = await acceptances(handle, problem.source_id, since - 5000);
      if (!evidence) return null;
      const profile = await query(profileQuery, { username: handle }, handle);
      if (profile.matchedUser?.username?.toLowerCase() !== handle.toLowerCase()) throw new Error("LeetCode returned a different profile.");
      const total = profile.matchedUser.submitStatsGlobal?.acSubmissionNum?.find(item => item.difficulty === "All")?.count;
      let metadata = null;
      try { metadata = await publicMetadata(handle, problem.source_id); }
      catch (error) { if (/signed in|Sign in|different profile/.test(error.message)) throw error; }
      return { handle, questions: [{ ...evidence, title: problem.title, ...metadata }],
        source_total_solved: Number.isSafeInteger(total) && total >= 0 ? total : null };
    }
    return { collect, capture };
  }
  globalThis.PF_HISTORY = { account, accepted, question, createClient };
})();
