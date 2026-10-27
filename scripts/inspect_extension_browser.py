"""Confirm the extension in the isolated real-account Chromium test window."""

import argparse
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BROWSER_PROFILE = ROOT / 'artifacts/real-account-browser'


async def main(reload_extension=False, screenshot_dir=None, browser_profile=DEFAULT_BROWSER_PROFILE):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp("http://127.0.0.1:9223")
        context = browser.contexts[0]
        # MV3 workers can be asleep. Locate only our unpacked extension in this
        # owned test profile and open its popup to wake the worker.
        preferences = json.loads((browser_profile / 'Default/Preferences').read_text())
        expected = str(ROOT / 'apps/extension/dist/chrome')
        for key, entry in preferences.get('extensions', {}).get('settings', {}).items():
            if entry.get('path') == expected:
                url = f'chrome-extension://{key}/popup.html'
                if reload_extension:
                    # Chromium requires developer mode when reloading unpacked
                    # extensions. Use its manager in this owned test profile.
                    manager = await context.new_page()
                    try:
                        await manager.goto('chrome://extensions/')
                        await manager.evaluate('''async id => {
                            await chrome.developerPrivate.updateProfileConfiguration({inDeveloperMode:true});
                            await chrome.developerPrivate.reload(id, {failQuietly:true});
                            for (let attempt = 0; attempt < 50; attempt++) {
                                const info = await chrome.developerPrivate.getExtensionInfo(id);
                                if (info.state === 'ENABLED') return;
                                await new Promise(resolve => setTimeout(resolve, 200));
                            }
                            throw new Error('The owned extension did not finish reloading');
                        }''', key)
                    finally:
                        await manager.close()
                popup = next((page for page in context.pages if page.url == url), None)
                if popup is None:
                    popup = await context.new_page()
                await popup.goto(url)
                await popup.bring_to_front()
                manifest = await popup.evaluate('chrome.runtime.getManifest()')
                assert manifest['name'] == 'Profligator'
                await popup.locator('#connection').filter(has_not_text='Checking connection').wait_for()
                await popup.evaluate('document.fonts.ready')
                visuals = await popup.evaluate('''() => ({
                    background: getComputedStyle(document.documentElement).backgroundColor,
                    primary: getComputedStyle(document.querySelector('#connect')).backgroundColor,
                    font: getComputedStyle(document.body).fontFamily,
                    brand_icon_loaded: document.querySelector('.brand img').naturalWidth > 0
                })''')
                assert visuals['background'] == 'rgb(255, 255, 255)', visuals
                assert visuals['primary'] == 'rgb(79, 70, 229)', visuals
                assert visuals['font'] == 'Inter, sans-serif', visuals
                assert visuals['brand_icon_loaded'], visuals
                if screenshot_dir:
                    screenshot_dir.mkdir(parents=True, exist_ok=True)
                    bounds = await popup.locator('body').bounding_box()
                    await popup.screenshot(path=str(screenshot_dir / 'popup.png'), clip=bounds)
                print(json.dumps({'loaded':True,'name':manifest['name'],'version':manifest['version'],
                    'browser':'isolated Chromium profile','origin':'http://localhost:5173',
                    'popup_opened':True,'visuals':visuals,
                    'connection_status':await popup.locator('#connection').inner_text(),
                    'signed_in_account_acceptance':False}),flush=True)
                return
        raise RuntimeError("Profligator extension was not found in the owned test profile")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reload', action='store_true', help='Reload only the extension in the owned test profile')
    parser.add_argument('--screenshot-dir', type=Path)
    parser.add_argument('--browser-profile', type=Path, default=DEFAULT_BROWSER_PROFILE)
    args = parser.parse_args()
    asyncio.run(main(args.reload, args.screenshot_dir, args.browser_profile))
