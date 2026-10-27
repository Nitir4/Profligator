import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const token = "pfext_" + "a".repeat(64);
const otherToken = "pfext_" + "b".repeat(64);
const popup = { id: "extension", url: "chrome-extension://extension/popup.html" };
const pairing = { id: "extension", frameId: 0, tab: { id: 2 }, url: "http://localhost:5173/extension/connect" };
const source = { id: "extension", frameId: 0, tab: { id: 1 }, url: "https://leetcode.com/problem-list/array/" };
const problem = { platform: "leetcode", source_id: "three-sum", canonical_url: "https://leetcode.com/problems/three-sum/",
  title: "Three Sum", statement: "Find triples.", topics: [] };

function harness() {
  let listener;
  let release;
  let hold = false;
  let checks = 0;
  const data = {};
  const calls = [];
  let alarmListener;
  const alarms = new Map();
  const profiles = [
    { profile_id: "lc", platform: "leetcode", handle: "candidate" },
    { profile_id: "gfg", platform: "geeksforgeeks", handle: "candidate" },
    { profile_id: "cf", platform: "codeforces", handle: "candidate" },
  ];
  const tabs = new Map([[1, { id: 1, url: "https://leetcode.com/problems/three-sum/description/" }],
    [3, { id: 3, url: "https://www.geeksforgeeks.org/problems/key-pair5616/1" }],
    [4, { id: 4, url: "https://codeforces.com/problemset/problem/100/A" }]]);
  const context = vm.createContext({ URL, AbortController, setTimeout, clearTimeout, console,
    PF_CONFIG: { webOrigin: "http://localhost:5173", apiOrigin: "http://localhost:5173", platformPatterns: ["https://leetcode.com/*"] },
    chrome: {
      runtime: { id: "extension", getURL: path => `chrome-extension://extension/${path}`, onMessage: { addListener: fn => { listener = fn; } } },
      storage: { local: {
        setAccessLevel: async () => {}, get: async key => ({ [key]: data[key] }),
        set: async value => { Object.assign(data, value); }, remove: async key => { delete data[key]; },
      } },
      alarms: { create: async (name, value) => { alarms.set(name, value); }, onAlarm: { addListener: fn => { alarmListener = fn; } } },
      tabs: { get: async id => tabs.get(id), query: async () => [], sendMessage: async (id, message) => ({ ok: true, value:
        message.type === "PF_READ_ACCEPTANCE" ? { handle: "candidate", questions: [{ source_id: "three-sum", title: "Three Sum",
          solved_at: "2025-01-01T08:00:00Z", submission_id: "123" }] } : { handle: "candidate", source_total_solved: 1,
          questions: [{ source_id: "three-sum", title: "Three Sum", solved_at: "2025-01-01T08:00:00Z", submission_id: "123", code: "never transmit" }],
          next_cursor: null, date_offset: 1 } }) },
    },
    fetch: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith("/history/profiles")) return { ok: true, json: async () => profiles };
      if (url.endsWith("/history/browser") || url.endsWith("/history/provider")) return { ok: true, json: async () => ({
        status: "succeeded", questions: 1, records_written: 1, timestamped_questions: 1,
      }) };
      if (url.endsWith("/check")) {
        checks++;
        if (hold) await new Promise(resolve => { release = resolve; });
        return { ok: true, json: async () => ({ duplicate: true, status: "exact" }) };
      }
      return { ok: true, json: async () => ({ handle: "candidate", session_id: "device", expires_at: "2099-01-01T00:00:00Z" }) };
    },
  });
  for (const name of ["core.js", "background.js"]) vm.runInContext(readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8"), context);
  return {
    send: (message, sender) => new Promise(resolve => listener(message, sender, resolve)),
    connect: async (value = token) => new Promise(resolve => listener({ type: "PF_CONNECT", grant: { token: value } }, pairing, resolve)),
    hold: () => { hold = true; }, release: () => { hold = false; release(); },
    calls, data, checks: () => checks, alarms, profiles, tabs,
    fireAlarm: async name => { alarmListener({ name }); await new Promise(resolve => setTimeout(resolve, 20)); },
  };
}

test("only the trusted application can connect and only the popup can read connection status", async () => {
  const h = harness();
  assert.equal((await h.send({ type: "PF_CONNECT", grant: { token } }, source)).ok, false);
  assert.equal(h.calls.length, 0);
  assert.equal((await h.connect()).ok, true);
  const state = await h.send({ type: "PF_STATE" }, popup);
  assert.equal(state.value.connected, true);
  assert.equal("token" in state.value, false);
  assert.equal((await h.send({ type: "PF_STATE" }, source)).ok, false);
  assert.equal((await h.send({ type: "PF_DISCONNECT" }, source)).ok, false);
  assert.equal(h.data.profligatorSession.token, token);
});

test("history controls are popup-only, whitelist browser data, and support every linked platform", async () => {
  const h = harness(); await h.connect();
  assert.equal((await h.send({ type: "PF_HISTORY_STATE" }, source)).ok, false);
  assert.equal((await h.send({ type: "PF_HISTORY_IMPORT", profile_id: "lc", tab_id: 1 }, source)).ok, false);
  assert.equal((await h.send({ type: "PF_TRACK", profile_id: "lc", enabled: true }, source)).ok, false);
  const imported = await h.send({ type: "PF_HISTORY_IMPORT", profile_id: "lc", tab_id: 1 }, popup);
  assert.equal(imported.ok, true);
  const browserRequest = h.calls.find(call => call.url.endsWith("/history/browser"));
  assert.equal(browserRequest.options.credentials, "omit");
  assert.equal(browserRequest.options.body.includes("never transmit"), false);
  assert.equal(browserRequest.options.body.includes("submission_id"), true);
  for (const profile_id of ["gfg", "cf"]) {
    assert.equal((await h.send({ type: "PF_HISTORY_IMPORT", profile_id }, popup)).ok, true);
    assert.equal((await h.send({ type: "PF_TRACK", profile_id, enabled: true }, popup)).ok, true);
  }
  assert.equal(h.calls.filter(call => call.url.endsWith("/history/provider")).length, 2);
  assert.equal((await h.send({ type: "PF_HISTORY_IMPORT", profile_id: "someone-else" }, popup)).ok, false);
});

test("tracking requires opt-in, survives navigation, and stops after disable or disconnect", async () => {
  const h = harness(); await h.connect();
  assert.equal((await h.send({ type: "PF_ARM_TRACKING", problem }, source)).value.enabled, false);
  assert.equal(h.alarms.size, 0);
  await h.send({ type: "PF_TRACK", profile_id: "lc", enabled: true }, popup);
  assert.equal((await h.send({ type: "PF_ARM_TRACKING", problem }, source)).value.enabled, true);
  const alarm = "pf-acceptance:leetcode:three-sum";
  assert.equal(h.alarms.has(alarm), true);
  h.tabs.set(1, { id: 1, url: "https://leetcode.com/submissions/" });
  await h.fireAlarm(alarm);
  assert.equal(h.calls.filter(call => call.url.endsWith("/history/browser")).length, 1);
  assert.equal(Object.keys(h.data.profligatorHistory.pending).length, 0);
  h.tabs.set(1, { id: 1, url: "https://leetcode.com/problems/three-sum/" });
  await h.send({ type: "PF_ARM_TRACKING", problem }, source);
  await h.send({ type: "PF_TRACK", profile_id: "lc", enabled: false }, popup);
  await h.fireAlarm(alarm);
  assert.equal(h.calls.filter(call => call.url.endsWith("/history/browser")).length, 1);
  await h.send({ type: "PF_DISCONNECT" }, popup);
  assert.equal(h.data.profligatorHistory, undefined);
  await h.fireAlarm(alarm);
  assert.equal(h.calls.filter(call => call.url.endsWith("/history/browser")).length, 1);
});

test("checks use the current tab after SPA navigation and cannot spoof a question or frame", async () => {
  const h = harness(); await h.connect();
  const response = await h.send({ type: "PF_CHECK", problem }, source);
  assert.equal(response.ok, true);
  assert.equal(h.checks(), 1);
  assert.equal(h.calls.at(-1).options.credentials, "omit");
  assert.equal((await h.send({ type: "PF_CHECK", problem: { ...problem, source_id: "two-sum" } }, source)).ok, false);
  assert.equal((await h.send({ type: "PF_CHECK", problem }, { ...source, frameId: 1 })).ok, false);
  assert.equal((await h.send({ type: "PF_CHECK", problem }, { ...source, url: "https://evil.test/" })).ok, false);
  assert.equal(h.checks(), 1);
});

test("overlapping checks share a request and an account change discards the old result", async () => {
  const h = harness(); await h.connect(); h.hold();
  const first = h.send({ type: "PF_CHECK", problem }, source);
  const second = h.send({ type: "PF_CHECK", problem }, source);
  while (!h.checks()) await new Promise(resolve => setTimeout(resolve, 1));
  await h.connect(otherToken);
  assert.equal(h.checks(), 1);
  h.release();
  assert.equal((await first).value.duplicate, false);
  assert.equal((await second).value.status, "sign_in_required");
  assert.equal(h.data.profligatorSession.token, otherToken);
});
