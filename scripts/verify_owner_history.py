"""Check or import the owner's LeetCode history in the dedicated test browser.

Uses the installed extension and the owner's browser session. Never prints or
saves cookies, OAuth URLs, email addresses or extension bearer credentials.
"""

import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

from inspect_extension_browser import DEFAULT_BROWSER_PROFILE, ROOT


def profile_summary(profile):
    keys = (
        "platform", "handle", "questions", "timestamped_questions",
        "source_local_question_times", "questions_with_statements",
        "questions_with_difficulty", "questions_with_topics",
        "source_total_solved", "history_complete",
    )
    return {key: profile[key] for key in keys if key in profile}


async def send(popup, message):
    response = await popup.evaluate("message => chrome.runtime.sendMessage(message)", message)
    if not response or not response.get("ok"):
        raise RuntimeError((response or {}).get("error", "The extension did not respond"))
    return response["value"]


async def inspect(args):
    report = {"checked_at": datetime.now(UTC).isoformat(), "import_requested": args.run_import}
    preferences_file = args.browser_profile / "Default/Preferences"
    if not preferences_file.exists():
        return {**report, "ready": False, "reason": "The dedicated browser profile is missing"}
    preferences = json.loads(preferences_file.read_text())
    extension_id = next((key for key, entry in preferences.get("extensions", {}).get("settings", {}).items()
                         if entry.get("path") == str(ROOT / "apps/extension/dist/chrome")), None)
    if not extension_id:
        return {**report, "ready": False, "reason": "Load Profligator in the dedicated browser first"}

    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp("http://127.0.0.1:9223")
        context = browser.contexts[0]
        popup_url = f"chrome-extension://{extension_id}/popup.html"
        popup = next((page for page in context.pages if page.url == popup_url), None)
        if popup is None:
            popup = await context.new_page()
            await popup.goto(popup_url)
        state = await send(popup, {"type": "PF_STATE"})
        # Public state contains no bearer token. Retain only readiness fields.
        report["extension"] = {key: state.get(key) for key in ("connected", "handle", "offline")}
        app = next((page for page in context.pages if urlsplit(page.url).scheme == "http"
                    and urlsplit(page.url).netloc == "localhost:5173"), None)
        if app:
            report["app"] = await app.evaluate("""async () => {
                const response = await fetch('/api/v1/auth/me', {credentials:'include'});
                if (!response.ok) return {signed_in:false, http_status:response.status};
                const user = await response.json();
                return {signed_in:true, handle:user.handle, role:user.role};
            }""")
        lc = next((page for page in context.pages if urlsplit(page.url).scheme == "https"
                   and urlsplit(page.url).hostname in ("leetcode.com", "www.leetcode.com")), None)
        report["leetcode_tab_open"] = lc is not None
        if lc:
            report["leetcode"] = await lc.evaluate("""async () => {
                const response = await fetch('/graphql/', {method:'POST', credentials:'include',
                    headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({query:'query OwnerIdentity { userStatus { isSignedIn username } }'})});
                if (!response.ok) return {signed_in:false, http_status:response.status};
                const payload = await response.json();
                const identity = payload.data?.userStatus;
                return {signed_in:identity?.isSignedIn === true, handle:identity?.username || null};
            }""")
        if not state.get("connected"):
            return {**report, "ready": False, "reason": "Sign in to Profligator and choose Connect this browser"}
        if state.get("offline"):
            return {**report, "ready": False, "reason": "The extension cannot reach Profligator"}
        history = await send(popup, {"type": "PF_HISTORY_STATE"})
        report["profiles"] = [profile_summary(profile) for profile in history["profiles"]]
        if not lc or not report["leetcode"].get("signed_in"):
            return {**report, "ready": False, "reason": "Sign in to LeetCode in the same dedicated browser"}
        handle = report["leetcode"]["handle"]
        profile = next((profile for profile in history["profiles"] if profile["platform"] == "leetcode"
                        and profile["handle"].lower() == handle.lower()), None)
        if profile is None:
            return {**report, "ready": False, "reason": "Link the signed-in LeetCode handle in Profligator first"}
        report["ready"] = True
        if not args.run_import:
            return report
        result = history.get("results", {}).get(profile["profile_id"], {})
        if result.get("status") == "running":
            return {**report, "import_started": False, "reason": "A history import is already running"}
        # Ask only for this platform's tab ID, without exposing other tab URLs.
        tab_id = await popup.evaluate("""async target => {
            const tabs = await chrome.tabs.query({url:['https://leetcode.com/*','https://www.leetcode.com/*']});
            return tabs.find(tab => tab.url === target)?.id ?? null;
        }""", lc.url)
        if tab_id is None:
            return {**report, "ready": False, "reason": "The extension cannot locate the LeetCode tab"}
        print(json.dumps({"stage": "importing", "handle": handle,
                          "before": profile_summary(profile)}), flush=True)
        # Reload once to attach the current content script after installation or
        # extension rebuilding. The site session remains in the browser.
        await lc.reload(wait_until="domcontentloaded")
        await popup.evaluate("""async id => {
            for (let attempt = 0; attempt < 30; attempt++) {
                try {await chrome.tabs.sendMessage(id, {type:'PF_SNAPSHOT'}); return;}
                catch {await new Promise(resolve => setTimeout(resolve, 500));}
            }
            throw new Error('Reload the signed-in LeetCode tab before importing');
        }""", tab_id)
        imported = await asyncio.wait_for(send(popup, {"type": "PF_HISTORY_IMPORT",
                                                      "profile_id": profile["profile_id"], "tab_id": tab_id}), 300)
        report["import_started"] = True
        report["import_result"] = {key: imported[key] for key in (
            "status", "questions", "records_written", "timestamped_questions",
            "source_local_question_times", "questions_with_statements", "questions_with_difficulty",
            "questions_with_topics", "source_total_solved", "history_complete", "next_cursor",
            "dated_history_checked", "warning", "enrichment_status",
        ) if key in imported}
        after = await send(popup, {"type": "PF_HISTORY_STATE"})
        report["profiles"] = [profile_summary(profile) for profile in after["profiles"]]
        report["passed"] = imported.get("status") == "succeeded"
        await popup.reload()
        return report


async def main(args):
    report = await inspect(args)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-profile", type=Path, default=DEFAULT_BROWSER_PROFILE)
    parser.add_argument("--import", dest="run_import", action="store_true", help="Import through the actual extension after owner checks")
    parser.add_argument("--output", type=Path)
    asyncio.run(main(parser.parse_args()))
