# C2: 字幕のみチャンク分割表示（TTSは1つ）

## ステータス: 完了

## 概要

TTSは長文のまま1つの音声として生成し、字幕表示だけを時間ベースでチャンク分割切り替えする。音声の自然さを維持しつつ、字幕パネルが教材コンテンツを覆い隠す問題を防ぐ。

## 背景

- 親プラン: [plans/subtitle-overflow-fix.md](subtitle-overflow-fix.md)（案C2）
- 授業モードで長いセリフ（display_text読み上げ等）が字幕パネルを巨大化させ、教材テキストを覆い隠す
- TTSを分割すると音声品質が低下するため、字幕表示のみを分割する

## 方針

1. **バックエンド**: `notify_overlay` で `duration`（音声秒数）を字幕イベントに含めて送信
2. **フロントエンド**: `showSubtitle()` で長文テキストを検出し、チャンク分割 → タイマーで順次切り替え

## 実装ステップ

### Step 1: バックエンドに `duration` を渡す

**ファイル**: `src/speech_pipeline.py`

`notify_overlay()` に `duration` 引数を追加し、`comment` イベントに含める。

```python
# notify_overlay: duration引数追加
async def notify_overlay(self, author, trigger_text, result, avatar_id="teacher", duration=None):
    ...
    payload = {
        "type": "comment",
        "author": author,
        "trigger_text": trigger_text,
        "speech": stripped_speech,
        "translation": result.get("translation", ""),
        "emotion": result["emotion"],
        "avatar_id": avatar_id,
    }
    if duration is not None:
        payload["duration"] = duration  # 秒数（float）
    await self._on_overlay(payload)
```

`_speak_impl()` の `notify_overlay` 呼び出し箇所（行180-183）で `duration` を渡す:

```python
if subtitle:
    await self.notify_overlay(
        subtitle["author"], subtitle["trigger_text"], subtitle["result"],
        avatar_id=avatar_id,
        duration=duration,  # ← 追加（行166で取得済み）
    )
```

### Step 2: フロントエンドにチャンク分割ロジックを追加

**ファイル**: `static/js/broadcast/panels.js`

#### 2a: チャンク分割関数 `splitSubtitleChunks(text, maxLen)` を追加

テキストを `maxLen` 文字以内のチャンクに分割する。分割位置は以下の優先順位:

1. 句読点・ピリオド（`。！？.!?`）の直後
2. 読点・カンマ（`、,`）の直後
3. スペースの位置
4. どこにもなければ `maxLen` で強制分割

```javascript
function splitSubtitleChunks(text, maxLen) {
  if (text.length <= maxLen) return [text];
  const chunks = [];
  let remaining = text;
  while (remaining.length > maxLen) {
    let cut = -1;
    // 優先1: 句読点
    for (let i = maxLen - 1; i >= maxLen * 0.4; i--) {
      if ('。！？.!?'.includes(remaining[i])) { cut = i + 1; break; }
    }
    // 優先2: 読点・カンマ
    if (cut < 0) {
      for (let i = maxLen - 1; i >= maxLen * 0.4; i--) {
        if ('、,，'.includes(remaining[i])) { cut = i + 1; break; }
      }
    }
    // 優先3: スペース
    if (cut < 0) {
      for (let i = maxLen - 1; i >= maxLen * 0.4; i--) {
        if (remaining[i] === ' ') { cut = i + 1; break; }
      }
    }
    // 強制分割
    if (cut < 0) cut = maxLen;
    chunks.push(remaining.slice(0, cut).trim());
    remaining = remaining.slice(cut).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}
```

#### 2b: `showSubtitle()` をチャンク対応に改修

- チャンク切り替え用のタイマーIDを管理する変数を追加（`_chunkTimers`）
- 新しい字幕表示時に前のチャンクタイマーをクリア
- `duration` がある場合: `(duration * 1000) / chunks.length` で均等割り
- `duration` がない場合: デフォルト5秒として計算（フォールバック）

```javascript
// チャンクタイマー管理（アバターIDごと）
const _chunkTimers = { teacher: [], student: [] };
const SUBTITLE_CHUNK_MAX_LEN = 80;

function clearChunkTimers(avatarId) {
  const key = avatarId === 'student' ? 'student' : 'teacher';
  _chunkTimers[key].forEach(t => clearTimeout(t));
  _chunkTimers[key] = [];
}

function showSubtitle(data) {
  const el = _getSubtitleEl(data.avatar_id);
  const isStudent = data.avatar_id === 'student';
  const timer = isStudent ? fadeTimerStudent : fadeTimerTeacher;
  clearTimeout(timer);
  clearChunkTimers(data.avatar_id);  // ← 追加

  // もう一方の字幕を速めにフェードアウト（既存ロジック維持）
  ...

  // 新しい字幕を上に表示（既存ロジック維持）
  _subtitleZCounter++;
  el.style.zIndex = _subtitleZCounter;
  el.classList.remove('fading');
  el.classList.remove('fading-fast');
  el.querySelector('.author').textContent = '';
  el.querySelector('.trigger-text').textContent = stripLangTags(data.trigger_text);
  el.querySelector('.translation').textContent = stripLangTags(data.translation || '');
  el.classList.add('visible');

  // --- チャンク分割表示 ---
  const speechText = stripLangTags(data.speech);
  const speechEl = el.querySelector('.speech');
  const chunks = splitSubtitleChunks(speechText, SUBTITLE_CHUNK_MAX_LEN);

  if (chunks.length <= 1) {
    // 短文: 従来通り一括表示
    speechEl.textContent = speechText;
    return;
  }

  // 長文: タイマーで順次切り替え
  const totalMs = (data.duration || 5) * 1000;
  const intervalMs = totalMs / chunks.length;
  const timerKey = isStudent ? 'student' : 'teacher';

  speechEl.textContent = chunks[0];  // 最初のチャンクを即表示
  for (let i = 1; i < chunks.length; i++) {
    const tid = setTimeout(() => {
      speechEl.textContent = chunks[i];
    }, intervalMs * i);
    _chunkTimers[timerKey].push(tid);
  }
}
```

#### 2c: `fadeSubtitle()` でチャンクタイマーもクリア

```javascript
function fadeSubtitle(avatarId) {
  if (!avatarId) {
    fadeSubtitle('teacher');
    fadeSubtitle('student');
    return;
  }
  clearChunkTimers(avatarId);  // ← 追加
  const el = _getSubtitleEl(avatarId);
  ...
}
```

### Step 3: translationのチャンク対応（任意）

翻訳テキストも長くなる可能性があるが、初期実装ではspeechのみチャンク分割とする。translationは全文表示のまま（通常はspeechより短いため）。必要に応じて後から対応。

## 変更ファイルまとめ

| ファイル | 変更内容 |
|---------|---------|
| `src/speech_pipeline.py` | `notify_overlay()` に `duration` 引数追加、`_speak_impl()` から渡す |
| `static/js/broadcast/panels.js` | `splitSubtitleChunks()` 追加、`showSubtitle()` チャンク対応、タイマー管理 |

## 動作イメージ

### 短文（80文字以下）
従来通りの表示。変化なし。

### 長文の例（240文字、音声10秒）
1. `0.0s`: チャンク1（〜80文字）を表示
2. `3.3s`: チャンク2（〜80文字）に切り替え
3. `6.7s`: チャンク3（〜80文字）に切り替え
4. `10.0s`: `speaking_end` → フェードアウト

## リスク・注意点

- **字幕と読み上げ箇所のズレ**: 均等割りのため、読み上げ速度とチャンク切り替えが完全には一致しない。ただし「今何を読んでいるか」の大まかな指標にはなる
- **チャンク切り替え時のちらつき**: `textContent` の直接書き換えなのでフレーム単位で完了し、実質ちらつきなし
- **duration未取得のケース**: TTS失敗時など `duration` がないフォールバックケースではデフォルト5秒で計算
- **maxLenの調整**: 80文字は1920x1080画面で `max-width: 62%` + `font-size: 1.875vw` の場合の目安。実際の配信画面で微調整が必要な可能性あり

## テスト方針

- 短文（80文字以下）: 従来通り一括表示されること
- 長文（100文字以上）: チャンクに分割されて順次切り替わること
- 日本語の句読点（。、）で適切に分割されること
- 英語のピリオド・カンマ・スペースで適切に分割されること
- 次の発話が来たら前のチャンクタイマーがクリアされること
- `speaking_end` でチャンクタイマーがクリアされフェードアウトすること
