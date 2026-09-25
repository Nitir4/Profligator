import { useState } from "react";
import addressLockIcon from "./assets/extension/address-lock.svg";
import arrowRightIcon from "./assets/extension/arrow-right.svg";
import backIcon from "./assets/extension/back.svg";
import bookmarkIcon from "./assets/extension/bookmark.svg";
import closeIcon from "./assets/extension/close.svg";
import duplicateIcon from "./assets/extension/duplicate.svg";
import extensionPinIcon from "./assets/extension/extension-pin.svg";
import forwardIcon from "./assets/extension/forward.svg";
import problemBookmarkIcon from "./assets/extension/problem-bookmark.svg";
import problemShareIcon from "./assets/extension/problem-share.svg";
import profligatorMarkIcon from "./assets/extension/profligator-mark.svg";
import refreshIcon from "./assets/extension/refresh.svg";
import syncedIcon from "./assets/extension/synced.svg";

const examples = [
  { input: "nums = [1,1,1], k = 2", output: "2" },
  { input: "nums = [1,2,3], k = 3", output: "2" },
];

function BrowserChrome() {
  return (
    <header className="extension-browser-bar" data-node-id="2603:1162">
      <div className="extension-browser-left">
        <div className="window-controls" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <div className="browser-history-controls">
          <button type="button" aria-label="Go back">
            <img src={backIcon} alt="" />
          </button>
          <button type="button" aria-label="Go forward" disabled>
            <img src={forwardIcon} alt="" />
          </button>
          <button type="button" aria-label="Refresh page">
            <img src={refreshIcon} alt="" />
          </button>
        </div>
      </div>

      <div className="browser-address-wrap">
        <div className="browser-address">
          <div>
            <img src={addressLockIcon} alt="Secure" />
            <span>https://</span>
            <strong>leetcode.com</strong>
            <span>/problems/subarray-sum-equals-k/description/</span>
          </div>
          <img src={bookmarkIcon} alt="" />
        </div>
      </div>

      <div className="browser-profile-area">
        <span className="browser-extension-pin" aria-label="Profligator extension active">
          <img src={extensionPinIcon} alt="" />
          <i aria-hidden="true" />
        </span>
        <span className="browser-profile-divider" aria-hidden="true" />
        <span className="browser-avatar">AL</span>
      </div>
    </header>
  );
}

function PlatformToolbar() {
  return (
    <nav className="coding-toolbar" aria-label="Coding platform navigation" data-node-id="2603:1216">
      <div className="coding-toolbar-left">
        <a className="coding-brand" href="#problem">
          <span aria-hidden="true">&lt;/&gt;</span>
          <strong>LeetCode</strong>
        </a>
        <i aria-hidden="true" />
        <div className="coding-nav-links">
          <a className="active" href="#problem">Problem</a>
          <a href="#submissions">Submissions</a>
          <a href="#solution">Solution</a>
          <a href="#discuss">Discuss</a>
        </div>
      </div>
      <div className="coding-actions">
        <span>Python3</span>
        <button type="button">Run</button>
        <button type="button">Submit</button>
      </div>
    </nav>
  );
}

function ProblemPanel() {
  return (
    <section className="problem-panel" id="problem" aria-labelledby="problem-title" data-node-id="2603:1241">
      <div className="problem-heading">
        <div>
          <h1 id="problem-title">560. Subarray Sum Equals K</h1>
          <div className="problem-meta">
            <span>Medium</span>
            <i aria-hidden="true">•</i>
            <p>Topics: Hash Table, Prefix Sum, Array</p>
          </div>
        </div>
        <div className="problem-tools">
          <button type="button" aria-label="Bookmark problem">
            <img src={problemBookmarkIcon} alt="" />
          </button>
          <button type="button" aria-label="Share problem">
            <img src={problemShareIcon} alt="" />
          </button>
        </div>
      </div>

      <div className="problem-copy">
        <p>
          Given an array of integers <code>nums</code> and an integer <code>k</code>, return the
          total number of subarrays whose sum equals to <code>k</code>.
        </p>
        <p>A subarray is a contiguous non-empty sequence of elements within an array.</p>
      </div>

      <div className="problem-examples">
        {examples.map((example, index) => (
          <article key={example.input}>
            <strong>EXAMPLE {index + 1}:</strong>
            <code>Input: {example.input}</code>
            <code>Output: {example.output}</code>
          </article>
        ))}
      </div>

      <div className="problem-constraints">
        <strong>CONSTRAINTS:</strong>
        <ul>
          <li>1 ≤ nums.length ≤ 2 × 10<sup>4</sup></li>
          <li>-1000 ≤ nums[i] ≤ 1000</li>
          <li>-10<sup>7</sup> ≤ k ≤ 10<sup>7</sup></li>
        </ul>
      </div>
    </section>
  );
}

function EditorPanel() {
  return (
    <section className="editor-panel" aria-label="Code editor" data-node-id="2603:1309">
      <div className="editor-tabs">
        <span>solution.py</span>
        <span>(Auto-saved)</span>
        <div>
          <span>Python3</span>
          <span>Ln 4, Col 8</span>
        </div>
      </div>
      <div className="code-editor" aria-label="Python solution">
        <div className="code-line"><span>1</span><code><b>class</b> <em>Solution</em>:</code></div>
        <div className="code-line"><span>2</span><code>  <b>def</b> <em>subarraySum</em>(self, nums: List[int], k: int) -&gt; int:</code></div>
        <div className="code-line"><span>3</span><code>      <i># Start typing your solution...</i></code></div>
        <div className="code-line"><span>4</span><code>      <b>pass</b></code></div>
      </div>
    </section>
  );
}

function DuplicateNotification({ onDismiss }: { onDismiss: () => void }) {
  return (
    <aside className="duplicate-toast" aria-labelledby="duplicate-title" data-node-id="2603:1342">
      <div className="duplicate-toast-accent" />
      <div className="duplicate-toast-body">
        <div className="duplicate-toast-header">
          <div className="duplicate-brand">
            <span><img src={profligatorMarkIcon} alt="" /></span>
            <strong>Profligator</strong>
            <small>EXTENSION</small>
          </div>
          <button type="button" aria-label="Dismiss notification" onClick={onDismiss}>
            <img src={closeIcon} alt="" />
          </button>
        </div>

        <div className="duplicate-summary">
          <h2 id="duplicate-title"><img src={duplicateIcon} alt="" />Duplicate Problem Detected</h2>
          <p>You have previously attempted a similar problem in your connected coding accounts.</p>
        </div>

        <section className="previous-attempt" aria-label="Previous attempt details">
          <div className="previous-attempt-labels">
            <span>YOUR PREVIOUS ATTEMPT</span>
            <strong><i aria-hidden="true" />SOLVED • OCT 2024</strong>
          </div>
          <div className="previous-attempt-title">
            <h3>Subarray Sum Divisible by K</h3>
            <p><span><i aria-hidden="true" />GeeksforGeeks</span><b>•</b><code>Prefix Sum &amp; Hash</code></p>
          </div>
          <div className="match-score">
            <span>Algorithmic similarity:</span>
            <strong>96% concept match</strong>
          </div>
        </section>

        <div className="duplicate-actions">
          <button type="button" onClick={onDismiss}>Dismiss</button>
          <a href="/dashboard">
            <span>View Previous Attempt</span>
            <img src={arrowRightIcon} alt="" />
          </a>
        </div>
      </div>
      <footer className="duplicate-toast-footer">
        <span><img src={syncedIcon} alt="" />Synced with your Unified Portfolio</span>
        <a href="/settings/sharing">Settings</a>
      </footer>
    </aside>
  );
}

function ExtensionNotificationPage() {
  const [notificationVisible, setNotificationVisible] = useState(true);

  return (
    <div className="extension-page" data-node-id="2603:1161">
      <BrowserChrome />
      <main className="coding-workspace" data-node-id="2603:1215">
        <PlatformToolbar />
        <div className="problem-layout">
          <ProblemPanel />
          <EditorPanel />
        </div>
      </main>

      {notificationVisible && (
        <DuplicateNotification onDismiss={() => setNotificationVisible(false)} />
      )}

      <footer className="extension-status-bar" data-node-id="2603:1203">
        <span><i aria-hidden="true" />Profligator Chrome &amp; Firefox Extension • Active Tab Detection</span>
        <div>
          <span>Context: LeetCode #560</span>
          <span>Detected Duplicate: GFG (Subarray Sum Divisible by K)</span>
          <span>Status: {notificationVisible ? "Floating Toast" : "Dismissed"}</span>
        </div>
      </footer>
    </div>
  );
}

export default ExtensionNotificationPage;
