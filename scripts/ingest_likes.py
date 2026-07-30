# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "meilisearch",
#     "python-dotenv",
# ]
# ///
"""Parse an extracted X (Twitter) archive's like*.js files and load them into
a separate 'likes' Meilisearch index.

Usage:
    uv run scripts/ingest_likes.py --archive-dir data/archive/data

Unlike tweets.js, like.js only stores tweetId/fullText/expandedUrl for
tweets you liked (they're someone else's posts, so the archive keeps no
author, media, counts, or hashtags) and no timestamp either - created_at
is recovered from the tweet ID itself, since X's IDs are Snowflake IDs
that encode the creation time in their high bits.
"""

import argparse
import datetime
import json
import os
import re
from pathlib import Path

import meilisearch
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
BATCH_SIZE = 500
JS_PREFIX_RE = re.compile(r"^\s*window\.YTD\.\w+\.\w+\s*=\s*", re.DOTALL)
TWITTER_EPOCH_MS = 1288834974657  # 2010-11-04T01:42:54.657Z, X's Snowflake ID epoch


def snowflake_to_dt(tweet_id: str) -> datetime.datetime:
    ms = (int(tweet_id) >> 22) + TWITTER_EPOCH_MS
    return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc)


def parse_like_files(archive_dir: Path):
    files = sorted(archive_dir.glob("like*.js"))
    if not files:
        raise SystemExit(f"No like*.js files found under {archive_dir}")
    for path in files:
        text = path.read_text(encoding="utf-8")
        json_text = JS_PREFIX_RE.sub("", text, count=1).strip()
        if json_text.endswith(";"):
            json_text = json_text[:-1]
        entries = json.loads(json_text)
        for entry in entries:
            yield entry["like"]


def normalize(like: dict) -> dict | None:
    tweet_id = like.get("tweetId")
    if not tweet_id:
        return None
    created_at = snowflake_to_dt(tweet_id)
    return {
        "id": tweet_id,
        "full_text": like.get("fullText", ""),
        "created_at_iso": created_at.isoformat(),
        "created_at_ts": int(created_at.timestamp()),
        "permalink": like.get("expandedUrl") or f"https://twitter.com/i/web/status/{tweet_id}",
    }


def batched(iterable, size):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--archive-dir",
        required=True,
        type=Path,
        help="Path to the extracted archive's data/ directory (contains like*.js)",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    host = os.environ.get("MEILI_HOST", "http://localhost:7700")
    master_key = os.environ["MEILI_MASTER_KEY"]
    client = meilisearch.Client(host, master_key)
    index = client.index("likes")

    total = 0
    docs = (d for d in (normalize(like) for like in parse_like_files(args.archive_dir)) if d)
    for batch in batched(docs, BATCH_SIZE):
        task = index.add_documents(batch, primary_key="id")
        client.wait_for_task(task.task_uid)
        total += len(batch)
        print(f"Indexed {total} likes...")

    print(f"Done. {total} likes indexed.")


if __name__ == "__main__":
    main()
