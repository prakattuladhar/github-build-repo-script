# GitHub Bulk Repo Setup

Manage GitHub repos for a class. These scripts help you create student repos once, clone them for grading, revert work to a deadline, and optionally clean up local folders to keep only the assignment you are reviewing.

## Scripts

- `create_course_repos.py`: one-time setup to create private repos in an org, invite students as collaborators, and seed a folder structure.
- `clone_org_repos.py`: clone all repos from an org into a local directory (supports filters and updates).
- `revert_to_deadline.py`: reset each local repo to the last commit before a deadline (Central Time, 11:59 PM plus grace).
- `cleanup_keep_dir.py`: optional cleanup to keep only a specific subdirectory inside each student repo.

## Requirements

- Python 3.9+ (3.8 may work, but 3.9+ is recommended)
- GitHub organization for student repos
- GitHub Personal Access Token with `repo` scope (and org access)
- `git` on PATH (for clone and revert scripts)
- Dependencies in `requirements.txt`

## Setup

1) Create and activate a virtual environment (optional but recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2) Install dependencies

```bash
pip install -r requirements.txt
```

3) Export your GitHub token

```bash
export GITHUB_TOKEN="ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXX"
```

## Input files

### `students.csv`

CSV file with headers `name` and `github_link`.

```csv
name,github_link
Ada Lovelace,https://github.com/ada
Alan Turing,https://github.com/aturing
```

### `structure.txt`

Text file with one folder path per line (used to seed student repos).

```text
Exercises/Exercise_1
Programming_Assignments/Programming_Assignment_1
```

## Usage

### 1) Create course repos (one-time setup)

```bash
python3 create_course_repos.py \
  --org ics365-fall-2025 \
  --csv students.csv \
  --structure structure.txt \
  --dry-run
```

```bash
python3 create_course_repos.py \
  --org ics365-fall-2025 \
  --csv students.csv \
  --structure structure.txt
```

Options: `--sleep` to slow down API calls, `--dry-run` to preview.

### 2) Clone org repos

```bash
python3 clone_org_repos.py ics365-fall-2025 \
  --dest ./ics365 \
  --protocol https \
  --shallow \
  --update
```

Options: `--match` / `--regex` to filter repo names, `--include-forks`, `--include-archived`.

### 3) Revert to deadline

Resets each local repo to the latest commit before the deadline date (Central Time, 11:59 PM + grace).

```bash
python3 revert_to_deadline.py --dir ./ics365 --date 2025-09-10 --dry-run
```

```bash
python3 revert_to_deadline.py --dir ./ics365 --date 09/10/2025
```

Options: `--grace` to change the grace period, `--force` to override dirty working trees.

### 4) Cleanup keep dir (optional)

Keeps only one subdirectory inside each student repo. This is destructive, so use `--dry-run` first.

```bash
python3 cleanup_keep_dir.py ./ics365 Programming_Assignments/Programming_Assignment_1 --dry-run
```

```bash
python3 cleanup_keep_dir.py ./ics365 Programming_Assignments/Programming_Assignment_1
```

## Notes

- `create_course_repos.py` requires `requests` from `requirements.txt`.
- `clone_org_repos.py` and `revert_to_deadline.py` require `git` on PATH.
- Use `--help` on any script for full options and defaults.
