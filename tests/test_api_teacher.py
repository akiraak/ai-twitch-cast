"""教師モードAPIのテスト"""

from unittest.mock import AsyncMock, patch


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

    def test_generate_script(self, api_client, test_db, mock_gemini):
        """スクリプト生成（Gemini APIモック）"""
        r = api_client.post("/api/lessons", json={"name": "GenTest"})
        lid = r.json()["lesson"]["id"]
        # 抽出テキストを設定
        test_db.update_lesson(lid, extracted_text="Present tense: He goes to school.")

        # Geminiの応答をモック
        mock_gemini.models.generate_content.return_value.text = """[
            {"section_type": "introduction", "content": "導入", "tts_text": "導入TTS",
             "display_text": "導入画面", "emotion": "excited", "question": "", "answer": "", "wait_seconds": 0},
            {"section_type": "explanation", "content": "説明", "tts_text": "説明TTS",
             "display_text": "説明画面", "emotion": "neutral", "question": "", "answer": "", "wait_seconds": 0}
        ]"""

        resp = api_client.post(f"/api/lessons/{lid}/generate-script")
        data = resp.json()
        assert data["ok"] is True
        assert len(data["sections"]) == 2
        assert data["sections"][0]["section_type"] == "introduction"

    def test_generate_script_no_text(self, api_client):
        """テキストなしでのスクリプト生成はエラー"""
        r = api_client.post("/api/lessons", json={"name": "Empty"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.post(f"/api/lessons/{lid}/generate-script")
        assert resp.json()["ok"] is False
