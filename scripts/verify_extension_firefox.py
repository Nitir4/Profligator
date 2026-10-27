"""Firefox connection/popup acceptance, called by verify_extension.py --firefox."""
import json
import os
import shutil


def verify_firefox(output, web_origin):
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service
    from selenium.webdriver.support.ui import WebDriverWait

    os.environ["SE_CACHE_PATH"] = str(output / "selenium-cache")
    options = Options()
    options.binary_location = shutil.which("firefox")
    options.add_argument("-headless")
    # This applies only to WebDriver's fresh temporary profile and lets the test
    # resolve its own extension UUID, without exposing credentials or tokens.
    driver = webdriver.Firefox(options=options, service=Service(service_args=["--allow-system-access"],
        log_output=str(output / "firefox-driver.log")))
    try:
        driver.set_page_load_timeout(30)
        wait = WebDriverWait(driver, 20)
        driver.install_addon(str(output / "extension/firefox.zip"), temporary=True)
        driver.get(web_origin + "/login")
        driver.find_element(By.ID, "email").send_keys("extension@example.com")
        driver.find_element(By.ID, "password").send_keys("ExtensionTest2026!")
        driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        wait.until(lambda d: "/onboarding/profiles" in d.current_url)
        driver.get(web_origin + "/extension/connect")
        wait.until(lambda d: "The extension is available in this browser." in d.find_element(By.TAG_NAME, "body").text)
        connect = wait.until(lambda d: d.find_element(By.XPATH, '//button[text()="Connect this browser"]'))
        wait.until(lambda d: connect.is_enabled())
        connect.click()
        wait.until(lambda d: "Browser connected. Open a supported question" in d.find_element(By.TAG_NAME, "body").text)
        driver.save_screenshot(str(output / "firefox-connection.png"))
        driver.set_context("chrome")
        uuids = json.loads(driver.execute_script("return Services.prefs.getStringPref('extensions.webextensions.uuids');"))
        driver.set_context("content")
        driver.get(f"moz-extension://{uuids['profligator@profligator.local']}/popup.html")
        wait.until(lambda d: "Connected as extension_test" in d.find_element(By.ID, "connection").text)
        driver.save_screenshot(str(output / "firefox-popup.png"))
        driver.find_element(By.ID, "disconnect").click()
        wait.until(lambda d: "Connect your existing Profligator account." in d.find_element(By.ID, "connection").text)
        driver.get(web_origin + "/extension/connect")
        wait.until(lambda d: "No active connections." in d.find_element(By.TAG_NAME, "body").text)
        result = {"passed": True, "browser": "Firefox", "checks": ["temporary package installation",
            "web session bridge", "scoped background authentication", "popup", "disconnect and server revocation"],
            "limits": "Platform page extraction and installed alerts are exercised in Chromium, not this Firefox smoke check."}
        (output / "firefox-results.json").write_text(json.dumps(result, indent=2))
        print("Firefox installed connection and popup acceptance passed.", flush=True)
    except Exception:
        driver.save_screenshot(str(output / "firefox-failure.png"))
        (output / "firefox-failure.html").write_text(driver.page_source)
        try:
            driver.set_context("chrome")
            messages = driver.execute_script("return Services.console.getMessageArray().map(message => message.message).filter(message => /profligator|bridge|background|extension/i.test(message));")
            (output / "firefox-console.json").write_text(json.dumps(messages, indent=2))
        except Exception:
            pass
        raise
    finally:
        driver.quit()
