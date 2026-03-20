"""WebUIチャットAPIのテスト"""

from unittest.mock import AsyncMock


def test_chat_webui_sends_message(api_client, monkeypatch):
    """POST /api/chat/webui がreader.respond_webuiを呼ぶ"""
    import scripts.state as st

    mock_result = {"speech": "テスト応答", "emotion": "neutral", "english": "test"}
    st.reader.respond_webui = AsyncMock(return_value=mock_result)
    st.ensure_reader = AsyncMock()

    res = api_client.post("/api/chat/webui", json={"message": "こんにちは"})
    assert res.status_code == 200
    data = res.json()
    assert data["speech"] == "テスト応答"
    st.reader.respond_webui.assert_called_once_with("こんにちは")


def test_chat_webui_empty_message(api_client, monkeypatch):
    """空メッセージでもエラーにならない"""
    import scripts.state as st

    mock_result = {"speech": "", "emotion": "neutral", "english": ""}
    st.reader.respond_webui = AsyncMock(return_value=mock_result)
    st.ensure_reader = AsyncMock()

    res = api_client.post("/api/chat/webui", json={"message": ""})
    assert res.status_code == 200


def test_chat_webui_ensures_reader(api_client, monkeypatch):
    """ensure_readerが呼ばれることを確認"""
    import scripts.state as st

    mock_result = {"speech": "応答", "emotion": "neutral", "english": ""}
    st.reader.respond_webui = AsyncMock(return_value=mock_result)
    st.ensure_reader = AsyncMock()

    api_client.post("/api/chat/webui", json={"message": "テスト"})
    st.ensure_reader.assert_called_once()
