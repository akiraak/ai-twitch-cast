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
        """正常なセクションインポート（version未指定で新バージョン自動作成）"""
        r = api_client.post("/api/lessons", json={"name": "ImportTest"})
        lid = r.json()["lesson"]["id"]

        resp = api_client.post(
            f"/api/lessons/{lid}/import-sections?lang=ja&generator=claude",
            json={"sections": self._make_sections(), "plan_summary": "テスト授業"},
        )
        data = resp.json()
        assert data["ok"] is True
        assert data["count"] == 2
        assert "version_number" in data
        assert data["version_number"] >= 1
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

    def test_import_replaces_same_version(self, api_client, test_db):
        """同じversionで再インポートすると置き換わる"""
        r = api_client.post("/api/lessons", json={"name": "ReplaceTest"})
        lid = r.json()["lesson"]["id"]

        sections = self._make_sections()
        resp1 = api_client.post(
            f"/api/lessons/{lid}/import-sections?generator=claude",
            json={"sections": sections},
        )
        v = resp1.json()["version_number"]
        # 同じバージョンに再インポート（1セクションだけ）
        resp = api_client.post(
            f"/api/lessons/{lid}/import-sections?generator=claude&version={v}",
            json={"sections": [sections[0]]},
        )
        assert resp.json()["count"] == 1

        # GETで確認: そのバージョンのclaudeセクションは1つだけ
        r2 = api_client.get(f"/api/lessons/{lid}?version={v}")
        claude_sections = r2.json()["sections_by_generator"].get("claude", [])
        assert len(claude_sections) == 1

    def test_import_does_not_affect_gemini(self, api_client, test_db):
        """claudeインポートがgeminiセクションに影響しない"""
        r = api_client.post("/api/lessons", json={"name": "CoexistTest"})
        lid = r.json()["lesson"]["id"]

        # geminiセクションを追加（version_number=1）
        test_db.add_lesson_section(lid, 0, "introduction", "geminiの導入",
                                   generator="gemini", version_number=1)

        # claudeセクションをインポート（新バージョンが自動作成される）
        api_client.post(
            f"/api/lessons/{lid}/import-sections?generator=claude",
            json={"sections": self._make_sections()},
        )

        # バージョン指定なしで全セクション取得
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


class TestCategoryAPI:
    """カテゴリCRUD APIのテスト"""

    def test_list_empty(self, api_client):
        """初期状態でカテゴリ一覧は空"""
        resp = api_client.get("/api/lesson-categories")
        data = resp.json()
        assert data["ok"] is True
        assert data["categories"] == []

    def test_create_category(self, api_client):
        """カテゴリ作成"""
        resp = api_client.post("/api/lesson-categories", json={
            "slug": "english_natgeo",
            "name": "英語（ナショジオ）",
            "description": "ナショジオの英語教材",
        })
        data = resp.json()
        assert data["ok"] is True
        assert data["category"]["slug"] == "english_natgeo"
        assert data["category"]["name"] == "英語（ナショジオ）"

    def test_create_duplicate_slug(self, api_client):
        """重複slugはエラー"""
        api_client.post("/api/lesson-categories", json={
            "slug": "dup", "name": "Dup1",
        })
        resp = api_client.post("/api/lesson-categories", json={
            "slug": "dup", "name": "Dup2",
        })
        assert resp.json()["ok"] is False

    def test_delete_category(self, api_client, test_db):
        """カテゴリ削除で関連授業のcategoryがリセットされる"""
        r = api_client.post("/api/lesson-categories", json={
            "slug": "to_del", "name": "削除テスト",
        })
        cat_id = r.json()["category"]["id"]

        # 授業にカテゴリを設定
        r2 = api_client.post("/api/lessons", json={
            "name": "CatLesson", "category": "to_del",
        })
        lid = r2.json()["lesson"]["id"]

        # カテゴリ削除
        resp = api_client.delete(f"/api/lesson-categories/{cat_id}")
        assert resp.json()["ok"] is True

        # 授業のcategoryが空になっている
        r3 = api_client.get(f"/api/lessons/{lid}")
        assert r3.json()["lesson"]["category"] == ""

    def test_lesson_create_with_category(self, api_client):
        """授業作成時にカテゴリを指定できる"""
        resp = api_client.post("/api/lessons", json={
            "name": "WithCat", "category": "math",
        })
        data = resp.json()
        assert data["ok"] is True
        assert data["lesson"]["category"] == "math"

    def test_lesson_update_category(self, api_client):
        """授業のカテゴリを更新できる"""
        r = api_client.post("/api/lessons", json={"name": "UpdateCat"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.put(f"/api/lessons/{lid}", json={"category": "science"})
        assert resp.json()["ok"] is True

        r2 = api_client.get(f"/api/lessons/{lid}")
        assert r2.json()["lesson"]["category"] == "science"


class TestVersionAPI:
    """バージョンCRUD APIのテスト"""

    def test_list_versions_empty(self, api_client):
        """セクションなしの授業のバージョン一覧"""
        r = api_client.post("/api/lessons", json={"name": "VerListTest"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.get(f"/api/lessons/{lid}/versions")
        data = resp.json()
        assert data["ok"] is True
        assert isinstance(data["versions"], list)

    def test_create_version(self, api_client):
        """バージョン作成"""
        r = api_client.post("/api/lessons", json={"name": "VerCreateTest"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.post(f"/api/lessons/{lid}/versions", json={
            "lang": "ja", "generator": "claude", "note": "初版",
        })
        data = resp.json()
        assert data["ok"] is True
        assert data["version"]["version_number"] >= 1
        assert data["version"]["note"] == "初版"

    def test_create_version_auto_increment(self, api_client):
        """バージョン番号は自動インクリメント"""
        r = api_client.post("/api/lessons", json={"name": "VerAutoInc"})
        lid = r.json()["lesson"]["id"]

        r1 = api_client.post(f"/api/lessons/{lid}/versions", json={
            "lang": "ja", "generator": "claude",
        })
        v1 = r1.json()["version"]["version_number"]

        r2 = api_client.post(f"/api/lessons/{lid}/versions", json={
            "lang": "ja", "generator": "claude",
        })
        v2 = r2.json()["version"]["version_number"]
        assert v2 == v1 + 1

    def test_update_version_note(self, api_client):
        """バージョンメモ更新"""
        r = api_client.post("/api/lessons", json={"name": "VerNoteTest"})
        lid = r.json()["lesson"]["id"]
        r1 = api_client.post(f"/api/lessons/{lid}/versions", json={
            "lang": "ja", "generator": "claude", "note": "old",
        })
        vn = r1.json()["version"]["version_number"]

        resp = api_client.put(
            f"/api/lessons/{lid}/versions/{vn}?lang=ja&generator=claude",
            json={"note": "updated note"},
        )
        assert resp.json()["ok"] is True

    def test_update_version_not_found(self, api_client):
        """存在しないバージョンの更新はエラー"""
        r = api_client.post("/api/lessons", json={"name": "VerNotFound"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.put(
            f"/api/lessons/{lid}/versions/999?lang=ja&generator=claude",
            json={"note": "x"},
        )
        assert resp.json()["ok"] is False

    def test_delete_version(self, api_client, test_db):
        """バージョン削除（セクション・プランも一緒に削除される）"""
        r = api_client.post("/api/lessons", json={"name": "VerDelTest"})
        lid = r.json()["lesson"]["id"]

        # バージョン作成 + セクション追加
        r1 = api_client.post(f"/api/lessons/{lid}/versions", json={
            "lang": "ja", "generator": "claude",
        })
        vn = r1.json()["version"]["version_number"]
        test_db.add_lesson_section(lid, 0, "introduction", "テスト",
                                   lang="ja", generator="claude", version_number=vn)

        # 削除
        resp = api_client.delete(
            f"/api/lessons/{lid}/versions/{vn}?lang=ja&generator=claude",
        )
        assert resp.json()["ok"] is True

        # セクションも消えている
        sections = test_db.get_lesson_sections(lid, lang="ja", generator="claude",
                                                version_number=vn)
        assert len(sections) == 0

    def test_delete_version_not_found(self, api_client):
        """存在しないバージョンの削除はエラー"""
        r = api_client.post("/api/lessons", json={"name": "VerDelNF"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.delete(
            f"/api/lessons/{lid}/versions/999?lang=ja&generator=claude",
        )
        assert resp.json()["ok"] is False

    def test_create_version_copy_from(self, api_client, test_db):
        """copy_fromでセクションがコピーされる"""
        r = api_client.post("/api/lessons", json={"name": "CopyTest"})
        lid = r.json()["lesson"]["id"]

        # v1作成 + セクション追加
        r1 = api_client.post(f"/api/lessons/{lid}/versions", json={
            "lang": "ja", "generator": "claude", "note": "v1",
        })
        v1 = r1.json()["version"]["version_number"]
        test_db.add_lesson_section(lid, 0, "introduction", "導入",
                                   tts_text="導入TTS", display_text="導入表示",
                                   lang="ja", generator="claude", version_number=v1)
        test_db.add_lesson_section(lid, 1, "summary", "まとめ",
                                   tts_text="まとめTTS", display_text="まとめ表示",
                                   lang="ja", generator="claude", version_number=v1)

        # v2をv1からコピー
        r2 = api_client.post(f"/api/lessons/{lid}/versions", json={
            "lang": "ja", "generator": "claude", "note": "v2 from v1",
            "copy_from": v1,
        })
        v2 = r2.json()["version"]["version_number"]
        assert v2 == v1 + 1

        # v2のセクション確認
        sections = test_db.get_lesson_sections(lid, lang="ja", generator="claude",
                                                version_number=v2)
        assert len(sections) == 2
        assert sections[0]["content"] == "導入"
        assert sections[1]["content"] == "まとめ"

    def test_copy_from_invalid_version(self, api_client):
        """存在しないバージョンからコピーはエラー"""
        r = api_client.post("/api/lessons", json={"name": "CopyErrTest"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.post(f"/api/lessons/{lid}/versions", json={
            "lang": "ja", "generator": "claude", "copy_from": 999,
        })
        assert resp.json()["ok"] is False

    def test_versions_in_get_lesson(self, api_client, test_db):
        """GET /api/lessons/{id} にversions一覧が含まれる"""
        r = api_client.post("/api/lessons", json={"name": "VerInGetTest"})
        lid = r.json()["lesson"]["id"]

        api_client.post(f"/api/lessons/{lid}/versions", json={
            "lang": "ja", "generator": "claude",
        })
        api_client.post(f"/api/lessons/{lid}/versions", json={
            "lang": "ja", "generator": "claude",
        })

        resp = api_client.get(f"/api/lessons/{lid}")
        data = resp.json()
        assert "versions" in data
        assert len(data["versions"]) == 2

    def test_get_lesson_with_version_filter(self, api_client, test_db):
        """GET /api/lessons/{id}?version=N でそのバージョンのセクションのみ返る"""
        r = api_client.post("/api/lessons", json={"name": "VerFilterTest"})
        lid = r.json()["lesson"]["id"]

        # v1にセクション2つ、v2にセクション1つ
        test_db.create_lesson_version(lid, lang="ja", generator="claude",
                                       version_number=1, note="v1")
        test_db.add_lesson_section(lid, 0, "introduction", "v1導入",
                                   lang="ja", generator="claude", version_number=1)
        test_db.add_lesson_section(lid, 1, "summary", "v1まとめ",
                                   lang="ja", generator="claude", version_number=1)

        test_db.create_lesson_version(lid, lang="ja", generator="claude",
                                       version_number=2, note="v2")
        test_db.add_lesson_section(lid, 0, "introduction", "v2導入",
                                   lang="ja", generator="claude", version_number=2)

        # v1のセクション
        r1 = api_client.get(f"/api/lessons/{lid}?version=1")
        assert len(r1.json()["sections"]) == 2

        # v2のセクション
        r2 = api_client.get(f"/api/lessons/{lid}?version=2")
        assert len(r2.json()["sections"]) == 1

        # バージョン指定なしは全セクション
        r3 = api_client.get(f"/api/lessons/{lid}")
        assert len(r3.json()["sections"]) == 3

    def test_list_versions_with_filter(self, api_client):
        """バージョン一覧をlang/generatorでフィルタ"""
        r = api_client.post("/api/lessons", json={"name": "VerFilterList"})
        lid = r.json()["lesson"]["id"]

        api_client.post(f"/api/lessons/{lid}/versions", json={
            "lang": "ja", "generator": "claude",
        })
        api_client.post(f"/api/lessons/{lid}/versions", json={
            "lang": "en", "generator": "claude",
        })

        resp_ja = api_client.get(f"/api/lessons/{lid}/versions?lang=ja")
        assert len(resp_ja.json()["versions"]) == 1

        resp_all = api_client.get(f"/api/lessons/{lid}/versions")
        assert len(resp_all.json()["versions"]) == 2


class TestImportWithVersioning:
    """インポートとバージョニングの統合テスト"""

    def _make_sections(self, n=2):
        secs = []
        for i in range(n):
            secs.append({
                "section_type": "explanation",
                "title": f"セクション{i}",
                "content": f"内容{i}",
                "tts_text": f"TTS{i}",
                "display_text": f"表示{i}",
                "emotion": "neutral",
            })
        return secs

    def test_import_creates_new_version(self, api_client, test_db):
        """version未指定のインポートは新バージョンを自動作成"""
        r = api_client.post("/api/lessons", json={"name": "AutoVerTest"})
        lid = r.json()["lesson"]["id"]

        resp = api_client.post(
            f"/api/lessons/{lid}/import-sections?generator=claude",
            json={"sections": self._make_sections()},
        )
        data = resp.json()
        assert data["ok"] is True
        assert data["version_number"] >= 1

        # バージョンが作成されている
        versions = test_db.get_lesson_versions(lid, lang="ja", generator="claude")
        assert len(versions) >= 1

    def test_import_twice_creates_two_versions(self, api_client, test_db):
        """version未指定で2回インポートすると2バージョンできる"""
        r = api_client.post("/api/lessons", json={"name": "TwiceVerTest"})
        lid = r.json()["lesson"]["id"]

        r1 = api_client.post(
            f"/api/lessons/{lid}/import-sections?generator=claude",
            json={"sections": self._make_sections(2)},
        )
        v1 = r1.json()["version_number"]

        r2 = api_client.post(
            f"/api/lessons/{lid}/import-sections?generator=claude",
            json={"sections": self._make_sections(3)},
        )
        v2 = r2.json()["version_number"]
        assert v2 > v1

        # 各バージョンのセクション数が正しい
        s1 = test_db.get_lesson_sections(lid, lang="ja", generator="claude",
                                          version_number=v1)
        s2 = test_db.get_lesson_sections(lid, lang="ja", generator="claude",
                                          version_number=v2)
        assert len(s1) == 2
        assert len(s2) == 3

    def test_import_with_version_replaces(self, api_client, test_db):
        """version指定のインポートは既存セクションを置き換え"""
        r = api_client.post("/api/lessons", json={"name": "ReplaceVerTest"})
        lid = r.json()["lesson"]["id"]

        # 最初のインポート
        r1 = api_client.post(
            f"/api/lessons/{lid}/import-sections?generator=claude",
            json={"sections": self._make_sections(3)},
        )
        v = r1.json()["version_number"]

        # 同じバージョンに再インポート（1セクション）
        r2 = api_client.post(
            f"/api/lessons/{lid}/import-sections?generator=claude&version={v}",
            json={"sections": self._make_sections(1)},
        )
        assert r2.json()["count"] == 1

        # セクション数が置き換わっている
        sections = test_db.get_lesson_sections(lid, lang="ja", generator="claude",
                                                version_number=v)
        assert len(sections) == 1

    def test_import_invalid_version(self, api_client):
        """存在しないバージョンへのインポートはエラー"""
        r = api_client.post("/api/lessons", json={"name": "BadVerImport"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.post(
            f"/api/lessons/{lid}/import-sections?generator=claude&version=999",
            json={"sections": [{
                "section_type": "introduction", "content": "x",
                "tts_text": "x", "display_text": "x",
            }]},
        )
        assert resp.json()["ok"] is False


class TestAnnotationAPI:
    """セクション注釈APIのテスト"""

    def test_update_annotation(self, api_client, test_db):
        """注釈を更新できる"""
        r = api_client.post("/api/lessons", json={"name": "AnnotTest"})
        lid = r.json()["lesson"]["id"]
        sec = test_db.add_lesson_section(lid, 0, "introduction", "テスト")

        resp = api_client.put(
            f"/api/lessons/{lid}/sections/{sec['id']}/annotation",
            json={"rating": "good", "comment": "わかりやすい"},
        )
        assert resp.json()["ok"] is True

        # DB確認
        sections = test_db.get_lesson_sections(lid)
        assert sections[0]["annotation_rating"] == "good"
        assert sections[0]["annotation_comment"] == "わかりやすい"

    def test_update_annotation_needs_improvement(self, api_client, test_db):
        """needs_improvement注釈"""
        r = api_client.post("/api/lessons", json={"name": "AnnotNI"})
        lid = r.json()["lesson"]["id"]
        sec = test_db.add_lesson_section(lid, 0, "explanation", "長い説明")

        resp = api_client.put(
            f"/api/lessons/{lid}/sections/{sec['id']}/annotation",
            json={"rating": "needs_improvement", "comment": "説明が長すぎる"},
        )
        assert resp.json()["ok"] is True

    def test_update_annotation_redo(self, api_client, test_db):
        """redo注釈"""
        r = api_client.post("/api/lessons", json={"name": "AnnotRedo"})
        lid = r.json()["lesson"]["id"]
        sec = test_db.add_lesson_section(lid, 0, "explanation", "ダメな説明")

        resp = api_client.put(
            f"/api/lessons/{lid}/sections/{sec['id']}/annotation",
            json={"rating": "redo", "comment": "作り直し"},
        )
        assert resp.json()["ok"] is True

    def test_clear_annotation(self, api_client, test_db):
        """注釈をクリアできる"""
        r = api_client.post("/api/lessons", json={"name": "AnnotClear"})
        lid = r.json()["lesson"]["id"]
        sec = test_db.add_lesson_section(lid, 0, "introduction", "テスト")

        # 設定
        api_client.put(
            f"/api/lessons/{lid}/sections/{sec['id']}/annotation",
            json={"rating": "good", "comment": "良い"},
        )
        # クリア
        resp = api_client.put(
            f"/api/lessons/{lid}/sections/{sec['id']}/annotation",
            json={"rating": "", "comment": ""},
        )
        assert resp.json()["ok"] is True

        sections = test_db.get_lesson_sections(lid)
        assert sections[0]["annotation_rating"] == ""
        assert sections[0]["annotation_comment"] == ""

    def test_invalid_rating(self, api_client, test_db):
        """不正なrating値はエラー"""
        r = api_client.post("/api/lessons", json={"name": "AnnotBad"})
        lid = r.json()["lesson"]["id"]
        sec = test_db.add_lesson_section(lid, 0, "introduction", "テスト")

        resp = api_client.put(
            f"/api/lessons/{lid}/sections/{sec['id']}/annotation",
            json={"rating": "invalid_value"},
        )
        assert resp.json()["ok"] is False


class TestVerifyAPI:
    """POST /api/lessons/{id}/verify のテスト"""

    def _setup_lesson_with_sections(self, api_client, test_db):
        """テスト用のlesson + extracted_text + セクション付きバージョンを作成"""
        r = api_client.post("/api/lessons", json={"name": "VerifyTest"})
        lid = r.json()["lesson"]["id"]

        # extracted_text を設定
        test_db.update_lesson(lid, extracted_text="変数とは値を格納する箱です。for文でループ処理を行います。")

        # セクション付きバージョンを作成
        sections = [
            {
                "section_type": "introduction",
                "title": "導入",
                "content": "今日は変数を学びます",
                "tts_text": "今日は変数を学びます",
                "display_text": "変数の学習",
                "emotion": "joy",
                "dialogues": [{"speaker": "teacher", "content": "変数を勉強しよう", "tts_text": "変数を勉強しよう", "emotion": "joy"}],
            },
            {
                "section_type": "explanation",
                "title": "変数",
                "content": "変数は値を入れる箱です",
                "tts_text": "変数は値を入れる箱です",
                "display_text": "変数 = 箱",
                "emotion": "neutral",
                "dialogues": [],
            },
        ]
        resp = api_client.post(
            f"/api/lessons/{lid}/import-sections?lang=ja&generator=claude",
            json={"sections": sections},
        )
        version_number = resp.json()["version_number"]
        return lid, version_number

    def test_verify_success(self, api_client, test_db, mock_gemini):
        """正常な整合性チェック"""
        lid, vn = self._setup_lesson_with_sections(api_client, test_db)

        # Gemini応答を設定
        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "coverage": [
                {"source_item": "変数の説明", "status": "covered", "section_index": 1, "detail": None},
                {"source_item": "for文の説明", "status": "missing", "detail": "セクションで触れていない"},
            ],
            "contradictions": [],
        })

        resp = api_client.post(f"/api/lessons/{lid}/verify", json={
            "lang": "ja", "generator": "claude", "version_number": vn,
        })
        data = resp.json()
        assert data["ok"] is True
        assert data["version_number"] == vn
        assert len(data["verify_result"]["coverage"]) == 2
        assert data["verify_result"]["coverage"][0]["status"] == "covered"
        assert data["verify_result"]["coverage"][1]["status"] == "missing"
        assert data["verify_result"]["contradictions"] == []
        # プロンプト全文が返る
        assert "prompt" in data
        assert "system" in data["prompt"]
        assert "user" in data["prompt"]
        assert "raw_output" in data

    def test_verify_saves_to_db(self, api_client, test_db, mock_gemini):
        """検証結果がDBに保存される"""
        lid, vn = self._setup_lesson_with_sections(api_client, test_db)

        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "coverage": [{"source_item": "テスト", "status": "covered", "section_index": 0, "detail": None}],
            "contradictions": [],
        })

        api_client.post(f"/api/lessons/{lid}/verify", json={
            "lang": "ja", "generator": "claude", "version_number": vn,
        })

        # DB確認
        ver = test_db.get_lesson_version(lid, "ja", "claude", vn)
        assert ver["verify_json"] != ""
        saved = json.loads(ver["verify_json"])
        assert "coverage" in saved

    def test_verify_auto_latest_version(self, api_client, test_db, mock_gemini):
        """version_number省略時は最新バージョンを使う"""
        lid, vn = self._setup_lesson_with_sections(api_client, test_db)

        mock_gemini.models.generate_content.return_value.text = json.dumps({
            "coverage": [], "contradictions": [],
        })

        resp = api_client.post(f"/api/lessons/{lid}/verify", json={
            "lang": "ja", "generator": "claude",
        })
        data = resp.json()
        assert data["ok"] is True
        assert data["version_number"] == vn

    def test_verify_not_found(self, api_client):
        """存在しないlesson"""
        resp = api_client.post("/api/lessons/9999/verify", json={
            "lang": "ja", "generator": "claude",
        })
        assert resp.json()["ok"] is False

    def test_verify_no_extracted_text(self, api_client, test_db, mock_gemini):
        """元教材テキストがない場合はエラー"""
        r = api_client.post("/api/lessons", json={"name": "NoText"})
        lid = r.json()["lesson"]["id"]
        # セクションは作るがextracted_textなし
        sections = [{
            "section_type": "introduction", "content": "x",
            "tts_text": "x", "display_text": "x",
        }]
        api_client.post(
            f"/api/lessons/{lid}/import-sections?lang=ja&generator=claude",
            json={"sections": sections},
        )

        resp = api_client.post(f"/api/lessons/{lid}/verify", json={
            "lang": "ja", "generator": "claude",
        })
        assert resp.json()["ok"] is False
        assert "元教材" in resp.json()["error"]

    def test_verify_no_sections(self, api_client, test_db, mock_gemini):
        """セクションがない場合はエラー"""
        r = api_client.post("/api/lessons", json={"name": "NoSections"})
        lid = r.json()["lesson"]["id"]
        test_db.update_lesson(lid, extracted_text="何かテキスト")
        # バージョンは作るがセクションなし
        test_db.create_lesson_version(lid, lang="ja", generator="claude")

        resp = api_client.post(f"/api/lessons/{lid}/verify", json={
            "lang": "ja", "generator": "claude",
        })
        assert resp.json()["ok"] is False

    def test_verify_version_not_found(self, api_client, test_db):
        """存在しないバージョン番号"""
        r = api_client.post("/api/lessons", json={"name": "VerNoVer"})
        lid = r.json()["lesson"]["id"]
        test_db.update_lesson(lid, extracted_text="テスト")

        resp = api_client.post(f"/api/lessons/{lid}/verify", json={
            "lang": "ja", "generator": "claude", "version_number": 99,
        })
        assert resp.json()["ok"] is False


class TestImproveAPI:
    """POST /api/lessons/{id}/improve のテスト"""

    def _setup_lesson_with_sections(self, api_client, test_db):
        """テスト用のlesson + セクション + バージョンを作成"""
        r = api_client.post("/api/lessons", json={"name": "ImproveTest"})
        lid = r.json()["lesson"]["id"]

        test_db.update_lesson(lid, extracted_text="変数は値を格納する箱。for文でループ。配列は0始まり。")

        sections = [
            {
                "section_type": "introduction",
                "title": "導入",
                "content": "プログラミングを学ぼう",
                "tts_text": "プログラミングを学ぼう",
                "display_text": "プログラミング入門",
                "emotion": "excited",
                "dialogues": [{"speaker": "teacher", "content": "始めよう", "tts_text": "始めよう", "emotion": "excited"}],
            },
            {
                "section_type": "explanation",
                "title": "変数",
                "content": "変数は箱です",
                "tts_text": "変数は箱です",
                "display_text": "変数 = 箱",
                "emotion": "neutral",
                "dialogues": [],
            },
            {
                "section_type": "summary",
                "title": "まとめ",
                "content": "今日の復習",
                "tts_text": "今日の復習",
                "display_text": "まとめ",
                "emotion": "joy",
                "dialogues": [],
            },
        ]
        resp = api_client.post(
            f"/api/lessons/{lid}/import-sections?lang=ja&generator=claude",
            json={"sections": sections},
        )
        vn = resp.json()["version_number"]
        return lid, vn

    def test_improve_success(self, api_client, test_db, mock_gemini):
        """正常な部分改善 → 新バージョン作成"""
        lid, vn = self._setup_lesson_with_sections(api_client, test_db)

        # AIの改善結果
        mock_gemini.models.generate_content.return_value.text = json.dumps([
            {
                "order_index": 1,
                "section_type": "explanation",
                "title": "変数とは",
                "content": "変数はデータを入れる箱のようなものです。ゲームのスコアを覚えるときに使います。",
                "tts_text": "変数はデータを入れる箱のようなものです",
                "display_text": "変数 = データの箱",
                "emotion": "thinking",
                "question": "",
                "answer": "",
                "wait_seconds": 5,
                "dialogues": [
                    {"speaker": "teacher", "content": "変数って知ってる？", "tts_text": "変数って知ってる？", "emotion": "thinking"},
                    {"speaker": "student", "content": "箱みたいなもの？", "tts_text": "箱みたいなもの？", "emotion": "surprise"},
                ],
                "dialogue_directions": [],
            }
        ])

        resp = api_client.post(f"/api/lessons/{lid}/improve", json={
            "source_version": vn,
            "lang": "ja",
            "generator": "claude",
            "target_sections": [1],
            "user_instructions": "変数の説明を具体例付きで短くして",
        })
        data = resp.json()
        assert data["ok"] is True
        assert data["version_number"] == vn + 1
        assert data["improved_sections"] == [1]
        assert len(data["sections"]) == 3  # 全3セクション（コピー+改善）
        # プロンプト全文
        assert "prompt" in data
        assert "raw_output" in data

    def test_improve_copies_unchanged_sections(self, api_client, test_db, mock_gemini):
        """改善対象外のセクションはソースからコピーされる"""
        lid, vn = self._setup_lesson_with_sections(api_client, test_db)

        mock_gemini.models.generate_content.return_value.text = json.dumps([
            {
                "order_index": 1,
                "section_type": "explanation",
                "title": "改善版",
                "content": "改善された内容",
                "tts_text": "改善された内容",
                "display_text": "改善",
                "emotion": "neutral",
                "dialogues": [],
                "dialogue_directions": [],
            }
        ])

        resp = api_client.post(f"/api/lessons/{lid}/improve", json={
            "source_version": vn, "lang": "ja", "generator": "claude",
            "target_sections": [1],
        })
        new_vn = resp.json()["version_number"]

        # 新バージョンのセクションを確認
        new_sections = test_db.get_lesson_sections(lid, lang="ja", generator="claude",
                                                    version_number=new_vn)
        assert len(new_sections) == 3
        # sec0（導入）はコピー
        assert new_sections[0]["content"] == "プログラミングを学ぼう"
        # sec1（変数）は改善済み
        assert new_sections[1]["content"] == "改善された内容"
        # sec2（まとめ）はコピー
        assert new_sections[2]["content"] == "今日の復習"

    def test_improve_version_metadata(self, api_client, test_db, mock_gemini):
        """改善で作成されたバージョンにメタ情報が入る"""
        lid, vn = self._setup_lesson_with_sections(api_client, test_db)

        mock_gemini.models.generate_content.return_value.text = json.dumps([
            {
                "order_index": 1, "section_type": "explanation", "title": "x",
                "content": "x", "tts_text": "x", "display_text": "x",
                "emotion": "neutral", "dialogues": [], "dialogue_directions": [],
            }
        ])

        resp = api_client.post(f"/api/lessons/{lid}/improve", json={
            "source_version": vn, "lang": "ja", "generator": "claude",
            "target_sections": [1],
            "user_instructions": "短くして",
        })
        new_vn = resp.json()["version_number"]

        ver = test_db.get_lesson_version(lid, "ja", "claude", new_vn)
        assert ver["improve_source_version"] == vn
        assert ver["improve_summary"] == "短くして"
        assert json.loads(ver["improved_sections"]) == [1]

    def test_improve_not_found(self, api_client):
        """存在しないlesson"""
        resp = api_client.post("/api/lessons/9999/improve", json={
            "source_version": 1, "target_sections": [0],
        })
        assert resp.json()["ok"] is False

    def test_improve_empty_targets(self, api_client, test_db):
        """target_sectionsが空"""
        r = api_client.post("/api/lessons", json={"name": "EmptyTarget"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.post(f"/api/lessons/{lid}/improve", json={
            "source_version": 1, "target_sections": [],
        })
        assert resp.json()["ok"] is False

    def test_improve_source_version_not_found(self, api_client, test_db):
        """存在しないソースバージョン"""
        r = api_client.post("/api/lessons", json={"name": "NoSrcVer"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.post(f"/api/lessons/{lid}/improve", json={
            "source_version": 99, "target_sections": [0],
        })
        assert resp.json()["ok"] is False

    def test_improve_invalid_target_index(self, api_client, test_db, mock_gemini):
        """存在しないorder_indexを指定"""
        lid, vn = self._setup_lesson_with_sections(api_client, test_db)
        resp = api_client.post(f"/api/lessons/{lid}/improve", json={
            "source_version": vn, "lang": "ja", "generator": "claude",
            "target_sections": [99],
        })
        data = resp.json()
        assert data["ok"] is False
        assert "99" in str(data["error"])

    def test_improve_with_verify_result(self, api_client, test_db, mock_gemini):
        """verify_resultを渡して改善"""
        lid, vn = self._setup_lesson_with_sections(api_client, test_db)

        mock_gemini.models.generate_content.return_value.text = json.dumps([
            {
                "order_index": 1, "section_type": "explanation", "title": "変数改善",
                "content": "改善済み", "tts_text": "改善済み", "display_text": "改善",
                "emotion": "neutral", "dialogues": [], "dialogue_directions": [],
            }
        ])

        verify = {
            "coverage": [
                {"source_item": "for文", "status": "missing", "detail": "未カバー"},
            ],
            "contradictions": [],
        }
        resp = api_client.post(f"/api/lessons/{lid}/improve", json={
            "source_version": vn, "lang": "ja", "generator": "claude",
            "target_sections": [1],
            "verify_result": verify,
        })
        assert resp.json()["ok"] is True

    def test_improve_copies_plan(self, api_client, test_db, mock_gemini):
        """改善時にプランもコピーされる"""
        lid, vn = self._setup_lesson_with_sections(api_client, test_db)

        # ソースバージョンにプランを追加
        test_db.upsert_lesson_plan(lid, "ja", knowledge="テスト知識",
                                    generator="claude", version_number=vn)

        mock_gemini.models.generate_content.return_value.text = json.dumps([
            {
                "order_index": 0, "section_type": "introduction", "title": "改善導入",
                "content": "改善", "tts_text": "改善", "display_text": "改善",
                "emotion": "neutral", "dialogues": [], "dialogue_directions": [],
            }
        ])

        resp = api_client.post(f"/api/lessons/{lid}/improve", json={
            "source_version": vn, "lang": "ja", "generator": "claude",
            "target_sections": [0],
        })
        new_vn = resp.json()["version_number"]

        plan = test_db.get_lesson_plan(lid, "ja", generator="claude", version_number=new_vn)
        assert plan is not None
        assert plan["knowledge"] == "テスト知識"


class TestLoadLearnings:
    """学習結果注入のテスト"""

    def test_load_empty(self, tmp_path, monkeypatch):
        """学習ファイルがない場合は空文字列"""
        from src.lesson_generator import improver
        monkeypatch.setattr(improver, "LEARNINGS_DIR", tmp_path / "learnings")
        result = improver.load_learnings("test_category")
        assert result == ""

    def test_load_common_only(self, tmp_path, monkeypatch):
        """共通学習のみ"""
        from src.lesson_generator import improver
        learnings_dir = tmp_path / "learnings"
        learnings_dir.mkdir()
        (learnings_dir / "_common.md").write_text("共通パターン", encoding="utf-8")
        monkeypatch.setattr(improver, "LEARNINGS_DIR", learnings_dir)

        result = improver.load_learnings("nonexistent")
        assert "共通パターン" in result

    def test_load_category_and_common(self, tmp_path, monkeypatch):
        """カテゴリ別 + 共通"""
        from src.lesson_generator import improver
        learnings_dir = tmp_path / "learnings"
        learnings_dir.mkdir()
        (learnings_dir / "_common.md").write_text("共通", encoding="utf-8")
        (learnings_dir / "python.md").write_text("Python学習", encoding="utf-8")
        monkeypatch.setattr(improver, "LEARNINGS_DIR", learnings_dir)

        result = improver.load_learnings("python")
        assert "共通" in result
        assert "Python学習" in result
