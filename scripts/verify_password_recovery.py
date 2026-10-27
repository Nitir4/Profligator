"""Browser + actual local SMTP acceptance; never sends external email."""
import argparse
import asyncio
from email.parser import BytesParser
from email.policy import default
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from playwright.async_api import async_playwright
from verify_extension import ROOT, port, ready


async def main(output_dir=None):
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="profligator-password-recovery-", dir=output_dir))
    messages = []
    async def smtp(reader, writer):
        writer.write(b"220 localhost test SMTP\r\n"); await writer.drain()
        while line := await reader.readline():
            command = line.decode().strip().split(" ", 1)[0].upper()
            if command in ("EHLO", "HELO", "MAIL", "RCPT", "RSET", "NOOP"):
                writer.write(b"250 localhost\r\n")
            elif command == "DATA":
                writer.write(b"354 End with a dot\r\n"); await writer.drain()
                body = []
                while (line := await reader.readline()) not in (b".\r\n", b""):
                    body.append(line[1:] if line.startswith(b"..") else line)
                messages.append(BytesParser(policy=default).parsebytes(b"".join(body)))
                writer.write(b"250 Message accepted\r\n")
            elif command == "QUIT":
                writer.write(b"221 Bye\r\n"); await writer.drain(); break
            else:
                writer.write(b"500 Unsupported command\r\n")
            await writer.drain()
        writer.close(); await writer.wait_closed()
    mail_server = await asyncio.start_server(smtp, "127.0.0.1", 0)
    smtp_port = mail_server.sockets[0].getsockname()[1]
    web_port, api_port = port(), port()
    origin = f"http://localhost:{web_port}"
    (output / "server.py").write_text(f'''
import sys
sys.path.insert(0, {str(ROOT / "apps/api/src")!r})
from profligator_api.config import Settings
from profligator_api.main import create_app
app = create_app(Settings(_env_file=None, database_url={"sqlite:///" + str(output / "test.db")!r},
    public_web_url={origin!r}, cors_origins=[{origin!r}], matching_backend="disabled",
    leetcode_connector="fixture", geeksforgeeks_connector="fixture", password_reset_email_backend="smtp",
    smtp_host="127.0.0.1", smtp_port={smtp_port}, smtp_security="plain", smtp_from_email="sender@example.com",
    smtp_username="", smtp_password=None))
''')
    processes, logs = [], []
    try:
        for name, command, cwd, env, url in [
            ("api", [str(ROOT / "apps/api/.venv/bin/python"), "-m", "uvicorn", "server:app", "--app-dir", str(output), "--host", "127.0.0.1", "--port", str(api_port)], ROOT, os.environ, f"http://127.0.0.1:{api_port}/health"),
            ("web", ["node", str(ROOT / "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"], ROOT / "apps/web", {**os.environ, "PROFLIGATOR_API_PORT":str(api_port)}, origin),
        ]:
            log = (output / f"{name}.log").open("w"); logs.append(log)
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
            processes.append(process); ready(url, process)
        async with async_playwright() as p:
            browser = await p.chromium.launch(executable_path=shutil.which("chromium"), headless=True)
            context = await browser.new_context(viewport={"width":1280,"height":900})
            page = await context.new_page()
            errors=[]; page.on("pageerror",lambda error:errors.append(str(error)))
            await page.goto(origin + "/login")
            registration = await context.request.post(origin + "/api/v1/auth/register", data={"email":"recovery@example.com","handle":"recovery_user","password":"original-password"})
            assert registration.status == 201
            await page.get_by_role("link",name="Forgot password?",exact=True).click()
            await page.get_by_label("Email address").fill("recovery@example.com")
            await page.get_by_role("button",name="Send reset link",exact=True).click()
            await page.get_by_role("status").filter(has_text="If an account exists").wait_for()
            await page.screenshot(path=str(output / "forgot-password.png"),full_page=True)
            for _ in range(100):
                if messages: break
                await asyncio.sleep(.1)
            assert len(messages)==1 and messages[0]["To"]=="recovery@example.com"
            link=next(line for line in messages[0].get_content().splitlines() if "/reset-password#token=" in line)
            await page.goto(link)
            await page.get_by_role("heading",name="Reset password",exact=True).wait_for()
            assert "token=" not in page.url
            await page.get_by_label("Password",exact=True).fill("replacement-password")
            await page.get_by_label("Confirm password",exact=True).fill("different-password")
            await page.get_by_role("button",name="Update password",exact=True).click()
            await page.get_by_role("alert").filter(has_text="Passwords do not match").wait_for()
            await page.get_by_label("Confirm password",exact=True).fill("replacement-password")
            await page.screenshot(path=str(output / "reset-password.png"),full_page=True)
            await page.get_by_role("button",name="Update password",exact=True).click()
            await page.wait_for_url("**/login")
            await page.get_by_role("status").filter(has_text="Password updated").wait_for()
            assert (await context.request.get(origin + "/api/v1/auth/me")).status==401
            await page.screenshot(path=str(output / "password-updated.png"),full_page=True)
            await page.get_by_label("Email address").fill("recovery@example.com")
            await page.get_by_label("Password",exact=True).fill("original-password")
            await page.get_by_role("button",name="Sign In",exact=True).click()
            await page.get_by_role("alert").filter(has_text="Incorrect email or password").wait_for()
            await page.get_by_label("Password",exact=True).fill("replacement-password")
            await page.get_by_role("button",name="Sign In",exact=True).click()
            await page.wait_for_url("**/onboarding/profiles")
            await page.goto(link)
            await page.get_by_label("Password",exact=True).fill("replacement-password")
            await page.get_by_label("Confirm password",exact=True).fill("replacement-password")
            await page.get_by_role("button",name="Update password",exact=True).click()
            await page.get_by_role("alert").filter(has_text="invalid or expired").wait_for()
            await page.set_viewport_size({"width":390,"height":844})
            await page.screenshot(path=str(output / "reset-mobile.png"),full_page=True)
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors,errors
            for _ in range(100):
                if len(messages)==2: break
                await asyncio.sleep(.1)
            assert len(messages)==2 and "changed" in messages[1]["Subject"]
            assert "replacement-password" not in messages[1].get_content()
            await browser.close()
        result={"passed":True,"transport":"actual loopback SMTP socket; synthetic recipient; no external email",
                "checks":["Forgot password link and request UI","SMTP reset message","fragment token removed from address bar",
                          "password confirmation","password reset UI","no automatic login","old password rejected",
                          "new password login","one-use reset link","SMTP change notification","mobile layout"],"output":str(output)}
        (output / "results.json").write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps(result,indent=2),flush=True)
    finally:
        for process in reversed(processes):
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        for log in logs: log.close()
        mail_server.close(); await mail_server.wait_closed()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    asyncio.run(main(parser.parse_args().output_dir))
