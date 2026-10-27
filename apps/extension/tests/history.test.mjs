import test from "node:test";
import assert from "node:assert/strict";
import "../src/history.js";
const history = globalThis.PF_HISTORY;
const userStatus = { isSignedIn: true, username: "sample_user" };
const epoch = date => String(Date.parse(date) / 1000);

function client(handler, options = {}) {
  const calls = [];
  const instance = history.createClient({ ...options, pause: async () => {}, cookie: () => "csrftoken=local-only; other=value",
    fetch: async (url, options) => {
      const body = JSON.parse(options.body); calls.push({ url, options, body });
      const data = await handler(body, calls);
      return { ok: true, text: async () => JSON.stringify({ data: { userStatus, ...data } }) };
    } });
  return { instance, calls };
}

const profile = total => ({ matchedUser: { username: "sample_user", submitStatsGlobal: { acSubmissionNum: [{ difficulty: "All", count: total }] } } });
const row = (slug, overrides = {}) => ({ title: slug.replaceAll("-", " "), titleSlug: slug, questionStatus: "SOLVED", ...overrides });
const submission = (slug, overrides = {}) => ({ id: "123", titleSlug: slug, statusDisplay: "Accepted", isPending: false,
  timestamp: epoch("2025-01-01T08:00:00Z"), ...overrides });

test("owner imports solved names and actual Accepted dates, never last-submitted dates", async () => {
  const h = client(body => {
    if (body.query.includes("matchedUser")) return profile(2);
    if (body.query.includes("userProgressQuestionList")) return { userProgressQuestionList: { questions: [
      row("two-sum", { lastSubmittedAt: "2026-01-01", lastResult: "WRONG_ANSWER" }), row("add-two-numbers"),
    ] } };
    if (body.query.includes("questionSubmissionList")) return { questionSubmissionList: { hasNext: false, lastKey: null,
      submissions: body.variables.questionSlug === "two-sum" ? [
        submission("two-sum", { id: "456", timestamp: epoch("2026-01-01T08:00:00Z") }), submission("two-sum"),
        submission("two-sum", { id: "2", statusDisplay: "Wrong Answer", timestamp: epoch("2024-01-01T08:00:00Z") }),
      ] : [] } };
    return {};
  });
  const result = await h.instance.collect({ handle: "sample_user" });
  assert.equal(result.questions.length, 2);
  assert.equal(result.source_total_solved, 2);
  assert.equal(result.next_cursor, null);
  assert.equal(result.questions[0].solved_at, "2025-01-01T08:00:00.000Z");
  assert.equal(result.questions[0].submission_id, "123");
  assert.equal(result.questions[1].solved_at, null);
  assert.equal(result.questions[1].submission_id, null);
  assert.ok(h.calls.every(call => call.options.credentials === "include" && call.url === "/graphql/"));
  assert.ok(h.calls.every(call => call.options.headers["x-csrftoken"] === "local-only"));
  assert.equal(JSON.stringify(result).includes("local-only"), false);
});

test("every query checks account identity and refuses anonymous or changed users", async () => {
  for (const status of [{ isSignedIn: false }, { isSignedIn: true, username: "OtherUser" }]) {
    const h = client(() => ({ ...profile(2), userStatus: status }));
    await assert.rejects(h.instance.collect({ handle: "sample_user" }), /Sign in|signed in/);
    assert.equal(h.calls.length, 1);
  }
  let changed = false;
  const h = client(body => {
    if (body.query.includes("matchedUser")) return profile(1);
    if (body.query.includes("userProgressQuestionList")) return { userProgressQuestionList: { questions: [row("two-sum")] } };
    changed = true;
    return { userStatus: { isSignedIn: true, username: "OtherUser" }, questionSubmissionList: { hasNext: false, submissions: [submission("two-sum")] } };
  });
  await assert.rejects(h.instance.collect({ handle: "sample_user" }), /signed in/);
  assert.equal(changed, true);
});

test("paginated names survive unavailable dates and later imports advance date enrichment", async () => {
  const names = Array.from({ length: 101 }, (_, index) => `problem-${index}`);
  const h = client(body => {
    if (body.query.includes("matchedUser")) return profile(101);
    if (body.query.includes("userProgressQuestionList")) {
      const skip = body.variables.filters.skip;
      return { userProgressQuestionList: { questions: names.slice(skip, skip + 100).map(name => row(name)) } };
    }
    if (body.query.includes("questionSubmissionList")) return { questionSubmissionList: { hasNext: false, submissions: [submission(body.variables.questionSlug)] } };
    return {};
  });
  const first = await h.instance.collect({ handle: "sample_user" });
  assert.equal(first.questions.length, 101);
  assert.equal(first.questions.filter(item => item.solved_at).length, 20);
  assert.equal(first.date_offset, 20);
  const second = await h.instance.collect({ handle: "sample_user", dateOffset: first.date_offset });
  assert.equal(second.questions[0].solved_at, null);
  assert.equal(second.questions[20].solved_at, "2025-01-01T08:00:00.000Z");
  const unavailable = client(body => {
    if (body.query.includes("matchedUser")) return profile(1);
    if (body.query.includes("userProgressQuestionList")) return { userProgressQuestionList: { questions: [row("two-sum")] } };
    if (body.query.includes("questionSubmissionList")) throw new Error("Submission dates unavailable");
    return {};
  });
  const partial = await unavailable.instance.collect({ handle: "sample_user" });
  assert.equal(partial.questions.length, 1);
  assert.equal(partial.questions[0].solved_at, null);
  assert.match(partial.warning, /dates could not be read/);
});

test("visits, old acceptances, pending results and wrong answers cannot capture a new solve", async () => {
  const since = Date.parse("2025-01-01T09:00:00Z");
  let rows = [submission("two-sum"), submission("two-sum", { id: "456", statusDisplay: "Wrong Answer", timestamp: String(since / 1000) })];
  const h = client(body => body.query.includes("matchedUser") ? profile(1) : ({ questionSubmissionList: { hasNext: false, submissions: rows } }));
  const problem = { platform: "leetcode", source_id: "two-sum", title: "Two Sum" };
  assert.equal(await h.instance.capture({ handle: "sample_user", problem, since }), null);
  rows = [submission("two-sum", { id: "789", timestamp: String(since / 1000), isPending: true })];
  assert.equal(await h.instance.capture({ handle: "sample_user", problem, since }), null);
  rows[0].isPending = false;
  const result = await h.instance.capture({ handle: "sample_user", problem, since });
  assert.equal(result.questions[0].submission_id, "789");
  assert.equal(result.questions[0].solved_at, "2025-01-01T09:00:00.000Z");
  assert.equal(result.source_total_solved, 1);
});

test("malformed and repeated question pages fail instead of claiming complete history", async () => {
  assert.throws(() => history.question(row("two-sum", { questionStatus: "ATTEMPTED" })), /unexpected solved question/);
  assert.equal(history.accepted(submission("two-sum", { timestamp: "unknown" }), "two-sum"), null);
  assert.equal(history.accepted(submission("other-question"), "two-sum"), null);
  const names = Array.from({ length: 100 }, (_, index) => row(`problem-${index}`));
  const h = client(body => body.query.includes("matchedUser") ? profile(101) : { userProgressQuestionList: { questions: names } });
  await assert.rejects(h.instance.collect({ handle: "sample_user" }), /repeated a solved-question page/);
});

test("older Accepted pages resume across imports until available history is exhausted", async () => {
  const offsets = [];
  const h = client(body => {
    if (body.query.includes("matchedUser")) return profile(1);
    if (body.query.includes("userProgressQuestionList")) return { userProgressQuestionList: { questions: [row("two-sum")] } };
    if (body.query.includes("questionSubmissionList")) {
      const offset = body.variables.offset; offsets.push(offset);
      return { questionSubmissionList: { hasNext: offset < 2, lastKey: offset < 2 ? `key-${offset}` : null,
        submissions: [submission("two-sum", { id: String(300 - offset * 100), timestamp: epoch(`${2026 - offset}-01-01T08:00:00Z`) })] } };
    }
    return {};
  });
  const first = await h.instance.collect({ handle: "sample_user" });
  assert.equal(first.questions[0].solved_at, "2025-01-01T08:00:00.000Z");
  assert.equal(first.date_progress["two-sum"].complete, false);
  const second = await h.instance.collect({ handle: "sample_user", dateProgress: first.date_progress, dateOffset: first.date_offset });
  assert.equal(second.questions[0].solved_at, "2024-01-01T08:00:00.000Z");
  assert.equal(second.dated_history_checked, 1);
  await h.instance.collect({ handle: "sample_user", dateProgress: second.date_progress });
  assert.deepEqual(offsets, [0, 1, 2]);
});

test("browser metadata imports public statements but excludes premium text", async () => {
  const parsed = [];
  const h = client(body => {
    if (body.query.includes("matchedUser")) return profile(2);
    if (body.query.includes("userProgressQuestionList")) return { userProgressQuestionList: { questions: [row("two-sum"), row("premium-question")] } };
    if (body.query.includes("questionSubmissionList")) return { questionSubmissionList: { hasNext: false, submissions: [] } };
    if (body.query.includes("OwnerPublicProblem")) return { question: { titleSlug: body.variables.titleSlug, difficulty: "Easy",
      isPaidOnly: body.variables.titleSlug === "premium-question", content: body.variables.titleSlug === "premium-question" ? "Private premium content" : "Public statement",
      topicTags: [{ name: "Array" }] } };
    return {};
  }, { parseStatement: value => { parsed.push(value); return value; } });
  const result = await h.instance.collect({ handle: "sample_user" });
  assert.equal(result.questions[0].statement, "Public statement");
  assert.equal(result.questions[0].public_statement, true);
  assert.equal(result.questions[1].statement, null);
  assert.deepEqual(parsed, ["Public statement"]);
  assert.equal(JSON.stringify(result).includes("Private premium content"), false);
});

test("an older-page failure retains the verified earlier acceptance and a resume cursor", async () => {
  const h = client(body => {
    if (body.query.includes("matchedUser")) return profile(1);
    if (body.query.includes("userProgressQuestionList")) return { userProgressQuestionList: { questions: [row("two-sum")] } };
    if (body.query.includes("questionSubmissionList")) {
      if (body.variables.offset > 0) throw new Error("Older page unavailable");
      return { questionSubmissionList: { hasNext: true, lastKey: "next", submissions: [submission("two-sum")] } };
    }
    return {};
  });
  const result = await h.instance.collect({ handle: "sample_user" });
  assert.equal(result.questions[0].solved_at, "2025-01-01T08:00:00.000Z");
  assert.equal(result.date_progress["two-sum"].offset, 1);
  assert.equal(result.date_progress["two-sum"].complete, false);
  assert.match(result.warning, /Earlier observed acceptances are retained/);
});
