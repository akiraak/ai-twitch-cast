# 管理画面からplans/docsファイルを閲覧する

## ステータス: 未着手

## 背景

plans/やdocs/配下のMarkdownファイルは現在、エディタやGitHubでしか確認できない。管理画面から直接閲覧できれば、配信中や外出先でもプランやドキュメントを素早く参照できる。

## 方針

- 既存のDBタブ（テーブル一覧→データ表示）と同じUI構造を踏襲
- 新しい「Docs」タブを追加し、左にファイル一覧、右にMarkdown表示
- バックエンドは2つのAPIのみ（一覧取得 + 内容取得）
- 既存の `simpleMarkdownToHtml()` を再利用してレンダリング
- パストラバーサル対策を行う

## 実装ステップ

### Step 1: バックエンドAPI (`scripts/routes/docs_viewer.py` 新規) ✅ 完了

新規ルートファイルを作成し、2つのエンドポイントを追加:

```
GET /api/docs/files?dir=plans   → { ok, files: [{name, size, modified}] }
GET /api/docs/files?dir=docs    → 同上
GET /api/docs/file?dir=plans&name=xxx.md → PlainTextResponse(Markdown本文)
```

**一覧API**:
- `dir` パラメータは `plans` または `docs` のみ許可（ホワイトリスト）
- プロジェクトルートからの相対パスで `plans/` or `docs/` を指定
- `*.md` ファイルのみ返す
- サブディレクトリ内のmdファイルも含める（`subdir/file.md` 形式）
- 更新日時降順でソート

**内容API**:
- `name` にパストラバーサル攻撃を防ぐバリデーション（`..` を含むパスは拒否）
- ファイルが存在しなければ404

**既存の `/api/docs/character-prompt`**:
- `character.py` にある既存エンドポイントはそのまま残す（互換性維持）

### Step 2: ルート登録 (`scripts/web.py`) ✅ 完了

`docs_viewer_router` を `app.include_router()` で登録。

### Step 3: フロントエンドUI ✅ 完了

#### 3a: HTML構造 (`static/index.html`)

タブバーに「Docs」タブを追加（DBタブの後）。`tab-docs` div の構成:

```html
<div class="tab-content" id="tab-docs">
  <!-- カード1: ディレクトリ切替 + ファイル一覧 -->
  <div class="card">
    <h2>ドキュメント</h2>
    <!-- ディレクトリ切替: db-tabスタイルのボタン2つ -->
    <div style="display:flex; gap:6px; margin-bottom:10px;">
      <button class="db-tab active" id="docs-dir-plans" onclick="switchDocsDir('plans')">plans</button>
      <button class="db-tab" id="docs-dir-docs" onclick="switchDocsDir('docs')">docs</button>
    </div>
    <!-- ファイル一覧: db-tabスタイルのボタン群（ファイル名表示） -->
    <div id="docs-file-list" style="display:flex; gap:6px; flex-wrap:wrap;"></div>
  </div>

  <!-- カード2: Markdown表示エリア -->
  <div class="card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
      <h2 id="docs-file-name">ファイルを選択してください</h2>
      <span id="docs-file-meta" style="font-size:0.8rem; color:#9a88b5;"></span>
    </div>
    <!-- doc-modal-bodyクラスを再利用してMarkdownスタイルを適用 -->
    <div id="docs-content" class="doc-modal-body"
         style="max-height:600px; overflow-y:auto; border:1px solid #d0c0e8; border-radius:6px; padding:20px;">
      <p style="color:#9a88b5;">← ファイルを選択すると内容が表示されます</p>
    </div>
  </div>
</div>
```

**UIの要点**:
- カード1（上部）: ディレクトリ切替 + ファイル一覧。DBタブの「テーブル選択」と同じレイアウト
- カード2（下部）: ファイル名ヘッダー + Markdown本文。DBタブの「テーブルデータ」と同じレイアウト
- ファイル一覧のボタンは既存の `.db-tab` / `.db-tab.active` クラスを再利用（紫ボーダー、アクティブ時紫背景）
- Markdown表示エリアは既存の `.doc-modal-body` クラスを再利用（見出し・コード・テーブル等のスタイルがそのまま効く）
- 追加CSSは不要（既存クラスの組み合わせで実現）

#### 3b: JavaScript (`static/js/admin/docs.js` 新規)

```javascript
// 状態
let _docsCurrentDir = 'plans';  // 'plans' or 'docs'
let _docsCurrentFile = '';

// ディレクトリ切替
function switchDocsDir(dir) {
  _docsCurrentDir = dir;
  _docsCurrentFile = '';
  // ボタンのactive切替
  document.getElementById('docs-dir-plans').classList.toggle('active', dir === 'plans');
  document.getElementById('docs-dir-docs').classList.toggle('active', dir === 'docs');
  // ファイル一覧リロード、表示エリアリセット
  loadDocFiles();
  resetDocsContent();
}

// ファイル一覧取得・表示
async function loadDocFiles() {
  const res = await fetch(`/api/docs/files?dir=${_docsCurrentDir}`);
  const data = await res.json();
  const el = document.getElementById('docs-file-list');
  el.innerHTML = data.files.map(f =>
    `<button class="db-tab${f.name === _docsCurrentFile ? ' active' : ''}"
            onclick="selectDocFile('${esc(f.name)}')">${esc(f.name)}</button>`
  ).join('');
}

// ファイル選択・内容表示
async function selectDocFile(name) {
  _docsCurrentFile = name;
  loadDocFiles();  // active状態を更新
  document.getElementById('docs-file-name').textContent = name;

  const res = await fetch(`/api/docs/file?dir=${_docsCurrentDir}&name=${encodeURIComponent(name)}`);
  if (!res.ok) { /* エラー表示 */ return; }
  const md = await res.text();

  document.getElementById('docs-file-meta').textContent = `${md.length}文字`;
  document.getElementById('docs-content').innerHTML = simpleMarkdownToHtml(md);
}

// 表示エリアリセット
function resetDocsContent() {
  document.getElementById('docs-file-name').textContent = 'ファイルを選択してください';
  document.getElementById('docs-file-meta').textContent = '';
  document.getElementById('docs-content').innerHTML =
    '<p style="color:#9a88b5;">← ファイルを選択すると内容が表示されます</p>';
}
```

**動作フロー**:
1. タブ切替時 → `loadDocFiles()` でplansの一覧を表示（初期状態）
2. `plans` / `docs` ボタンクリック → `switchDocsDir()` でディレクトリ切替 + 一覧リロード
3. ファイルボタンクリック → `selectDocFile()` でMarkdown取得 → `simpleMarkdownToHtml()` で描画
4. ディレクトリを切り替えると表示エリアはリセット

#### 3c: タブ登録 (`static/js/admin/utils.js`)

`TAB_NAMES` 配列に `'docs'` を追加。

#### 3d: タブ初期化 (`static/js/admin/init.js`)

Docsタブ表示時に `loadDocFiles()` を呼ぶ処理を追加（既存のタブ切替コールバックパターンに従う）。

#### 3e: scriptタグ (`static/index.html`)

`<script src="/static/js/admin/docs.js"></script>` を追加（markdown.jsの後）。

### Step 4: テスト (`tests/test_api_docs_viewer.py` 新規)

- 一覧API: plans/docs両方のファイル一覧が返ること
- 一覧API: 不正なdirパラメータが拒否されること
- 内容API: 存在するファイルの内容が返ること
- 内容API: パストラバーサル（`../`）が拒否されること
- 内容API: 存在しないファイルで404が返ること

## 対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `scripts/routes/docs_viewer.py` | 新規: ファイル一覧 + 内容取得API |
| `scripts/web.py` | ルート登録追加 |
| `static/index.html` | Docsタブ追加 |
| `static/js/admin/docs.js` | 新規: ファイル一覧・Markdown表示UI |
| `static/js/admin/utils.js` | TAB_NAMESに追加 |
| `tests/test_api_docs_viewer.py` | 新規: APIテスト |

## セキュリティ

- `dir` パラメータ: `plans` / `docs` のみホワイトリスト許可
- `name` パラメータ: `..` を含むパスは拒否、`.md` 拡張子のみ許可
- ファイル読み取りは `resolve()` 後に対象ディレクトリ内であることを検証
