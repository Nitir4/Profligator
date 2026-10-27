#!/usr/bin/env python3
"""Profile editing acceptance on isolated local data or disposable hosted accounts.

Hosted mode writes exact synthetic account IDs to cleanup-users.json for the
operator to remove after acceptance. It does not touch existing accounts.
"""
import argparse
import asyncio
from io import BytesIO
import json
import os
from pathlib import Path
import random
import secrets
import shutil
import subprocess
import tempfile

from PIL import Image
from playwright.async_api import async_playwright
from verify_extension import ROOT, port, ready


async def exercise(origin, output):
    username = "profile_check_" + secrets.token_hex(5)
    password = secrets.token_urlsafe(28)
    user_ids = []
    checks = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=shutil.which("chromium"), headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 1000})
        guest = await browser.new_context(viewport={"width": 1280, "height": 1000})
        try:
            response = await context.request.post(origin + "/api/v1/auth/register", data={
                "email": username + "@example.com", "handle": username, "password": password})
            assert response.status == 201, f"Registration status {response.status}"
            user = (await response.json())["user"]
            user_ids.append(user["id"])
            (output / "cleanup-users.json").write_text(json.dumps(user_ids))
            page = await context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(origin + "/settings/account")
            await page.get_by_role("heading", name="Your profile", exact=True).wait_for()
            await page.get_by_label("Display name", exact=True).fill("Alex Rivera")
            await page.get_by_label("Username", exact=True).fill(username + "-new")
            await page.get_by_label("Short bio", exact=True).fill("Learning algorithms and building useful tools.\nOpen to collaboration.")
            assert await page.get_by_label("Username", exact=True).evaluate("el => el.checkValidity()")
            await page.get_by_role("button", name="Save profile", exact=True).click()
            await page.get_by_role("status").filter(has_text="Profile updated.").wait_for()
            assert await page.locator(".dashboard-user-copy strong").inner_text() == "Alex Rivera"
            await page.reload()
            await page.get_by_label("Display name", exact=True).wait_for()
            assert await page.get_by_label("Username", exact=True).input_value() == username + "-new"
            assert await page.get_by_label("Display name", exact=True).input_value() == "Alex Rivera"
            checks.append("display name, username and bio saved; header and reload reflect changes")
            # Exercise the advertised size through the real reverse proxy as well.
            large = BytesIO()
            Image.frombytes("RGB", (1100, 850), random.Random(42).randbytes(1100 * 850 * 3)).save(large, "PNG")
            assert 2 * 1024 * 1024 < len(large.getvalue()) < 4 * 1024 * 1024
            large_response = await context.request.put(origin + "/api/v1/account/avatar", data=large.getvalue(), headers={"Content-Type": "image/png", "Origin": origin})
            assert large_response.status == 200, f"2MiB+ photo status {large_response.status}"
            checks.append("valid photo larger than 2MiB accepted through proxy")
            image = BytesIO()
            Image.new("RGB", (640, 480), "#147d92").save(image, "PNG")
            await page.locator('input[type="file"]').set_input_files({"name": "profile.png", "mimeType": "image/png", "buffer": image.getvalue()})
            await page.get_by_role("status").filter(has_text="Profile photo updated.").wait_for()
            await page.wait_for_function("() => { const img = document.querySelector('.profile-photo-editor img'); return img?.complete && img.naturalWidth === 384; }")
            for width in (1280, 770, 390):
                await page.set_viewport_size({"width": width, "height": 1000})
                assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"Settings overflow at {width}"
                assert await page.locator(".profile-edit-form").evaluate("form => { const r=form.getBoundingClientRect(); return [...form.querySelectorAll('input,textarea,button')].every(el=> {const q=el.getBoundingClientRect();return q.left>=r.left-1&&q.right<=r.right+1});}")
                await page.screenshot(path=str(output / f"profile-settings-{width}.png"), full_page=True)
            checks.append("photo upload and desktop/tablet/mobile settings layout")
            sharing = await context.request.put(origin + "/api/v1/sharing", data={"enabled": True})
            assert sharing.status == 200
            # Use the actual configured frontend route from the returned URL.
            from urllib.parse import urlsplit
            share_path = urlsplit((await sharing.json())["shareable_link"]).path
            public = await guest.new_page()
            await public.goto(origin + share_path)
            await public.get_by_role("heading", name="Alex Rivera", exact=True).wait_for()
            public_photo = public.locator(".public-profile-identity img")
            await public_photo.wait_for()
            await public.wait_for_function("() => { const img = document.querySelector('.public-profile-identity img'); return img?.complete && img.naturalWidth === 384; }")
            private_response = await guest.request.get(origin + "/api/v1/account/avatar")
            assert private_response.status == 401
            await public.screenshot(path=str(output / "shared-profile.png"), full_page=True)
            checks.append("chosen identity/photo visible to active share link; owner photo endpoint stays authenticated")
            await page.goto(origin + "/dashboard")
            await page.get_by_role("heading", name="Alex Rivera", exact=True).wait_for()
            for width in (1280, 390):
                await page.set_viewport_size({"width": width, "height": 1000})
                assert await page.evaluate("""() => {
                    const header = document.querySelector('.dashboard-profile-header').getBoundingClientRect();
                    const copy = document.querySelector('.dashboard-profile-copy').getBoundingClientRect();
                    const actions = document.querySelector('.dashboard-profile-actions').getBoundingClientRect();
                    return copy.bottom <= header.bottom && actions.bottom <= header.bottom && document.documentElement.scrollWidth <= innerWidth + 1;
                }"""), f"Dashboard identity overflow at {width}"
                await page.screenshot(path=str(output / f"profile-dashboard-{width}.png"), full_page=True)
            checks.append("dashboard identity and responsive geometry")
            long_name = "Alex " + "Rivera" * 12
            changed = await context.request.put(origin + "/api/v1/account/profile", data={"handle": username + "-new", "display_name": long_name, "bio": "A" * 280})
            assert changed.status == 200
            await page.reload()
            await page.get_by_role("heading", name=long_name, exact=True).wait_for()
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "Long name overflow"
            await context.request.put(origin + "/api/v1/account/profile", data={"handle": username + "-new", "display_name": "Alex Rivera", "bio": "Learning algorithms and building useful tools."})
            checks.append("long display name and maximum bio fit mobile layout")
            await page.goto(origin + "/settings/account#profile")
            await page.get_by_role("button", name="Remove photo", exact=True).click()
            await page.get_by_role("status").filter(has_text="Profile photo removed.").wait_for()
            assert await page.locator(".profile-photo-editor img").count() == 0
            await public.reload()
            await public.get_by_role("heading", name="Alex Rivera", exact=True).wait_for()
            assert await public.locator(".public-profile-identity img").count() == 0
            await context.request.put(origin + "/api/v1/sharing", data={"enabled": False})
            await public.reload()
            await public.get_by_role("alert").filter(has_text="unavailable").wait_for()
            checks.append("photo removal restores initials; sharing revocation hides public profile")
            assert not errors, errors
            result = {"origin": origin, "checks": checks, "browser_errors": errors, "synthetic_user_ids": user_ids, "passed": True}
            (output / "browser-results.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
        except Exception:
            if "page" in locals():
                await page.screenshot(path=str(output / "failure.png"), full_page=True)
                (output / "failure.html").write_text(await page.content())
            raise
        finally:
            await guest.close()
            await context.close()
            await browser.close()


async def main(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.base_url:
        await exercise(args.base_url.rstrip("/"), output)
        return
    api_port, web_port = port(), port()
    origin = f"http://localhost:{web_port}"
    with tempfile.TemporaryDirectory(prefix="profile-acceptance-") as temp:
        directory = Path(temp)
        (directory / "server.py").write_text(f'''
from profligator_api.config import Settings
from profligator_api.main import create_app
app = create_app(Settings(_env_file=None, database_url={"sqlite:///" + str(directory / "test.db")!r}, auto_create_schema=True, public_web_url={origin!r}, cors_origins=[{origin!r}], matching_backend="disabled", sync_backend="inline", leetcode_connector="fixture", geeksforgeeks_connector="fixture"))
''')
        processes, logs = [], []
        try:
            for name, command, cwd, env, url in [
                ("api", [str(ROOT / "apps/api/.venv/bin/python"), "-m", "uvicorn", "server:app", "--app-dir", temp, "--host", "127.0.0.1", "--port", str(api_port)], ROOT, {**os.environ, "PYTHONPATH": str(ROOT / "apps/api/src")}, f"http://127.0.0.1:{api_port}/health"),
                ("web", ["node", str(ROOT / "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"], ROOT / "apps/web", {**os.environ, "PROFLIGATOR_API_PORT": str(api_port)}, origin),
            ]:
                log = (output / f"{name}.log").open("w"); logs.append(log)
                process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
                processes.append(process); ready(url, process)
            await exercise(origin, output)
        finally:
            for process in reversed(processes):
                process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            for log in logs: log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/editable-profile-20261027/local-browser")
    asyncio.run(main(parser.parse_args()))
