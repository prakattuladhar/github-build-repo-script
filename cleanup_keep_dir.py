import argparse
import sys
from pathlib import Path
import shutil


def is_relative_to(descendant: Path, ancestor: Path) -> bool:
    try:
        descendant.relative_to(ancestor)
        return True
    except ValueError:
        return False


def remove_path(target: Path, dry_run: bool) -> None:
    if dry_run:
        print(f"Would remove {target}")
        return
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink()


def prune_tree(root: Path, keep: Path, dry_run: bool) -> None:
    for entry in root.iterdir():
        if entry == keep or is_relative_to(keep, entry):
            if entry.is_dir() and entry != keep:
                prune_tree(entry, keep, dry_run)
            continue
        remove_path(entry, dry_run)


def clean_student_dir(student_dir: Path, keep_relative: Path, dry_run: bool) -> None:
    keep_path = student_dir / keep_relative
    if not keep_path.exists():
        print(f"Skipping {student_dir}: missing {keep_relative}", file=sys.stderr)
        return

    for entry in student_dir.iterdir():
        if entry == keep_path:
            continue
        if is_relative_to(keep_path, entry):
            prune_tree(entry, keep_path, dry_run)
            continue
        remove_path(entry, dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep only a specified subdirectory inside each directory of a base path.")
    parser.add_argument("base_dir", type=Path, help="Directory containing subdirectories to clean")
    parser.add_argument("keep_dir", type=Path, help="Relative path to keep inside each subdirectory")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without deleting anything")
    args = parser.parse_args()

    base_dir = args.base_dir.resolve()
    if not base_dir.is_dir():
        print(f"Base directory {base_dir} does not exist or is not a directory", file=sys.stderr)
        return 1

    for student_dir in sorted(base_dir.iterdir()):
        if not student_dir.is_dir():
            continue
        clean_student_dir(student_dir, args.keep_dir, args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
