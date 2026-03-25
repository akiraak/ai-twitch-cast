# 二人会話デモ（Debugタブ）

## ステータス: 完了

## ゴール

Debugタブに、先生（ちょビ）と生徒（まなび）が掛け合い会話するデモ機能を追加する。
ユーザーが「〇〇について会話して」とテーマを入力→4往復（8発話）の会話を生成→順次再生。

## 背景

- `speak_event()` は `avatar_id` パラメータをサポート済み
- broadcast.html のWebSocketは `avatar_id` で字幕・リップシンク・感情を振り分け済み
- 二人のアバターが実際に会話する統合テストがない
- Step 3（対話スクリプト）/Step 4（対話再生）の検証にも使える

## 仕様

### UI（Debugタブ）

既存カード（スクショ）の上に「会話デモ」カードを追加:

```
┌─ 会話デモ ──────────────────────────┐
│ [__テーマ入力______________] [会話スタート] │
│ ステータス: まなびが話し中... (4/8)       │
└─────────────────────────────────────┘
```

- テーマ入力欄（placeholder: 「好きな食べ物」「最近ハマってること」等）
- 「会話スタート」ボタン（実行中は無効化）
- ステータス行（進捗表示）

### 会話フロー

1. テーマを `POST /api/debug/conversation-demo` に送信
2. サーバー側でLLMに対話スクリプトを生成させる（4往復=8発話）
   - DBから先生・生徒のキャラ設定（性格・感情）を取得
   - `rules` はシーン依存なので含めない（`_format_character_for_prompt` を流用）
   - JSON配列: `[{speaker, content, tts_text, emotion}, ...]`
3. 各発話を順次再生
   - `speak_event()` で `avatar_id="teacher"` / `"student"` を指定
   - voice/style はDBのキャラ設定から取得
   - 字幕の `author` はキャラ名（「ちょビ」「まなび」）
   - 1発話完了を待ってから次へ（SpeechPipelineのロックで自然に順次実行）
4. 全発話完了後、ステータスを「完了」に

## 変更対象

| ファイル | 変更内容 |
|---------|---------|
| `static/index.html` | Debugタブに会話デモカード追加 |
| `static/js/admin/debug.js` | `conversationDemo()` 関数追加 |
| `scripts/routes/avatar.py` | `POST /api/debug/conversation-demo` エンドポイント |

## 実装

### 1. APIエンドポイント（`scripts/routes/avatar.py`）

```python
class ConversationDemoRequest(BaseModel):
    topic: str

@router.post("/api/debug/conversation-demo")
async def conversation_demo(body: ConversationDemoRequest):
```

処理:
1. `get_lesson_characters()` で先生・生徒設定を取得
2. LLM呼び出し — 両キャラの性格＋テーマで4往復の対話を生成
   - `_format_character_for_prompt()` を流用
   - プロンプト: 「以下の2人のキャラクターが〇〇について4往復の雑談をします。JSON配列で出力」
   - 出力: `[{speaker: "teacher"|"student", content, tts_text, emotion}]`
3. 各発話を順次 `speak_event()` で再生
   - speaker に応じて avatar_id / voice / style を切り替え
   - voice/style はキャラ config の `tts_voice` / `tts_style` を使用
4. レスポンスは即座に返す（再生はバックグラウンド）

```python
# LLMプロンプトイメージ
prompt = f"""以下の2人のキャラクターが「{topic}」について会話します。
4往復（8発話）の自然な雑談を生成してください。

{teacher_desc}
{student_desc}

出力形式（JSON配列のみ）:
[{{"speaker": "teacher", "content": "...", "tts_text": "...", "emotion": "..."}}]
"""
```

### 2. UI（`static/index.html`）

スクショカードの前に挿入:

```html
<div class="card">
  <h2>会話デモ</h2>
  <p style="font-size:0.75rem; color:#9a88b5; margin-bottom:8px;">
    テーマを入力すると先生と生徒が4往復の会話をします
  </p>
  <div style="display:flex; gap:8px; align-items:center;">
    <input type="text" id="conv-demo-topic" placeholder="好きな食べ物"
           style="flex:1; padding:6px 10px; ...">
    <button onclick="conversationDemo()" id="btn-conv-demo"
            style="...">会話スタート</button>
  </div>
  <div class="status" id="conv-demo-status" style="margin-top:6px; font-size:0.75rem;"></div>
</div>
```

### 3. JS（`static/js/admin/debug.js`）

```javascript
async function conversationDemo() {
  const topic = document.getElementById('conv-demo-topic').value.trim();
  if (!topic) return;
  const btn = document.getElementById('btn-conv-demo');
  const status = document.getElementById('conv-demo-status');
  btn.disabled = true;
  status.textContent = '会話生成・再生中...';
  try {
    const res = await api('POST', '/api/debug/conversation-demo', { topic });
    status.textContent = res.ok ? '完了' : `エラー: ${res.error}`;
  } catch (e) {
    status.textContent = `エラー: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}
```

**注意**: 再生はサーバー側バックグラウンドなので、APIレスポンスは再生完了を待つ。
ボタン無効化で多重実行を防止。

## 完了条件

- [ ] Debugタブに会話デモカードがある
- [ ] テーマを入力して「会話スタート」→ 先生と生徒が4往復の会話をする
- [ ] 各キャラの声（voice/style）・感情・アバターアニメーションが正しく動作する
- [ ] broadcast.html で字幕・リップシンクが話者別に表示される
