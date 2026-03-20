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


def read_html_index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


def read_js_index() -> str:
    return (STATIC_DIR / "js" / "index-app.js").read_text(encoding="utf-8")


def read_js_text_variables() -> str:
    return (STATIC_DIR / "js" / "lib" / "text-variables.js").read_text(encoding="utf-8")


# === ITEM_REGISTRY ===

EXPECTED_ITEMS = ["avatar", "subtitle", "todo", "topic"]


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

    def test_applies_styles_directly(self):
        """共通プロパティが直接スタイル適用されること"""
        js = read_js()
        func_match = re.search(
            r"function applyCommonStyle\(.*?\n\}", js, re.DOTALL
        )
        body = func_match.group(0)
        # 直接適用
        assert "el.style.borderRadius" in body, "borderRadiusが直接適用されていない"
        assert "el.style.color" in body, "textColorが直接適用されていない"
        assert "el.style.padding" in body, "paddingが直接適用されていない"
        assert "el.style.border" in body, "borderが直接適用されていない"
        assert "el.style.webkitTextStroke" in body, "textStrokeが直接適用されていない"
        # CSS変数も並行設定
        assert "--item-bg-color" in body
        assert "--item-border-radius" in body


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

    def test_custom_text_variable_expansion(self):
        """テキスト変数展開関数が共通ファイルに存在すること"""
        js = read_js_text_variables()
        assert "function replaceTextVariables(" in js
        assert "key: 'version'" in js
        assert "key: 'date'" in js
        # broadcast-main.jsから共通関数を呼び出していること
        broadcast_js = read_js()
        assert "replaceTextVariables(" in broadcast_js



# === broadcast.html の data-editable 属性 ===


class TestWebUICommonProps:
    """Web UI (index.html/index-app.js) の共通プロパティUI検証"""

    def test_all_panels_have_data_section(self):
        html = read_html_index()
        for section in EXPECTED_ITEMS:
            assert f'data-section="{section}"' in html, (
                f'index.html に data-section="{section}" のパネルがない'
            )

    def test_init_common_props_exists(self):
        js = read_js_index()
        assert "function initCommonProps()" in js
        assert "function _commonPropsHTML(" in js

    def test_common_props_generates_controls(self):
        js = read_js_index()
        func_match = re.search(
            r"function _commonPropsHTML\(.*?\n\}", js, re.DOTALL
        )
        assert func_match
        body = func_match.group(0)
        # 共通コントロール（17項目: 配置6 + 背景6 + 文字5）
        for key in ["visible", "positionX", "positionY", "width", "height", "zIndex",
                     "bgColor", "bgOpacity", "borderRadius",
                     "borderColor", "borderSize",
                     "textColor", "textStrokeSize", "textStrokeColor",
                     "textStrokeOpacity", "padding"]:
            assert key in body, f"_commonPropsHTML に {key} がない"

    def test_common_props_has_groups(self):
        """共通コントロールがグループ分けされていること"""
        js = read_js_index()
        func_match = re.search(
            r"function _commonPropsHTML\(.*?\n\}", js, re.DOTALL
        )
        body = func_match.group(0)
        assert "配置" in body, "配置グループがない"
        assert "背景" in body, "背景グループがない"
        assert "文字" in body, "文字グループがない"

    def test_no_details_folding(self):
        """折りたたみ<details>が使われていないこと"""
        js = read_js_index()
        func_match = re.search(
            r"function _commonPropsHTML\(.*?\n\}", js, re.DOTALL
        )
        body = func_match.group(0)
        assert "<details" not in body, "_commonPropsHTML に <details> が残っている"

    def test_common_inserted_at_top(self):
        """共通コントロールがpanel-body先頭に挿入されること"""
        js = read_js_index()
        assert "function _injectCommonProps(" in js
        func_match = re.search(
            r"function _injectCommonProps\(.*?\n\}", js, re.DOTALL
        )
        assert func_match
        body = func_match.group(0)
        assert "afterbegin" in body, "panel-body.afterbegin への挿入がない"

    def test_color_handler_exists(self):
        js = read_js_index()
        assert "function onLayoutColor(" in js
        assert "function cssColorToHex(" in js

    def test_toggle_handler_exists(self):
        js = read_js_index()
        assert "function onLayoutToggle(" in js

    def test_apply_layout_handles_colors_and_toggles(self):
        js = read_js_index()
        func_match = re.search(
            r"function _applyLayoutToUI\(.*?\n\}", js, re.DOTALL
        )
        assert func_match
        body = func_match.group(0)
        assert "layout-color" in body, "_applyLayoutToUI がカラーピッカーを初期化していない"
        assert "layout-toggle" in body, "_applyLayoutToUI がトグルを初期化していない"


class TestCssVariables:
    """broadcast.cssがCSS変数を使っていること"""

    def _read_css(self):
        return (STATIC_DIR / "css" / "broadcast.css").read_text(encoding="utf-8")

    def test_css_uses_item_variables(self):
        """CSS変数 --item-* がCSSで参照されていること"""
        css = self._read_css()
        assert "var(--item-border-radius" in css
        assert "var(--item-text-color" in css
        assert "var(--item-font-size" in css

    def test_existing_items_use_border_radius_var(self):
        """subtitle, todo, topicのborder-radiusがCSS変数を使っていること"""
        css = self._read_css()
        for panel in ["#subtitle", "#todo-panel", "#topic-panel"]:
            # パネルのCSSブロックを探してborder-radius: var(を確認
            idx = css.find(panel + " {") if panel + " {" in css else css.find(panel + " {\n")
            if idx == -1:
                idx = css.find(panel + "\n")
            assert idx != -1, f"{panel} が見つからない"
            block = css[idx:css.find("}", idx) + 1]
            assert "var(--item-border-radius" in block, (
                f"{panel} の border-radius が CSS変数を使っていない"
            )


class TestDataEditableAttributes:
    """broadcast.htmlの各パネルにdata-editable属性があること"""

    def test_all_items_have_data_editable(self):
        html = read_html()
        expected = {
            "avatar": "avatar-area",
            "subtitle": "subtitle",
            "todo": "todo-panel",
            "topic": "topic-panel",
        }
        for editable_name, element_id in expected.items():
            pattern = rf'id="{element_id}"[^>]*data-editable="{editable_name}"'
            alt_pattern = rf'data-editable="{editable_name}"[^>]*id="{element_id}"'
            assert re.search(pattern, html) or re.search(alt_pattern, html), (
                f'{element_id} に data-editable="{editable_name}" がない'
            )
