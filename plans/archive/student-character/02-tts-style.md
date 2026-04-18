# Step 2: TTS style パラメータ + WebUI設定

## ステータス: 未着手

## ゴール

**話者ごとに異なる声・スタイルで喋らせる。** `speech_pipeline` に `style` を伝搬し、WebUIからキャラクターごとの声（voice）と話し方（style）を設定できるようにする。

ここまでで「2体のアバターが別々の声で喋る＋WebUIで自由に変更できる」が実現する。

## 現状

- `tts.py`: `synthesize()` は既に `voice` / `style` 引数を受け取れる ✅
- `ai_responder.py`: `get_tts_config()` がキャラDBから `tts_voice` / `tts_style` を返す ✅
- `speech_pipeline.py`: `speak()` / `generate_tts()` に **`style` が伝搬されていない** ❌
- WebUI: キャラクター設定画面に **voice/style の入力UIがない** ❌
- API: `CharacterUpdate` モデルに `tts_voice` / `tts_style` がない（ただし既存configとのマージで保持はされる） ❌

## 変更対象

| ファイル | 変更内容 |
|---------|---------|
| `src/speech_pipeline.py` | `generate_tts()` / `speak()` に `style` 引数を追加・伝搬 |
| `scripts/routes/character.py` | `CharacterUpdate` に `tts_voice` / `tts_style` を追加（Optional） |
| `static/index.html` | キャラ設定の第1層に voice ドロップダウン + style テキストエリアを追加 |
| `static/index.html` | サウンドテストUIをDebugタブに移動（キャラタブ・サウンドタブから削除） |
| `static/js/admin/character.js` | voice/style の読み込み・保存を追加 |

## 前提

- なし（他Stepと独立）

## 実装

### 2-1. speech_pipeline.py — style伝搬

```python
async def generate_tts(self, text, voice=None, style=None, tts_text=None):
    wav_path = Path(tempfile.mkdtemp()) / "speech.wav"
    try:
        await asyncio.to_thread(synthesize, tts_text or text, str(wav_path),
                                voice=voice, style=style)
        return wav_path
    except Exception as e:
        # ...

async def speak(self, text, voice=None, style=None, subtitle=None,
                chat_result=None, tts_text=None, post_to_chat=None,
                se=None, wav_path=None, avatar_id=None):
    async with self._speak_lock:
        await self._speak_impl(text, voice=voice, style=style, ...)
```

### 2-2. character.py API — CharacterUpdate拡張

```python
class CharacterUpdate(BaseModel):
    name: str
    system_prompt: str
    rules: list[str]
    emotions: dict[str, str]
    emotion_blendshapes: dict[str, dict[str, float]]
    tts_voice: str | None = None
    tts_style: str | None = None
```

### 2-3. index.html — キャラ設定UIにTTSフィールド追加

第1層カードの「感情BlendShape」の前あたりに配置:

```html
<div>
  <label class="field-label">声の種類（TTS Voice）</label>
  <select id="char-tts-voice" class="text-input">
    <option value="">デフォルト (Despina)</option>
    <!-- Gemini TTS 全30音声 -->
    <option value="Zephyr">Zephyr</option>
    <option value="Puck">Puck</option>
    ...（全30音声）
  </select>
</div>
<div>
  <label class="field-label">話し方スタイル（TTS Style）</label>
  <textarea id="char-tts-style" rows="2" class="text-input"
    placeholder="例: 元気で明るい声で、好奇心いっぱいに読み上げてください"></textarea>
</div>
```

### 2-4. character.js — voice/styleの読み込み・保存

```javascript
// _loadCharacterFromApi 内
document.getElementById('char-tts-voice').value = data.tts_voice || '';
document.getElementById('char-tts-style').value = data.tts_style || '';

// saveCharacter 内
const body = {
  ...既存フィールド,
  tts_voice: document.getElementById('char-tts-voice').value || null,
  tts_style: document.getElementById('char-tts-style').value || null,
};
```

### 2-5. サウンドテストUIをDebugタブに移動

現在2箇所に分散しているテスト機能をDebugタブに集約する。

**移動元（削除）:**
- キャラクタータブ > セリフ > 「テスト再生」カード（L213-230）— `ttsTest()` 6ボタン + `emotionTest()` 4ボタン
- サウンドタブ > 読み上げ > 「連続発話テスト」（L306-312）— `ttsTestMulti()` ボタン

**移動先（追加）:**
Debugタブに「サウンドテスト」カードを追加。既存の「アバター制御テスト」カードの後に配置。

```html
<!-- Debugタブ内に追加 -->
<div class="card">
  <h2>サウンドテスト</h2>
  <div style="font-size:0.85rem; color:#6a5590; margin-bottom:6px;">単発テスト</div>
  <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
    <button onclick="ttsTest('greeting')" style="font-size:0.75rem;">挨拶</button>
    <button onclick="ttsTest('topic')" style="font-size:0.75rem;">雑談</button>
    <button onclick="ttsTest('react')" style="font-size:0.75rem;">リアクション</button>
    <button onclick="ttsTest('question')" style="font-size:0.75rem;">質問</button>
    <button onclick="ttsTest('story')" style="font-size:0.75rem;">エピソード</button>
    <button onclick="ttsTest('explain')" style="font-size:0.75rem;">解説</button>
  </div>
  <div style="margin-top:10px; display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
    <span style="font-size:0.8rem; color:#666;">感情:</span>
    <button onclick="emotionTest('joy')" style="font-size:0.75rem;">joy</button>
    <button onclick="emotionTest('surprise')" style="font-size:0.75rem;">surprise</button>
    <button onclick="emotionTest('thinking')" style="font-size:0.75rem;">thinking</button>
    <button onclick="emotionTest('neutral')" style="font-size:0.75rem;">neutral</button>
  </div>
  <div style="margin-top:12px; padding-top:10px; border-top:1px solid #e0d8f0;">
    <div style="font-size:0.85rem; color:#6a5590; margin-bottom:6px;">連続発話テスト</div>
    <div style="display:flex; gap:8px; align-items:center;">
      <button onclick="ttsTestMulti()" style="font-size:0.8rem; background:#7b1fa2;">連続発話</button>
      <span id="tts-multi-status" style="font-size:0.8rem; color:#9a88b5;"></span>
    </div>
  </div>
</div>
```

**JS変更なし** — `ttsTest()`, `emotionTest()`, `ttsTestMulti()` は `sound.js` に定義済みでそのまま使える。

### 2-6. 動作確認

1. WebUIでキャラクターを選択 → voice/styleが表示される
2. 生徒キャラで voice=Kore, style=「元気で明るい...」を設定 → 保存
3. 先生キャラは voice=Despina, style=にこにこスタイル（デフォルト）
4. 発話テストで声の差が確認できる

## 完了条件

- [ ] `speech_pipeline.speak()` に `style` が伝搬される
- [ ] `style=None` の場合は従来のデフォルトスタイルが使われる
- [ ] 既存の呼び出し元（comment_reader等）が影響を受けない
- [ ] WebUIのキャラ設定に voice ドロップダウンと style テキストエリアがある
- [ ] WebUIで変更した voice/style がDBに保存される
- [ ] 保存した voice/style がTTS発話時に反映される
- [ ] サウンドテスト（ttsTest/emotionTest/ttsTestMulti）がDebugタブに移動されている
- [ ] キャラクタータブの「テスト再生」カードが削除されている
- [ ] サウンドタブの「連続発話テスト」セクションが削除されている
