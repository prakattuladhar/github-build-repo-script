#!/usr/bin/env python3
"""
Clone all repositories from a GitHub organization.

Features
- Uses GitHub REST API v3 with pagination
- Optional authentication via token (env or flag)
- Choose SSH or HTTPS clone URL
- Skip forks/archived by default; optional include
- Optional shallow clones; optional update existing repos
- Simple name filter via substring or regex

Usage examples
  python3 clone_org_repos.py ics365-fall-2025 \
    --token $GITHUB_TOKEN --dest ./ics365 --protocol https --shallow --update

Requirements
- Python 3.8+ (tested with 3.12)
- `git` available on PATH

Token
- Read from `--token`, or env `GITHUB_TOKEN` or `GH_TOKEN`.
- Needed for private repos or to avoid rate limits.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

try:
    # Prefer stdlib (no external deps)
    from urllib.request import Request, urlopen
    from urllib.parse import urlencode
except Exception as e:  # pragma: no cover
    print(f"Failed to import urllib modules: {e}", file=sys.stderr)
    sys.exit(2)


API_BASE = "https://api.github.com"


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def ensure_git_available() -> None:
    if shutil.which("git") is None:
        eprint("Error: `git` is not found on PATH. Please install Git.")
        sys.exit(1)


def get_token(cli_token: Optional[str]) -> Optional[str]:
    if cli_token:
        return cli_token.strip()
    env = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    return env.strip() if env else None


def gh_request(url: str, token: Optional[str]) -> tuple[int, Dict[str, str], bytes]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "clone-org-repos-script",
    }
    if token:
        # Works for classic and fine-grained tokens
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req) as resp:
            code = resp.getcode()
            headers_out = {k: v for k, v in resp.headers.items()}
            data = resp.read()
            return code, headers_out, data
    except Exception as e:
        raise RuntimeError(f"Request failed: {url}: {e}")


def fetch_org_repos(
    org: str,
    token: Optional[str],
    include_forks: bool,
    include_archived: bool,
    visibility: str,
    type_param: str,
) -> List[dict]:
    """
    Fetch all repos for the org using REST v3, handling pagination.

    visibility: filter locally: public|private|all
    type_param: maps to API 'type' query: all|public|private|forks|sources|member
    """
    per_page = 100
    page = 1
    repos: List[dict] = []
    while True:
        query = {
            "per_page": per_page,
            "page": page,
            "type": type_param,
        }
        url = f"{API_BASE}/orgs/{org}/repos?{urlencode(query)}"
        code, headers, body = gh_request(url, token)

        # Handle simple rate limiting feedback
        if code == 403 and headers.get("X-RateLimit-Remaining") == "0":
            reset = headers.get("X-RateLimit-Reset")
            if reset and reset.isdigit():
                reset_ts = int(reset)
                wait_secs = max(0, reset_ts - int(time.time()))
                if wait_secs <= 600:
                    eprint(f"Rate limited. Waiting {wait_secs}s until reset...")
                    time.sleep(wait_secs + 1)
                    continue
            raise SystemExit(
                "GitHub API rate limit exceeded. Provide a token or try later."
            )

        if code != 200:
            raise SystemExit(f"GitHub API error {code} for {url}: {body[:200]!r}")

        try:
            page_repos = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(f"Failed to parse JSON from GitHub: {e}")

        if not page_repos:
            break

        repos.extend(page_repos)
        page += 1

    # Local filtering
    out = []
    for r in repos:
        if not include_forks and r.get("fork"):
            continue
        if not include_archived and r.get("archived"):
            continue
        if visibility != "all":
            if visibility == "public" and r.get("private"):
                continue
            if visibility == "private" and not r.get("private"):
                continue
        out.append(r)
    return out


def choose_remote_url(repo: dict, protocol: str) -> str:
    if protocol == "ssh":
        return repo.get("ssh_url")
    # Default to HTTPS
    return repo.get("clone_url")


def clone_or_update(
    repo: dict,
    dest_dir: Path,
    protocol: str,
    shallow: bool,
    update_existing: bool,
) -> bool:
    name = repo.get("name") or repo.get("full_name", "repo").split("/")[-1]
    target = dest_dir / name
    remote = choose_remote_url(repo, protocol)

    if target.exists():
        if (target / ".git").is_dir():
            if update_existing:
                eprint(f"Updating {name}...")
                cmd = ["git", "-C", str(target), "pull", "--ff-only", "--quiet"]
                res = subprocess.run(cmd)
                return res.returncode == 0
            else:
                eprint(f"Skipping existing repo: {name}")
                return True
        else:
            eprint(f"Path exists and is not a git repo, skipping: {target}")
            return False

    cmd = ["git", "clone", remote, str(target)]
    if shallow:
        cmd[2:2] = ["--depth", "1"]
    eprint(f"Cloning {name} -> {target}")
    res = subprocess.run(cmd)
    return res.returncode == 0


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("org", help="GitHub organization login (e.g., ics365-fall-2025)")
    p.add_argument("--dest", default=".", help="Destination directory (default: cwd)")
    p.add_argument(
        "--token",
        default=None,
        help="GitHub token. Falls back to env GITHUB_TOKEN/GH_TOKEN.",
    )
    p.add_argument(
        "--protocol",
        choices=["ssh", "https"],
        default="ssh",
        help="Clone protocol to use (default: ssh)",
    )
    p.add_argument("--include-forks", action="store_true", help="Include forked repos")
    p.add_argument("--include-archived", action="store_true", help="Include archived repos")
    p.add_argument(
        "--visibility",
        choices=["all", "public", "private"],
        default="all",
        help="Filter repos by visibility (default: all)",
    )
    p.add_argument(
        "--type",
        choices=["all", "public", "private", "forks", "sources", "member"],
        default="all",
        help="API type parameter; usually 'all' is fine",
    )
    p.add_argument("--shallow", action="store_true", help="Perform shallow clone (--depth 1)")
    p.add_argument(
        "--update",
        action="store_true",
        help="If repo dir exists, run 'git pull --ff-only'",
    )
    p.add_argument(
        "--match",
        default=None,
        help="Substring to match in repo name (case-insensitive)",
    )
    p.add_argument(
        "--regex",
        default=None,
        help="Python regex to filter repo names (applies after --match)",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    ensure_git_available()
    token = get_token(args.token)

    dest = Path(args.dest).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)

    eprint(f"Listing repos for org: {args.org}")
    repos = fetch_org_repos(
        org=args.org,
        token=token,
        include_forks=args.include_forks,
        include_archived=args.include_archived,
        visibility=args.visibility,
        type_param=args.type,
    )

    # Additional name filters
    if args.match:
        needle = args.match.lower()
        repos = [r for r in repos if needle in (r.get("name") or "").lower()]
    if args.regex:
        try:
            rx = re.compile(args.regex)
        except re.error as e:
            eprint(f"Invalid regex: {e}")
            return 2
        repos = [r for r in repos if rx.search(r.get("name") or "")]

    total = len(repos)
    if total == 0:
        eprint("No repositories matched filters.")
        return 0

    eprint(f"Found {total} repos. Starting clone to: {dest}")
    ok = 0
    failed: List[str] = []
    for i, r in enumerate(repos, start=1):
        name = r.get("name") or r.get("full_name", f"repo-{i}")
        eprint(f"[{i}/{total}] {name}")
        if clone_or_update(r, dest, args.protocol, args.shallow, args.update):
            ok += 1
        else:
            failed.append(name)

    eprint("")
    eprint(f"Completed: {ok}/{total} successful")
    if failed:
        eprint("Failed repos:")
        for name in failed:
            eprint(f" - {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

