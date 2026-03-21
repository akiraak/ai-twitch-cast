"""SE APIエンドポイントのテスト"""

import shutil
from pathlib import Path


def _se_dir():
    return Path(__file__).resolve().parent.parent / "resources" / "audio" / "se"


def test_se_list_empty(api_client, test_db, tmp_path, monkeypatch):
    """SE一覧: ファイルがない場合は空リスト"""
    import scripts.routes.se as se_mod
    monkeypatch.setattr(se_mod, "SE_DIR", tmp_path / "se")
    (tmp_path / "se").mkdir()
    resp = api_client.get("/api/se/list")
    assert resp.status_code == 200
    assert resp.json()["tracks"] == []


def test_se_list_with_files(api_client, test_db, tmp_path, monkeypatch):
    """SE一覧: ファイルがある場合"""
    import scripts.routes.se as se_mod
    se_dir = tmp_path / "se"
    se_dir.mkdir()
    monkeypatch.setattr(se_mod, "SE_DIR", se_dir)

    # テスト用WAVファイルを作成
    import struct, wave
    wav_path = se_dir / "test.wav"
    with wave.open(str(wav_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(struct.pack("<h", 0) * 24000)

    test_db.upsert_se_track("test.wav", category="test", description="テスト", volume=0.9, duration=1.0)

    resp = api_client.get("/api/se/list")
    assert resp.status_code == 200
    tracks = resp.json()["tracks"]
    assert len(tracks) == 1
    assert tracks[0]["file"] == "test.wav"
    assert tracks[0]["category"] == "test"
    assert tracks[0]["volume"] == 0.9


def test_se_play(api_client, test_db, tmp_path, monkeypatch):
    """SE再生テスト"""
    import scripts.routes.se as se_mod
    se_dir = tmp_path / "se"
    se_dir.mkdir()
    monkeypatch.setattr(se_mod, "SE_DIR", se_dir)

    # ダミーファイル
    (se_dir / "test.wav").write_bytes(b"dummy")
    test_db.upsert_se_track("test.wav", category="test", volume=1.0, duration=0.5)

    resp = api_client.post("/api/se/play", json={"file": "test.wav"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_se_play_not_found(api_client, test_db, tmp_path, monkeypatch):
    """SE再生: ファイルが見つからない場合"""
    import scripts.routes.se as se_mod
    se_dir = tmp_path / "se"
    se_dir.mkdir()
    monkeypatch.setattr(se_mod, "SE_DIR", se_dir)

    resp = api_client.post("/api/se/play", json={"file": "missing.wav"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


def test_se_track_update(api_client, test_db, tmp_path, monkeypatch):
    """SEトラック情報更新"""
    import scripts.routes.se as se_mod
    se_dir = tmp_path / "se"
    se_dir.mkdir()
    monkeypatch.setattr(se_mod, "SE_DIR", se_dir)

    # WAVファイル作成
    import struct, wave
    wav_path = se_dir / "test.wav"
    with wave.open(str(wav_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(struct.pack("<h", 0) * 12000)

    resp = api_client.post("/api/se/track", json={
        "file": "test.wav",
        "category": "greeting",
        "description": "挨拶音",
        "volume": 0.7,
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    tracks = test_db.get_all_se_tracks()
    assert "test.wav" in tracks
    assert tracks["test.wav"]["category"] == "greeting"
    assert tracks["test.wav"]["volume"] == 0.7


def test_se_track_delete(api_client, test_db, tmp_path, monkeypatch):
    """SEトラック削除"""
    import scripts.routes.se as se_mod
    se_dir = tmp_path / "se"
    se_dir.mkdir()
    monkeypatch.setattr(se_mod, "SE_DIR", se_dir)

    (se_dir / "delete_me.wav").write_bytes(b"dummy")
    test_db.upsert_se_track("delete_me.wav", category="test")

    resp = api_client.delete("/api/se/track?file=delete_me.wav")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert not (se_dir / "delete_me.wav").exists()
    assert "delete_me.wav" not in test_db.get_all_se_tracks()
