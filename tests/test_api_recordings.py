"""録画ファイル管理APIのテスト（Phase 5: アップロード受信 + 一覧 + DL + 削除）"""


def _videos_dir(tmp_path, monkeypatch):
    import scripts.routes.recordings as rec_mod
    videos = tmp_path / "videos"
    videos.mkdir()
    monkeypatch.setattr(rec_mod, "VIDEOS_DIR", videos)
    return videos


def test_recordings_list_empty(api_client, tmp_path, monkeypatch):
    _videos_dir(tmp_path, monkeypatch)
    resp = api_client.get("/api/recordings")
    assert resp.status_code == 200
    assert resp.json()["recordings"] == []


def test_recordings_list_sorted(api_client, tmp_path, monkeypatch):
    videos = _videos_dir(tmp_path, monkeypatch)
    import time
    (videos / "broadcast_20260419_100000.mp4").write_bytes(b"aaa")
    time.sleep(0.02)
    (videos / "broadcast_20260419_200000.mp4").write_bytes(b"bbbb")
    resp = api_client.get("/api/recordings")
    items = resp.json()["recordings"]
    assert len(items) == 2
    # 新しい順
    assert items[0]["filename"] == "broadcast_20260419_200000.mp4"
    assert items[0]["size_bytes"] == 4
    assert items[1]["filename"] == "broadcast_20260419_100000.mp4"


def test_recordings_upload(api_client, tmp_path, monkeypatch):
    videos = _videos_dir(tmp_path, monkeypatch)
    body = b"\x00\x00\x00\x1cftypisom" + b"x" * 100
    resp = api_client.post(
        "/api/recordings/upload",
        headers={"X-Filename": "broadcast_20260419_150000.mp4"},
        content=body,
    )
    assert resp.status_code == 200, resp.text
    j = resp.json()
    assert j["ok"] is True
    assert j["filename"] == "broadcast_20260419_150000.mp4"
    assert j["size"] == len(body)
    saved = videos / "broadcast_20260419_150000.mp4"
    assert saved.exists()
    assert saved.read_bytes() == body
    # partファイルは残っていない
    assert list(videos.glob(".*.part")) == []


def test_recordings_upload_invalid_filename(api_client, tmp_path, monkeypatch):
    _videos_dir(tmp_path, monkeypatch)
    for bad in [
        "../etc/passwd",
        "foo/bar.mp4",
        "foo\\bar.mp4",
        "noext",
        "foo.exe",
        "",
    ]:
        resp = api_client.post(
            "/api/recordings/upload",
            headers={"X-Filename": bad},
            content=b"data",
        )
        assert resp.status_code in (400, 422), f"should reject {bad!r}: {resp.status_code}"


def test_recordings_delete(api_client, tmp_path, monkeypatch):
    videos = _videos_dir(tmp_path, monkeypatch)
    path = videos / "broadcast_20260419_150000.mp4"
    path.write_bytes(b"data")
    resp = api_client.delete("/api/recordings/broadcast_20260419_150000.mp4")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert not path.exists()


def test_recordings_delete_not_found(api_client, tmp_path, monkeypatch):
    _videos_dir(tmp_path, monkeypatch)
    resp = api_client.delete("/api/recordings/missing.mp4")
    assert resp.status_code == 404


def test_recordings_delete_traversal(api_client, tmp_path, monkeypatch):
    _videos_dir(tmp_path, monkeypatch)
    resp = api_client.delete("/api/recordings/..%2Fetc%2Fpasswd")
    assert resp.status_code in (400, 404)


def test_recordings_download(api_client, tmp_path, monkeypatch):
    videos = _videos_dir(tmp_path, monkeypatch)
    content = b"MP4_CONTENT" * 10
    (videos / "broadcast_20260419_150000.mp4").write_bytes(content)
    resp = api_client.get("/api/recordings/broadcast_20260419_150000.mp4/download")
    assert resp.status_code == 200
    assert resp.content == content
    assert resp.headers["content-type"] == "video/mp4"
    assert "attachment" in resp.headers.get("content-disposition", "").lower()


def test_recordings_download_not_found(api_client, tmp_path, monkeypatch):
    _videos_dir(tmp_path, monkeypatch)
    resp = api_client.get("/api/recordings/missing.mp4/download")
    assert resp.status_code == 404
