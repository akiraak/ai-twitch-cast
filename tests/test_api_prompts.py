"""プロンプト管理API (scripts/routes/prompts.py) のテスト

方針:
- PROMPTS_DIR を tmp_path に差し替えて、実際の prompts/ ディレクトリへの副作用を防ぐ
- AI編集 (Gemini呼び出し) は mock_gemini フィクスチャで制御
- _validate_name のパストラバーサル/不正ファイル名防御を単体でも確認
"""

from unittest.mock import MagicMock


def _make_prompts_dir(tmp_path, monkeypatch):
    """PROMPTS_DIR を tmp_path/prompts に差し替える"""
    import scripts.routes.prompts as prompts_mod
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    monkeypatch.setattr(prompts_mod, "PROMPTS_DIR", prompts_dir)
    return prompts_dir


class TestValidateName:
    """_validate_name（安全なPath返却 or None）"""

    def test_valid_md_filename(self, tmp_path, monkeypatch):
        prompts = _make_prompts_dir(tmp_path, monkeypatch)
        import scripts.routes.prompts as prompts_mod
        result = prompts_mod._validate_name("lesson_generate.md")
        assert result == (prompts / "lesson_generate.md").resolve()

    def test_valid_nested_path(self, tmp_path, monkeypatch):
        prompts = _make_prompts_dir(tmp_path, monkeypatch)
        (prompts / "subdir").mkdir()
        import scripts.routes.prompts as prompts_mod
        result = prompts_mod._validate_name("subdir/nested.md")
        assert result == (prompts / "subdir" / "nested.md").resolve()

    def test_rejects_empty(self, tmp_path, monkeypatch):
        _make_prompts_dir(tmp_path, monkeypatch)
        import scripts.routes.prompts as prompts_mod
        assert prompts_mod._validate_name("") is None

    def test_rejects_parent_traversal(self, tmp_path, monkeypatch):
        _make_prompts_dir(tmp_path, monkeypatch)
        import scripts.routes.prompts as prompts_mod
        assert prompts_mod._validate_name("../etc/passwd.md") is None
        assert prompts_mod._validate_name("foo/../../secrets.md") is None

    def test_rejects_non_md_extension(self, tmp_path, monkeypatch):
        _make_prompts_dir(tmp_path, monkeypatch)
        import scripts.routes.prompts as prompts_mod
        assert prompts_mod._validate_name("script.py") is None
        assert prompts_mod._validate_name("data.json") is None
        assert prompts_mod._validate_name("no_extension") is None

    def test_rejects_escape_via_absolute_path(self, tmp_path, monkeypatch):
        _make_prompts_dir(tmp_path, monkeypatch)
        import scripts.routes.prompts as prompts_mod
        # 絶対パスを渡された場合、resolve() で PROMPTS_DIR 外に出る → None
        # (".." を含まない絶対パスは最初のチェックを通るが、startswith で弾かれる)
        assert prompts_mod._validate_name("/etc/evil.md") is None


class TestListPrompts:
    """GET /api/prompts"""

    def test_missing_dir_returns_empty_list(self, api_client, tmp_path, monkeypatch):
        import scripts.routes.prompts as prompts_mod
        # PROMPTS_DIR が存在しないパスを指す
        monkeypatch.setattr(prompts_mod, "PROMPTS_DIR", tmp_path / "no_such_dir")
        resp = api_client.get("/api/prompts")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"ok": True, "files": []}

    def test_empty_dir(self, api_client, tmp_path, monkeypatch):
        _make_prompts_dir(tmp_path, monkeypatch)
        resp = api_client.get("/api/prompts")
        body = resp.json()
        assert body == {"ok": True, "files": []}

    def test_lists_md_files_with_metadata(self, api_client, tmp_path, monkeypatch):
        prompts = _make_prompts_dir(tmp_path, monkeypatch)
        (prompts / "a.md").write_text("# タイトルA\n\n本文", encoding="utf-8")
        (prompts / "b.md").write_text("本文のみ（タイトル無し）", encoding="utf-8")

        resp = api_client.get("/api/prompts")
        body = resp.json()
        assert body["ok"] is True
        files = {f["name"]: f for f in body["files"]}
        assert set(files.keys()) == {"a.md", "b.md"}
        assert files["a.md"]["title"] == "タイトルA"
        assert files["b.md"]["title"] == ""
        assert files["a.md"]["size"] > 0
        assert isinstance(files["a.md"]["modified"], float)

    def test_includes_nested_md(self, api_client, tmp_path, monkeypatch):
        prompts = _make_prompts_dir(tmp_path, monkeypatch)
        (prompts / "sub").mkdir()
        (prompts / "sub" / "deep.md").write_text("# 深い場所", encoding="utf-8")

        resp = api_client.get("/api/prompts")
        names = [f["name"] for f in resp.json()["files"]]
        assert "sub/deep.md" in names

    def test_ignores_non_md_files(self, api_client, tmp_path, monkeypatch):
        prompts = _make_prompts_dir(tmp_path, monkeypatch)
        (prompts / "a.md").write_text("# A", encoding="utf-8")
        (prompts / "b.txt").write_text("ignored", encoding="utf-8")
        (prompts / "c.py").write_text("ignored", encoding="utf-8")

        resp = api_client.get("/api/prompts")
        names = [f["name"] for f in resp.json()["files"]]
        assert names == ["a.md"]


class TestGetPrompt:
    """GET /api/prompts/{name:path}"""

    def test_returns_file_content(self, api_client, tmp_path, monkeypatch):
        prompts = _make_prompts_dir(tmp_path, monkeypatch)
        content = "# タイトル\n\n本文のテスト"
        (prompts / "lesson.md").write_text(content, encoding="utf-8")

        resp = api_client.get("/api/prompts/lesson.md")
        assert resp.status_code == 200
        assert resp.text == content
        assert resp.headers["content-type"].startswith("text/plain")

    def test_nested_path(self, api_client, tmp_path, monkeypatch):
        prompts = _make_prompts_dir(tmp_path, monkeypatch)
        (prompts / "sub").mkdir()
        (prompts / "sub" / "x.md").write_text("nested content", encoding="utf-8")

        resp = api_client.get("/api/prompts/sub/x.md")
        assert resp.status_code == 200
        assert resp.text == "nested content"

    def test_invalid_name_returns_400(self, api_client, tmp_path, monkeypatch):
        _make_prompts_dir(tmp_path, monkeypatch)
        resp = api_client.get("/api/prompts/evil.py")
        assert resp.status_code == 400
        assert "不正なファイル名" in resp.text

    def test_traversal_returns_400(self, api_client, tmp_path, monkeypatch):
        _make_prompts_dir(tmp_path, monkeypatch)
        resp = api_client.get("/api/prompts/..%2Fetc%2Fpasswd.md")
        # ".." がパスに含まれるため _validate_name が None を返す → 400
        assert resp.status_code == 400

    def test_nonexistent_returns_404(self, api_client, tmp_path, monkeypatch):
        _make_prompts_dir(tmp_path, monkeypatch)
        resp = api_client.get("/api/prompts/ghost.md")
        assert resp.status_code == 404
        assert "見つかりません" in resp.text


class TestUpdatePrompt:
    """PUT /api/prompts/{name:path}"""

    def test_overwrites_file(self, api_client, tmp_path, monkeypatch):
        prompts = _make_prompts_dir(tmp_path, monkeypatch)
        target = prompts / "lesson.md"
        target.write_text("古い内容", encoding="utf-8")

        resp = api_client.put(
            "/api/prompts/lesson.md",
            content="新しい内容",
            headers={"content-type": "text/plain"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert target.read_text(encoding="utf-8") == "新しい内容"

    def test_invalid_name(self, api_client, tmp_path, monkeypatch):
        _make_prompts_dir(tmp_path, monkeypatch)
        resp = api_client.put(
            "/api/prompts/evil.py",
            content="x",
            headers={"content-type": "text/plain"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "不正なファイル名" in body["error"]

    def test_nonexistent_file(self, api_client, tmp_path, monkeypatch):
        _make_prompts_dir(tmp_path, monkeypatch)
        resp = api_client.put(
            "/api/prompts/ghost.md",
            content="x",
            headers={"content-type": "text/plain"},
        )
        body = resp.json()
        assert body["ok"] is False
        assert "見つかりません" in body["error"]

    def test_does_not_create_new_file(self, api_client, tmp_path, monkeypatch):
        """存在しないファイルへのPUTは作成しない（update専用）"""
        prompts = _make_prompts_dir(tmp_path, monkeypatch)
        resp = api_client.put(
            "/api/prompts/new.md",
            content="new content",
            headers={"content-type": "text/plain"},
        )
        assert resp.json()["ok"] is False
        assert not (prompts / "new.md").exists()


class TestEscapeHtml:
    """_escape_html（ヘルパー）"""

    def test_escapes_basic_chars(self):
        import scripts.routes.prompts as prompts_mod
        assert prompts_mod._escape_html("<b>hi</b>") == "&lt;b&gt;hi&lt;/b&gt;"
        assert prompts_mod._escape_html('a & b') == "a &amp; b"
        assert prompts_mod._escape_html('say "hi"') == "say &quot;hi&quot;"

    def test_ampersand_escaped_first(self):
        """& → &amp; が最初。連鎖エスケープで二重 & にならないこと"""
        import scripts.routes.prompts as prompts_mod
        # "<" → "&lt;" だが "&" が先に "&amp;" にならず残るとおかしくなる
        assert prompts_mod._escape_html("&<") == "&amp;&lt;"


class TestMakeDiffHtml:
    """_make_diff_html（ヘルパー）"""

    def test_add_and_remove_lines(self):
        import scripts.routes.prompts as prompts_mod
        html = prompts_mod._make_diff_html("a\nb\nc\n", "a\nB\nc\n")
        # 追加行と削除行がそれぞれ別クラスで出る
        assert 'class="diff-line-add"' in html
        assert 'class="diff-line-del"' in html
        # ヘッダ（---/+++）もctxクラスで出る
        assert "diff-line-ctx" in html

    def test_hunk_header_gets_purple_ctx(self):
        import scripts.routes.prompts as prompts_mod
        html = prompts_mod._make_diff_html("a\n", "b\n")
        assert "#7b1fa2" in html  # @@ ハンクヘッダ

    def test_identical_inputs_produce_empty(self):
        import scripts.routes.prompts as prompts_mod
        html = prompts_mod._make_diff_html("same\n", "same\n")
        assert html == ""

    def test_escapes_html_in_content(self):
        import scripts.routes.prompts as prompts_mod
        html = prompts_mod._make_diff_html("<old>\n", "<new>\n")
        # "<" は &lt; にエスケープされる
        assert "&lt;old&gt;" in html
        assert "&lt;new&gt;" in html
        # 生の "<old>" は残らない
        assert "<old>" not in html.replace("<div", "")


class TestAiEditPrompt:
    """POST /api/prompts/ai-edit"""

    def test_empty_instruction(self, api_client, tmp_path, monkeypatch):
        _make_prompts_dir(tmp_path, monkeypatch)
        resp = api_client.post(
            "/api/prompts/ai-edit",
            json={"name": "lesson.md", "instruction": ""},
        )
        body = resp.json()
        assert body["ok"] is False
        assert "指示" in body["error"]

    def test_invalid_name(self, api_client, tmp_path, monkeypatch):
        _make_prompts_dir(tmp_path, monkeypatch)
        resp = api_client.post(
            "/api/prompts/ai-edit",
            json={"name": "evil.py", "instruction": "改善して"},
        )
        body = resp.json()
        assert body["ok"] is False
        assert "不正なファイル名" in body["error"]

    def test_nonexistent_file(self, api_client, tmp_path, monkeypatch):
        _make_prompts_dir(tmp_path, monkeypatch)
        resp = api_client.post(
            "/api/prompts/ai-edit",
            json={"name": "ghost.md", "instruction": "改善"},
        )
        body = resp.json()
        assert body["ok"] is False
        assert "見つかりません" in body["error"]

    def test_llm_edit_returns_diff(self, api_client, tmp_path, monkeypatch, mock_gemini):
        prompts = _make_prompts_dir(tmp_path, monkeypatch)
        (prompts / "lesson.md").write_text("# 古いタイトル\n古い本文", encoding="utf-8")

        mock_gemini.models.generate_content.return_value.text = "# 新しいタイトル\n新しい本文"

        resp = api_client.post(
            "/api/prompts/ai-edit",
            json={"name": "lesson.md", "instruction": "タイトルを新しくして"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["original"] == "# 古いタイトル\n古い本文"
        assert body["modified"] == "# 新しいタイトル\n新しい本文"
        assert "diff_html" in body
        assert 'class="diff-line-add"' in body["diff_html"]

        # ファイル自体は書き換わらない（プレビューのみ）
        assert (prompts / "lesson.md").read_text(encoding="utf-8") == "# 古いタイトル\n古い本文"

    def test_strips_code_block_wrapper(self, api_client, tmp_path, monkeypatch, mock_gemini):
        """LLM応答が ```...``` で囲まれていたら剥がす"""
        prompts = _make_prompts_dir(tmp_path, monkeypatch)
        (prompts / "a.md").write_text("original", encoding="utf-8")

        mock_gemini.models.generate_content.return_value.text = "```markdown\n# 修正後\n本文\n```"

        resp = api_client.post(
            "/api/prompts/ai-edit",
            json={"name": "a.md", "instruction": "直して"},
        )
        body = resp.json()
        assert body["ok"] is True
        # 先頭と末尾の ``` 行が除去される
        assert body["modified"] == "# 修正後\n本文"

    def test_llm_error_returns_error(self, api_client, tmp_path, monkeypatch):
        prompts = _make_prompts_dir(tmp_path, monkeypatch)
        (prompts / "a.md").write_text("x", encoding="utf-8")

        # mock_gemini を使わず、get_client を例外スロー版に差し替え
        import src.gemini_client as gc

        def broken_client():
            raise RuntimeError("API key invalid")

        monkeypatch.setattr(gc, "get_client", broken_client)

        resp = api_client.post(
            "/api/prompts/ai-edit",
            json={"name": "a.md", "instruction": "直して"},
        )
        body = resp.json()
        assert body["ok"] is False
        assert "API key invalid" in body["error"]

    def test_llm_receives_original_content_and_instruction(self, api_client, tmp_path, monkeypatch, mock_gemini):
        """LLMに渡される contents と system_instruction を検証"""
        prompts = _make_prompts_dir(tmp_path, monkeypatch)
        (prompts / "lesson.md").write_text("元の内容", encoding="utf-8")

        mock_gemini.models.generate_content.return_value.text = "修正済み"

        api_client.post(
            "/api/prompts/ai-edit",
            json={"name": "lesson.md", "instruction": "もっとやさしく"},
        )

        mock_gemini.models.generate_content.assert_called_once()
        kwargs = mock_gemini.models.generate_content.call_args.kwargs
        assert "もっとやさしく" in kwargs["contents"][0]
        assert "元の内容" in kwargs["contents"][0]
        # system_instruction にプロンプトエンジニア指示
        assert "プロンプトエンジニア" in kwargs["config"].system_instruction
