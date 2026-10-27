import test from "node:test";
import assert from "node:assert/strict";
import "../src/core.js";
const core = globalThis.PF_CORE;

test("platform identity survives alternate problem routes, query strings and tabs", () => {
  assert.equal(core.identify("https://leetcode.com/problems/two-sum/description/?envType=daily-question").source_id, "two-sum");
  assert.equal(core.identify("https://leetcode.com/contest/weekly-contest-2/problems/two-sum/").canonical_url, "https://leetcode.com/problems/two-sum/");
  assert.equal(core.identify("https://practice.geeksforgeeks.org/problems/find-pair0000/1").source_id, "find-pair0000");
  assert.deepEqual(core.identify("https://codeforces.com/contest/100/problem/A"), core.identify("https://mirror.codeforces.com/problemset/problem/100/A?locale=en"));
  assert.equal(core.identify("https://codeforces.com/gym/123456/problem/B2").source_id, "123456-B2");
});

test("nonproblem pages, lookalike hosts, insecure URLs and credentials cannot initiate checks", () => {
  for (const url of ["https://leetcode.com/problem-list/array/", "https://leetcode.com.evil.test/problems/two-sum/",
    "https://evil.test/leetcode.com/problems/two-sum/", "http://leetcode.com/problems/two-sum/",
    "https://user@leetcode.com/problems/two-sum/", "https://leetcode.com:8443/problems/two-sum/",
    "https://codeforces.com/profile/handle", "https://www.geeksforgeeks.org/user/handle", "not a URL"]) assert.equal(core.identify(url), null, url);
});

test("attempt links prefer valid original submissions and reject unsafe redirects", () => {
  const attempt = { platform: "leetcode", submission_url: "https://leetcode.com/submissions/detail/123/", problem_url: "https://leetcode.com/problems/two-sum/" };
  assert.equal(core.attemptUrl(attempt), attempt.submission_url);
  assert.equal(core.attemptUrl({ ...attempt, submission_url: "javascript:alert(1)" }), attempt.problem_url);
  assert.equal(core.attemptUrl({ ...attempt, submission_url: "https://evil.test/", problem_url: "https://leetcode.com.evil.test/" }), null);
  assert.equal(core.attemptUrl({ ...attempt, submission_url: "https://user:password@leetcode.com/", problem_url: null }), null);
});

test("unavailable matching never claims that an opened question is new", () => {
  assert.match(core.describe({ duplicate: false, status: "matching_disabled" }), /No exact match.*after the model is enabled/);
  assert.match(core.describe({ duplicate: false, status: "insufficient_data" }), /unavailable/);
  assert.match(core.describe({ duplicate: true, status: "source_identity" }), /solved history/);
});
