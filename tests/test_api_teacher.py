"""教師モードAPIのテスト"""

import asyncio

from unittest.mock import AsyncMock, MagicMock, patch


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


class TestLessonPlan:
    def test_generate_plan(self, api_client, test_db, mock_gemini):
        """三者視点プラン生成"""
        r = api_client.post("/api/lessons", json={"name": "PlanTest"})
        lid = r.json()["lesson"]["id"]
        test_db.update_lesson(lid, extracted_text="Python asyncio basics")

        # Geminiの応答を段階的にモック（3回呼ばれる）
        mock_gemini.models.generate_content.side_effect = [
            # 1回目: 知識先生
            MagicMock(text="### 要点\n- asyncioの基本\n- イベントループ\n### 推奨構成\n導入→説明→まとめ"),
            # 2回目: エンタメ先生
            MagicMock(text="### 起承転結\n【起】驚きの事実\n【承】展開\n【転】実は…\n【結】オチ"),
            # 3回目: 校長先生（JSON）
            MagicMock(text="""[
                {"section_type": "introduction", "title": "導入", "summary": "興味を引く", "emotion": "excited", "has_question": false},
                {"section_type": "explanation", "title": "説明", "summary": "基本概念", "emotion": "thinking", "has_question": false},
                {"section_type": "question", "title": "クイズ", "summary": "理解確認", "emotion": "joy", "has_question": true},
                {"section_type": "summary", "title": "まとめ", "summary": "オチ", "emotion": "excited", "has_question": false}
            ]"""),
        ]

        resp = api_client.post(f"/api/lessons/{lid}/generate-plan")
        data = resp.json()
        assert data["ok"] is True
        assert "knowledge" in data
        assert "entertainment" in data
        assert len(data["plan_sections"]) == 4
        assert data["plan_sections"][0]["section_type"] == "introduction"
        assert data["plan_sections"][2]["has_question"] is True

        # DBに保存されていることを確認
        lesson = test_db.get_lesson(lid)
        assert lesson["plan_knowledge"] != ""
        assert lesson["plan_entertainment"] != ""
        assert lesson["plan_json"] != ""

    def test_generate_plan_no_text(self, api_client):
        """テキストなしでのプラン生成はエラー"""
        r = api_client.post("/api/lessons", json={"name": "NoText"})
        lid = r.json()["lesson"]["id"]
        resp = api_client.post(f"/api/lessons/{lid}/generate-plan")
        assert resp.json()["ok"] is False

    def test_generate_plan_not_found(self, api_client):
        """存在しないコンテンツのプラン生成"""
        resp = api_client.post("/api/lessons/9999/generate-plan")
        assert resp.json()["ok"] is False

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

    def test_generate_script_uses_plan(self, api_client, test_db, mock_gemini):
        """プランがある場合、スクリプト生成がプランに基づく"""
        import json
        r = api_client.post("/api/lessons", json={"name": "PlanScript"})
        lid = r.json()["lesson"]["id"]
        test_db.update_lesson(
            lid,
            extracted_text="Test content",
            plan_json=json.dumps([
                {"section_type": "introduction", "title": "導入", "summary": "テスト", "emotion": "excited", "has_question": False},
            ]),
        )

        mock_gemini.models.generate_content.return_value.text = """[
            {"section_type": "introduction", "content": "プランベース導入", "tts_text": "TTS",
             "display_text": "画面", "emotion": "excited", "question": "", "answer": "", "wait_seconds": 0}
        ]"""

        resp = api_client.post(f"/api/lessons/{lid}/generate-script")
        data = resp.json()
        assert data["ok"] is True
        assert len(data["sections"]) == 1
        assert data["sections"][0]["content"] == "プランベース導入"


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
        # セクション追加
        test_db.add_lesson_section(lid, 0, "introduction", "はじめに")
        test_db.add_lesson_section(lid, 1, "explanation", "説明")

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
