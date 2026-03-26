"""Step 2: 基本ページ表示テスト — CLAUDE.mdの「壊れやすいポイント」を自動検出"""

import pytest


pytestmark = pytest.mark.browser


class TestIndexPage:
    """管理画面（index.html）の基本表示"""

    def test_tabs_visible(self, page, base_url):
        """全タブが表示される"""
        page.goto(f"{base_url}/")
        page.wait_for_selector(".tabs", timeout=5000)
        expected_tabs = [
            "キャラクター", "会話モード", "配信画面", "サウンド",
            "チャット", "TODO", "Debug", "DB",
        ]
        for tab_name in expected_tabs:
            tab = page.locator(f".tab:has-text('{tab_name}')")
            assert tab.is_visible(), f"タブ '{tab_name}' が表示されていない"

    def test_teacher_subtab_loads(self, page, base_url):
        """会話モード → 教師モード サブタブが開ける"""
        page.goto(f"{base_url}/")
        page.wait_for_selector(".tabs", timeout=5000)
        # 会話モードタブをクリック
        page.locator(".tab:has-text('会話モード')").click()
        # 教師モードサブタブが表示される
        teacher_subtab = page.locator(".char-subtab:has-text('教師モード')")
        teacher_subtab.wait_for(state="visible", timeout=3000)
        teacher_subtab.click()
        # lesson-list コンテナが存在する
        page.wait_for_selector("#lesson-list", timeout=3000)

    def test_character_tab_default(self, page, base_url):
        """初期表示でキャラクタータブがアクティブ"""
        page.goto(f"{base_url}/")
        page.wait_for_selector(".tabs", timeout=5000)
        active_tab = page.locator(".tab.active")
        assert "キャラクター" in active_tab.text_content()

    def test_no_js_errors(self, page, base_url):
        """JSコンソールエラーがない"""
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        assert errors == [], f"JSエラー検出: {errors}"


class TestBroadcastPage:
    """配信ページ（broadcast.html）の基本表示"""

    @pytest.fixture
    def broadcast_url(self, page, base_url):
        """トークン付きbroadcast URL"""
        resp = page.request.get(f"{base_url}/api/broadcast/token")
        token = resp.json()["token"]
        return f"{base_url}/broadcast?token={token}"

    def test_todo_panel_exists(self, page, broadcast_url):
        """TODOパネルが存在する"""
        page.goto(broadcast_url, wait_until="domcontentloaded")
        page.wait_for_selector("#todo-panel", timeout=5000)

    def test_subtitle_exists(self, page, broadcast_url):
        """字幕パネルが存在する"""
        page.goto(broadcast_url, wait_until="domcontentloaded")
        page.wait_for_selector("#subtitle", timeout=5000)

    def test_avatar_area_exists(self, page, broadcast_url):
        """アバターエリアが存在する"""
        page.goto(broadcast_url, wait_until="domcontentloaded")
        page.wait_for_selector("#avatar-area-1", timeout=5000)

    def test_lesson_panels_exist(self, page, broadcast_url):
        """授業用パネルが存在する（非表示でもDOM上に存在）"""
        page.goto(broadcast_url, wait_until="domcontentloaded")
        # 授業パネルは通常非表示だが DOM 上に存在する
        page.wait_for_selector("#lesson-text-panel", state="attached", timeout=5000)
        page.wait_for_selector("#lesson-progress-panel", state="attached", timeout=5000)

    def test_websocket_connects(self, page, broadcast_url):
        """WebSocket接続が確立される"""
        page.goto(broadcast_url, wait_until="domcontentloaded")
        # WebSocket接続を待つ（window._ws が設定され readyState=OPEN になるまで）
        page.wait_for_function(
            "() => window._ws && window._ws.readyState === 1",
            timeout=10000,
        )

    def test_no_js_errors(self, page, broadcast_url):
        """JSコンソールエラーがない（VRM読み込みエラーは除外）"""
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(broadcast_url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")
        # VRMモデル未設定によるエラーは許容
        real_errors = [e for e in errors if "vrm" not in e.lower() and "404" not in e]
        assert real_errors == [], f"JSエラー検出: {real_errors}"
