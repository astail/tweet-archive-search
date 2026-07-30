# Tweet Archive Search

X (Twitter) の「データアーカイブ」エクスポートを [Meilisearch](https://www.meilisearch.com/) に取り込み、自分のツイート履歴を高速・曖昧検索するための個人用ツール。画像・動画もローカルに展開し、インターネット接続なしで閲覧できる。

## 構成

| サービス | 役割 | URL |
|---|---|---|
| `meilisearch` | 検索エンジン本体。内蔵の管理ダッシュボードもここ | http://localhost:7700 |
| `web` | nginxで配信する検索用ページ（自作） | http://localhost:8080 |

検索ロジックはMeilisearch単体。ブラウザは検索専用の権限が絞られたAPIキーで直接Meilisearchを叩く構成。

## セットアップ

```bash
# 1. シークレット生成 & .env作成
openssl rand -hex 32   # MEILI_MASTER_KEY に設定
cp .env.example .env   # 上記の値を書き込む

# 2. コンテナ起動
docker compose up -d

# 3. インデックス設定を適用（初回のみ、再実行しても安全）
uv run scripts/configure_index.py

# 4. 検索専用APIキーをブラウザ用に発行
uv run scripts/write_web_config.py
```

## アーカイブの取り込み

1. Xの「設定とプライバシー」→「アーカイブをダウンロード」からzipを取得
2. zipを指定するだけで展開〜投入まで自動実行:
   ```bash
   uv run scripts/extract_archive.py path/to/twitter-archive.zip
   ```
   zip内の`data/`フォルダの中身（`tweets*.js`、`account.js`/`profile.js`、`tweets_media/`など）をまるごと`data/archive/data/`に展開し、続けて`ingest.py`を自動実行する。展開だけ行いたい場合は`--no-ingest`を付ける。
   `id`（ツイートID）をprimary keyにしているため、再実行しても重複せず上書きされる（冪等）。

アーカイブを再ダウンロード・更新した場合も、同じコマンドをもう一度実行すればよい（`write_web_config.py`は`account.js`が変わらない限り再実行不要）。

## 使い方

http://localhost:8080 を開くと、検索語なしでも最新50件のツイートがそのまま表示される。検索語を入れると絞り込み検索になる。

- 下までスクロールすると次の結果を自動で読み込む（無限スクロール）
- **並び替え**: 関連度 / 新しい順 / 古い順 / いいね数順（検索語なしの一覧表示では「関連度」は自動的に「新しい順」として扱われる）
- **リツイートを除外**: チェックボックス
- **日付範囲**: 「次の日付以降」「次の日付以前」で絞り込み
- 検索語を`"完全一致"`のように`"`で囲むと、語順固定・タイポ非許容のフレーズ検索になる（Meilisearchの標準構文）
- 検索結果には画像・動画（ローカル保存分）とハッシュタグ、いいね/リツイート数を表示
- 各ツイートの「開く」リンクは元のX（twitter.com）のパーマリンクに遷移

デバッグ用に以下も使える:
```bash
uv run scripts/search.py "検索語"                    # CLIから即確認
uv run scripts/search.py "検索語" --sort newest       # 新着順
```
Meilisearchの内蔵ダッシュボード（http://localhost:7700 、マスターキーでログイン）でも生データを直接確認できる。

## ファイル構成

```
docker-compose.yml           meilisearch + web の2サービス
.env                          MEILI_MASTER_KEY 等（gitignore対象）
.env.example                  上記のテンプレート
scripts/configure_index.py    インデックス設定（検索対象/絞り込み対象の属性、タイポ耐性）を適用
scripts/extract_archive.py    Xの archive zip の data/ を data/archive/data/ に展開し、続けて ingest.py を実行
scripts/ingest.py             アーカイブのtweets*.jsをパースしてMeilisearchに投入。メディアのローカルファイル名も解決
scripts/write_web_config.py   検索専用APIキー＋アカウント表示名をweb/config.jsに書き出し
scripts/search.py             動作確認用の簡易CLI検索
web/index.html                検索ページ本体（ビルド不要の単一HTML）
web/config.js                 生成物。検索専用キー等（gitignore対象）
web/media/                    tweets_mediaのマウントポイント（空、docker composeで自動マウント）
data/archive/                 展開済みアーカイブの配置場所（gitignore対象、.gitkeepのみ管理下）
```

## 既知の制限

- **短い日本語単語の完全一致が0件になることがある**（例: 「韓国」で0件、「韓」なら33件ヒット）。Meilisearch内蔵の日本語分かち書き（lindera）が文脈依存で単語境界を決めるため、クエリを単独で打つと実際の文中とは違う区切り方をされることがある。助詞や前後の文字を足す（例: 「韓国語」「韓国に」）と直ることが多い。根本対応（Sudachi/MeCab等への置き換え）はスコープ外。
  - 同様の例: 「渋谷」単独では0件になるが、「渋谷で」なら「渋谷」「で」が別トークンとして正しくヒットする。さらに「渋」（1文字）だけで検索すると「渋谷」を含むツイートがヒットすることもある（前方一致で「渋谷」トークンの先頭部分にマッチするため）。一方「東京」は同じ2文字の地名でも単独で問題なくヒットする、というように単語ごとに挙動が異なり法則性はない。
- 280文字を超える長文ツイート（X「メモ」機能、`note-tweet.js`）は未対応。
- `Your archive.html`（X公式のアーカイブビューア）自体の検索窓は改造していない。理由: 中身が難読化済み6.9MBのwebpackバンドルで安全な書き換えが事実上不可能なため、別ページとして本ツールを用意している。

## ライセンス

このリポジトリ自体は [MIT License](./LICENSE)。

利用している主なOSSとそのライセンス:
- [Meilisearch](https://github.com/meilisearch/meilisearch) — MIT（一部Enterprise Edition機能のみBUSL-1.1、本ツールでは未使用）
- [nginx](https://nginx.org/) — BSD-2-Clause
- [meilisearch-python](https://github.com/meilisearch/meilisearch-python) — MIT
- [python-dotenv](https://github.com/theskumar/python-dotenv) — BSD-3-Clause
