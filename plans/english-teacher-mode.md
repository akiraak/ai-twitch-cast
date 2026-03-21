# 画像/URLで授業モード

## ステータス: 完了

## 概要

教材画像やURLをアップロード/入力すると、ちょビが先生として内容を解説・授業してくれるモード。Gemini APIで画像解析またはWebページのテキスト抽出を行い、授業スクリプトを生成してから段階的に授業を進める。科目・内容はAIが自動判定する。

## 背景

- 現在のちょビは雑談・コメント応答がメイン
- 「授業」という教育コンテンツを加えることで配信の幅を広げる
- Gemini APIは画像入力をサポートしており、技術的に実現可能
- ファイルアップロードシステム（`scripts/routes/files.py`）が既に存在し、カテゴリ追加で教材管理に対応できる

## コアフロー

```
入力ソース          → コンテキスト生成            → スクリプト生成                → 発話
─────────────────────────────────────────────────────────────────────────────────
画像(1〜複数枚)     → analyze_images()            →  ┐
URL                → fetch + テキスト抽出          →  ├→ generate_lesson_script() → 順番に発話
(将来: PDF等)       → (拡張可能)                   →  ┘
```

1. 教材画像をアップロード or URLを入力
2. コンテキスト生成（画像→Geminiマルチモーダル解析 / URL→テキスト抽出）
3. コンテキストから授業スクリプトを生成（1回だけ、JSON配列）
4. スクリプトに沿って順番に発話（テキストベース）
   - 画像の場合: 配信画面に該当画像を表示（ステップに応じてページ送り）
   - URLの場合: トピックパネルに記事タイトル+要約を表示

## 対応パターン

| 例 | 入力 | 授業スタイル | 配信画面表示 |
|----|------|-------------|-------------|
| 英語教材 | 画像1枚 | 語彙→文法→応用 | 教材画像 |
| 歴史教科書 | 画像4枚 | ページ順に解説 | ページ送り |
| 数学数式 | 画像1枚 | 深掘り・計算実演 | 数式画像を固定表示 |
| AIニュース | URL | 要点→解説→議論 | 記事タイトル+要約テキスト |

全パターンが同じ仕組みで動く:
- 入力ソースに応じたコンテキスト生成（`analyze_images()` or `analyze_url()`）
- AIが内容を自動判定してスクリプト生成
- `content`（表示用）/ `tts_text`（読み上げ用）の分離で数式等にも対応
- `image_index` でどの画像を表示するかステップごとに制御（URLの場合はnull）

## ユーザー体験

1. WebUI のトピックタブで教材画像をアップロード or URLを入力
2. 「授業開始」ボタンを押す
3. コンテキスト生成 → 授業スクリプトを自動生成（ローディング表示）
4. ちょビがスクリプトに沿って段階的に授業を進める
5. 配信画面に教材を表示（画像→該当ページ / URL→記事タイトル+要約）
6. 視聴者がチャットで質問 → ちょビが教材のコンテキスト（スクリプト）に基づいて回答
7. 「授業終了」またはトピック解除で通常モードに戻る

## 方針：ベース機能と拡張機能の分離

### ベース機能（汎用）

| 機能 | 説明 | 再利用例 |
|------|------|---------|
| コンテンツソース抽象化 | 画像/URLからコンテキストテキストを生成する汎用関数群 | 任意のソースを解析してテキスト化 |
| トピックへのコンテキスト/画像紐付け | トピックに解析済みテキスト+画像パスを持たせる | 画像以外にも長文資料などをコンテキストに |
| 配信画面のトピック画像/情報表示 | 画像→ページ送り表示 / URL→タイトル+要約表示 | 画像付きトピック全般 |
| ファイルアップロードカテゴリ | files.py にカテゴリ追加の既存パターン | 任意のリソース種別を追加可能 |

### 拡張機能（授業モード固有）

| 機能 | 説明 |
|------|------|
| 授業スクリプト生成 | コンテキストから授業の流れ（複数ステップ+image_index）をAIが生成 |
| 授業開始/終了UI | 教材アップロード/URL入力 + ワンクリック開始 |

---

## 実装ステップ

### ベースPhase 1: コンテンツソース抽象化

**`src/ai_responder.py` に画像解析・URL解析の汎用機能を追加**

#### 画像ソース

```python
def _make_image_part(image_path: str):
    """画像ファイルからGemini APIのPartを作成"""
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    ext = Path(image_path).suffix.lower()
    mime_type = mime_map.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        data = f.read()
    return types.Part(inline_data=types.Blob(mime_type=mime_type, data=data))

def analyze_images(image_paths: list[str], prompt: str) -> str:
    """複数画像をGeminiに送り、promptに従って解析結果テキストを返す"""
    client = _get_client()
    parts = [_make_image_part(p) for p in image_paths]
    parts.append(types.Part(text=prompt))
    response = client.models.generate_content(
        model=GEMINI_CHAT_MODEL,
        contents=[types.Content(role="user", parts=parts)],
    )
    return response.text
```

#### URLソース

```python
def analyze_url(url: str) -> dict:
    """URLのページ内容を取得し、タイトルとテキストを返す"""
    import requests
    from bs4 import BeautifulSoup

    resp = requests.get(url, timeout=15, headers={"User-Agent": "..."})
    soup = BeautifulSoup(resp.text, "html.parser")

    # タイトル取得
    title = ""
    if soup.title:
        title = soup.title.string or ""
    # OGPタイトル優先
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"]

    # OGP画像
    og_image = soup.find("meta", property="og:image")
    image_url = og_image["content"] if og_image and og_image.get("content") else None

    # 本文テキスト抽出（不要なタグを除去）
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)

    return {"title": title, "text": text, "image_url": image_url}
```

**ポイント**: `analyze_images()` と `analyze_url()` はどちらも汎用関数。授業モードに依存しない。

### ベースPhase 2: トピックへのコンテキスト/画像紐付け

**`src/topic_talker.py` のトピックにコンテキストと画像を持たせる**

```python
async def set_topic(self, title, description="", image_paths=None, context=None):
    topic = db.set_topic(title, description)
    self._image_paths = image_paths or []  # 配信画面表示用（複数枚）
    self._context = context                # AI発話時のコンテキスト（解析済みテキスト等）
    ...
```

**コメント応答への統合**（`src/comment_reader.py`）:

トピックにコンテキストがある場合、`stream_context` に含める。視聴者の質問に対して教材の内容を踏まえた回答ができる。

```python
async def _get_stream_context(self):
    ctx = {...}
    if state.topic_talker and state.topic_talker.get_context():
        ctx["topic_context"] = state.topic_talker.get_context()
    return ctx
```

### ベースPhase 3: 配信画面のトピック画像/情報表示

**broadcast.html の `#topic-panel` を拡張**

画像がある場合は画像表示+ページ送り、ない場合はタイトル+要約テキスト表示。

- WebSocketイベント `topic`:
  ```json
  // 画像ありの場合
  {"type": "topic", "title": "授業", "image_urls": ["/resources/images/teaching/p1.jpg", ...]}
  // URLの場合（画像なし or OGP画像のみ）
  {"type": "topic", "title": "AIニュース解説", "description": "記事の要約...", "image_urls": ["https://example.com/ogp.jpg"]}
  // トピック解除
  {"type": "topic", "title": null}
  ```
- 発話時に表示画像を切り替え:
  ```json
  {"type": "topic_image_index", "index": 2}
  ```
- `#topic-panel` 内に `<img>` + テキスト表示要素を追加
- 画像があれば画像表示（`image_index` でページ送り）、なければタイトル+説明テキスト

### ベースPhase 4: 教材ファイルアップロード

**`scripts/routes/files.py` にカテゴリ追加**

```python
"teaching": {
    "dir": RESOURCES_DIR / "images" / "teaching",
    "extensions": {".png", ".jpg", ".jpeg", ".webp"},
    "config_key": "files.active_teaching",
},
```

- `resources/images/teaching/` ディレクトリ作成
- 既存APIがそのまま使える（upload/list/select/delete）

---

### 拡張Phase 5: 授業スクリプト生成

**コンテキストから授業スクリプトを生成**

入力ソースに関わらず、コンテキストテキストからスクリプトを生成:

```python
def generate_lesson_script(context: str, num_images: int = 0) -> list[dict]:
    """コンテキストから授業スクリプト（複数ステップ）を生成"""
    image_rule = ""
    if num_images > 0:
        image_rule = f"- image_index: このステップで表示する画像の番号（0〜{num_images - 1}）、画像不要ならnull"
    else:
        image_rule = "- image_index: 常にnull（画像なし）"

    prompt = f"""以下のコンテンツについて、授業スクリプトをJSON配列で生成してください。
科目・内容はコンテンツから判断してください。

各ステップの形式:
[
  {{"step": 1, "content": "表示テキスト", "tts_text": "読み上げテキスト", "image_index": 0}},
  ...
]

ルール:
- content: 字幕に表示するテキスト
- tts_text: 音声読み上げ用（数式は日本語で読み下し、英語は[lang:en]タグで囲む）
{image_rule}
- 1ステップの発話は100文字以内
- 導入→解説→まとめの流れで構成
- フレンドリーな先生のトーンで

コンテンツ:
{context}"""

    client = _get_client()
    response = client.models.generate_content(
        model=GEMINI_CHAT_MODEL,
        contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return json.loads(response.text)
```

**呼び出しフロー（画像の場合）:**
```python
# 1. 画像をGeminiで解析 → コンテキスト生成
context = analyze_images(image_paths, "この教材の内容を詳細にテキスト化してください")
# 2. コンテキストからスクリプト生成
script = generate_lesson_script(context, num_images=len(image_paths))
```

**呼び出しフロー（URLの場合）:**
```python
# 1. URLからテキスト抽出 → コンテキスト生成
page = analyze_url(url)
context = f"タイトル: {page['title']}\n\n{page['text']}"
# 2. コンテキストからスクリプト生成（画像なし）
script = generate_lesson_script(context, num_images=0)
```

生成されたスクリプトは `topic_scripts` テーブル（既存）に保存し、既存の `get_next()` の仕組みで順番に発話。発話時に `image_index` を WebSocket で配信画面に送る。

### 拡張Phase 6: WebUI（授業開始/終了）

**index.html のトピックタブに教材管理セクションを追加**

- 入力方式の切り替え: 「画像アップロード」タブ / 「URL入力」タブ
- 画像: アップロード・選択・削除（files APIを利用、複数枚対応）、サムネイルプレビュー
- URL: テキスト入力欄
- 「授業開始」ボタン:
  1. 入力ソースに応じてコンテキスト生成
  2. `POST /api/topic/lesson` → コンテキスト生成 + スクリプト生成 + トピック設定を一括実行
  3. ローディング表示（コンテキスト生成+スクリプト生成に数秒かかるため）
- 「授業終了」ボタン: `DELETE /api/topic` でトピック解除

### 共通Phase 7: テスト

**ベース機能テスト:**
- `tests/test_ai_responder.py` — `_make_image_part()` のMIMEタイプ判定テスト
- `tests/test_ai_responder.py` — `analyze_images()` のGemini APIコール構築テスト（モック）
- `tests/test_ai_responder.py` — `analyze_url()` のテキスト抽出テスト（HTMLモック）
- `tests/test_topic_talker.py` — `set_topic()` に `image_paths`/`context` を渡した時の保持・取得テスト
- `tests/test_api_files.py` — teaching カテゴリのアップロード・一覧・選択テスト

**拡張機能テスト:**
- `tests/test_ai_responder.py` — `generate_lesson_script()` のレスポンスパーステスト（モック）
- 全テスト通過確認

## 変更ファイル一覧

### ベース機能（汎用）

| ファイル | 変更内容 |
|----------|----------|
| `src/ai_responder.py` | `_make_image_part()` / `analyze_images()` / `analyze_url()` 追加 |
| `src/topic_talker.py` | `set_topic()` に `image_paths`/`context` 追加、`get_context()` / `get_image_paths()` 追加 |
| `src/comment_reader.py` | `_get_stream_context()` でトピックコンテキストを含める |
| `static/broadcast.html` | `#topic-panel` に画像表示+ページ送り / テキスト情報表示を追加 |
| `scripts/routes/files.py` | teaching カテゴリ追加 |
| `scripts/routes/topic.py` | トピック設定APIに `image_paths` パラメータ追加 |

### 拡張機能（授業モード固有）

| ファイル | 変更内容 |
|----------|----------|
| `src/ai_responder.py` | `generate_lesson_script()` 追加 |
| `scripts/routes/topic.py` | `POST /api/topic/lesson` 授業開始エンドポイント追加 |
| `static/index.html` | 教材管理UI（トピックタブ拡張）、画像/URL入力、授業開始/終了ボタン |

### 依存追加

| パッケージ | 用途 |
|-----------|------|
| `beautifulsoup4` | URL→テキスト抽出 |

## リスク

| リスク | 影響度 | 対策 |
|--------|--------|------|
| スクリプト生成に時間がかかる | 中 | WebUIにローディング表示、非同期実行 |
| 教材画像のOCR精度（手書き・低解像度） | 中 | Geminiの精度は高いが、画質が悪い場合はユーザーに撮り直しを案内 |
| 画像サイズが大きすぎてAPIコール遅延 | 中 | アップロード時にリサイズ（最大1920px）、Gemini APIのサイズ制限内に収める |
| 複数枚の画像でGemini APIのサイズ制限超過 | 中 | 枚数上限を設定（例: 10枚まで）、超過時は警告 |
| URLのページ取得失敗（タイムアウト・認証壁） | 中 | タイムアウト設定、エラー時にユーザーに通知 |
| URLのテキスト抽出品質（SPA・JS描画ページ） | 中 | 基本的なHTML解析で対応、JS描画ページは非対応と割り切る |
| 生成されたスクリプトのJSON解析失敗 | 中 | `response_mime_type="application/json"` 指定、リトライ |
| TTSの数式・専門用語読み上げ | 低 | AIがtts_textに日本語読み下しを生成（content/tts_text分離で対応済み） |

## 将来の拡張

ベース機能（コンテンツソース抽象化 + トピックコンテキスト + 画像表示）を使った他の用途:

- **PDFソース追加** — PDF→テキスト抽出→同じフローで授業
- **動画ソース追加** — YouTube URL→字幕抽出→解説
- **料理解説** — 料理の写真から解析 → レシピ・食材解説スクリプト生成
- **コードレビュー** — コードのスクショから解析 → バグ・改善点スクリプト生成

いずれも「ソースからコンテキスト生成 → スクリプト生成 → 順番に発話」の同じパターン。

## 参考

- [Gemini API マルチモーダル](https://ai.google.dev/gemini-api/docs/vision) — `types.Part(inline_data=...)` で画像送信
- 既存のファイルアップロード: `scripts/routes/files.py` の `CATEGORIES` パターン
- 既存のトピック発話: `src/topic_talker.py` の `generate_topic_line()` / `topic_scripts` テーブル
