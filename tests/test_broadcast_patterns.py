"""broadcast.html / broadcast-main.js のパターン検証テスト。

アイテム共通化で導入した構造（ITEM_REGISTRY, applyCommonStyle, data-editable）の
回帰を防止する。実行環境にブラウザは不要（ソースコード解析のみ）。
"""

import re
from pathlib import Path

STATIC_DIR = Path(__file__).parent.parent / "static"


def read_js() -> str:
    return (STATIC_DIR / "js" / "broadcast-main.js").read_text(encoding="utf-8")


def read_html() -> str:
    return (STATIC_DIR / "broadcast.html").read_text(encoding="utf-8")


# === ITEM_REGISTRY ===

EXPECTED_ITEMS = ["avatar", "subtitle", "todo", "topic", "version", "dev_activity"]


class TestItemRegistry:
    """ITEM_REGISTRYの構造検証"""

    def test_registry_exists(self):
        js = read_js()
        assert "const ITEM_REGISTRY" in js, "ITEM_REGISTRY が broadcast-main.js に存在しない"

    def test_registry_contains_all_items(self):
        js = read_js()
        for prefix in EXPECTED_ITEMS:
            assert f"prefix: '{prefix}'" in js, (
                f"ITEM_REGISTRY に prefix: '{prefix}' がない"
            )

    def test_registry_has_default_z(self):
        """各アイテムにdefaultZが定義されていること"""
        js = read_js()
        # ITEM_REGISTRY部分を抽出
        match = re.search(r"const ITEM_REGISTRY\s*=\s*\[(.*?)\];", js, re.DOTALL)
        assert match, "ITEM_REGISTRY の定義が見つからない"
        registry_body = match.group(1)
        for prefix in EXPECTED_ITEMS:
            # 各アイテムにdefaultZがあることを確認
            item_match = re.search(
                rf"prefix:\s*'{prefix}'.*?defaultZ:\s*\d+", registry_body, re.DOTALL
            )
            assert item_match, f"{prefix} に defaultZ がない"


# === applyCommonStyle ===


class TestApplyCommonStyle:
    """applyCommonStyle関数の構造検証"""

    def test_function_exists(self):
        js = read_js()
        assert "function applyCommonStyle(" in js

    def test_handles_visible(self):
        js = read_js()
        # applyCommonStyle内でvisibleを処理していること
        func_match = re.search(
            r"function applyCommonStyle\(.*?\n\}", js, re.DOTALL
        )
        assert func_match, "applyCommonStyle 関数が見つからない"
        body = func_match.group(0)
        assert "props.visible" in body, "applyCommonStyle が visible を処理していない"

    def test_handles_position(self):
        js = read_js()
        func_match = re.search(
            r"function applyCommonStyle\(.*?\n\}", js, re.DOTALL
        )
        body = func_match.group(0)
        assert "props.positionX" in body
        assert "props.positionY" in body

    def test_handles_bg_opacity(self):
        js = read_js()
        func_match = re.search(
            r"function applyCommonStyle\(.*?\n\}", js, re.DOTALL
        )
        body = func_match.group(0)
        assert "props.bgOpacity" in body

    def test_sets_css_variables(self):
        """新規共通プロパティがCSS変数として設定されること"""
        js = read_js()
        func_match = re.search(
            r"function applyCommonStyle\(.*?\n\}", js, re.DOTALL
        )
        body = func_match.group(0)
        expected_vars = [
            "--item-bg-color",
            "--item-border-radius",
            "--item-text-color",
            "--item-font-size",
            "--item-padding",
        ]
        for var in expected_vars:
            assert var in body, f"applyCommonStyle に CSS変数 {var} の設定がない"


# === applySettings が applyCommonStyle を使用 ===


class TestApplySettingsUsesCommon:
    """applySettingsが各アイテムでapplyCommonStyleを呼んでいること"""

    def test_calls_common_for_visual_items(self):
        js = read_js()
        # applySettings関数内でapplyCommonStyleが呼ばれていること
        func_match = re.search(
            r"function applySettings\(s\)\s*\{(.*?)\n\}", js, re.DOTALL
        )
        assert func_match, "applySettings 関数が見つからない"
        body = func_match.group(1)
        # 各アイテムでapplyCommonStyleが呼ばれているか
        expected_calls = [
            "applyCommonStyle(avatarArea",
            "applyCommonStyle(subtitleEl",
            "applyCommonStyle(todoPanelEl",
            "applyCommonStyle(topicPanelEl",
            "applyCommonStyle(vp, s.version",
            "applyCommonStyle(dap, s.dev_activity",
        ]
        for call in expected_calls:
            assert call in body, f"applySettings に {call} がない"


# === editSave が ITEM_REGISTRY を使用 ===


class TestEditSaveUsesRegistry:
    """editSaveがITEM_REGISTRYループで保存していること"""

    def test_uses_registry_loop(self):
        js = read_js()
        func_match = re.search(
            r"async function editSave\(\)\s*\{(.*?)\n\}", js, re.DOTALL
        )
        assert func_match, "editSave 関数が見つからない"
        body = func_match.group(1)
        assert "ITEM_REGISTRY" in body, "editSave が ITEM_REGISTRY を使用していない"
        assert "item.prefix" in body, "editSave が item.prefix でキーを生成していない"

    def test_saves_visible_by_default(self):
        """visibleがskipVisible以外の全アイテムで保存されること"""
        js = read_js()
        func_match = re.search(
            r"async function editSave\(\)\s*\{(.*?)\n\}", js, re.DOTALL
        )
        body = func_match.group(1)
        assert "skipVisible" in body, "editSave が skipVisible を参照していない"
        assert "data.visible" in body, "editSave が visible を保存していない"

    def test_saves_subtitle_specific_props(self):
        """subtitle固有プロパティ（bottom, fontSize, maxWidth, fadeDuration, bgOpacity）が保存されること"""
        js = read_js()
        func_match = re.search(
            r"async function editSave\(\)\s*\{(.*?)\n\}", js, re.DOTALL
        )
        body = func_match.group(1)
        assert "overlaySettings.subtitle" in body
        assert "subtitle.bottom" in body or ".bottom" in body
        assert "subtitle.fontSize" in body or ".fontSize" in body
        assert "subtitle.maxWidth" in body or ".maxWidth" in body
        assert "subtitle.fadeDuration" in body or ".fadeDuration" in body
        assert "subtitle.bgOpacity" in body or ".bgOpacity" in body

    def test_saves_topic_specific_props(self):
        """topic固有プロパティ（maxWidth, titleFontSize）が保存されること"""
        js = read_js()
        func_match = re.search(
            r"async function editSave\(\)\s*\{(.*?)\n\}", js, re.DOTALL
        )
        body = func_match.group(1)
        assert "overlaySettings.topic" in body
        assert "topic.maxWidth" in body or "topic].maxWidth" in body

    def test_saves_version_specific_props(self):
        """version固有プロパティ（fontSize, strokeSize, strokeOpacity, format）が保存されること"""
        js = read_js()
        func_match = re.search(
            r"async function editSave\(\)\s*\{(.*?)\n\}", js, re.DOTALL
        )
        body = func_match.group(1)
        assert "overlaySettings.version" in body
        assert "version.fontSize" in body or "version].fontSize" in body
        assert "strokeSize" in body
        assert "strokeOpacity" in body
        assert "_versionFormat" in body

    def test_dev_activity_skips_visible(self):
        """dev_activityはskipVisible: trueでvisibleを保存しないこと"""
        js = read_js()
        match = re.search(r"const ITEM_REGISTRY\s*=\s*\[(.*?)\];", js, re.DOTALL)
        assert match
        registry = match.group(1)
        # dev_activityのエントリにskipVisibleがあること
        da_match = re.search(
            r"prefix:\s*'dev_activity'.*?skipVisible:\s*true", registry, re.DOTALL
        )
        assert da_match, "dev_activity に skipVisible: true がない"


# === broadcast.html の data-editable 属性 ===


class TestDataEditableAttributes:
    """broadcast.htmlの各パネルにdata-editable属性があること"""

    def test_all_items_have_data_editable(self):
        html = read_html()
        expected = {
            "avatar": "avatar-area",
            "subtitle": "subtitle",
            "todo": "todo-panel",
            "topic": "topic-panel",
            "version": "version-panel",
            "dev_activity": "dev-activity-panel",
        }
        for editable_name, element_id in expected.items():
            pattern = rf'id="{element_id}"[^>]*data-editable="{editable_name}"'
            alt_pattern = rf'data-editable="{editable_name}"[^>]*id="{element_id}"'
            assert re.search(pattern, html) or re.search(alt_pattern, html), (
                f'{element_id} に data-editable="{editable_name}" がない'
            )
