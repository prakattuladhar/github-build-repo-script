#!/usr/bin/env python3
"""
Create private GitHub repos for students, add them as collaborators (push),
and seed each repo with a folder structure read from a text file.

Usage:
  export GITHUB_TOKEN=ghp_your_token_here
  python create_course_repos.py \
    --org ics365-fall-2025 \
    --csv students.csv \
    --structure structure.txt \
    [--dry-run]
"""

import argparse
import base64
import csv
import os
import re
import time
from typing import List, Optional

import requests

GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 20
SLEEP_BETWEEN_CALLS_SEC = 0.35
COLLAB_PERMISSION = "push"  # pull | triage | push | maintain | admin


# ----------------------------
# HTTP session with auth
# ----------------------------
def make_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return s


# ----------------------------
# Helpers
# ----------------------------
def parse_github_username(github_link: str) -> Optional[str]:
    m = re.search(r"github\.com/([^/?#\s]+)", github_link.strip())
    return m.group(1) if m else None


def normalize_student_name(name: str) -> str:
    return re.sub(r"\s+", "_", (name or "").strip()).lower()


def build_repo_name(student_name: str) -> str:
    return f"ICS365_fall_2025-{normalize_student_name(student_name)}"


def ensure_org_exists(session: requests.Session, org: str, dry_run: bool) -> bool:
    if dry_run:
        print(f"[DRY RUN] Would verify org exists: {org}")
        return True
    r = session.get(f"{GITHUB_API}/orgs/{org}", timeout=REQUEST_TIMEOUT)
    if r.status_code == 200:
        return True
    print(f"❌ Org '{org}' not found or token lacks access: {r.status_code} {r.text}")
    return False


def create_repo_in_org(session: requests.Session, org: str, repo_name: str, dry_run: bool) -> Optional[dict]:
    if dry_run:
        print(f"[DRY RUN] Would create repo {org}/{repo_name} (private, with README)")
        return {"full_name": f"{org}/{repo_name}", "owner": {"login": org}, "name": repo_name}

    payload = {"name": repo_name, "private": True, "auto_init": True}
    r = session.post(f"{GITHUB_API}/orgs/{org}/repos", json=payload, timeout=REQUEST_TIMEOUT)
    if r.status_code == 201:
        repo = r.json()
        print(f"✅ Created repo: {repo.get('full_name')} (private)")
        return repo
    if r.status_code == 422 and "name already exists" in r.text.lower():
        rr = session.get(f"{GITHUB_API}/repos/{org}/{repo_name}", timeout=REQUEST_TIMEOUT)
        if rr.status_code == 200:
            print(f"ℹ️  Repo already exists: {org}/{repo_name}")
            return rr.json()
    print(f"❌ Failed to create repo '{org}/{repo_name}': {r.status_code} {r.text}")
    return None


def add_collaborator(session: requests.Session, owner: str, repo: str, username: str,
                     permission: str, dry_run: bool) -> bool:
    if dry_run:
        print(f"[DRY RUN] Would add @{username} as collaborator with '{permission}' to {owner}/{repo}")
        return True

    url = f"{GITHUB_API}/repos/{owner}/{repo}/collaborators/{username}"
    r = session.put(url, json={"permission": permission}, timeout=REQUEST_TIMEOUT)
    if r.status_code in (201, 204, 202):
        state = {201: "invited", 204: "already a collaborator", 202: "invited (pending)"}[r.status_code]
        print(f"👤 @{username} {state} with '{permission}' on {owner}/{repo}")
        return True
    print(f"⚠️  Failed to add @{username} to {owner}/{repo}: {r.status_code} {r.text}")
    return False


def create_placeholder_file(session: requests.Session, owner: str, repo: str, path: str, dry_run: bool) -> None:
    path = path.strip().strip("/")
    if not path:
        return

    if dry_run:
        print(f"[DRY RUN] Would create {path}/.gitkeep in {owner}/{repo}")
        return

    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}/.gitkeep"
    message = f"Add placeholder for {path}"
    content_b64 = base64.b64encode(b"").decode("utf-8")
    r = session.put(url, json={"message": message, "content": content_b64}, timeout=REQUEST_TIMEOUT)
    if r.status_code in (201, 200):
        print(f"📂 Created {path}/.gitkeep")
    else:
        print(f"⚠️  {path}/.gitkeep: {r.status_code} {r.text}")


def load_paths_from_file(filename: str) -> List[str]:
    paths: List[str] = []
    with open(filename, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if line:
                paths.append(line)
    return paths


# ----------------------------
# Main
# ----------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Create student repos in a GitHub org with a preset folder structure.")
    parser.add_argument("--org", required=True, help="GitHub organization login (e.g., ics365-fall-2025)")
    parser.add_argument("--csv", default="students.csv", help="CSV file with columns: name,github_link")
    parser.add_argument("--structure", default="structure.txt", help="Text file with one folder path per line")
    parser.add_argument("--sleep", type=float, default=SLEEP_BETWEEN_CALLS_SEC,
                        help="Sleep seconds between API calls (rate limit safety)")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without calling GitHub API")
    args = parser.parse_args()

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ Please set GITHUB_TOKEN environment variable with a PAT that has 'repo' scope (and SSO authorized if required).")
        raise SystemExit(1)

    session = make_session(token)

    if not ensure_org_exists(session, args.org, args.dry_run):
        raise SystemExit(1)

    try:
        folder_paths = load_paths_from_file(args.structure)
        if not folder_paths:
            print(f"⚠️  No paths found in '{args.structure}'. Nothing to create.")
    except FileNotFoundError:
        print(f"❌ Structure file not found: {args.structure}")
        raise SystemExit(1)

    try:
        with open(args.csv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("name") or "").strip()
                gh_link = (row.get("github_link") or "").strip()

                if not name:
                    print("⚠️  Skipping row with missing 'name'.")
                    continue

                repo_name = build_repo_name(name)
                repo = create_repo_in_org(session, args.org, repo_name, args.dry_run)
                if not repo:
                    continue

                gh_username = parse_github_username(gh_link)
                if gh_username:
                    add_collaborator(session, args.org, repo_name, gh_username, COLLAB_PERMISSION, args.dry_run)
                else:
                    print(f"⚠️  {name}: invalid/missing github_link; cannot invite.")

                for p in folder_paths:
                    create_placeholder_file(session, args.org, repo_name, p, args.dry_run)
                    time.sleep(args.sleep)

    except FileNotFoundError:
        print(f"❌ CSV file not found: {args.csv}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
