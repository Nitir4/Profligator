/* Shared pure logic. Loaded only from the extension package. */
(() => {
  function platform(value) {
    try {
      const url = new URL(value);
      if (url.protocol !== "https:" || url.username || url.password || url.port) return null;
      const host = url.hostname.replace(/^www\./, "");
      if (host === "leetcode.com") return "leetcode";
      if (["geeksforgeeks.org", "practice.geeksforgeeks.org"].includes(host)) return "geeksforgeeks";
      if (["codeforces.com", "mirror.codeforces.com"].includes(host)) return "codeforces";
    } catch { /* Unsupported URL. */ }
    return null;
  }
  function identify(value) {
    let url;
    try { url = new URL(value); } catch { return null; }
    if (url.protocol !== "https:" || url.username || url.password || url.port) return null;
    const host = url.hostname.replace(/^www\./, "");
    let match;
    if (host === "leetcode.com" && (match = url.pathname.match(/^\/(?:contest\/[a-z0-9-]+\/)?problems\/([a-z0-9-]+)(?:\/|$)/))) {
      return { platform: "leetcode", source_id: match[1], canonical_url: `https://leetcode.com/problems/${match[1]}/` };
    }
    if (["geeksforgeeks.org", "practice.geeksforgeeks.org"].includes(host) &&
        (match = url.pathname.match(/^\/problems\/([a-z0-9-]+)(?:\/|$)/))) {
      return { platform: "geeksforgeeks", source_id: match[1], canonical_url: `https://www.geeksforgeeks.org/problems/${match[1]}/1` };
    }
    if (["codeforces.com", "mirror.codeforces.com"].includes(host)) {
      match = url.pathname.match(/^\/problemset\/problem\/(\d+)\/([A-Za-z]\d?)(?:\/|$)/) ||
        url.pathname.match(/^\/(?:contest|gym)\/(\d+)\/problem\/([A-Za-z]\d?)(?:\/|$)/);
      if (match) return { platform: "codeforces", source_id: `${match[1]}-${match[2].toUpperCase()}`,
        canonical_url: Number(match[1]) >= 100000 ? `https://codeforces.com/gym/${match[1]}/problem/${match[2].toUpperCase()}`
          : `https://codeforces.com/problemset/problem/${match[1]}/${match[2].toUpperCase()}` };
    }
    return null;
  }

  const selectors = {
    leetcode: {
      title: ['[data-cy="question-title"]', '[data-cy="question-title-link"]', '[class*="text-title"]', 'h1'],
      statement: ['[data-track-load="description_content"]', '[data-cy="question-content"]', '.question-content', '[class*="elfjS"]'],
      topics: ['a[href*="/tag/"]'],
    },
    geeksforgeeks: {
      title: ['[class*="problems_header_content__title"]', '[class*="problemHeading"]', '[class*="problemTitle"]', 'h1', 'h3'],
      statement: ['[class*="problems_problem_content"]', '[class*="problems_problemContent"]', '[class*="problemStatement"]', '.problem-statement', '#problem-statement'],
      topics: ['a[href*="/explore?page=1&category="]', 'a[href*="/explore?category="]'],
    },
    codeforces: { title: ['.problem-statement .title'], statement: ['.problem-statement'], topics: ['.tag-box'] },
  };

  function text(element) {
    if (!element) return "";
    const copy = element.cloneNode(true);
    for (const node of copy.querySelectorAll('script,style,button,input,textarea,select,[aria-hidden="true"],.header .title')) node.remove();
    for (const node of copy.querySelectorAll("br")) node.replaceWith("\n");
    for (const node of copy.querySelectorAll("p,div,li,pre,h1,h2,h3,h4,tr")) node.append("\n");
    for (const node of [...copy.querySelectorAll("sup,sub")].reverse()) node.replaceWith(`${node.tagName.toLowerCase() === "sup" ? "^" : "_"}(${node.textContent})`);
    for (const node of copy.querySelectorAll("td,th")) node.prepend(" | ");
    for (const node of copy.querySelectorAll("img")) {
      let source = node.getAttribute("src") || "";
      const base = /^https?:/.test(element.ownerDocument?.baseURI || "") ? element.ownerDocument.baseURI : globalThis.location?.href;
      try { if (source) source = new URL(source, base).href; } catch { /* Keep the original public marker. */ }
      node.replaceWith(`[image: ${source} ${node.getAttribute("alt") || ""}]`);
    }
    return copy.textContent.split(/\n/).map(line => line.replace(/[ \t\r\f\v]+/g, " ").trim()).filter(Boolean).join("\n");
  }

  function statementText(element) {
    if (!element || element.querySelector("svg,canvas,math")) return null;
    const value = text(element);
    if (/^(?:authentication required|please (?:sign|log) in|(?:sign|log) in to (?:view|continue|access)(?: this problem)?)[.!\s]*$/i.test(value)) return null;
    return value && value.length <= 50000 ? value : null;
  }

  function fromHtml(html) {
    if (typeof html !== "string" || html.length > 500000 || typeof DOMParser === "undefined") return null;
    return statementText(new DOMParser().parseFromString(html, "text/html").body);
  }

  function extract(document, value) {
    const problem = identify(value);
    if (!problem) return null;
    const adapter = selectors[problem.platform];
    const find = (list) => list.map((selector) => document.querySelector(selector)).find(Boolean);
    const heading = find(adapter.title)?.textContent || "";
    if (problem.platform === "codeforces" && heading.match(/^\s*([A-Z]\d?)\./)?.[1] !== problem.source_id.split("-")[1]) return null;
    const canonical = document.querySelector('link[rel="canonical"]')?.getAttribute("href");
    const canonicalProblem = canonical ? identify(canonical) : null;
    if (canonicalProblem && (canonicalProblem.platform !== problem.platform || canonicalProblem.source_id !== problem.source_id)) return null;
    let title = heading.replace(/^\s*(?:\d+\.|[A-Z]\d?\.)\s*/, "").trim();
    if (!title) title = document.title.replace(/\s*[-|–]\s*(?:LeetCode|GeeksforGeeks|Codeforces).*$/i, "").trim();
    if (!title || /^(?:LeetCode|GeeksforGeeks|Codeforces|Just a moment|Loading)/i.test(title)) return null;
    // LeetCode navigates without reloading. Do not match a newly opened URL using the preceding question's DOM.
    if (problem.platform === "leetcode" && title.toLowerCase().replace(/[^a-z0-9]/g, "") !== problem.source_id.replace(/[^a-z0-9]/g, "")) return null;
    const element = find(adapter.statement);
    const statement = statementText(element);
    const topics = [...new Set(adapter.topics.flatMap((selector) => [...document.querySelectorAll(selector)]
      .map((node) => node.textContent.trim()).filter((topic) => topic && topic.length <= 128)))].slice(0, 50);
    return { ...problem, title: title.slice(0, 512), statement, topics };
  }

  function attemptUrl(attempt) {
    if (!attempt) return null;
    for (const value of [attempt.submission_url, attempt.problem_url]) {
      try {
        const url = new URL(value);
        const host = url.hostname.replace(/^www\./, "");
        const hosts = { leetcode: ["leetcode.com"], geeksforgeeks: ["geeksforgeeks.org", "practice.geeksforgeeks.org"],
          codeforces: ["codeforces.com", "mirror.codeforces.com"] };
        if (url.protocol === "https:" && !url.username && !url.password && !url.port && hosts[attempt.platform]?.includes(host)) return url.href;
      } catch { /* Invalid source URLs never become clickable links. */ }
    }
    return null;
  }

  function describe(result) {
    if (result?.duplicate) return result.status === "source_identity" ? "Already in your solved history" : "A previous matching problem was found";
    return {
      matching_disabled: "No exact match found. Similarity matching will be available after the model is enabled.",
      insufficient_data: "The question text is unavailable. Only known question identities could be checked.",
      matching_unavailable: "Similarity matching is temporarily unavailable. Try again shortly.",
      no_confirmed_match: "No confirmed match found in your imported history.",
      sign_in_required: "Connect your Profligator account to check your history.",
      api_unavailable: "Profligator could not be reached. Check that the app is running, then try again.",
      unsupported: "Open a LeetCode, GFG or Codeforces question to check your history.",
      loading: "Waiting for the question to finish loading…",
      checking: "Checking your imported history…",
    }[result?.status] || "This question could not be checked. Try again.";
  }

  globalThis.PF_CORE = { identify, platform, extract, attemptUrl, describe, fromHtml };
})();
