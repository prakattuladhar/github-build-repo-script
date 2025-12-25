#!/usr/bin/env python3
"""
Reset each Git repo in a directory to the latest commit before a deadline.

Behavior
- Accepts a directory containing multiple Git repositories (each subfolder with a .git dir)
- Accepts a date in Central Time (America/Chicago) and assumes time 11:59 PM
- Adds a 5-minute grace period to the deadline
- Resets each repo to the latest commit BEFORE the adjusted deadline

Examples
  python3 revert_to_deadline.py --dir ./ics365 --date 09/10/2025
  python3 revert_to_deadline.py --dir ./ics365 --date 2025-09-10 --dry-run

Notes
- Uses local repositories only; no network needed.
- By default, operates on the current (or detected default) branch.
- Use --dry-run to preview what would be reset without changing anything.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception as e:  # pragma: no cover
    print("This script requires Python 3.9+ for zoneinfo.", file=sys.stderr)
    raise


CENTRAL_TZ = ZoneInfo("America/Chicago")


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def ensure_git() -> None:
    if shutil.which("git") is None:
        eprint("Error: git is not installed or not on PATH.")
        sys.exit(1)


def _format_utc_offset(d: dt.datetime) -> str:
    off = d.utcoffset() or dt.timedelta(0)
    sign = "+" if off >= dt.timedelta(0) else "-"
    total = int(abs(off).total_seconds())
    h = total // 3600
    m = (total % 3600) // 60
    return f"UTC{sign}{h:02d}:{m:02d}"


def format_pretty_central(d: dt.datetime) -> str:
    local = d.astimezone(CENTRAL_TZ)
    # Example: Wed, Sep 10, 2025 11:57 PM CDT (UTC-05:00)
    return local.strftime("%a, %b %d, %Y %I:%M %p %Z") + f" ({_format_utc_offset(local)})"


def parse_date_central(date_str: str, grace_minutes: int = 5) -> dt.datetime:
    """
    Parse input date as Central Time and return deadline with 11:59 PM + grace.
    Accepts formats: MM/DD/YYYY or YYYY-MM-DD.
    Returns timezone-aware datetime in America/Chicago with grace applied.
    """
    date_str = date_str.strip()
    date: dt.date
    mdy = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
    ymd = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_str)
    if mdy:
        m, d, y = map(int, mdy.groups())
        date = dt.date(y, m, d)
    elif ymd:
        y, m, d = map(int, ymd.groups())
        date = dt.date(y, m, d)
    else:
        raise SystemExit("Invalid date format. Use MM/DD/YYYY or YYYY-MM-DD")

    # 11:59 PM local time, then add grace
    base = dt.datetime(date.year, date.month, date.day, 23, 59, tzinfo=CENTRAL_TZ)
    adjusted = base + dt.timedelta(minutes=grace_minutes)
    return adjusted


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def repo_is_git(repo: Path) -> bool:
    return (repo / ".git").is_dir()


def detect_branch(repo: Path) -> str:
    """
    Detect a sensible branch to operate on.
    Priority: current branch -> origin/HEAD -> main -> master -> HEAD
    """
    # Current branch (not detached)
    cp = run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if cp.returncode == 0:
        name = cp.stdout.strip()
        if name and name != "HEAD":
            return name

    # origin/HEAD
    cp = run_git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if cp.returncode == 0:
        ref = cp.stdout.strip()  # e.g., origin/main
        if ref.startswith("origin/"):
            return ref.split("/", 1)[1]

    # main or master if exist
    for cand in ("main", "master"):
        cp = run_git(repo, "show-ref", f"refs/heads/{cand}")
        if cp.returncode == 0:
            return cand

    # Fallback: HEAD
    return "HEAD"


def commit_before(repo: Path, branch: str, deadline: dt.datetime) -> str | None:
    # Format like: 2025-09-11 00:04:00 -0500
    offset = deadline.utcoffset() or dt.timedelta(0)
    sign = "+" if offset >= dt.timedelta(0) else "-"
    total_minutes = int(abs(offset).total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    offset_str = f"{sign}{hours:02d}{minutes:02d}"
    ts = deadline.strftime("%Y-%m-%d %H:%M:%S") + f" {offset_str}"

    cp = run_git(repo, "rev-list", "-1", f"--before={ts}", branch)
    if cp.returncode != 0:
        return None
    sha = cp.stdout.strip()
    return sha or None


def checkout_branch(repo: Path, branch: str) -> bool:
    cp = run_git(repo, "checkout", "-q", branch)
    return cp.returncode == 0


def hard_reset(repo: Path, commit: str) -> bool:
    cp = run_git(repo, "reset", "--hard", commit)
    return cp.returncode == 0


def is_dirty(repo: Path) -> bool:
    cp = run_git(repo, "status", "--porcelain")
    return cp.returncode == 0 and bool(cp.stdout.strip())


def commit_timestamp_central(repo: Path, sha: str) -> str | None:
    """Return the commit's committer timestamp formatted in Central Time."""
    cp = run_git(repo, "show", "-s", "--format=%cI", sha)
    if cp.returncode != 0:
        return None
    iso = cp.stdout.strip()
    if not iso:
        return None
    try:
        # %cI is strict ISO 8601, may include 'Z'
        aware = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return format_pretty_central(aware)
    except Exception:
        return None


def commit_subject(repo: Path, sha: str) -> str | None:
    """Return the commit's subject line (first line of message)."""
    cp = run_git(repo, "show", "-s", "--format=%s", sha)
    if cp.returncode != 0:
        return None
    subj = cp.stdout.strip()
    return subj or None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--dir", required=True, help="Directory containing Git repositories (subfolders)")
    p.add_argument("--date", required=True, help="Deadline date in Central Time: MM/DD/YYYY or YYYY-MM-DD")
    p.add_argument("--grace", type=int, default=5, help="Grace period minutes to add (default: 5)")
    p.add_argument("--dry-run", action="store_true", help="Print actions without changing repos")
    p.add_argument("--force", action="store_true", help="Proceed even if working tree has uncommitted changes")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ensure_git()

    root = Path(args.dir).expanduser().resolve()
    if not root.is_dir():
        eprint(f"Not a directory: {root}")
        return 2

    deadline = parse_date_central(args.date, grace_minutes=args.grace)
    eprint("Adjusted deadline (Central): ", format_pretty_central(deadline))

    repos = [p for p in root.iterdir() if p.is_dir() and repo_is_git(p)]
    if not repos:
        eprint("No Git repositories found (subfolders with a .git directory).")
        return 0

    ok = 0
    skipped = 0
    failed = 0
    for i, repo in enumerate(sorted(repos), start=1):
        if i > 1:
            eprint("")  # blank line between repo sections
        eprint(f"[{i}/{len(repos)}] {repo.name}")

        if is_dirty(repo) and not args.force:
            eprint("  - Skipped: working tree has uncommitted changes (use --force)")
            skipped += 1
            continue

        branch = detect_branch(repo)
        sha = commit_before(repo, branch, deadline)
        if not sha:
            eprint("  - No commit before deadline; leaving repo unchanged")
            skipped += 1
            continue

        eprint(f"  - Target branch: {branch}")
        ts = commit_timestamp_central(repo, sha)
        subj = commit_subject(repo, sha)
        line = f"  - Commit before deadline: {sha}"
        if ts:
            line += f" @ {ts}"
        if subj:
            line += f" — {subj}"
        eprint(line)

        if args.dry_run:
            ok += 1
            continue

        # Ensure on target branch when possible
        if branch not in ("HEAD",):
            if not checkout_branch(repo, branch):
                eprint("  - Failed to checkout branch; skipping")
                failed += 1
                continue

        if hard_reset(repo, sha):
            eprint("  - Reset complete")
            ok += 1
        else:
            eprint("  - Reset failed")
            failed += 1
            
    eprint("")
    eprint(f"Done. Successful: {ok}, Skipped: {skipped}, Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
