"""Installed Chromium extension acceptance against an isolated API and controlled pages.

Requires Playwright's Python package and a local Chromium executable. No platform
requests, real-account credentials, or application database are used.
"""
import asyncio
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from urllib.request import urlopen

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
STATEMENT = "Return the sum of two integers. Example: 1 + 2 = 3. Constraints: 0 <= a, b <= 100."


def port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def ready(url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited with code {process.returncode}; command: {process.args}")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(.15)
    raise TimeoutError(url)


async def main() -> None:
    global OUTPUT
    OUTPUT = Path(tempfile.mkdtemp(prefix="profligator-extension-check-"))
    web_port, api_port = port(), port()
    web_origin = f"http://localhost:{web_port}"
    build_env = {**os.environ, "PROFLIGATOR_EXTENSION_WEB_ORIGIN": web_origin,
                 "PROFLIGATOR_EXTENSION_OUTPUT_DIR": str(OUTPUT / "extension")}
    subprocess.run(["npm", "run", "extension:build"], cwd=ROOT, env=build_env, check=True,
                   stdout=(OUTPUT / "build.log").open("w"), stderr=subprocess.STDOUT)
    server_file = OUTPUT / "server.py"
    provider_state = OUTPUT / "provider-state.json"
    provider_state.write_text(json.dumps({"gfg": False, "cf": False}))
    server_file.write_text(f'''
import sys
sys.path.insert(0, {str(ROOT / "apps/api/src")!r})
from profligator_api.config import Settings
from profligator_api.main import create_app
from profligator_api.database import Database
from profligator_api.repository import Repository
from profligator_api.security import hash_password
from profligator_api.connectors.base import payload_checksum
from profligator_api.schemas import CanonicalProfile, ConnectorMode, NormalizedRecord, Platform
from profligator_api.schemas import ConnectorPage, ProfileSnapshot
from profligator_api import extension_history
from datetime import UTC, datetime
import json
from pathlib import Path
settings = Settings(_env_file=None, database_url={"sqlite:///" + str(OUTPUT / "test.db")!r},
    public_web_url={web_origin!r}, cors_origins=[{web_origin!r}],
    leetcode_connector="fixture", geeksforgeeks_connector="fixture", extension_history_cooldown_seconds=0)
class HistoryProvider:
    def __init__(self, platform): self.platform = platform
    async def fetch_profile(self, profile):
        return ProfileSnapshot(profile=profile, fetched_at=datetime.now(UTC), source_total_solved=2, history_complete=True)
    async def fetch_solved_records(self, profile, cursor=None):
        state = json.loads(Path({str(provider_state)!r}).read_text())
        rows = []
        if self.platform == Platform.GEEKSFORGEEKS:
            values = [("sum-of-two-numbers0001", "Sum of Two Numbers", "2025-01-01T08:00:00")]
            if state["gfg"]: values.append(("key-pair5616", "Key Pair", "2026-10-03T10:00:00"))
            for source_id, title, local in values:
                rows.append(NormalizedRecord(platform=self.platform, source_id=source_id, title=title, kind="problem", status="solved",
                    canonical_url=f"https://www.geeksforgeeks.org/problems/{{source_id}}/1", source_solved_at=local, source_payload_checksum=source_id))
        else:
            values = [("100-A", "Theatre Square", datetime(2025, 1, 1, tzinfo=UTC))]
            if state["cf"]: values.append(("100-B", "New Codeforces Question", datetime.now(UTC)))
            for source_id, title, when in values:
                rows.append(NormalizedRecord(platform=self.platform, source_id=source_id, title=title, kind="problem", status="solved",
                    canonical_url=f"https://codeforces.com/problemset/problem/100/{{source_id[-1]}}", occurred_at=when,
                    source_payload_checksum=source_id, submission_url=f"https://codeforces.com/contest/100/submission/{{100 if source_id.endswith('A') else 101}}"))
        return ConnectorPage(records=rows)
class HistoryRegistry:
    def __init__(self, *args, **kwargs): pass
    def get(self, platform): return HistoryProvider(platform)
extension_history.ConnectorRegistry = HistoryRegistry
database = Database(settings.database_url)
database.initialize()
with database.session() as session:
    repository = Repository(session)
    user = repository.create_user(email="extension@example.com", handle="extension_test", password_hash=hash_password("ExtensionTest2026!"))
    for platform, host, source_id, title, statement, submission in [
        (Platform.LEETCODE, "leetcode.com", "two-sum", "Two Sum", {STATEMENT!r}, "https://leetcode.com/submissions/detail/123/"),
        (Platform.CODEFORCES, "codeforces.com", "100-A", "Theatre Square", "Tile a rectangle using squares.", None),
    ]:
        profile = repository.save_profile(user.id, CanonicalProfile(platform=platform, handle="extension_test", canonical_url=f"https://{{host}}/u/extension_test"), ConnectorMode.FIXTURE, live_data=False)
        canonical = "https://leetcode.com/problems/two-sum/" if platform == Platform.LEETCODE else "https://codeforces.com/problemset/problem/100/A"
        repository.upsert_records(profile.id, [NormalizedRecord(platform=platform, source_id=source_id, kind="problem", status="solved", title=title, canonical_url=canonical, statement=statement, submission_url=submission, source_payload_checksum="extension-test")])
    repository.save_profile(user.id, CanonicalProfile(platform=Platform.GEEKSFORGEEKS, handle="extension_test",
        canonical_url="https://www.geeksforgeeks.org/profile/extension_test"), ConnectorMode.FIXTURE, live_data=False)
database.dispose()
app = create_app(settings)
''')
    api_log = (OUTPUT / "api.log").open("w")
    web_log = (OUTPUT / "web.log").open("w")
    processes = []
    try:
        api_process = subprocess.Popen([str(ROOT / "apps/api/.venv/bin/python"), "-m", "uvicorn", "server:app",
            "--app-dir", str(OUTPUT), "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT,
            stdout=api_log, stderr=subprocess.STDOUT)
        processes.append(api_process)
        ready(f"http://127.0.0.1:{api_port}/health", api_process)
        web_process = subprocess.Popen(["node", str(ROOT / "node_modules/vite/bin/vite.js"),
            "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"], cwd=ROOT / "apps/web",
            env={**os.environ, "PROFLIGATOR_API_PORT": str(api_port)}, stdout=web_log, stderr=subprocess.STDOUT)
        processes.append(web_process)
        ready(web_origin, web_process)
        async with async_playwright() as playwright:
            extension = OUTPUT / "extension/chrome"
            browser = await playwright.chromium.launch_persistent_context(str(OUTPUT / "browser"),
                executable_path=shutil.which("chromium"), headless=True,
                args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"],
                viewport={"width": 1280, "height": 900})
            try:
                errors = []
                browser.on("page", lambda page: page.on("pageerror", lambda error: errors.append(str(error))))
                worker = browser.service_workers[0] if browser.service_workers else await browser.wait_for_event("serviceworker")
                extension_id = worker.url.split("/")[2]
                # Exercise native DOM parsing of formulas/images and reject stale CF headings.
                probe = await browser.new_page()
                await probe.set_content('<base href="https://codeforces.com/problemset/problem/4/A"><div class="problem-statement"><div class="header"><div class="title">A. Watermelon</div><div class="time-limit">time limit per test: 2 seconds</div><div class="memory-limit">memory limit per test: 256 megabytes</div></div><p>n &lt; 10<sup>2<sup>m</sup></sup></p><div>Input: n</div><div>Output: n</div><img src="/graph.png" alt="Graph"></div>')
                await probe.add_script_tag(path=str(ROOT / "apps/extension/src/core.js"))
                extracted = await probe.evaluate("PF_CORE.extract(document, 'https://codeforces.com/problemset/problem/4/A')")
                assert "10^(2^(m))" in extracted["statement"] and "https://codeforces.com/graph.png" in extracted["statement"]
                assert "Input: n" in extracted["statement"] and "Output: n" in extracted["statement"]
                assert "time limit per test: 2 seconds" in extracted["statement"] and "memory limit per test: 256 megabytes" in extracted["statement"]
                assert "Watermelon" not in extracted["statement"]
                assert await probe.evaluate("PF_CORE.extract(document, 'https://codeforces.com/problemset/problem/4/B')") is None
                await probe.close()
                lc_accepted = False
                async def fixture(route):
                    url = route.request.url
                    if "leetcode.com/graphql" in url:
                        body = route.request.post_data_json
                        query = body["query"]
                        data = {"userStatus": {"isSignedIn": True, "username": "extension_test"}}
                        if "matchedUser" in query:
                            data["matchedUser"] = {"username": "extension_test", "submitStatsGlobal": {"acSubmissionNum": [{"difficulty": "All", "count": 3 if lc_accepted else 2}]}}
                        if "userProgressQuestionList" in query:
                            data["userProgressQuestionList"] = {"questions": [{"titleSlug": slug, "title": title, "questionStatus": "SOLVED"}
                                for slug, title in [("two-sum", "Two Sum"), ("add-two-numbers", "Add Two Numbers")]]}
                        if "questionSubmissionList" in query:
                            slug = body["variables"]["questionSlug"]
                            timestamp = int(datetime.now(UTC).timestamp()) if slug == "three-sum" else 1735718400
                            rows = [{"id": "789" if slug == "three-sum" else "123", "titleSlug": slug,
                                     "statusDisplay": "Accepted", "timestamp": str(timestamp), "isPending": False}]
                            data["questionSubmissionList"] = {"hasNext": False, "lastKey": None,
                                "submissions": rows if slug != "three-sum" or lc_accepted else []}
                        if "OwnerPublicProblem" in query:
                            slug = body["variables"]["titleSlug"]
                            data["question"] = {"titleSlug": slug, "difficulty": "Easy", "isPaidOnly": False,
                                "content": f"<p>Public statement for {slug}.</p><p>Input: n. Output: result.</p>",
                                "topicTags": [{"name": "Array"}]}
                        return await route.fulfill(json={"data": data})
                    if "submissions/detail/123" in url:
                        return await route.fulfill(body="<h1>Recorded earlier submission</h1>", content_type="text/html")
                    if "leetcode.com" in url:
                        title = "Two Sum" if "/two-sum/" in url else "Three Sum"
                        statement = STATEMENT if title == "Two Sum" else "Find all triples whose sum is zero."
                        html = f'<title>{title} - LeetCode</title><h1 data-cy="question-title">1. {title}</h1><div data-track-load="description_content"><p>{statement}</p></div><button>Submit</button><button>Run</button>'
                    elif "geeksforgeeks.org" in url:
                        title = "Key Pair" if "key-pair5616" in url else "Sum of Two Numbers"
                        html = f'<title>{title} - GeeksforGeeks</title><h1 class="problems_header_content__title">{title}</h1><div class="problems_problem_content__test"><p>{STATEMENT}</p></div><button>Submit</button>'
                    else:
                        title = "B. New Codeforces Question" if url.endswith("/B") else "A. Theatre Square"
                        html = f'<title>Problem - Codeforces</title><div class="problem-statement"><div class="header"><div class="title">{title}</div></div><p>Tile a rectangle using squares.</p></div><button>Submit</button>'
                    await route.fulfill(body=html, content_type="text/html")
                for pattern in ["https://leetcode.com/**", "https://www.geeksforgeeks.org/**", "https://codeforces.com/**"]:
                    await browser.route(pattern, fixture)
                page = await browser.new_page()
                await page.goto(web_origin + "/extension/connect")
                await page.get_by_text("The extension is available in this browser.").wait_for()
                await page.get_by_text("Sign in with your existing Google or password account").wait_for()
                login = await browser.new_page()
                await login.goto(web_origin + "/login")
                await login.get_by_label("Email address").fill("extension@example.com")
                await login.get_by_label("Password", exact=True).fill("ExtensionTest2026!")
                await login.get_by_role("button", name="Sign In", exact=True).click()
                await login.wait_for_url("**/onboarding/profiles")
                await page.bring_to_front()
                await page.get_by_role("button", name="I’ve signed in — refresh").click()
                await page.get_by_role("button", name="Connect this browser", exact=True).click()
                await page.get_by_text("Browser connected. Open a supported question").wait_for()
                await page.screenshot(path=str(OUTPUT / "connection.png"))
                lc = await browser.new_page()
                await lc.goto("https://leetcode.com/problems/two-sum/description/")
                await lc.locator("#profligator-duplicate-alert").wait_for()
                await lc.screenshot(path=str(OUTPUT / "leetcode-alert.png"))
                async def snapshot(target):
                    return await worker.evaluate('''async (url) => {
                        const tabs = await chrome.tabs.query({});
                        const tab = tabs.find(tab => tab.url === url);
                        return chrome.tabs.sendMessage(tab.id, {type: "PF_SNAPSHOT"});
                    }''', target.url)
                result = await snapshot(lc)
                assert result["result"]["status"] == "source_identity", result
                # The installed popup gets current-tab data from the content script.
                popup = await browser.new_page()
                await popup.goto(f"chrome-extension://{extension_id}/popup.html")
                await lc.bring_to_front()
                await popup.reload()
                await popup.get_by_text("Connected as extension_test").wait_for()
                await popup.get_by_text("Already in your solved history").wait_for()
                assert await popup.locator("#attempt").get_attribute("href") == "https://leetcode.com/submissions/detail/123/"
                await popup.screenshot(path=str(OUTPUT / "popup.png"))
                # Exercise the rendered alert link and dismiss button through Chrome's
                # DOM protocol; the website cannot inspect the closed shadow root.
                cdp = await browser.new_cdp_session(lc)
                await cdp.send("DOM.enable")
                nodes = (await cdp.send("DOM.getFlattenedDocument", {"depth": -1, "pierce": True}))["nodes"]
                def node_with(attribute, value):
                    for node in nodes:
                        attrs = node.get("attributes", [])
                        if dict(zip(attrs[::2], attrs[1::2])).get(attribute) == value:
                            return node
                    raise AssertionError(f"Missing alert control: {attribute}={value}")
                async def click_node(node):
                    quad = (await cdp.send("DOM.getBoxModel", {"nodeId": node["nodeId"]}))["model"]["content"]
                    await lc.mouse.click((quad[0] + quad[4]) / 2, (quad[1] + quad[5]) / 2)
                await lc.bring_to_front()
                async with browser.expect_page() as opened:
                    await click_node(node_with("href", "https://leetcode.com/submissions/detail/123/"))
                previous = await opened.value
                await previous.wait_for_load_state()
                assert previous.url == "https://leetcode.com/submissions/detail/123/"
                await previous.close()
                await click_node(node_with("aria-label", "Dismiss Profligator alert"))
                await lc.locator("#profligator-duplicate-alert").wait_for(state="detached")
                await snapshot(lc)
                assert await lc.locator("#profligator-duplicate-alert").count() == 0
                # Client-side navigation must clear the preceding question's result,
                # even while that question's DOM is still on the page.
                await lc.evaluate("history.pushState({}, '', '/problems/three-sum/description/')")
                assert (await snapshot(lc))["result"]["status"] == "loading"
                await lc.evaluate("document.querySelector('h1').textContent = '15. Three Sum'; document.querySelector('[data-track-load]').textContent = 'Find all triples whose sum is zero.'")
                for _ in range(30):
                    current = await snapshot(lc)
                    if current["result"]["status"] == "matching_disabled": break
                    await asyncio.sleep(.1)
                assert current["result"]["status"] == "matching_disabled", current
                assert await lc.locator("#profligator-duplicate-alert").count() == 0
                gfg = await browser.new_page()
                await gfg.goto("https://www.geeksforgeeks.org/problems/sum-of-two-numbers0001/1")
                await gfg.locator("#profligator-duplicate-alert").wait_for()
                assert (await snapshot(gfg))["result"]["status"] == "exact"
                await gfg.screenshot(path=str(OUTPUT / "gfg-alert.png"))
                cf = await browser.new_page()
                await cf.goto("https://codeforces.com/contest/100/problem/A")
                await cf.locator("#profligator-duplicate-alert").wait_for()
                assert (await snapshot(cf))["result"]["previous_attempt"]["submission_url"] is None
                await cf.screenshot(path=str(OUTPUT / "codeforces-alert.png"))
                # Exercise the installed history UI, provider imports and dated acceptance tracking.
                await lc.bring_to_front()
                await popup.reload()
                accounts = popup.locator(".history-account")
                await accounts.filter(has_text="LeetCode · @extension_test").get_by_role("button", name="Import solved history").click()
                await accounts.filter(has_text="LeetCode · @extension_test").get_by_text("2 questions · 2 with dated acceptances", exact=False).wait_for(timeout=60000)
                await accounts.filter(has_text="LeetCode · @extension_test").get_by_text("2 with statements", exact=False).wait_for()
                for platform in ["GeeksforGeeks", "Codeforces"]:
                    account = accounts.filter(has_text=f"{platform} · @extension_test")
                    await account.get_by_role("button", name="Import solved history").click()
                    await account.get_by_text("1 question", exact=False).wait_for()
                await accounts.filter(has_text="GeeksforGeeks ·").get_by_text("time zone unspecified", exact=False).wait_for()
                await popup.screenshot(path=str(OUTPUT / "history-imports.png"))
                for platform in ["LeetCode", "GeeksforGeeks", "Codeforces"]:
                    await accounts.filter(has_text=f"{platform} ·").get_by_label("Track accepted submissions").check()
                await lc.bring_to_front()
                # Run never arms acceptance tracking; submitting creates a durable provider check.
                await lc.get_by_role("button", name="Run", exact=True).click()
                assert await worker.evaluate("async () => (await chrome.alarms.getAll()).length") == 0
                lc_accepted = True
                await lc.get_by_role("button", name="Submit", exact=True).click()
                await gfg.goto("https://www.geeksforgeeks.org/problems/key-pair5616/1")
                await gfg.get_by_role("button", name="Submit", exact=True).click()
                await cf.goto("https://codeforces.com/problemset/problem/100/B")
                await cf.get_by_role("button", name="Submit", exact=True).click()
                provider_state.write_text(json.dumps({"gfg": True, "cf": True}))
                # Codeforces navigates after submitting; its confirmation still uses the linked handle.
                await cf.goto("https://codeforces.com/submissions/extension_test")
                deadline = time.monotonic() + 80
                while time.monotonic() < deadline:
                    stored = await worker.evaluate("async () => (await chrome.storage.local.get('profligatorHistory')).profligatorHistory")
                    if not stored.get("pending"):
                        break
                    await asyncio.sleep(.5)
                assert not stored.get("pending"), stored
                await popup.reload()
                await accounts.filter(has_text="LeetCode ·").get_by_text("3 questions · 3 with dated acceptances", exact=False).wait_for()
                await accounts.filter(has_text="GeeksforGeeks ·").get_by_text("2 questions", exact=False).wait_for()
                await accounts.filter(has_text="Codeforces ·").get_by_text("2 questions · 2 with dated acceptances", exact=False).wait_for()
                await accounts.filter(has_text="GeeksforGeeks ·").get_by_text("1 with statements", exact=False).wait_for()
                await accounts.filter(has_text="Codeforces ·").get_by_text("2 with statements", exact=False).wait_for()
                await popup.screenshot(path=str(OUTPUT / "history-tracking.png"))
                live = []
                if "--live" in sys.argv:
                    for pattern in ["https://leetcode.com/**", "https://www.geeksforgeeks.org/**", "https://codeforces.com/**"]:
                        await browser.unroute(pattern, fixture)
                    for label, url in [("leetcode", "https://leetcode.com/problems/two-sum/description/"),
                                       ("gfg", "https://www.geeksforgeeks.org/problems/key-pair5616/1"),
                                       ("codeforces", "https://codeforces.com/problemset/problem/100/A")]:
                        target = await browser.new_page()
                        try:
                            response = await target.goto(url, wait_until="domcontentloaded", timeout=25000)
                            observed = None
                            for _ in range(10):
                                try:
                                    observed = await snapshot(target)
                                except Exception:
                                    await asyncio.sleep(1)
                                    continue
                                if observed.get("problem"): break
                                await asyncio.sleep(1)
                            observed = observed or {}
                            extracted = observed.get("problem") or {}
                            live.append({"platform": label, "http_status": response.status if response else None,
                                "page_title": await target.title(), "question_detected": bool(extracted),
                                "statement_characters": len(extracted.get("statement") or ""),
                                "check_status": observed.get("result", {}).get("status")})
                            (OUTPUT / f"live-{label}.html").write_text(await target.content())
                            await target.screenshot(path=str(OUTPUT / f"live-{label}.png"))
                        except Exception as error:
                            live.append({"platform": label, "error": str(error)[:250]})
                        finally:
                            await target.close()
                    print("Live page compatibility:", json.dumps(live))
                # Restart the entire browser to exercise durable MV3 credentials.
                await browser.close()
                browser = await playwright.chromium.launch_persistent_context(str(OUTPUT / "browser"),
                    executable_path=shutil.which("chromium"), headless=True,
                    args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"],
                    viewport={"width": 1280, "height": 900})
                worker = browser.service_workers[0] if browser.service_workers else await browser.wait_for_event("serviceworker")
                for pattern in ["https://leetcode.com/**", "https://www.geeksforgeeks.org/**", "https://codeforces.com/**"]:
                    await browser.route(pattern, fixture)
                cf = await browser.new_page()
                await cf.goto("https://codeforces.com/contest/100/problem/A")
                await cf.locator("#profligator-duplicate-alert").wait_for()
                assert (await snapshot(cf))["result"]["status"] == "source_identity"
                popup = await browser.new_page()
                await popup.goto(f"chrome-extension://{extension_id}/popup.html")
                await popup.get_by_text("Connected as extension_test").wait_for()
                await popup.get_by_label("Track accepted submissions").first.wait_for()
                assert await popup.get_by_label("Track accepted submissions").first.is_checked()
                page = await browser.new_page()
                await page.goto(web_origin + "/extension/connect")
                await page.get_by_role("button", name="Revoke connection", exact=True).wait_for()
                # Server revocation removes existing alerts and forces reauthorization.
                await page.bring_to_front()
                await page.get_by_role("button", name="Revoke connection", exact=True).click()
                await page.get_by_text("No active connections.").wait_for()
                await cf.locator("#profligator-duplicate-alert").wait_for(state="detached")
                await popup.reload()
                await popup.get_by_text("Connect your existing Profligator account.").wait_for()
                assert not errors, errors
                (OUTPUT / "results.json").write_text(json.dumps({"passed": True, "browser": "Chromium",
                    "checks": ["web login and explicit connection", "known solved identity", "cross-platform exact match",
                        "popup and current question", "original submission navigation", "dismissal", "SPA stale DOM",
                        "unrelated question without alert", "Codeforces fallback link", "browser restart", "revocation"],
                    "history_checks": ["installed popup imports for all three platforms", "LeetCode signed-in names and acceptance dates",
                        "GFG source clocks stay unzoned", "opt-in acceptance tracking on all three platforms",
                        "Run does not track", "Codeforces confirmation survives navigation", "tracking persists across browser restart"],
                    "platform_pages": "controlled fixtures", "live_page_compatibility": live}, indent=2))
                print(f"Installed extension acceptance passed. Evidence: {OUTPUT}")
            finally:
                await browser.close()
        if "--firefox" in sys.argv:
            from verify_extension_firefox import verify_firefox
            verify_firefox(OUTPUT, web_origin)
    finally:
        for process in reversed(processes):
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        api_log.close(); web_log.close()


if __name__ == "__main__":
    asyncio.run(main())
