# Step 2: WebSocket アバター制御

## ステータス: 未着手

## ゴール

**2体のアバターを独立して制御できるようにする。** リップシンク・感情BlendShape・ジェスチャーが `avatar_id` で振り分けられ、先生が喋っているとき生徒の口は動かない（逆も然り）。

```
サーバー → WebSocket → {type:"lipsync", avatar_id:"student", frames:[...]}
                                ↓
                     avatarInstances["student"].setLipsync(frames)
```

## 変更対象

| ファイル | 変更内容 |
|---------|---------|
| `static/js/broadcast/websocket.js` | avatar_id に基づくルーティング |
| `src/speech_pipeline.py` | イベントに avatar_id フィールド追加 |
| `static/js/broadcast/panels.js` | 字幕に話者名・色分け |
| `static/css/broadcast.css` | 生徒字幕のスタイル |

## 前提

- Step 1（マルチアバター表示）完了済み

## 実装

### 2-1. websocket.js — ルーティング

ヘルパー関数:
```javascript
function getAvatar(avatarId) {
  if (window.avatarInstances) {
    return window.avatarInstances[avatarId || 'teacher'];
  }
  return window.avatarVRM;  // Step 1未適用時のフォールバック
}
```

各イベントハンドラの変更:
```javascript
case 'blendshape': {
  const avatar = getAvatar(data.avatar_id);
  if (avatar && data.shapes) avatar.setBlendShapes(data.shapes);
  if (avatar && data.gesture) avatar.playGesture(data.gesture);
  break;
}
case 'lipsync': {
  const avatar = getAvatar(data.avatar_id);
  if (avatar && data.frames) {
    avatar.setLipsync(data.frames);
    if (data.autostart) avatar.startLipsync();
  }
  break;
}
case 'lipsync_stop': {
  const avatar = getAvatar(data.avatar_id);
  if (avatar) avatar.stopLipsync();
  break;
}
```

### 2-2. 生徒アバター表示/非表示イベント

```javascript
case 'student_avatar_show': {
  const area = document.getElementById('avatar-area-2');
  if (area) area.style.display = 'block';
  const student = window.avatarInstances?.['student'];
  if (student && data.vrm) {
    student.loadVRM(`/resources/vrm/${data.vrm}`);
  }
  break;
}
case 'student_avatar_hide': {
  const area = document.getElementById('avatar-area-2');
  if (area) area.style.display = 'none';
  break;
}
```

### 2-3. speech_pipeline.py — avatar_id 付与

`apply_emotion()`:
```python
def apply_emotion(self, emotion, gesture=None, avatar_id=None):
    char = get_character()
    blendshapes = char.get("emotion_blendshapes", {}).get(emotion, {})
    if self._on_overlay and blendshapes:
        event = {"type": "blendshape", "shapes": blendshapes}
        if avatar_id:
            event["avatar_id"] = avatar_id
        if gesture:
            event["gesture"] = gesture
        asyncio.create_task(self._on_overlay(event))
```

`_speak_impl()` 内のリップシンク:
```python
# avatar_id パラメータを speak() → _speak_impl() に伝搬
if lipsync_frames:
    event = {"type": "lipsync", "frames": lipsync_frames, "autostart": True}
    if avatar_id:
        event["avatar_id"] = avatar_id
    await self._on_overlay(event)

# ...

if lipsync_frames:
    event = {"type": "lipsync_stop"}
    if avatar_id:
        event["avatar_id"] = avatar_id
    await self._on_overlay(event)
```

`notify_overlay()` にも avatar_id:
```python
async def notify_overlay(self, author, trigger_text, result, avatar_id=None):
    event = {
        "type": "comment",
        "author": author,
        "trigger_text": trigger_text,
        "speech": self.strip_lang_tags(result["speech"]),
        "translation": result.get("translation", ""),
        "emotion": result["emotion"],
    }
    if avatar_id:
        event["avatar_id"] = avatar_id
    await self._on_overlay(event)
```

### 2-4. 字幕の話者色分け

`panels.js`:
```javascript
// comment イベント受信時
const subtitle = document.getElementById('subtitle');
subtitle.dataset.speaker = data.avatar_id || 'teacher';
```

`broadcast.css`:
```css
#subtitle[data-speaker="student"] .author {
  color: #ff88aa;
}
```

### 2-5. 動作確認方法

1. サーバー起動 → `/broadcast` を開く
2. DevToolsコンソールで生徒アバターを表示:
   ```javascript
   document.getElementById('avatar-area-2').style.display = 'block';
   window.avatarInstances['student'].loadVRM('/resources/vrm/Shinano.vrm');
   ```
3. `/api/avatar/speak` でちょビに喋らせる → 先生のみリップシンク、生徒は動かない
4. Python側から直接テスト:
   ```python
   # avatar_id="student" でイベント送信 → 生徒のみリップシンク
   await on_overlay({"type": "blendshape", "shapes": {"happy": 1.0}, "avatar_id": "student"})
   ```

## 完了条件

- [ ] `avatar_id` ありイベントが正しいアバターにルーティングされる
- [ ] `avatar_id` なしイベントは teacher にフォールバック（後方互換）
- [ ] `student_avatar_show` / `student_avatar_hide` が動作する
- [ ] 字幕に `data-speaker` 属性が設定され、生徒は色が変わる
- [ ] 既存のコメント応答（授業モード外）が影響を受けない
