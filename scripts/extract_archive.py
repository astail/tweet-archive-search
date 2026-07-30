# /// script
# requires-python = ">=3.11"
# ///
"""Extract an X (Twitter) archive .zip's data/ folder into data/archive/data/,
restart the 'web' container (its tweets_media bind mount can go stale after
the directory is replaced), then (by default) run ingest.py against it.

Usage:
    uv run scripts/extract_archive.py path/to/twitter-archive.zip
    uv run scripts/extract_archive.py path/to/twitter-archive.zip --no-ingest
"""

import argparse
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "data" / "archive" / "data"


def is_symlink(zinfo: zipfile.ZipInfo) -> bool:
    return (zinfo.external_attr >> 16) & 0o170000 == 0o120000


def extract(zip_path: Path, target: Path) -> int:
    with zipfile.ZipFile(zip_path) as zf:
        infos = [zi for zi in zf.infolist() if zi.filename.startswith("data/") and not zi.is_dir()]
        if not infos:
            raise SystemExit(
                f"No data/ entries found inside {zip_path.name} - "
                "is this an X 'archive of your data' zip "
                "(設定とプライバシー > アーカイブをダウンロード)?"
            )
        target.mkdir(parents=True, exist_ok=True)
        target_resolved = target.resolve()
        for zinfo in infos:
            if is_symlink(zinfo):
                raise SystemExit(f"Refusing to extract symlink entry: {zinfo.filename}")
            dest = (target / Path(zinfo.filename).relative_to("data")).resolve()
            if dest != target_resolved and target_resolved not in dest.parents:
                raise SystemExit(f"Unsafe path in archive: {zinfo.filename}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(zinfo) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
    return len(infos)


def restart_web_container():
    """Cheap and always safe, so just do it unconditionally rather than detecting staleness."""
    result = subprocess.run(
        ["docker", "compose", "restart", "web"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            "Note: could not restart the 'web' container automatically "
            "(if images/videos 404 in the browser, run `docker compose restart web` manually):\n"
            f"{result.stderr.strip()}"
        )


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("zip_path", type=Path, help="Path to the downloaded X archive .zip")
    parser.add_argument(
        "--no-ingest",
        action="store_true",
        help="Only extract; skip running scripts/ingest.py afterward",
    )
    args = parser.parse_args()

    if not args.zip_path.is_file():
        raise SystemExit(f"{args.zip_path} not found")

    count = extract(args.zip_path, TARGET)
    print(f"Extracted {count} files into {TARGET}")

    restart_web_container()

    if not args.no_ingest:
        subprocess.run(
            ["uv", "run", str(ROOT / "scripts" / "ingest.py"), "--archive-dir", str(TARGET)],
            check=True,
        )


if __name__ == "__main__":
    main()
