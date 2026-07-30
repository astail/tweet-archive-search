# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "meilisearch",
#     "python-dotenv",
# ]
# ///
"""Parse an extracted X (Twitter) archive's tweets*.js files and load them into Meilisearch.

Usage:
    uv run scripts/ingest.py --archive-dir data/archive/data

Known limitations (not handled, out of scope for v1):
- Tweets over 280 chars stored via X's "Notes" feature live in a separate
  note-tweet.js file and are not picked up here.

Media (photos/videos/gifs) are referenced by local filename under
tweets_media/, matching how the archive itself names extracted files:
"{owning_tweet_id}-{basename_of_media_url}". The web page resolves these
against nginx's /media/ mount, so search results stay viewable offline.
"""

import argparse
import email.utils
import json
import os
import posixpath
import re
from pathlib import Path
from urllib.parse import urlparse

import meilisearch
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
BATCH_SIZE = 500
JS_PREFIX_RE = re.compile(r"^\s*window\.YTD\.\w+\.\w+\s*=\s*", re.DOTALL)


def media_basename(url: str) -> str:
    return posixpath.basename(urlparse(url).path)


def extract_media(tweet: dict) -> list[dict]:
    items = (
        tweet.get("extended_entities", {}).get("media")
        or tweet.get("entities", {}).get("media")
        or []
    )
    media = []
    for m in items:
        media_type = m.get("type")
        if media_type == "photo":
            bn = media_basename(m["media_url_https"])
        else:
            variants = m.get("video_info", {}).get("variants", [])
            mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
            if not mp4s:
                continue
            best = max(mp4s, key=lambda v: int(v.get("bitrate", 0)))
            bn = media_basename(best["url"])
        media.append({
            "type": media_type,
            "filename": f"{tweet['id_str']}-{bn}",
        })
    return media


def read_username(archive_dir: Path) -> str | None:
    account_path = archive_dir / "account.js"
    if not account_path.exists():
        return None
    text = account_path.read_text(encoding="utf-8")
    json_text = JS_PREFIX_RE.sub("", text, count=1).strip()
    if json_text.endswith(";"):
        json_text = json_text[:-1]
    return json.loads(json_text)[0]["account"].get("username")


def parse_tweet_files(archive_dir: Path):
    files = sorted(archive_dir.glob("tweets*.js"))
    if not files:
        raise SystemExit(f"No tweets*.js files found under {archive_dir}")
    for path in files:
        text = path.read_text(encoding="utf-8")
        json_text = JS_PREFIX_RE.sub("", text, count=1).strip()
        if json_text.endswith(";"):
            json_text = json_text[:-1]
        entries = json.loads(json_text)
        for entry in entries:
            yield entry["tweet"]


def normalize(tweet: dict, username: str | None) -> dict:
    full_text = tweet.get("full_text") or tweet.get("text", "")
    created_at = email.utils.parsedate_to_datetime(tweet["created_at"])
    entities = tweet.get("entities", {})
    hashtags = [h["text"] for h in entities.get("hashtags", [])]
    urls = [u.get("expanded_url") for u in entities.get("urls", [])]
    # Canonical form, not the /i/web/status/ redirect: the X app's deep-link routing doesn't resolve that on tap.
    base = f"https://x.com/{username}" if username else "https://twitter.com/i/web"
    media = extract_media(tweet)
    return {
        "id": tweet["id_str"],
        "full_text": full_text,
        "created_at_iso": created_at.isoformat(),
        "created_at_ts": int(created_at.timestamp()),
        "favorite_count": int(tweet.get("favorite_count", 0)),
        "retweet_count": int(tweet.get("retweet_count", 0)),
        "lang": tweet.get("lang"),
        "hashtags": hashtags,
        "urls": urls,
        "is_retweet": full_text.startswith("RT @"),
        "permalink": f"{base}/status/{tweet['id_str']}",
        "media": media,
        "has_media": bool(media),
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive-dir",
        required=True,
        type=Path,
        help="Path to the extracted archive's data/ directory (contains tweets*.js)",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    host = os.environ.get("MEILI_HOST", "http://localhost:7700")
    master_key = os.environ["MEILI_MASTER_KEY"]
    client = meilisearch.Client(host, master_key)
    index = client.index("tweets")

    username = read_username(args.archive_dir)
    total = 0
    docs = (normalize(t, username) for t in parse_tweet_files(args.archive_dir))
    for batch in batched(docs, BATCH_SIZE):
        task = index.add_documents(batch, primary_key="id")
        client.wait_for_task(task.task_uid)
        total += len(batch)
        print(f"Indexed {total} tweets...")

    print(f"Done. {total} tweets indexed.")


if __name__ == "__main__":
    main()
