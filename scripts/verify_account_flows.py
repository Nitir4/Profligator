"""Isolated UI acceptance for draft pages, verification and password recovery.

All email delivery and source profile names are controlled locally. This does
not send Gmail messages or establish live platform format compatibility.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import parse_qs, urlsplit

from playwright.async_api import async_playwright
from verify_extension import ROOT, port, ready


async def main(output_root):
    output_root.mkdir(parents=True, exist_ok=True)
    output=Path(tempfile.mkdtemp(prefix='account-flows-',dir=output_root))
    web_port,api_port=port(),port()
    origin=f'http://localhost:{web_port}'
    (output/'server.py').write_text(f'''
import sys
sys.path.insert(0,{str(ROOT / 'apps/api/src')!r})
from datetime import UTC, datetime
from fastapi import HTTPException
from profligator_api.config import Settings
from profligator_api.main import create_app
from profligator_api.schemas import ProfileSnapshot
from profligator_api.connectors.leetcode import LeetCodeConnector
from profligator_api.connectors.geeksforgeeks import GeeksForGeeksConnector
from profligator_api.connectors.codeforces import CodeforcesConnector
settings=Settings(_env_file=None,database_url={('sqlite:///'+str(output/'test.db'))!r},
 public_web_url={origin!r},cors_origins=[{origin!r}],matching_backend='disabled',
 password_reset_email_backend='smtp',smtp_host='localhost',smtp_from_email='reset@example.com',
 verification_email_backend='smtp',verification_smtp_host='localhost',verification_smtp_from_email='verify@example.com')
app=create_app(settings)
mail=[]
app.state.recovery_mailer.send=lambda recipient,subject,body:mail.append(dict(recipient=recipient,subject=subject,body=body))
app.state.verification_mailer.send=lambda recipient,subject,body:mail.append(dict(recipient=recipient,subject=subject,body=body))
names={{}}
async def profile(self,canonical):
 return ProfileSnapshot(profile=canonical.model_copy(update={{'display_name':names.get(canonical.platform.value,'Unverified owner')}}),fetched_at=datetime.now(UTC))
for cls in [LeetCodeConnector,GeeksForGeeksConnector,CodeforcesConnector]: cls.fetch_profile=profile
# Test endpoints exist only in this generated isolated server, never in the app.
@app.get('/_test/mail')
def mailbox():return mail
@app.post('/_test/name')
def name(payload:dict):names[payload['platform']]=payload['name'];return {{'ok':True}}
''')
    processes=[];logs=[]
    try:
        for name,cmd,cwd,env,url in [
            ('api',[str(ROOT/'apps/api/.venv/bin/python'),'-m','uvicorn','server:app','--app-dir',str(output),'--host','127.0.0.1','--port',str(api_port)],ROOT,os.environ,f'http://127.0.0.1:{api_port}/health'),
            ('web',['node',str(ROOT/'node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port',str(web_port),'--strictPort'],ROOT/'apps/web',{**os.environ,'PROFLIGATOR_API_PORT':str(api_port)},origin)]:
            log=(output/f'{name}.log').open('w');logs.append(log)
            process=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
            processes.append(process);ready(url,process)
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
            context=await browser.new_context(viewport={'width':1280,'height':900})
            page=await context.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            for path,title in [('/privacy','Privacy'),('/terms','Terms of use'),('/status','Service status'),('/support','Contact support'),('/documentation','Getting started')]:
                await page.goto(origin+path)
                await page.get_by_role('heading',name=title,exact=True).wait_for()
                assert await page.locator('a[href="mailto:support@example.com"]').count()>0
                await page.set_viewport_size({'width':390,'height':844})
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                await page.screenshot(path=str(output/(path[1:]+'-mobile.png')),full_page=True)
            await page.set_viewport_size({'width':1280,'height':900})
            response=await context.request.post(origin+'/api/v1/auth/register',data={'email':'owner@example.com','handle':'owner','password':'original-password'})
            assert response.status==201
            for platform in ['leetcode','geeksforgeeks','codeforces']:
                response=await context.request.post(origin+'/api/v1/platform-profiles',data={'platform':platform,'handle_or_url':'sourceowner'})
                assert response.status==201,await response.text()
            await page.goto(origin+'/settings/account')
            await page.get_by_role('button',name='Send verification email').click()
            await page.get_by_role('status').filter(has_text='Verification email requested').wait_for()
            mailbox=(await (await context.request.get(f'http://127.0.0.1:{api_port}/_test/mail')).json())
            link=next(line for line in mailbox[-1]['body'].splitlines() if '/verify-email#token=' in line)
            await page.goto(link)
            await page.get_by_role('button',name='Verify email',exact=True).click()
            await page.get_by_role('status').filter(has_text='Your account email is verified').wait_for()
            assert await page.evaluate('location.hash')==''
            await page.get_by_role('link',name='Return to account settings').click()
            await page.get_by_text('owner@example.com: Verified',exact=True).wait_for()
            for platform in ['leetcode','geeksforgeeks','codeforces']:
                card=page.locator('.profile-detail-card').filter(has=page.get_by_role('heading',name=platform+' · sourceowner',exact=True)).last
                await card.get_by_role('button',name='Create ownership challenge').click()
                code=await card.locator('code').inner_text()
                await card.get_by_role('button',name='Check public profile name').click()
                await page.get_by_role('alert').filter(has_text='Challenge not found').wait_for()
                await context.request.post(f'http://127.0.0.1:{api_port}/_test/name',data={'platform':platform,'name':'Owner '+code})
                await card.get_by_role('button',name='Check public profile name').click()
                await card.get_by_text('Ownership: Verified',exact=True).wait_for()
            await page.screenshot(path=str(output/'account-verified-desktop.png'),full_page=True)
            await page.set_viewport_size({'width':390,'height':844})
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            await page.screenshot(path=str(output/'account-verified-mobile.png'),full_page=True)
            await context.request.post(origin+'/api/v1/auth/logout')
            await page.goto(origin+'/forgot-password')
            await page.get_by_label('Email address').fill('owner@example.com')
            await page.get_by_role('button',name='Send reset link',exact=True).click()
            await page.get_by_role('status').filter(has_text='If an account exists').wait_for()
            mailbox=await (await context.request.get(f'http://127.0.0.1:{api_port}/_test/mail')).json()
            link=next(line for line in mailbox[-1]['body'].splitlines() if '/reset-password#token=' in line)
            await page.goto(link)
            await page.get_by_label('Password',exact=True).fill('replacement-password')
            await page.get_by_label('Confirm password',exact=True).fill('replacement-password')
            await page.get_by_role('button',name='Update password',exact=True).click()
            await page.get_by_role('status').filter(has_text='Password updated').wait_for()
            assert (await context.request.post(origin+'/api/v1/auth/login',data={'email':'owner@example.com','password':'original-password'})).status==401
            assert (await context.request.post(origin+'/api/v1/auth/login',data={'email':'owner@example.com','password':'replacement-password'})).status==200
            recruiter = await browser.new_context()
            response = await recruiter.request.post(origin+'/api/v1/auth/register',data={'email':'recruiter@example.com','handle':'recruiter','password':'original-password','role':'recruiter'})
            assert response.status == 201
            recruiter_page = await recruiter.new_page()
            recruiter_page.on('pageerror',lambda error:errors.append(str(error)))
            await recruiter_page.goto(origin+'/settings/account')
            await recruiter_page.get_by_role('button',name='Send verification email').click()
            await recruiter_page.get_by_role('status').filter(has_text='Verification email requested').wait_for()
            assert await recruiter_page.get_by_role('heading',name='Coding-profile ownership').count() == 0
            assert not errors,errors
            await browser.close()
        result={'passed':True,'scope':'isolated SQLite, captured SMTP messages, controlled source profile responses; no live Gmail/platform acceptance',
                'checks':['five public pages desktop/mobile','support mail link','UI inbox verification and fragment removal','all three platform challenge mismatch/success','ownership desktop/mobile','UI recovery and replacement-password login','recruiter inbox-verification controls'],'output':str(output)}
        (output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    finally:
        for process in reversed(processes):
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        for log in logs:log.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,default=ROOT/'artifacts/account-flows')
    asyncio.run(main(parser.parse_args().output_dir.resolve()))
