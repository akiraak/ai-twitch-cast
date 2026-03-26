# ブラウザテスト（Playwright）導入プラン

## ステータス: Step 2 完了、Step 3 待ち

---

## 背景

現在のテスト基盤は pytest + FastAPI TestClient による API/ユニットテスト（28ファイル、573+ テスト）。
しかしフロントエンドの動作確認は完全に手動であり、以下のリスクがある:

- UI変更でTODOパネルやアバター表示が消える（CLAUDE.md「壊れやすいポイント」）
- SSEストリーミング（プラン生成・スクリプト生成）の表示確認がない
- WebSocket接続の確認がない
- 授業モード v3 のような複雑なワークフローは手動テストに依存（[teacher-mode-v3-test.md](teacher-mode-v3-test.md) 参照）

### Playwright を選ぶ理由

| 比較項目 | Playwright | Selenium | Cypress |
|----------|-----------|----------|---------|
| Python統合 | pytest-playwright で既存基盤と統合 | ○ | Node.js のみ |
| SSE/WebSocket | ネイティブサポート | 手動実装 | 部分的 |
| ヘッドレス実行 | ○ CI向き | ○ | △ |
| セットアップ | `pip install` + `playwright install` | ドライバ管理が面倒 | npm |
| 速度 | 高速 | 遅い | 中程度 |

**結論**: pytest基盤にそのまま乗せられる Playwright が最適。

---

## 方針

### 段階的導入

一度に全UIをカバーせず、投資対効果が高いテストから段階的に導入する。

1. **Step 1: 環境構築 + Smoke Test** — まず動くことを確認
2. **Step 2: 基本ページ表示テスト** — 壊れやすい箇所を最低限ガード
3. **Step 3: 授業モード ワークフローテスト** — 手動テストの自動化
4. **Step 4: WebSocket/リアルタイムテスト** — broadcast.htmlの動作確認

### 設計方針

- **既存 pytest 基盤に統合**（`pytest-playwright`使用、新フレームワーク不要）
- **テストファイルは `tests/browser/` に配置**（既存ユニットテストと分離）
- **外部API（Gemini等）はサーバー側でモック**（既存conftest.pyのモックを活用）
- **ヘッドレスモードをデフォルト**（CI/WSL2環境対応）
- **テストサーバーを自動起動**（フィクスチャでuvicornを起動・終了）

---

## Step 1: 環境構築 + Smoke Test

### 1-1. 依存追加

```
# requirements.txt に追加
pytest-playwright>=0.5.0
playwright>=1.40.0
```

```bash
pip install pytest-playwright
playwright install chromium  # Chromiumのみでよい
```

### 1-2. ディレクトリ構成

```
tests/
├── browser/                    # ブラウザテスト（新規）
│   ├── conftest.py             # ブラウザテスト用フィクスチャ（テストサーバー起動等）
│   ├── test_smoke.py           # Smoke Test
│   ├── test_pages.py           # 基本ページ表示テスト
│   ├── test_teacher_workflow.py # 授業モードワークフロー
│   └── test_broadcast.py       # broadcast.html テスト
├── conftest.py                 # 既存（変更なし）
├── test_db.py                  # 既存（変更なし）
└── ...
```

### 1-3. ブラウザテスト用 conftest.py

```python
"""ブラウザテスト用フィクスチャ"""
import subprocess
import time
import pytest
import requests

@pytest.fixture(scope="session")
def browser_server():
    """テスト用Webサーバーを起動"""
    port = 18080  # テスト専用ポート
    proc = subprocess.Popen(
        ["python3", "-m", "uvicorn", "scripts.web:app",
         "--host", "127.0.0.1", "--port", str(port)],
        env={**os.environ, "WEB_PORT": str(port),
             "GEMINI_API_KEY": "test-key",
             "TWITCH_TOKEN": "test-token",
             "TWITCH_CLIENT_ID": "test-client-id",
             "TWITCH_CHANNEL": "test-channel"},
    )
    # サーバー起動待ち
    for _ in range(30):
        try:
            requests.get(f"http://127.0.0.1:{port}/api/status", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    proc.wait(timeout=5)

@pytest.fixture
def base_url(browser_server):
    return browser_server
```

**検討事項**:
- テストサーバー方式（上記）vs FastAPI TestClient + ASGI直接接続 — Playwrightは実HTTPが必要なので前者
- テスト用DBの分離方法 — 環境変数 `TEST_DB_PATH` でテスト専用DBを指定する案
- Gemini等外部APIのモック — テストサーバー起動時に環境変数でモックモードを有効化する案

### 1-4. Smoke Test

```python
# tests/browser/test_smoke.py
def test_index_loads(page, base_url):
    """管理画面が読み込める"""
    page.goto(f"{base_url}/")
    assert page.title()  # ページにタイトルがある
    page.wait_for_selector("#tabs")  # タブUIが表示される

def test_broadcast_loads(page, base_url):
    """配信ページが読み込める"""
    page.goto(f"{base_url}/broadcast")
    page.wait_for_selector("#broadcast-container")

def test_api_status(page, base_url):
    """APIが応答する"""
    resp = page.request.get(f"{base_url}/api/status")
    assert resp.ok
```

### 1-5. 実行方法

```bash
# ブラウザテストのみ実行
python3 -m pytest tests/browser/ -q

# 全テスト（ユニット + ブラウザ）
python3 -m pytest tests/ -q

# ヘッドモード（デバッグ時）
python3 -m pytest tests/browser/ -q --headed
```

### 1-5b. pytest.ini 更新

```ini
[pytest]
asyncio_mode = auto
markers =
    browser: ブラウザテスト（Playwright）
```

---

## Step 2: 基本ページ表示テスト

CLAUDE.mdの「壊れやすいポイント」を自動検出する。

### テスト項目

```python
# tests/browser/test_pages.py

class TestIndexPage:
    """管理画面（index.html）の基本表示"""

    def test_tabs_visible(self, page, base_url):
        """全タブが表示される"""
        page.goto(f"{base_url}/")
        tabs = ["キャラクター", "会話モード", "配信画面", "サウンド",
                "チャット", "TODO", "Debug", "DB"]
        for tab in tabs:
            assert page.get_by_role("tab", name=tab).is_visible()

    def test_teacher_tab_loads(self, page, base_url):
        """教師モードタブが開ける"""
        page.goto(f"{base_url}/")
        page.get_by_role("tab", name="授業").click()
        page.wait_for_selector(".lesson-list")

    def test_no_js_errors(self, page, base_url):
        """JSコンソールエラーがない"""
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{base_url}/")
        page.wait_for_timeout(2000)
        assert errors == [], f"JSエラー: {errors}"


class TestBroadcastPage:
    """配信ページ（broadcast.html）の基本表示"""

    def test_panels_visible(self, page, base_url):
        """主要パネルが存在する"""
        page.goto(f"{base_url}/broadcast")
        for panel_id in ["avatar-area", "subtitle-main",
                         "todo-panel", "lesson-text-panel"]:
            assert page.locator(f"#{panel_id}").count() >= 0  # 存在確認

    def test_websocket_connects(self, page, base_url):
        """WebSocket接続が確立される"""
        page.goto(f"{base_url}/broadcast")
        # WebSocket接続を待つ（broadcast.htmlが接続時にログ出力するのを利用）
        page.wait_for_function(
            "() => window._wsConnected === true",
            timeout=5000
        )
```

---

## Step 3: 授業モード ワークフローテスト

[teacher-mode-v3-test.md](teacher-mode-v3-test.md) の手動テストを段階的に自動化する。

### 優先度: 高（手動テストで最も時間がかかる部分）

```python
# tests/browser/test_teacher_workflow.py

class TestLessonCRUD:
    """Phase 0: コンテンツ管理の基本操作"""

    def test_create_lesson(self, page, base_url):
        """新規コンテンツ作成"""
        page.goto(f"{base_url}/")
        page.get_by_role("tab", name="授業").click()
        page.get_by_role("button", name="新規作成").click()
        # 作成ダイアログ → 名前入力 → 保存
        page.fill("input[name='lesson-name']", "テスト授業")
        page.get_by_role("button", name="作成").click()
        # 作成されたカードが表示される
        page.wait_for_selector(".lesson-item")

    def test_delete_lesson(self, page, base_url):
        """コンテンツ削除"""
        # 事前にAPIで作成
        page.request.post(f"{base_url}/api/lessons",
                          data={"name": "削除テスト"})
        page.goto(f"{base_url}/")
        page.get_by_role("tab", name="授業").click()
        page.wait_for_selector(".lesson-item")
        # 削除ボタン → 確認ダイアログ
        page.locator(".lesson-item .delete-btn").first.click()
        page.get_by_role("button", name="OK").click()


class TestPlanGeneration:
    """Phase 1: プラン生成の検証（teacher-mode-v3-test.md Phase 1 相当）"""

    def test_plan_generation_sse_progress(self, page, base_url):
        """プラン生成中にSSE進捗が表示される"""
        # NOTE: Geminiモックが必要 — テストサーバーのモック戦略次第
        # 1. コンテンツ作成 + ソース追加（API経由で事前準備）
        # 2. プラン生成ボタンクリック
        # 3. SSE進捗バーが表示される
        # 4. 完了トーストが表示される
        pass  # Step 3実装時に具体化

    def test_director_sections_displayed(self, page, base_url):
        """生成されたdirector_sectionsが管理画面に表示される"""
        # Phase 3 (3-3) の自動化
        # パース結果カードが表示される
        # 各セクションが展開可能
        pass


class TestAdminUI:
    """Phase 3: 管理画面UI検証（teacher-mode-v3-test.md Phase 3 相当）"""

    def test_phase_a_analysis_cards(self, page, base_url):
        """Phase A: 教材分析カードの表示"""
        # 3-1: 知識先生・エンタメ先生・監督のカード
        # 折りたたみでプロンプト全文が確認できる
        pass

    def test_data_flow_arrows(self, page, base_url):
        """データフロー矢印の表示"""
        # 3-2: Step間の矢印
        pass

    def test_phase_c_dialogue_cards(self, page, base_url):
        """Phase C: セリフ個別生成カードの表示"""
        # 3-4: 監督指示・key_content・生成プロンプト
        pass

    def test_persistence_after_reload(self, page, base_url):
        """ページリロード後もデータ保持"""
        # 3-6: リロード前後でデータ一致
        pass
```

### モック戦略（要検討）

授業モードのワークフローテストでは Gemini API のモックが必要。候補:

| 方式 | メリット | デメリット |
|------|---------|-----------|
| **A. テストサーバーにモックモード追加** | 実際のHTTPフローを通る | サーバーコード変更が必要 |
| **B. Playwright route.fulfill でAPIレスポンスを差し替え** | サーバー変更不要 | SSEのモックが複雑 |
| **C. 事前にDBにデータ投入** | 生成をスキップ、UI表示のみテスト | ワークフロー全体はカバーできない |

**推奨: C（まずUI表示テスト） → A（ワークフロー全体テスト）の段階導入**

Step 3の初期段階ではCを使い、APIで事前にデータを投入してUI表示を検証する。
ワークフロー全体の自動テストはモック戦略が固まってからStep 3後半で実装。

---

## Step 4: WebSocket / リアルタイムテスト

broadcast.htmlのリアルタイム機能を検証する。

```python
# tests/browser/test_broadcast.py

class TestWebSocket:
    """WebSocket経由のリアルタイム更新"""

    def test_subtitle_display(self, page, base_url):
        """字幕がWebSocket経由で表示される"""
        page.goto(f"{base_url}/broadcast")
        # APIでアバター発話をトリガー → 字幕表示を確認
        page.request.post(f"{base_url}/api/avatar/speak",
                          data={"text": "テスト字幕"})
        page.wait_for_selector(".subtitle-text:has-text('テスト字幕')")

    def test_todo_panel_updates(self, page, base_url):
        """TODOパネルが更新される"""
        page.goto(f"{base_url}/broadcast")
        # TODO更新API → パネル表示確認
        page.wait_for_selector("#todo-panel")

    def test_lesson_text_display(self, page, base_url):
        """授業テキストが配信画面に表示される"""
        page.goto(f"{base_url}/broadcast")
        # 授業開始 → lesson-text-panelにテキスト表示
        pass
```

---

## 実行構成

### 通常開発時

```bash
# ユニットテストのみ（高速、ブラウザ不要）
python3 -m pytest tests/ --ignore=tests/browser/ -q

# ブラウザテストのみ
python3 -m pytest tests/browser/ -q

# 全テスト
python3 -m pytest tests/ -q
```

### コミット前チェック

既存のテストは高速（数秒）だが、ブラウザテストはサーバー起動が必要で遅い（数十秒〜）。
post-commit hookには含めず、手動または定期的に実行する。

---

## リスク・課題

| リスク | 対策 |
|--------|------|
| WSL2でヘッドレスブラウザが動くか | `playwright install --with-deps chromium` で依存含めてインストール |
| テストサーバー起動が遅い | session スコープフィクスチャでテストスイート全体で1回のみ起動 |
| Gemini APIモックの複雑さ | まずUI表示テスト（事前データ投入）から始め、ワークフローテストは後回し |
| テストの不安定さ（flaky） | 明示的なwait_for_selectorを使い、固定タイムアウトを避ける |
| Chromiumのディスク容量（~400MB） | Chromiumのみインストール（Firefox/WebKit不要） |

---

## 成功基準

| Step | 完了条件 |
|------|---------|
| Step 1 | Smoke Test 3件が通る。`pytest tests/browser/` で実行可能 |
| Step 2 | 管理画面・配信ページの基本表示テスト通過。JSエラー検出が自動化 |
| Step 3 | 授業モードのCRUD + UI表示テスト通過。手動テストの50%以上を自動化 |
| Step 4 | WebSocket経由の字幕・TODO更新テスト通過 |

---

## 参考

- [teacher-mode-v3-test.md](teacher-mode-v3-test.md) — 授業モード手動テストプラン（自動化の元ネタ）
- [Playwright Python docs](https://playwright.dev/python/)
- [pytest-playwright](https://playwright.dev/python/docs/test-runners)
