# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "meilisearch",
#     "python-dotenv",
# ]
# ///
"""Create (if needed) and configure the 'tweets' and 'likes' Meilisearch indexes.

Safe to re-run: index creation is skipped if it already exists, and
settings are applied idempotently.
"""

import os
from pathlib import Path

import meilisearch
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

# Japanese word tokens are frequently 2-4 characters, so typo tolerance
# barely engages against Meilisearch's English-tuned defaults (5/9 chars)
# unless these thresholds are lowered.
TYPO_TOLERANCE = {
    "enabled": True,
    "minWordSizeForTypos": {"oneTypo": 3, "twoTypos": 7},
}

INDEXES = {
    "tweets": {
        "searchableAttributes": ["full_text", "hashtags"],
        "filterableAttributes": ["lang", "is_retweet", "has_media", "hashtags", "created_at_ts"],
        "sortableAttributes": ["created_at_ts", "favorite_count", "retweet_count"],
        "typoTolerance": TYPO_TOLERANCE,
    },
    # Liked tweets: X's archive only gives us tweetId/fullText/expandedUrl
    # (no author, media, counts) - see ingest_likes.py.
    "likes": {
        "searchableAttributes": ["full_text"],
        "filterableAttributes": ["created_at_ts"],
        "sortableAttributes": ["created_at_ts"],
        "typoTolerance": TYPO_TOLERANCE,
    },
}


def main():
    load_dotenv(ROOT / ".env")
    host = os.environ.get("MEILI_HOST", "http://localhost:7700")
    master_key = os.environ["MEILI_MASTER_KEY"]
    client = meilisearch.Client(host, master_key)

    for name, settings in INDEXES.items():
        try:
            task = client.create_index(name, {"primaryKey": "id"})
            client.wait_for_task(task.task_uid)
            print(f"Created index '{name}'.")
        except meilisearch.errors.MeilisearchApiError as e:
            if "index_already_exists" not in str(e):
                raise
            print(f"Index '{name}' already exists.")

        index = client.index(name)
        task = index.update_settings(settings)
        client.wait_for_task(task.task_uid)
        print(f"Applied index settings for '{name}'.")


if __name__ == "__main__":
    main()
