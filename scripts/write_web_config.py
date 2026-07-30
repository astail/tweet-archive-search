# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "python-dotenv",
# ]
# ///
"""Fetch Meilisearch's default search-only API key and write it to web/config.js.

The browser-side search page must never see MEILI_MASTER_KEY, only a
search-scoped key. Meilisearch auto-generates a "Default Search API Key"
(actions=["search"]) the first time it boots with a master key set; this
script just looks it up over the REST API and writes it out.

Only the port is written (not a full host/URL): the page itself is accessed
from varying hostnames (localhost, a LAN IP, ...), and Meilisearch is always
reachable on the same host the page was loaded from, just on a different
port. index.html builds the actual URL from window.location.hostname.

Also reads the account display name / handle from the archive's
account.js/profile.js (if present under --archive-dir's parent, i.e.
data/archive/data/) so the page header can show who the archive belongs to.
"""

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
JS_PREFIX_RE = re.compile(r"^\s*window\.YTD\.\w+\.\w+\s*=\s*", re.DOTALL)


def load_archive_js(path: Path):
    text = path.read_text(encoding="utf-8")
    json_text = JS_PREFIX_RE.sub("", text, count=1).strip()
    if json_text.endswith(";"):
        json_text = json_text[:-1]
    return json.loads(json_text)


def read_account_info():
    archive_data = ROOT / "data" / "archive" / "data"
    account_path = archive_data / "account.js"
    if not account_path.exists():
        return None, None, None
    account = load_archive_js(account_path)[0]["account"]
    return account.get("accountDisplayName"), account.get("username"), account.get("accountId")


def read_avatar_filename(account_id: str | None) -> str | None:
    profile_path = ROOT / "data" / "archive" / "data" / "profile.js"
    if not account_id or not profile_path.exists():
        return None
    avatar_url = load_archive_js(profile_path)[0]["profile"].get("avatarMediaUrl")
    if not avatar_url:
        return None
    # Matches how the archive names extracted profile_media files: "{accountId}-{basename_of_url}".
    basename = urllib.parse.urlparse(avatar_url).path.rsplit("/", 1)[-1]
    return f"{account_id}-{basename}"


def main():
    load_dotenv(ROOT / ".env")
    host = os.environ.get("MEILI_HOST", "http://localhost:7700")
    master_key = os.environ["MEILI_MASTER_KEY"]
    port = urllib.parse.urlparse(host).port or 7700

    req = urllib.request.Request(
        f"{host}/keys",
        headers={"Authorization": f"Bearer {master_key}"},
    )
    with urllib.request.urlopen(req) as resp:
        keys = json.load(resp)["results"]

    search_key = next(
        k["key"]
        for k in keys
        if k.get("actions") == ["search"] and k.get("indexes") in (["*"], ["tweets"])
    )

    display_name, username, account_id = read_account_info()
    avatar_filename = read_avatar_filename(account_id)

    lines = [
        f'const MEILI_PORT = "{port}";',
        f'const MEILI_SEARCH_KEY = "{search_key}";',
        f"const ARCHIVE_DISPLAY_NAME = {json.dumps(display_name)};",
        f"const ARCHIVE_USERNAME = {json.dumps(username)};",
        f"const ARCHIVE_AVATAR_FILENAME = {json.dumps(avatar_filename)};",
    ]
    config_path = ROOT / "web" / "config.js"
    config_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {config_path}")


if __name__ == "__main__":
    main()
