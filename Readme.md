# GitHub Bulk Repo Setup

Create private GitHub repos for students, add them as collaborators, and seed each repo with a folder structure.

## Requirements

- Python 3.9+ (Python 3.8 should work, but 3.9+ is recommended)
- A GitHub organization (required). If you don't have one yet, create an org in GitHub and use its login name for `--org`.
- A GitHub Personal Access Token with `repo` scope and access to the target org
- `requests` library (installed via `requirements.txt`)

## Setup (Step-by-step)

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

## Input Files

### students.csv

CSV file with the headers `name` and `github_link`.

```csv
name,github_link
Ada Lovelace,https://github.com/ada
Alan Turing,https://github.com/aturing
```

### structure.txt

Text file with one folder path per line.

```text
Exercises/Exercise_1
Programming_Assignments/Programming_Assignment_1
```

## Run the Script

### Basic (dry-run)

```bash
python3 create_course_repos.py \
  --org ics365-fall-2025 \
  --csv students.csv \
  --structure structure.txt \
  --dry-run
```

### Create repos for real

```bash
python3 create_course_repos.py \
  --org ics365-fall-2025 \
  --csv students.csv \
  --structure structure.txt
```

### Use a different CSV or structure file

```bash
python3 create_course_repos.py \
  --org ics365-fall-2025 \
  --csv students-prod.csv \
  --structure structure.txt
```

### Slow down API calls (rate limit safety)

```bash
python3 create_course_repos.py \
  --org ics365-fall-2025 \
  --sleep 0.75
```

## Options

Run `python3 create_course_repos.py --help` to see all options.

- `--org` (required): GitHub org login, e.g. `ics365-fall-2025`
- `--csv`: CSV file path (default: `students.csv`)
- `--structure`: folder structure file (default: `structure.txt`)
- `--sleep`: seconds between API calls (default: `0.35`)
- `--dry-run`: print actions without calling GitHub API
