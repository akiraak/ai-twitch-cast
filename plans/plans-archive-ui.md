# 管理画面から plans をアーカイブへ移動するUI

## 背景
- 完了した作業プランは `plans/archive/` に手動で `git mv` して整理している（例: コミット `cee7402 完了済みプラン30件を plans/archive/ へ移動`）
- いちいちWSLのターミナルに戻って `git mv` するのが地味に面倒
- 管理画面の Docs タブで plans 一覧は既に見えており、ここからワンクリックでアーカイブへ送れると運用が軽くなる
- TODO.md の「その他」項目: `管理画面の docs/plans にアーカイブに移動させるUIを入れる`

## 現状
- Docs タブ（`static/index.html` + `static/js/admin/docs.js`）は plans/ docs/ prompts/ の Markdown を **閲覧のみ**
- サーバ側は `scripts/routes/docs_viewer.py` に以下の2本だけ:
  - `GET /api/docs/files?dir=...` — ファイル一覧
  - `GET /api/docs/file?dir=...&name=...` — ファイル本文
- 書き換え/移動系のエンドポイントは未実装
- `plans/` 直下と `plans/archive/` 配下のファイルは UI 上ですでにグループ分けされて表示されている（`docs.js` が `archive` ディレクトリを末尾に折りたたみ表示）

## 方針
最小構成で「plans/ 直下のファイルを選んで archive/ に移動」だけをサポートする。

- **対象**: `plans/` 直下の `*.md` のみ（サブディレクトリのものは対象外 = 既にアーカイブ済みまたは子プラン集は触らない）
- **逆方向（archive → plans）は今回はやらない**（普段使わないので YAGNI）
- **git mv は使わず、Python の `Path.rename` で移動**（ファイルシステム上のリネームで十分。コミットは手動または既存のコミットフローに任せる）
- **確認ダイアログ**: 誤爆防止で `confirm()` を挟む

## 実装ステップ

### 1. サーバ側: POST エンドポイント追加
`scripts/routes/docs_viewer.py` に以下を追加:

```python
@router.post("/api/docs/archive-plan")
async def archive_plan(name: str):
    """plans/<name>.md を plans/archive/<name>.md に移動する"""
    # バリデーション:
    #   - name に "/" や ".." を含まない（サブディレクトリ禁止）
    #   - name が *.md
    #   - plans/<name> が存在する
    #   - plans/archive/<name> が既に存在する場合はエラー（上書き防止）
    # 処理:
    #   - plans/archive/ が無ければ mkdir
    #   - Path.rename で移動
    # レスポンス: {"ok": True} / {"ok": False, "error": "..."}
```

ポイント:
- `ALLOWED_DIRS` と同じく `PROJECT_ROOT / "plans"` を基準にパスを組み立て、`resolve()` 後に `plans/` 配下から出ていないか確認（シンボリックリンク等の脱出対策）
- 既存の `docs_viewer.py` の `GET /api/docs/file` と同じ防御パターンを踏襲

### 2. クライアント側: ボタン追加
`static/js/admin/docs.js`:

- `renderDocFileBtn(f)` で、plans 直下のファイル（= ルートファイル、`f.name` に `/` を含まない）かつ `_docsCurrentDir === 'plans'` のときだけ「📦 アーカイブ」ボタンをファイル行の末尾に追加する
  - archive 内のファイルには出さない（`/` を含むため自然に除外される）
  - plans 以外のディレクトリ（docs, prompts）にも出さない
- クリックで `archivePlan(name)` を呼ぶ（`event.stopPropagation()` で選択クリックと分離）

```js
async function archivePlan(name) {
  if (!confirm(`${name} を plans/archive/ に移動しますか？`)) return;
  const res = await fetch(`/api/docs/archive-plan?name=${encodeURIComponent(name)}`, { method: 'POST' });
  const data = await res.json();
  if (!data.ok) {
    alert(`移動失敗: ${data.error || '不明なエラー'}`);
    return;
  }
  // 移動したファイルを選択中だったらクリア
  if (_docsCurrentFile === name) {
    _docsCurrentFile = '';
    resetDocsContent();
  }
  loadDocFiles();
}
```

### 3. スタイル
- ボタンは既存の `.docs-file-btn` のレイアウトを崩さないよう、小さいアイコンボタンとして右端に配置
- CSS は `static/css/` 配下の既存シートに `.docs-file-archive-btn` クラスを追加（または `docs.js` 内でインラインでもよい）

### 4. テスト
`tests/test_api_docs.py`（新規 or 既存があればそこへ）:
- 正常系: `plans/foo.md` → `plans/archive/foo.md` に移動できる
- 異常系: `name` に `/` を含む → 400
- 異常系: `name` に `..` を含む → 400
- 異常系: 存在しないファイル → 404 or エラーレスポンス
- 異常系: archive に同名ファイルが既にある → エラー（上書きしない）

テスト後に必ず `python3 -m pytest tests/ -q` で全体がグリーンを確認。

## リスク
- **ファイル移動はコミット外で起こる** → 管理画面で移動した直後に `git status` すると ` D plans/foo.md` と `?? plans/archive/foo.md` が残る。これは既存の手動 `git mv` と同等の挙動なので問題なしとする（コミットは従来どおり手動）
- **同名ファイル衝突**: エラーにして上書きしない。上書きしたいケースが出たら別途拡張
- **書き込みAPIの追加**: 今まで docs_viewer は読み取り専用だった。POST を足すことで攻撃面が広がる点に注意。パスの `..`/絶対パス/サブディレクトリを徹底拒否する

## スコープ外（今回はやらない）
- archive → plans への復帰
- 任意パスへの移動
- 複数ファイル一括アーカイブ
- docs/ や prompts/ のアーカイブ
- git commit の自動化

## 拡張（2026-04-18）: plans/ 直下のサブディレクトリも対応
- `plans/student-character/` `plans/teacher-mode-v2/` のようなサブディレクトリ単位のプランも 📦 ボタンで `plans/archive/<dir>/` に移動できる
- `Path.rename` は同一ファイルシステム上ならディレクトリもそのまま移動できる（中身ごと）
- `archive` 自身の移動は明示的に拒否（400）

## ステータス
完了（2026-04-18）
