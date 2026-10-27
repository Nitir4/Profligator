#!/usr/bin/env python3
"""Check tracked source or reachable Git history without printing matched data.

Use --private-terms-file with an ignored JSON list or newline-delimited local
file to also check operator-specific values. Keep that file out of Git.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "personal_mailbox": rb"[A-Za-z0-9._%+-]+@(?:gmail\.com|outlook\.com|hotmail\.com|yahoo\.com|protonmail\.com|proton\.me)\b",
    "cloud_instance_hostname": rb"[a-z0-9.-]+\.cloudapp\.azure\.com\b",
    "personal_home_directory": rb"/home/(?!runner(?:/|\b)|profligator(?:/|\b))[A-Za-z0-9_.-]+/",
    "private_design_reference": rb"https?://(?:www\.)?figma\.com/(?:design|file)/[A-Za-z0-9]+",
    "private_key": rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "provider_credential": rb"(?:gsk_|ghp_|github_pat_|GOCSPX-)[A-Za-z0-9_-]{20,}",
}


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT, help="Repository to inspect (also supports bare history)")
    parser.add_argument("--history", action="store_true", help="Check every reachable blob and commit")
    parser.add_argument("--private-terms-file", type=Path)
    args = parser.parse_args()
    ROOT = args.repository.resolve()
    patterns = {name: re.compile(value, re.I) for name, value in PATTERNS.items()}
    terms = []
    if args.private_terms_file:
        content = args.private_terms_file.read_text()
        values = json.loads(content) if args.private_terms_file.suffix == ".json" else content.splitlines()
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            parser.error("Private terms must be a list of strings")
        terms = [re.compile(rb"(?<![A-Za-z0-9_])" + re.escape(value.encode()) + rb"(?![A-Za-z0-9_])", re.I)
                 for value in values if value.strip()]
    findings = set()
    checked = 0

    def inspect(label, data):
        nonlocal checked
        checked += 1
        for kind, pattern in patterns.items():
            if pattern.search(data):
                findings.add((label, kind))
        if any(term.search(data) for term in terms):
            findings.add((label, "configured_private_term"))

    def private_filename(path):
        name = Path(path).name
        return (name.startswith(".env") and not name.endswith(".example")) or name.endswith((".pem", ".key", ".db"))

    if args.history:
        for line in git("rev-list", "--objects", "--all").splitlines():
            oid, _, raw_path = line.partition(b" ")
            kind = git("cat-file", "-t", oid.decode()).strip()
            if kind == b"blob":
                path = raw_path.decode(errors="replace")
                if private_filename(path):
                    findings.add((path, "private_runtime_file"))
                inspect(path, git("cat-file", "blob", oid.decode()))
            elif kind == b"commit":
                inspect("commit metadata", git("cat-file", "commit", oid.decode()))
    else:
        for raw_path in git("ls-files", "-z").split(b"\0"):
            if not raw_path:
                continue
            path = raw_path.decode()
            if private_filename(path):
                findings.add((path, "private_runtime_file"))
            file = ROOT / path
            if file.is_file():
                inspect(path, file.read_bytes())
    result = {"scope": "reachable history" if args.history else "tracked working files", "objects_checked": checked,
              "findings": [{"path": path, "category": kind} for path, kind in sorted(findings)], "passed": not findings}
    print(json.dumps(result, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
