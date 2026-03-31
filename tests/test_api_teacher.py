"""教師モードAPIのテスト"""

import asyncio
import json

from unittest.mock import AsyncMock, MagicMock, patch


def parse_sse_result(response):
    """SSEレスポンスから最終結果（ok付き）を取得する"""
    text = response.text
    result = None
    for line in text.split('\n'):
        if line.startswith('data: '):
            try:
                data = json.loads(line[6:])
                if 'ok' in data:
                    result = data
            except json.JSONDecodeError:
                pass
    return result


class TestLessonCRUD:
    def test_list_empty(self, api_client):
        resp = api_client.get("/api/lessons")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["lessons"] == []

    def test_create_lesson(self, api_client):
        resp = api_client.post("/api/lessons", json={"name": "English 1-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["lesson"]["name"] == "English 1-1"
        assert data["lesson"]["id"] is not None

    def test_get_lesson(self, api_client):
        # 作成
        r1 = api_client.post("/api/lessons", json={"name": "Test"})
        lid = r1.json()["lesson"]["id"]
        # 取得
        resp = api_client.get(f"/api/lessons/{lid}")
        data = resp.json()
        assert data["ok"] is True
        assert data["lesson"]["name"] == "Test"
        assert data["sources"] == []
        assert data["sections"] == []

    def test_get_lesson_not_found(self, api_client):
        resp = api_client.get("/api/lessons/9999")
        data = resp.json()
        assert data["ok"] is False

    def test_update_lesson_name(self, api_client):
        r1 = api_client.post("/api/lessons", json={"name": "Old"})
        lid = r1.json()["lesson"]["id"]
        resp = api_client.put(f"/api/lessons/{lid}", json={"name": "New"})
        assert resp.json()["ok"] is True
        # 確認
        r2 = api_client.get(f"/api/lessons/{lid}")
        assert r2.json()["lesson"]["name"] == "New"

    def test_delete_lesson(self, api_client):
        r1 = api_client.post("/api/lessons", json={"name": "ToDelete"})
        lid = r1.json()["lesson"]["id"]
        resp = api_client.delete(f"/api/lessons/{lid}")
        assert resp.json()["ok"] is True
        # 取得不可
        r2 = api_client.get(f"/api/lessons/{lid}")
        assert r2.json()["ok"] is False

    def test_list_after_create(self, api_client):
        api_client.post("/api/lessons", json={"name": "A"})
        api_client.post("/api/lessons", json={"name": "B"})
        resp = api_client.get("/api/lessons")
        data = resp.json()
        assert len(data["lessons"]) == 2


class TestLessonSources:
    def test_upload_image(self, api_client, tmp_path):
        r1 = api_client.post("/api/lessons", json={"name": "ImgTest"})
        lid = r1.json()["lesson"]["id"]

        # テスト画像
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        resp = api_client.post(
            f"/api/lessons/{lid}/upload-image",
            files={"file": ("test.png", img.read_bytes(), "image/png")},
        )
        data = resp.json()
        assert data["ok"] is True
        assert data["source"]["source_type"] == "image"

    def test_upload_invalid_extension(self, api_client):
        r1 = api_client.post("/api/lessons", json={"name": "ExtTest"})
        lid = r1.json()["lesson"]["id"]

        resp = api_client.post(
            f"/api/lessons/{lid}/upload-image",
            files={"file": ("test.txt", b"hello", "text/plain")},
        )
        data = resp.json()
        assert data["ok"] is False

    def test_delete_source(self, api_client, tmp_path):
        r1 = api_client.post("/api/lessons", json={"name": "DelSrc"})
        lid = r1.json()["lesson"]["id"]

        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        r2 = api_client.post(
            f"/api/lessons/{lid}/upload-image",
            files={"file": ("test.png", img.read_bytes(), "image/png")},
        )
        sid = r2.json()["source"]["id"]

        resp = api_client.delete(f"/api/lessons/{lid}/sources/{sid}")
        assert resp.json()["ok"] is True

        # ソース確認
        r3 = api_client.get(f"/api/lessons/{lid}")
        assert len(r3.json()["sources"]) == 0


    def test_clear_sources(self, api_client, test_db, tmp_path):
        """clear-sourcesで既存ソース・セクション・抽出テキストがクリアされる"""
        r1 = api_client.post("/api/lessons", json={"name": "ClearTest"})
        lid = r1.json()["lesson"]["id"]

        # 画像追加
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        api_client.post(
            f"/api/lessons/{lid}/upload-image",
            files={"file": ("test.png", img.read_bytes(), "image/png")},
        )
        test_db.add_lesson_section(lid, 0, "introduction", "old")
        test_db.update_lesson(lid, extracted_text="old text")

        # クリア
        resp = api_client.post(f"/api/lessons/{lid}/clear-sources")
        assert resp.json()["ok"] is True

        r = api_client.get(f"/api/lessons/{lid}")
        data = r.json()
        assert len(data["sources"]) == 0
        assert len(data["sections"]) == 0
        assert data["lesson"]["extracted_text"] == ""

    def test_upload_multiple_images(self, api_client, tmp_path):
        """複数画像を連続アップロードできる"""
        r1 = api_client.post("/api/lessons", json={"name": "MultiImg"})
        lid = r1.json()["lesson"]["id"]

        for name in ["a.png", "b.png", "c.png"]:
            img = tmp_path / name
            img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
            api_client.post(
                f"/api/lessons/{lid}/upload-image",
                files={"file": (name, img.read_bytes(), "image/png")},
            )

        r = api_client.get(f"/api/lessons/{lid}")
        assert len(r.json()["sources"]) == 3

    def test_extract_text_saves_main_content(self, api_client, test_db, mock_gemini, tmp_path):
        """extract-text が main_content も保存する"""
        r1 = api_client.post("/api/lessons", json={"name": "MainContent"})
        lid = r1.json()["lesson"]["id"]

        # 画像ソース追加
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        api_client.post(
            f"/api/lessons/{lid}/upload-image",
            files={"file": ("test.png", img.read_bytes(), "image/png")},
        )

        # Geminiモック: 1回目=テキスト抽出, 2回目=メインコンテンツ識別
        mc_json = json.dumps([
            {"content_type": "passage", "content": "Hello world", "label": "Greeting", "role": "main"}
        ])
        mock_gemini.models.generate_content.side_effect = [
            MagicMock(text="Hello world text"),
            MagicMock(text=mc_json),
        ]

        resp = api_client.post(f"/api/lessons/{lid}/extract-text")
        data = resp.json()
        assert data["ok"] is True
        assert len(data["main_content"]) == 1
        assert data["main_content"][0]["content_type"] == "passage"
        assert data["main_content"][0]["role"] == "main"

        # DBにも保存されているか
        lesson = test_db.get_lesson(lid)
        assert lesson["main_content"] != ""
        saved = json.loads(lesson["main_content"])
        assert saved[0]["content_type"] == "passage"
        assert saved[0]["role"] == "main"

    def test_add_url_saves_main_content(self, api_client, test_db, mock_gemini):
        """add-url が main_content も保存する"""
        r1 = api_client.post("/api/lessons", json={"name": "UrlMC"})
        lid = r1.json()["lesson"]["id"]

        mc_json = json.dumps([
            {"content_type": "conversation", "content": "A: Hi\nB: Hello", "label": "Dialog", "role": "main"}
        ])
        mock_gemini.models.generate_content.side_effect = [
            MagicMock(text="A: Hi\nB: Hello"),  # URL抽出
            MagicMock(text=mc_json),             # メインコンテンツ識別
        ]

        with patch("src.lesson_generator.extractor.httpx.AsyncClient") as mock_http:
            mock_resp = AsyncMock()
            mock_resp.text = "<html><body>A: Hi B: Hello</body></html>"
            mock_resp.raise_for_status = MagicMock()
            mock_http.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_resp)
            ))
            mock_http.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = api_client.post(
                f"/api/lessons/{lid}/add-url",
                json={"url": "https://example.com/lesson"},
            )

        data = resp.json()
        assert data["ok"] is True
        assert len(data["main_content"]) == 1
        assert data["main_content"][0]["content_type"] == "conversation"

    def test_main_content_in_get_response(self, api_client, test_db):
        """GET /api/lessons/{id} に main_content が含まれる"""
        r1 = api_client.post("/api/lessons", json={"name": "MCGet"})
        lid = r1.json()["lesson"]["id"]

        mc = json.dumps([{"content_type": "passage", "content": "text", "label": "L"}])
        test_db.update_lesson(lid, main_content=mc)

        resp = api_client.get(f"/api/lessons/{lid}")
        data = resp.json()
        assert data["lesson"]["main_content"] == mc


class TestLessonSections:
    def _create_lesson_with_sections(self, api_client, test_db):
        """ヘルパー: セクション付きレッスンを作成"""
        r = api_client.post("/api/lessons", json={"name": "SecTest"})
        lid = r.json()["lesson"]["id"]
        # 直接DBにセクション追加
        s1 = test_db.add_lesson_section(lid, 0, "introduction", "はじめに")
        s2 = test_db.add_lesson_section(lid, 1, "explanation", "説明")
        s3 = test_db.add_lesson_section(lid, 2, "summary", "まとめ")
        return lid, [s1, s2, s3]

    def test_update_section(self, api_client, test_db):
        lid, secs = self._create_lesson_with_sections(api_client, test_db)
        sid = secs[0]["id"]
        resp = api_client.put(
            f"/api/lessons/{lid}/sections/{sid}",
            json={"content": "更新後", "emotion": "excited"},
        )
        assert resp.json()["ok"] is True

        # 確認
        r = api_client.get(f"/api/lessons/{lid}")
        updated = [s for s in r.json()["sections"] if s["id"] == sid][0]
        assert updated["content"] == "更新後"
        assert updated["emotion"] == "excited"

    def test_delete_section(self, api_client, test_db):
        lid, secs = self._create_lesson_with_sections(api_client, test_db)
        sid = secs[1]["id"]
        resp = api_client.delete(f"/api/lessons/{lid}/sections/{sid}")
        assert resp.json()["ok"] is True

        r = api_client.get(f"/api/lessons/{lid}")
        assert len(r.json()["sections"]) == 2

    def test_reorder_sections(self, api_client, test_db):
        lid, secs = self._create_lesson_with_sections(api_client, test_db)
        ids = [s["id"] for s in secs]
        # 逆順にする
        reversed_ids = list(reversed(ids))
        resp = api_client.put(
            f"/api/lessons/{lid}/sections/reorder",
            json={"section_ids": reversed_ids},
        )
        assert resp.json()["ok"] is True

        r = api_client.get(f"/api/lessons/{lid}")
        result_ids = [s["id"] for s in r.json()["sections"]]
        assert result_ids == reversed_ids

    def test_update_plan(self, api_client, test_db):
        """プランの手動編集"""
        r = api_client.post("/api/lessons", json={"name": "PlanEdit"})
        lid = r.json()["lesson"]["id"]

        resp = api_client.put(f"/api/lessons/{lid}/plan", json={
            "plan_knowledge": "更新された知識分析",
            "plan_entertainment": "更新されたエンタメ構成",
        })
        assert resp.json()["ok"] is True

        lesson = test_db.get_lesson(lid)
        assert lesson["plan_knowledge"] == "更新された知識分析"
        assert lesson["plan_entertainment"] == "更新されたエンタメ構成"

class TestImportSections:
    """セクションインポートAPIのテスト"""

    def _make_sections(self):
        return [
            {
                "section_type": "introduction",
                "title": "導入",
                "content": "今日は英語を学びます",
                "tts_text": "今日は英語を学びます",
                "display_text": "英語の基礎",
                "emotion": "excited",
                "dialogues": [
                    {"speaker": "teacher", "content": "こんにちは！", "tts_text": "こんにちは！", "emotion": "excited"},
                    {"speaker": "student", "content": "よろしく！", "tts_text": "よろしく！", "emotion": "joy"},
                ],
                "dialogue_directions": [
                    {"speaker": "teacher", "direction": "挨拶する", "key_content": ""},
                ],
            },
            {
                "section_type": "summary",
                "title": "まとめ",
                "content": "今日の復習です",
                "tts_text": "今日の復習です",
                "display_text": "まとめ",
                "emotion": "joy",
                "dialogues": [],
            },
        ]

    def test_import_sections(self, api_client, test_db):
        """正常なセクションインポート"""
        r = api_client.post("/api/lessons", json={"name": "ImportTest"})
        lid = r.json()["lesson"]["id"]

        resp = api_client.post(
            f"/api/lessons/{lid}/import-sections?lang=ja&generator=claude",
            json={"sections": self._make_sections(), "plan_summary": "テスト授業"},
        )
        data = resp.json()
        assert data["ok"] is True
        assert data["count"] == 2
        assert data["sections"][0]["generator"] == "claude"
        assert data["sections"][0]["section_type"] == "introduction"
        assert data["sections"][1]["section_type"] == "summary"

        # dialoguesがJSON文字列として保存されている
        dlgs = json.loads(data["sections"][0]["dialogues"])
        assert len(dlgs) == 2
        assert dlgs[0]["speaker"] == "teacher"

    def test_import_sections_not_found(self, api_client):
        """存在しないレッスンへのインポート"""
        resp = api_client.post(
            "/api/lessons/9999/import-sections?generator=claude",
            json={"sections": [{"section_type": "introduction", "content": "x", "tts_text": "x", "display_text": "x"}]},
        )
        assert resp.json()["ok"] is False

    def test_import_sections_empty(self, api_client):
        """空セクションのインポート"""
        r = api_client.post("/api/lessons", json={"name": "EmptyImport"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.post(
            f"/api/lessons/{lid}/import-sections?generator=claude",
            json={"sections": []},
        )
        assert resp.json()["ok"] is False

    def test_import_sections_validation_error(self, api_client):
        """必須フィールド不足のインポート"""
        r = api_client.post("/api/lessons", json={"name": "ValErr"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.post(
            f"/api/lessons/{lid}/import-sections?generator=claude",
            json={"sections": [{"section_type": "introduction"}]},
        )
        data = resp.json()
        assert data["ok"] is False
        assert "details" in data

    def test_import_replaces_same_generator(self, api_client, test_db):
        """同じgeneratorで再インポートすると置き換わる"""
        r = api_client.post("/api/lessons", json={"name": "ReplaceTest"})
        lid = r.json()["lesson"]["id"]

        sections = self._make_sections()
        api_client.post(
            f"/api/lessons/{lid}/import-sections?generator=claude",
            json={"sections": sections},
        )
        # 再インポート（1セクションだけ）
        resp = api_client.post(
            f"/api/lessons/{lid}/import-sections?generator=claude",
            json={"sections": [sections[0]]},
        )
        assert resp.json()["count"] == 1

        # GETで確認: claudeセクションは1つだけ
        r2 = api_client.get(f"/api/lessons/{lid}")
        claude_sections = r2.json()["sections_by_generator"].get("claude", [])
        assert len(claude_sections) == 1

    def test_import_does_not_affect_gemini(self, api_client, test_db):
        """claudeインポートがgeminiセクションに影響しない"""
        r = api_client.post("/api/lessons", json={"name": "CoexistTest"})
        lid = r.json()["lesson"]["id"]

        # geminiセクションを追加
        test_db.add_lesson_section(lid, 0, "introduction", "geminiの導入", generator="gemini")

        # claudeセクションをインポート
        api_client.post(
            f"/api/lessons/{lid}/import-sections?generator=claude",
            json={"sections": self._make_sections()},
        )

        r2 = api_client.get(f"/api/lessons/{lid}")
        by_gen = r2.json()["sections_by_generator"]
        assert len(by_gen.get("gemini", [])) == 1
        assert len(by_gen.get("claude", [])) == 2

    def test_sections_by_generator_in_get(self, api_client, test_db):
        """GET /api/lessons/{id} に sections_by_generator が含まれる"""
        r = api_client.post("/api/lessons", json={"name": "ByGenTest"})
        lid = r.json()["lesson"]["id"]

        test_db.add_lesson_section(lid, 0, "introduction", "gemini", generator="gemini")
        test_db.add_lesson_section(lid, 0, "introduction", "claude", generator="claude")

        resp = api_client.get(f"/api/lessons/{lid}")
        data = resp.json()
        assert "sections_by_generator" in data
        assert "gemini" in data["sections_by_generator"]
        assert "claude" in data["sections_by_generator"]


class TestPaceScale:
    def test_get_default_pace_scale(self, api_client):
        """デフォルトのpace_scaleは1.0"""
        resp = api_client.get("/api/lessons/pace-scale")
        data = resp.json()
        assert data["ok"] is True
        assert data["pace_scale"] == 1.0

    def test_set_pace_scale(self, api_client):
        """pace_scaleを設定・取得できる"""
        resp = api_client.put("/api/lessons/pace-scale", json={"pace_scale": 1.5})
        assert resp.json()["ok"] is True
        assert resp.json()["pace_scale"] == 1.5

        resp2 = api_client.get("/api/lessons/pace-scale")
        assert resp2.json()["pace_scale"] == 1.5

    def test_pace_scale_clamped(self, api_client):
        """pace_scaleは0.5〜2.0にクランプされる"""
        api_client.put("/api/lessons/pace-scale", json={"pace_scale": 0.1})
        resp = api_client.get("/api/lessons/pace-scale")
        assert resp.json()["pace_scale"] == 0.5

        api_client.put("/api/lessons/pace-scale", json={"pace_scale": 5.0})
        resp = api_client.get("/api/lessons/pace-scale")
        assert resp.json()["pace_scale"] == 2.0


class TestLessonControl:
    def test_get_status_idle(self, api_client):
        """初期状態はidle"""
        resp = api_client.get("/api/lessons/status")
        data = resp.json()
        assert data["ok"] is True
        assert data["status"]["state"] == "idle"

    def test_start_lesson(self, api_client, test_db):
        """授業開始"""
        r = api_client.post("/api/lessons", json={"name": "StartTest"})
        lid = r.json()["lesson"]["id"]
        # セクション追加（APIデフォルトが"claude"なのでgeneratorを合わせる）
        test_db.add_lesson_section(lid, 0, "introduction", "はじめに", generator="claude")
        test_db.add_lesson_section(lid, 1, "explanation", "説明", generator="claude")

        resp = api_client.post(f"/api/lessons/{lid}/start")
        data = resp.json()
        assert data["ok"] is True
        assert data["status"]["state"] == "running"
        assert data["status"]["total_sections"] == 2

        # クリーンアップ: 授業を停止
        api_client.post("/api/lessons/stop")

    def test_start_lesson_no_sections(self, api_client):
        """セクションなしでの授業開始はエラー"""
        r = api_client.post("/api/lessons", json={"name": "NoSec"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.post(f"/api/lessons/{lid}/start")
        assert resp.json()["ok"] is False

    def test_pause_resume(self, api_client, test_db):
        """一時停止と再開（直接LessonRunnerを操作）"""
        from scripts import state
        runner = state.reader.lesson_runner

        r = api_client.post("/api/lessons", json={"name": "PauseTest"})
        lid = r.json()["lesson"]["id"]
        # 多くのセクションを追加して再生が終わらないようにする
        for i in range(10):
            test_db.add_lesson_section(lid, i, "explanation", f"テスト{i}" * 20)

        api_client.post(f"/api/lessons/{lid}/start")

        # LessonRunnerがrunning状態になったことを確認してからpause
        if runner.state.value == "running":
            resp = api_client.post("/api/lessons/pause")
            assert resp.json()["status"]["state"] == "paused"

            resp = api_client.post("/api/lessons/resume")
            assert resp.json()["status"]["state"] == "running"

        # クリーンアップ
        api_client.post("/api/lessons/stop")

    def test_stop_lesson(self, api_client, test_db):
        """授業停止"""
        r = api_client.post("/api/lessons", json={"name": "StopTest"})
        lid = r.json()["lesson"]["id"]
        test_db.add_lesson_section(lid, 0, "introduction", "テスト")

        api_client.post(f"/api/lessons/{lid}/start")
        resp = api_client.post("/api/lessons/stop")
        assert resp.json()["status"]["state"] == "idle"

    def test_start_not_found(self, api_client):
        """存在しないコンテンツの授業開始"""
        resp = api_client.post("/api/lessons/9999/start")
        assert resp.json()["ok"] is False


class TestTtsCacheAPI:
    """TTSキャッシュAPIのテスト"""

    def test_get_tts_cache_empty(self, api_client, test_db, tmp_path, monkeypatch):
        """キャッシュなし状態の取得"""
        import src.lesson_runner as lr
        monkeypatch.setattr(lr, "LESSON_AUDIO_DIR", tmp_path / "audio")

        r = api_client.post("/api/lessons", json={"name": "CacheTest"})
        lid = r.json()["lesson"]["id"]
        test_db.add_lesson_section(lid, 0, "intro", "Hello", generator="claude")

        resp = api_client.get(f"/api/lessons/{lid}/tts-cache")
        data = resp.json()
        assert data["ok"] is True
        assert len(data["sections"]) == 1
        assert data["sections"][0]["parts"] == []

    def test_get_tts_cache_not_found(self, api_client):
        """存在しないレッスンのキャッシュ取得"""
        resp = api_client.get("/api/lessons/9999/tts-cache")
        assert resp.json()["ok"] is False

    def test_delete_tts_cache(self, api_client):
        """TTSキャッシュ全削除"""
        r = api_client.post("/api/lessons", json={"name": "DelCacheTest"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.delete(f"/api/lessons/{lid}/tts-cache")
        assert resp.json()["ok"] is True

    def test_delete_tts_cache_section(self, api_client):
        """特定セクションのTTSキャッシュ削除"""
        r = api_client.post("/api/lessons", json={"name": "DelSecCache"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.delete(f"/api/lessons/{lid}/tts-cache/0")
        assert resp.json()["ok"] is True

    def test_section_edit_clears_cache(self, api_client, test_db, tmp_path, monkeypatch):
        """セクション編集時にTTSキャッシュが削除される"""
        import src.lesson_runner as lr
        monkeypatch.setattr(lr, "LESSON_AUDIO_DIR", tmp_path)

        r = api_client.post("/api/lessons", json={"name": "EditCache"})
        lid = r.json()["lesson"]["id"]
        sec = test_db.add_lesson_section(lid, 0, "intro", "Hello")

        # キャッシュファイルを作成
        cache_dir = tmp_path / str(lid)
        cache_dir.mkdir(parents=True)
        cache_file = cache_dir / "section_00_part_00.wav"
        cache_file.write_bytes(b"fake_wav")

        # tts_text を編集
        resp = api_client.put(
            f"/api/lessons/{lid}/sections/{sec['id']}",
            json={"tts_text": "ハロー"}
        )
        assert resp.json()["ok"] is True
        assert not cache_file.exists()
