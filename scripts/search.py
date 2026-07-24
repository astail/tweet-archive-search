# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "meilisearch",
#     "python-dotenv",
# ]
# ///
"""Quick CLI search against the 'tweets' index, for verification/ad hoc use.

Usage:
    uv run scripts/search.py "検索語" [--limit 20] [--sort newest|likes]
"""

import argparse
import os
from pathlib import Path

import meilisearch
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--sort", choices=["relevance", "newest", "likes"], default="relevance"
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    host = os.environ.get("MEILI_HOST", "http://localhost:7700")
    master_key = os.environ["MEILI_MASTER_KEY"]
    client = meilisearch.Client(host, master_key)
    index = client.index("tweets")

    search_params = {"limit": args.limit, "attributesToHighlight": ["full_text"]}
    if args.sort == "newest":
        search_params["sort"] = ["created_at_ts:desc"]
    elif args.sort == "likes":
        search_params["sort"] = ["favorite_count:desc"]

    result = index.search(args.query, search_params)

    for hit in result["hits"]:
        highlighted = hit.get("_formatted", {}).get("full_text", hit["full_text"])
        print(f"[{hit['created_at_iso']}] {highlighted}")
        print(f"  ♥{hit['favorite_count']} \U0001F501{hit['retweet_count']}  {hit['permalink']}")
        print()

    print(f"{result['estimatedTotalHits']} hits (showing {len(result['hits'])})")


if __name__ == "__main__":
    main()
