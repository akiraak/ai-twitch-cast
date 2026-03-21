# プレビューウィンドウ チャット欄追加プラン

## 背景

preview.htmlのコントロールパネルに「チャット（準備中）」セクションが既にある。
ここにチャット表示＋コメント入力欄を実装し、WebUIからアバターと会話できるようにする。

## 要件

- preview.htmlの右パネル「チャット」セクションにチャット表示＋入力欄を追加
- 書き込むとAIが応答（フルパイプライン: AI応答 → 感情 → TTS → 字幕 → DB保存）
- **返答はプレビューのチャット欄にのみ表示**（Twitchチャットには投稿しない）
- 配信中・未配信中を問わず動作する

## 実装ステップ

### Step 1: バックエンド - APIエンドポイント追加

**ファイル**: `scripts/routes/avatar.py`

```python
class WebUIChatRequest(BaseModel):
    message: str

@router.post("/api/chat/webui")
async def chat_webui(body: WebUIChatRequest):
    """WebUIからアバターに会話を送る（AI応答 → TTS → 字幕、Twitch投稿なし）"""
    await state.ensure_reader()
    result = await state.reader.respond_webui(body.message)
    return result  # {response, emotion, english}
```

- レスポンスにAI応答を返す（チャット欄に表示するため）
- `ensure_reader()` で未起動時も自動起動

### Step 2: CommentReaderに公開メソッド追加

**ファイル**: `src/comment_reader.py`

```python
async def respond_webui(self, message):
    """WebUIからの会話に応答する（Twitch投稿なし）"""
    author = "WebUI"
    user = await asyncio.to_thread(db.get_or_create_user, author)
    result = await self._generate_ai_response(author, message, user["comment_count"])
    await self._save_to_db(user, message, result)
    await asyncio.to_thread(db.update_user_last_seen, user["id"])
    self._speech.apply_emotion(result["emotion"])
    await self._speech.speak(result["response"], subtitle={
        "author": author, "message": message, "result": result,
    }, tts_text=result.get("tts_text"))
    # post_to_chat を渡さない → Twitch投稿なし
    self._speech.apply_emotion("neutral")
    await self._speech.notify_overlay_end()
    return result
```

- `_respond()` とほぼ同じだが `post_to_chat` を渡さない
- レスポンスを返す（APIで結果をクライアントに返すため）

### Step 3: preview.html - チャットUI実装

**ファイル**: `static/preview.html`

既存の `#chat-section`（L238-241）を置き換え:

```html
<div class="panel-section" id="chat-section">
  <h3>チャット</h3>
  <div id="chat-messages"></div>
  <div class="chat-input-area">
    <input type="text" id="chat-input" placeholder="メッセージを入力..."
           onkeydown="if(event.key==='Enter'&&!this.disabled)sendChat()">
    <button id="chat-send-btn" onclick="sendChat()">送信</button>
  </div>
</div>
```

### Step 4: preview.html - CSS追加

```css
#chat-messages {
  height: 200px;
  overflow-y: auto;
  margin-bottom: 8px;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.chat-msg-user {
  color: #999;
}
.chat-msg-user .chat-name { color: #7c4dff; font-weight: 600; }
.chat-msg-ai {
  color: #e0e0e0;
  padding-left: 8px;
  border-left: 2px solid #7c4dff;
}
.chat-input-area {
  display: flex;
  gap: 4px;
}
#chat-input {
  flex: 1;
  padding: 6px 8px;
  border: 1px solid #555;
  border-radius: 4px;
  background: #1a1a2e;
  color: #eee;
  font-size: 12px;
}
#chat-send-btn {
  padding: 6px 12px;
  background: #7c4dff;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
#chat-send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
```

### Step 5: preview.html - JavaScript

```javascript
async function sendChat() {
  const input = document.getElementById('chat-input');
  const btn = document.getElementById('chat-send-btn');
  const msg = input.value.trim();
  if (!msg) return;

  // UI: 送信中は無効化
  input.disabled = true;
  btn.disabled = true;
  input.value = '';

  // ユーザーメッセージを即表示
  appendChat('WebUI', msg);

  try {
    const res = await fetch('/api/chat/webui', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    });
    const data = await res.json();
    if (data.response) {
      appendChat(null, data.response);  // AI応答
    }
  } catch (e) {
    appendChat(null, '(エラー: ' + e.message + ')');
  } finally {
    input.disabled = false;
    btn.disabled = false;
    input.focus();
  }
}

function appendChat(author, text) {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  if (author) {
    div.className = 'chat-msg-user';
    div.innerHTML = '<span class="chat-name">' + author + '</span> ' + escapeHtml(text);
  } else {
    div.className = 'chat-msg-ai';
    div.textContent = text;
  }
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
```

### Step 6: テスト追加

**ファイル**: `tests/test_api_chat.py`（新規）

- `POST /api/chat/webui` が200を返すこと
- reader.respond_webuiが呼ばれること（モック）

## ファイル変更一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/comment_reader.py` | `respond_webui()` 公開メソッド追加 |
| `scripts/routes/avatar.py` | `POST /api/chat/webui` エンドポイント追加 |
| `static/preview.html` | チャットセクションにUI実装（HTML+CSS+JS） |
| `tests/test_api_chat.py` | APIテスト追加（新規） |

## 注意点

- APIは同期的にレスポンスを返す（`await`で応答完了まで待つ）。TTS再生中はレスポンスが遅れるが、送信ボタン無効化で二重送信を防止
- `ensure_reader()` により未配信時でもReaderが起動する。ただしTwitchチャット接続がない場合もエラーにならないこと要確認

## ステータス: 未着手
