# Profligator browser extension

Build from the repository root with `npm run extension:build`. Load `dist/chrome` in Chromium, or `dist/firefox/manifest.json` temporarily in Firefox. Open the popup and choose **Connect with Profligator**, then authorize the browser using your existing signed-in candidate account.

See [installation, behavior and verification](../../docs/browser-extension.md).

The popup also offers **Import solved history** and optional **Track accepted submissions** for linked LeetCode, GFG and Codeforces accounts. LeetCode imports require a tab signed in to the selected linked handle; GFG/Codeforces use their provider collectors. Available source dates are retained, and unknown dates remain unknown. Reload the extension and coding tabs after rebuilding.
