# トピック発話の文量拡張（1文→2文、キャンセル対応）

## ステータス: 完了

## 背景

現在、トピック発話は「1文のみ、30文字以内」に制限されている。もう少し内容のある話をしたい。
コメント応答は短いまま（テンポ重視）。

## 方針

AIに2文を生成させ、**別々のセグメントとしてキューに入れる**。
セグメント間でコメントが来たら2文目をキャンセルしてコメント応答を優先する。

```
[AI生成] → seg1, seg2（2つの独立したセグメント）
[再生]   → speak(seg1) → コメント来た？ → Yes: キャンセル、コメント応答へ
                                         → No:  speak(seg2)
```

## 変更箇所

### 1. AI生成の変更 — `src/ai_responder.py`

`generate_topic_line()` の出力形式を配列に変更:

```python
# Before
"- 1文のみ、30文字以内で短く（日本語の場合。英語は15 words以内）",
# 出力: {"content": "...", "emotion": "...", "tts_text": "...", "translation": "..."}

# After
"- 1〜2文を別々のセグメントとして生成する",
"- 各セグメントは30文字以内（日本語の場合。英語は15 words以内）",
"- 1文で十分なときは1セグメントだけでOK",
# 出力: [{"content": "...", "emotion": "...", "tts_text": "...", "translation": "..."}, ...]
```

返り値が `dict` → `list[dict]` に変わる。
1セグメントのみの場合も `[{...}]` の配列で返す（呼び出し側を統一的に扱うため）。

**後方互換**: AIが配列でなくdictを返した場合は `[result]` でラップしてフォールバック。

### 2. トピック発話のキュー化 — `src/comment_reader.py`

`_auto_speak()` で生成したセグメントを**内部キューに入れる**。
`_process_loop()` の既存ロジック（コメント優先）がそのまま活きる。

```python
async def _auto_speak(self):
    """トピックに基づいて自発的に発話する（複数セグメント対応）"""
    # ... (ローテーションチェックは同じ) ...

    segments = await self._topic_talker.get_next()
    if not segments:
        return

    # 1文目は即座に発話
    seg = segments[0]
    await self._speak_topic_segment(seg)

    # 2文目以降はトピックキューに入れる（コメントが来たらキャンセルされる）
    for seg in segments[1:]:
        self._topic_queue.append(seg)
```

`_process_loop()` の優先順位:
```python
async def _process_loop(self):
    while self._running:
        if self._queue:                          # 1. コメント最優先
            self._topic_queue.clear()            #    → トピック残りはキャンセル
            self._idle_since = None
            author, message = self._queue.popleft()
            await self._respond(author, message)
        elif self._topic_queue:                  # 2. トピックの続き
            seg = self._topic_queue.popleft()
            await self._speak_topic_segment(seg)
        elif self._topic_talker and self._should_auto_speak():  # 3. 新規トピック発話
            await self._auto_speak()
            self._idle_since = time.monotonic()
        else:
            if self._idle_since is None:
                self._idle_since = time.monotonic()
            await asyncio.sleep(0.5)
```

**キャンセルの仕組み**: コメントが来たら `self._topic_queue.clear()` するだけ。シンプル。

### 3. TopicTalker の返り値変更 — `src/topic_talker.py`

`get_next()` の返り値を `dict` → `list[dict]` に変更:

```python
async def get_next(self):
    """次の発話セグメントを生成する

    Returns:
        list[dict] or None: [{"content": str, "emotion": str, ...}, ...]
    """
    # ... generate_topic_line() を呼ぶ（配列が返る）
    # ... 各セグメントをDBに保存
```

### 4. SpeechPipeline — 変更なし

`speak()` は今まで通り1セグメントずつ呼ばれる。変更不要。

## 変更しないもの

- `SpeechPipeline`: 変更なし（1回のspeakは1セグメント）
- コメント応答 (`generate_response()`): 短いまま
- DB スキーマ: 変更なし（セグメントごとに `avatar_comments` に1レコード）
- `scenes.json`: 変更なし

## セグメント間の間

トピックキューからの連続再生では、`_speak_topic_segment()` 内で `speak()` 完了後に自然な間を入れる。
`speak()` 自体に `duration + 0.5s` の待機が既にあるので、追加の間は不要かもしれない。
配信で聞いてみて調整。

## リスク

| リスク | 対策 |
|--------|------|
| AIが配列を返さない | dictなら `[result]` にラップしてフォールバック |
| 毎回2文になって冗長 | プロンプトで「1文で十分なときは1セグメントだけでOK」 |
| 2文目キャンセル頻発 | 問題なし。コメント応答を優先するのは正しい動作 |
| speak間が不自然 | 既存の0.5s待機で自然。必要なら調整 |

## 作業量

- `ai_responder.py`: プロンプト変更 + 出力パース修正
- `topic_talker.py`: `get_next()` の返り値を配列に
- `comment_reader.py`: `_topic_queue` 追加 + `_process_loop` / `_auto_speak` 修正
- テスト更新: `test_ai_responder.py`, `test_topic_talker.py`, `test_comment_reader.py`

小〜中規模。新クラス・新ファイルなし。
