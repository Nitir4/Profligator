#!/usr/bin/env python3
"""Browser acceptance for onboarding, synchronization, roles and sharing (isolated DB)."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from playwright.async_api import async_playwright
from verify_extension import ROOT, port, ready


async def check_breakdown_layout(page, output, state):
    await page.locator(".difficulty-row").last.wait_for()
    for width in (1280, 950, 770, 390):
        await page.set_viewport_size({"width": width, "height": 900})
        assert await page.evaluate("""() => {
            const rect = (selector) => document.querySelector(selector).getBoundingClientRect();
            const rows = [...document.querySelectorAll('.difficulty-row')];
            const last = rows.at(-1).getBoundingClientRect();
            const summary = rect('.difficulty-summary');
            const card = rect('.difficulty-card');
            const next = rect('[aria-labelledby="solved-title"]');
            return rows.length === 4 && summary.top >= last.bottom + 8 &&
                summary.bottom <= card.bottom && next.top >= card.bottom &&
                document.documentElement.scrollWidth <= innerWidth + 1;
        }"""), f"Breakdown overlap/overflow at {width}px ({state})"
        if width in (950, 390):
            await page.screenshot(path=str(output / f"dashboard-{state}-{width}.png"), full_page=True)
    await page.set_viewport_size({"width": 1280, "height": 900})


async def check_profile_layout(page, output):
    for count in (1, 3, 5):
        while await page.locator('.profile-row').count() < count:
            await page.get_by_role('button', name='Add another platform', exact=True).click()
        for width in (1280, 950, 770, 390):
            await page.set_viewport_size({"width": width, "height": 900})
            geometry = await page.evaluate("""() => {
                const rows = [...document.querySelectorAll('.profile-row')];
                const panel = document.querySelector('.profile-rows').getBoundingClientRect();
                const add = document.querySelector('.add-platform-section').getBoundingClientRect();
                const last = rows.at(-1).getBoundingClientRect();
                const valid = panel.bottom >= last.bottom && add.top >= last.bottom + 8 &&
                    rows.every((row, index) => {
                        const r = row.getBoundingClientRect();
                        const field = row.querySelector('.profile-url-field').getBoundingClientRect();
                        const next = rows[index + 1]?.getBoundingClientRect();
                        return field.bottom <= r.bottom && (!next || next.top >= r.bottom + 8);
                    }) && document.documentElement.scrollWidth <= innerWidth + 1;
                return {valid, panel: panel.toJSON(), add: add.toJSON(), last: last.toJSON(),
                    scrollWidth: document.documentElement.scrollWidth, innerWidth,
                    rows: rows.map(row => ({row: row.getBoundingClientRect().toJSON(),
                        field: row.querySelector('.profile-url-field').getBoundingClientRect().toJSON()}))};
            }""")
            assert geometry['valid'], f"Profile row overlap/overflow with {count} rows at {width}px: {geometry}"
            if count == 3 and width in (770, 390):
                await page.screenshot(path=str(output / f"profiles-three-{width}.png"), full_page=True)
    while await page.locator('.profile-row').count() > 1:
        await page.locator('.remove-profile-button').last.click()
    await page.set_viewport_size({"width": 1280, "height": 900})


async def main(output_root=None):
    if output_root:
        output_root.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="profligator-frontend-check-", dir=output_root))
    web_port, api_port = port(), port()
    origin = f"http://localhost:{web_port}"
    (output / "server.py").write_text(f'''
import sys
sys.path.insert(0, {str(ROOT / "apps/api/src")!r})
from datetime import UTC, datetime
from profligator_api.config import Settings
from profligator_api.database import Database
from profligator_api.main import create_app
from profligator_api.repository import Repository
from profligator_api.schemas import CanonicalProfile, ConnectorMode, NormalizedRecord
from profligator_api.security import hash_password
settings = Settings(_env_file=None, database_url={"sqlite:///" + str(output / "test.db")!r},
    public_web_url={origin!r}, cors_origins=[{origin!r}], leetcode_connector="fixture", geeksforgeeks_connector="fixture",
    profile_sync_cooldown_seconds=3600, scraper_statement_limit=0,
    sync_backend="inline", matching_backend="disabled")
database = Database(settings.database_url)
database.initialize()
with database.session() as session:
    repository = Repository(session)
    for role in ["candidate", "recruiter"]:
        user = repository.create_user(email=f"frontend-{{role}}@example.com", handle=f"{{role}}_test", password_hash=hash_password("FrontendTest2026!"), role=role)
        if role == "candidate":
            for platform, key, url in [("leetcode", "two-sum", "https://leetcode.com/problems/two-sum/"),
                                      ("geeksforgeeks", "key-pair5616", "https://www.geeksforgeeks.org/problems/key-pair5616/1")]:
                profile = repository.save_profile(user.id, CanonicalProfile(platform=platform, handle="public_user", canonical_url=url), ConnectorMode.FIXTURE, live_data=False)
                profile.source_total_solved = 1
                profile.history_complete = True
                repository.upsert_records(profile.id, [NormalizedRecord(platform=platform, source_id=key, kind="problem", status="solved",
                    title="Two Sum", canonical_url=url, statement="Public statement. Input: array. Output: pair." if platform == "leetcode" else None,
                    occurred_at=datetime(2025, 1, 1, tzinfo=UTC) if platform == "leetcode" else None,
                    source_solved_at="2025-01-01T08:00:00" if platform == "geeksforgeeks" else None, source_payload_checksum=key)])
                repository.finish_sync(repository.start_sync(profile.id), seen=1, written=1)
    pagination_user = repository.create_user(email="frontend-pagination@example.com", handle="pagination_test", password_hash=hash_password("FrontendTest2026!"), role="candidate")
    pagination_profile = repository.save_profile(pagination_user.id, CanonicalProfile(platform="leetcode", handle="page_fixture", canonical_url="https://leetcode.com/u/page_fixture/"), ConnectorMode.FIXTURE, live_data=False)
    pagination_profile.source_total_solved = 23
    pagination_profile.history_complete = True
    repository.upsert_records(pagination_profile.id, [NormalizedRecord(platform="leetcode", source_id=f"page-{{i}}", kind="problem", status="solved", title=f"Pagination problem {{i:02d}}", canonical_url=f"https://leetcode.com/problems/page-{{i}}/", source_payload_checksum=str(i)) for i in range(23)])
    repository.finish_sync(repository.start_sync(pagination_profile.id), seen=23, written=23)
database.dispose()
app = create_app(settings)
''')
    processes, logs = [], []
    try:
        for name, cmd, cwd, env, url in [
            ("api", [str(ROOT / "apps/api/.venv/bin/python"), "-m", "uvicorn", "server:app", "--app-dir", str(output), "--host", "127.0.0.1", "--port", str(api_port)], ROOT, os.environ, f"http://127.0.0.1:{api_port}/health"),
            ("web", ["node", str(ROOT / "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"], ROOT / "apps/web", {**os.environ, "PROFLIGATOR_API_PORT": str(api_port)}, origin),
        ]:
            log = (output / f"{name}.log").open("w"); logs.append(log)
            process = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
            processes.append(process); ready(url, process)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True)
            onboarding = await browser.new_context(viewport={"width": 1280, "height": 900})
            candidate = await browser.new_context(viewport={"width": 1280, "height": 900})
            recruiter = await browser.new_context(viewport={"width": 1280, "height": 900})
            guest = await browser.new_context()
            errors = []
            async def page_for(context):
                page = await context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                return page
            # Exercise the real UI and backend instead of seeding this candidate's
            # profiles/history or intercepting registration/synchronization calls.
            new_page = await page_for(onboarding)
            await onboarding.tracing.start(screenshots=True, snapshots=True)
            try:
                await new_page.goto(origin + "/login")
                await new_page.get_by_role("button", name="Create account", exact=True).click()
                await new_page.get_by_label("Email address").fill("onboarding@example.com")
                await new_page.get_by_label("Candidate handle").fill("onboarding_candidate")
                await new_page.get_by_label("Password", exact=True).fill("FrontendTest2026!")
                await new_page.get_by_role("button", name="Create Account", exact=True).click()
                await new_page.wait_for_url("**/onboarding/profiles")
                await new_page.get_by_role("button", name="Check all", exact=True).wait_for()
                await new_page.goto(origin + "/dashboard")
                await new_page.get_by_role("heading", name="Solved questions", exact=True).wait_for()
                await check_breakdown_layout(new_page, output, "empty")
                await new_page.get_by_text("No rated questions yet", exact=True).wait_for()
                await new_page.goto(origin + "/onboarding/profiles")
                await new_page.locator('.profile-row').wait_for()
                await check_profile_layout(new_page, output)
                assert await new_page.locator('option[value="codechef"]').first.evaluate('(option) => option.disabled')
                assert await new_page.locator('.quick-platforms button').count() == 3
                sync_request_pages = []
                def record_sync_request(request):
                    if request.method == 'POST' and request.url.endswith('/api/v1/syncs'):
                        sync_request_pages.append(new_page.url)
                new_page.on('request', record_sync_request)
                await new_page.get_by_label("Coding platform").select_option("leetcode")
                await new_page.get_by_label("LeetCode username", exact=True).fill("fixture_lc")
                await new_page.get_by_role("button", name="Add another platform", exact=True).click()
                await new_page.get_by_label("Coding platform").nth(1).select_option("geeksforgeeks")
                await new_page.get_by_label("GeeksforGeeks username", exact=True).fill("fixture_gfg")
                await new_page.get_by_role("button", name="Check all", exact=True).click()
                await new_page.get_by_text("Profile checks completed.", exact=True).wait_for()
                await new_page.get_by_role("button", name="Save & Continue to Dashboard", exact=True).click()
                await new_page.wait_for_url("**/dashboard")
                await new_page.get_by_role("heading", name="Solved questions", exact=True).wait_for()
                await new_page.get_by_role("link", name="Two Sum", exact=True).wait_for()
                dashboard = await onboarding.request.get(origin + "/api/v1/dashboard")
                assert dashboard.ok
                assert (await dashboard.json())["total_problems_solved"] == 5
                assert sync_request_pages and all('/dashboard' in url for url in sync_request_pages), sync_request_pages
                await check_breakdown_layout(new_page, output, "populated")
                coverage = new_page.locator('.platform-coverage .coverage-details').first
                assert not await coverage.get_attribute('open')
                await coverage.locator('summary').click()
                await coverage.get_by_text('Last successful sync', exact=True).wait_for()
                await coverage.locator('summary').click()
                await new_page.get_by_placeholder("Search by question title").fill("Islands")
                await new_page.get_by_role("link", name="Number of Islands", exact=True).wait_for()
                assert await new_page.get_by_role("link", name="Two Sum", exact=True).count() == 0
                await new_page.screenshot(path=str(output / "onboarding-dashboard.png"), full_page=True)
                await new_page.goto(origin + "/settings/sharing")
                switch = new_page.get_by_role("switch", name="Enable profile sharing")
                await switch.click()
                share_link = await new_page.get_by_label("Your Shareable Link").input_value()
                for width in (1280, 390):
                    await new_page.set_viewport_size({'width':width,'height':900})
                    assert await new_page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                    assert await new_page.evaluate('document.querySelector(".settings-heading").getBoundingClientRect().top >= document.querySelector(".dashboard-header").getBoundingClientRect().bottom')
                    assert float(await switch.evaluate('(e) => parseFloat(getComputedStyle(e).borderRadius)')) >= 10
                    await new_page.screenshot(path=str(output / f'sharing-settings-{width}.png'), full_page=True)
                await new_page.set_viewport_size({'width':1280,'height':900})
                public_page = await page_for(guest)
                await public_page.goto(share_link)
                await public_page.get_by_role("heading", name="onboarding_candidate", exact=True).wait_for()
                await public_page.get_by_role("link", name="Two Sum", exact=True).wait_for()
                await switch.click()
                await public_page.reload()
                await public_page.get_by_role("alert").wait_for()
                assert await public_page.get_by_role("heading", name="onboarding_candidate", exact=True).count() == 0
                await new_page.goto(origin + "/dashboard")
                await new_page.get_by_role("button", name="Open user menu").click()
                await new_page.get_by_role("button", name="Sign out", exact=True).click()
                await new_page.wait_for_url("**/login")
                await new_page.get_by_label("Email address").fill("onboarding@example.com")
                await new_page.get_by_label("Password", exact=True).fill("FrontendTest2026!")
                await new_page.get_by_role("button", name="Sign In", exact=True).click()
                await new_page.wait_for_url("**/onboarding/profiles")
                await new_page.get_by_label("LeetCode username", exact=True).wait_for()
                assert await new_page.get_by_label("LeetCode username", exact=True).input_value() == "fixture_lc"
                same_user = await (await onboarding.request.get(origin + '/api/v1/auth/me')).json()
                await new_page.get_by_role('link', name='Profligator home', exact=True).click()
                await new_page.wait_for_url('**/dashboard')
                assert (await (await onboarding.request.get(origin + '/api/v1/auth/me')).json())['id'] == same_user['id']
                await new_page.goto(origin + '/onboarding/profiles')
                await new_page.get_by_label('LeetCode username', exact=True).wait_for()
                before = await (await onboarding.request.get(origin + '/api/v1/platform-profiles')).json()
                await new_page.get_by_label('LeetCode username', exact=True).fill('bad handle!')
                await new_page.get_by_role('button', name='Save & Continue to Dashboard', exact=True).click()
                await new_page.get_by_role('alert').wait_for()
                after = await (await onboarding.request.get(origin + '/api/v1/platform-profiles')).json()
                assert {p['id'] for p in before} == {p['id'] for p in after}, 'Failed replacement disconnected saved profiles'
                assert new_page.url.endswith('/onboarding/profiles')
                await new_page.get_by_label('LeetCode username', exact=True).fill('fixture_lc')
                assert await new_page.get_by_role('alert').count() == 0
                await new_page.get_by_role('button', name='Save & Continue to Dashboard', exact=True).click()
                await new_page.wait_for_url('**/dashboard')
                after = await (await onboarding.request.get(origin + '/api/v1/platform-profiles')).json()
                assert {p['id'] for p in before} == {p['id'] for p in after}, 'Canonicalized retry disconnected the retained profile'
            except Exception:
                await new_page.screenshot(path=str(output / "onboarding-failure.png"), full_page=True)
                raise
            finally:
                await onboarding.tracing.stop(path=str(output / "onboarding-trace.zip"))
            async def login(page, role):
                await page.goto(origin + "/login")
                await page.get_by_label("Email address").fill(f"frontend-{role}@example.com")
                await page.get_by_label("Password", exact=True).fill("FrontendTest2026!")
                await page.get_by_role("button", name="Sign In", exact=True).click()
                await page.wait_for_url("**/team" if role == "recruiter" else "**/onboarding/profiles")
            owner_page = await page_for(candidate)
            await login(owner_page, "candidate")
            await owner_page.goto(origin + "/team")
            await owner_page.get_by_text("Enable sharing to create a public profile link.", exact=False).wait_for()
            sharing = await candidate.request.put(origin + "/api/v1/sharing", data={"enabled": True})
            assert sharing.ok
            link = (await sharing.json())["shareable_link"]
            await owner_page.goto(origin + "/dashboard")
            await owner_page.get_by_role("heading", name="Matching coverage").wait_for()
            await owner_page.get_by_text("1 of 2 imported questions have text", exact=False).wait_for()
            await check_breakdown_layout(owner_page, output, "partial")
            await owner_page.get_by_label('Activity source', exact=True).select_option('geeksforgeeks:public_user')
            await owner_page.get_by_label('Activity period', exact=True).select_option('2025')
            await owner_page.get_by_role('img', name='1 dated solves · platform time · timezone unspecified', exact=True).wait_for()
            assert await owner_page.locator('rect[data-date="2025-01-01"]').get_attribute('data-count') == '1'
            await owner_page.screenshot(path=str(output / 'source-local-activity.png'), full_page=True)
            for path in ('/onboarding/profiles','/settings/account','/settings/sharing','/dashboard'):
                await owner_page.goto(origin + path)
                trigger = owner_page.get_by_role('button', name='Open user menu', exact=True)
                await trigger.get_by_text('frontend-candidate@example.com', exact=True).click()
                await owner_page.get_by_role('link', name='Account settings', exact=True).wait_for()
                await owner_page.keyboard.press('Escape')
                assert await trigger.get_attribute('aria-expanded') == 'false'
            await owner_page.goto(origin + '/settings/account')
            await owner_page.get_by_role('heading', name='Sign-in methods', exact=True).wait_for()
            for width in (1280, 390):
                await owner_page.set_viewport_size({'width':width,'height':900})
                assert await owner_page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                assert await owner_page.evaluate('document.querySelector(".settings-heading").getBoundingClientRect().top >= document.querySelector(".dashboard-header").getBoundingClientRect().bottom')
                await owner_page.screenshot(path=str(output / f'account-settings-{width}.png'), full_page=True)
            await owner_page.set_viewport_size({'width':1280,'height':900})
            await owner_page.goto(origin + '/dashboard')
            owner_id = (await (await candidate.request.get(origin + '/api/v1/auth/me')).json())['id']
            await owner_page.goto(origin + '/terms')
            await owner_page.get_by_role('button', name='Open user menu', exact=True).wait_for()
            await owner_page.get_by_role('link', name='Profligator home', exact=True).click()
            await owner_page.wait_for_url('**/dashboard')
            assert (await (await candidate.request.get(origin + '/api/v1/auth/me')).json())['id'] == owner_id
            await owner_page.goto(origin + '/login')
            await owner_page.wait_for_url('**/dashboard')
            await owner_page.screenshot(path=str(output / "candidate-coverage.png"), full_page=True)
            recruiter_page = await page_for(recruiter)
            await login(recruiter_page, "recruiter")
            await recruiter_page.goto(origin + '/login')
            await recruiter_page.wait_for_url('**/team')
            await recruiter_page.get_by_role("heading", name="Open a candidate profile").wait_for()
            nav = recruiter_page.get_by_role("navigation", name="Primary navigation")
            assert await nav.get_by_role("link", name="Dashboard").count() == 0
            for path in ["/dashboard", "/onboarding/profiles", "/integrations", "/settings/sharing"]:
                await recruiter_page.goto(origin + path)
                await recruiter_page.wait_for_url("**/team")
                await recruiter_page.get_by_role("heading", name="Open a candidate profile").wait_for()
            await recruiter_page.get_by_label("Shared profile link").fill("https://evil.test/p/" + "a" * 43)
            await recruiter_page.get_by_role("button", name="Open profile", exact=True).click()
            await recruiter_page.get_by_role("alert").wait_for()
            await recruiter_page.screenshot(path=str(output / "recruiter-workspace.png"))
            await recruiter_page.get_by_label("Shared profile link").fill(link)
            await recruiter_page.get_by_role("button", name="Open profile", exact=True).click()
            await recruiter_page.get_by_role("heading", name="candidate_test", exact=True).wait_for()
            await recruiter_page.get_by_role("heading", name="Matching coverage").wait_for()
            await recruiter_page.get_by_text("Source time · time zone unspecified").wait_for()
            await recruiter_page.get_by_text("Question text unavailable", exact=True).wait_for()
            await recruiter_page.screenshot(path=str(output / "shared-coverage.png"), full_page=True)
            await recruiter_page.set_viewport_size({"width": 390, "height": 844})
            assert await recruiter_page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            await recruiter_page.screenshot(path=str(output / "shared-mobile.png"), full_page=True)
            assert (await candidate.request.put(origin + "/api/v1/sharing", data={"enabled": False})).ok
            # Filtering a revoked shared table must hide the complete stale profile.
            await recruiter_page.get_by_placeholder("Search by question title").fill("Two")
            await recruiter_page.get_by_role("alert").wait_for()
            assert await recruiter_page.get_by_role("heading", name="candidate_test", exact=True).count() == 0
            await recruiter_page.screenshot(path=str(output / "revoked-profile.png"))
            guest_page = await page_for(guest)
            await guest_page.goto(origin + "/dashboard")
            await guest_page.wait_for_url("**/login")
            await guest_page.goto(link)
            await guest_page.get_by_role("alert").wait_for()
            pagination = await browser.new_context(viewport={'width':1280,'height':900})
            pagination_page = await page_for(pagination)
            await login(pagination_page, 'pagination')
            await pagination_page.goto(origin + '/dashboard')
            table = pagination_page.locator('[aria-labelledby="solved-title"]')
            await table.get_by_text('1–10 of 23 imported questions', exact=True).wait_for()
            assert await table.locator('tbody tr').count() == 10
            await table.get_by_role('button', name='Next', exact=True).click()
            await table.get_by_text('11–20 of 23 imported questions', exact=True).wait_for()
            persistent_dir = output / 'persistent-browser-profile'
            persistent = await playwright.chromium.launch_persistent_context(str(persistent_dir), executable_path=shutil.which('chromium'), headless=True)
            persistent_page = await persistent.new_page()
            await login(persistent_page, 'pagination')
            persistent_user = (await (await persistent.request.get(origin + '/api/v1/auth/me')).json())['id']
            refresh_before = next(cookie for cookie in await persistent.cookies() if cookie['name']=='profligator_refresh')
            assert refresh_before['httpOnly'] and refresh_before['expires'] > time.time() + 29 * 86400
            await persistent.clear_cookies(name='profligator_access')
            await persistent.close()
            persistent = await playwright.chromium.launch_persistent_context(str(persistent_dir), executable_path=shutil.which('chromium'), headless=True)
            persistent_page = await persistent.new_page()
            await persistent_page.goto(origin + '/login')
            await persistent_page.wait_for_url('**/dashboard')
            assert (await (await persistent.request.get(origin + '/api/v1/auth/me')).json())['id'] == persistent_user
            refresh_after = next(cookie for cookie in await persistent.cookies() if cookie['name']=='profligator_refresh')
            assert refresh_after['value'] != refresh_before['value']
            assert any(cookie['name']=='profligator_access' for cookie in await persistent.cookies())
            await persistent.request.post(origin + '/api/v1/auth/logout')
            await persistent_page.goto(origin + '/login')
            await persistent_page.get_by_role('heading', name='Welcome back', exact=True).wait_for()
            await persistent.close()
            assert await table.locator('tbody tr').count() == 10
            await table.get_by_role('button', name='Next', exact=True).click()
            await table.get_by_text('21–23 of 23 imported questions', exact=True).wait_for()
            assert await table.locator('tbody tr').count() == 3
            await table.get_by_role('button', name='Previous', exact=True).click()
            await table.get_by_text('11–20 of 23 imported questions', exact=True).wait_for()
            assert not errors, errors
            await browser.close()
        result = {"passed": True, "data": "isolated database, real application API and offline LC/GFG fixtures; no Google or signed-in platform acceptance",
            "checks": ["UI registration", "UI profile validation/linking and actual synchronization", "five imported solved records",
            "terms brand preserves signed-in user", "login page restores candidate/recruiter workspace", "real browser profile restart restores30-day refresh session without access cookie", "refresh rotation and logout prevent automatic re-entry",
            "styled account/sharing settings desktop/mobile", "email control opens account menu on all tested signed-in pages", "source-local activity shown separately from UTC", "solved pagination 10/10/3 with next/previous",
            "unsupported platforms cannot be selected", "navigation precedes profile synchronization", "invalid replacement preserves saved profiles and retry keeps canonical IDs", "onboarding logo opens dashboard and preserves authenticated user",
            "four-row difficulty geometry on empty/populated dashboards at four widths", "one/three/five account row geometry at four widths", "expandable coverage notes",
            "solved-question search", "UI sharing and anonymous public view/revocation", "logout/login persists linked accounts",
            "candidate sharing text", "recruiter navigation and route guards",
            "same-site shared link validation", "statement/date/matching coverage", "public desktop/mobile rendering",
            "revoked shared table clears profile", "anonymous protected-route redirect"], "output": str(output)}
        (output / "results.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    finally:
        for process in reversed(processes):
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        for log in logs: log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Parent directory for per-run logs, traces and screenshots")
    asyncio.run(main(parser.parse_args().output_dir))
