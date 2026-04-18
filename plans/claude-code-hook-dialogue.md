# Claude Code Hook 読み上げの二人掛け合い化

## ステータス: 完了

## 背景

Claude Codeのグローバルフック（`notify-prompt.py` / `notify-stop.py` / `long-execution-timer.py`）は `POST /api/avatar/speak` を叩いて状況を読み上げている。現在は `CommentReader.speak_event()` → `generate_multi_event_response()` にルーティングされ、以下の挙動になっている:

- プロンプト指示: 「`teacher`単独（約70%）または両者応答（約30%）」
- 出力: 1〜2エントリ（ほぼ単独応答・1文の短いリアクション）

結果、Hook読み上げはほぼ先生一人のコメントになっており、TODOの要件である「キャラ2名の掛け合い」になっていない。

一方で `ClaudeWatcher` の定期実況は `generate_claude_work_conversation()` を使って2〜3往復（最大4エントリ）の掛け合いを既に生成している。同じ仕組みをHook読み上げにも持ち込みたい。

## 目的

Hook経由の読み上げ（「指示」「作業報告」「待機コメント」等のイベント）を、常に **先生と生徒の2人の掛け合い（2〜3往復）** に統一する。

## 現状コールツリー

```
notify-prompt.py  ──┐
notify-stop.py    ──┼─> POST /api/avatar/speak
long-execution-timer.py ─┘      └─> CommentReader.speak_event(event_type, detail)
                                      ├─ 生徒キャラあり → generate_multi_event_response()  ※1〜2エントリ
                                      └─ 生徒キャラなし → generate_event_response()        ※単独
```

`state.py` の `_on_git_commit` や `scripts/routes/overlay.py` の「作業開始」も同じ `speak_event()` を経由するため、本変更は **Hook以外のイベント発話にも波及する**。

## 設計方針

### 方針A（採用候補）: `generate_multi_event_response()` を掛け合い出力に改修

- プロンプトを「2〜4エントリの掛け合い」に変更（`generate_claude_work_conversation()` のルールを踏襲）
- エントリ数・speaker検証は既存の `_validate_multi_response()` を再利用
- 生徒キャラがあるときは常に掛け合い。なければ現状どおり単独（`generate_event_response()` にフォールバック）
- 変更点が最小で、既存のイベント発話（コミット・作業開始）にも自然に波及

### 方針B: Hook専用エンドポイント/関数を追加

- `generate_event_dialogue()` を新設し、Hook経路だけ掛け合いにする
- Git commitイベント等は単独のまま維持

### 採用

**方針A** を採用する。理由:
- Hook以外のイベント発話も掛け合いになったほうが配信として面白い
- 既に `generate_claude_work_conversation()` で同じ掛け合いパターンが運用実績あり（プロンプト設計を流用できる）
- コード追加が最小

ただし `speak_event()` の呼び出し元の中には **TTSテスト / 感情テスト / ボイスサンプル** のように単独発話を期待しているものがある（`scripts/routes/avatar.py`）。これらは今までも `generate_multi_event_response()` 経由ではなく、直接プロンプトを組んでTTSを鳴らしていたので影響なし（要確認: `avatar.py` の `tts_test` 等は `speak_event()` を呼んでいる → 呼び出し経路を再確認のうえ、掛け合い化が望ましくないものは `speak_event(..., multi=False)` オプションでスキップできるようにする）。

## 実装ステップ

### Step 1: プロンプト改修

**ファイル**: `src/ai_responder.py` — `generate_multi_event_response()`

- プロンプトのルールを書き換え:
  - 「単独約70% / 両者約30%」 → 「二人が交互に2〜3往復（2〜4エントリ）」
  - 「各エントリ: 1〜2文、40文字以内」
  - 「先生が出来事を説明、生徒がリアクション・質問・感想」（`generate_claude_work_conversation` と同趣旨）
- 出力スキーマは既存のまま（`speaker/speech/tts_text/emotion/translation`）
- `last_event_responses` の指示（繰り返し防止）は維持
- 英語モードの対応文も同じルールに置換
- 上限: `result = result[:4]`（既存の `generate_claude_work_conversation` と同じ）

### Step 2: 呼び出し側の想定に合わせた保険

**ファイル**: `src/comment_reader.py` — `speak_event()`

- 既にエントリを for ループで順次再生しているので、エントリ数が2〜4に増えても動作は変わらない
- コメント割り込みは現状未対応（ClaudeWatcherには実装済み）。Hookの掛け合い中にコメントが来た場合、今は最後まで再生される。**本タスクのスコープ外**（TODOに別項目を追加する）

### Step 3: 呼び出し元の影響調査と調整

**調査対象**:
- `scripts/routes/avatar.py` の `tts_test` / `tts_test_emotion` / `tts_voice_sample` は `speak_event()` を呼んでいる
  - TTSテスト/感情テストはもともと単独の短文発話が目的なので、掛け合いになると違和感がある
  - 解決: `speak_event(..., multi=False)` オプションを追加して該当呼び出しから指定する

**`speak_event()` のシグネチャ変更案**:
```python
async def speak_event(self, event_type, detail, voice=None, style=None,
                     avatar_id="teacher", multi=True):
    ...
    if multi and self._characters and self._characters.get("student"):
        # 掛け合いモード（generate_multi_event_response 改修版）
    else:
        # シングルキャラモード
```

**呼び出し元の整理**:
| 呼び出し元 | 現状 | 変更後 |
|---|---|---|
| `POST /api/avatar/speak`（Hook） | デフォルト | `multi=True`（デフォルト）→ 掛け合い |
| `_on_git_commit`（state.py） | デフォルト | 掛け合い |
| 「作業開始」（overlay.py） | デフォルト | 掛け合い |
| `tts_test` / `tts_test_emotion` | デフォルト | `multi=False` を渡す（単独維持） |
| `tts_voice_sample` | デフォルト | `multi=False` を渡す（単独維持） |

### Step 4: テスト

**ファイル**: `tests/test_ai_responder.py`, `tests/test_comment_reader.py`（存在しない場合は新規）

- `generate_multi_event_response()` が2〜4エントリを返すことを確認（モックLLM）
- プロンプトに「2〜3往復」「交互」の指示が含まれることを確認
- `speak_event(multi=False)` がシングルキャラ経路を通ることを確認
- TTSテスト系の呼び出しが単独発話のまま動くことを確認

### Step 5: メモリ・ドキュメント更新

- `docs/speech-generation-flow.md` にHook読み上げの掛け合い化を反映
- `MEMORY.md` / `.claude/projects/.../memory/` の該当ファイルを更新

## リスク・注意点

1. **LLM呼び出しコスト増** — 1回の発話が2〜4エントリに増えるため、TTS生成回数も増える。コミットイベントが頻発する状況では体感レスポンスが遅くなる可能性
   - 対策: `generate_claude_work_conversation` 同様に最大4エントリで固定。必要ならTODOで頻度制御（コミットは最新のみにデバウンス）を別途検討
2. **Hook応答の発話時間が長くなる** — 「指示を受けました」程度で済んでいたものが会話化するため、ユーザーが次の指示を打ち込むまでの間に発話が終わらない場合がある
   - 対策: Hook由来の「指示受信」は依然として短めにするプロンプト調整（例: 指示受信は2エントリまで、コミットは2〜4エントリ）も検討
3. **コメント割り込み未対応** — 掛け合い中にコメントが来てもスキップされない。ClaudeWatcherと同じ割り込み機構を入れるかは別TODO
4. **テスト/ボイスサンプル経路の退行** — `speak_event()` 経由でTTSテスト・ボイスサンプルを鳴らす箇所が単独発話のまま動くことを確認必須

## ファイル変更一覧

| ファイル | 変更内容 |
|---|---|
| `src/ai_responder.py` | `generate_multi_event_response()` のプロンプト改修（2〜4エントリの掛け合い） |
| `src/comment_reader.py` | `speak_event()` に `multi` 引数追加 |
| `scripts/routes/avatar.py` | `tts_test` / `tts_test_emotion` / `tts_voice_sample` から `multi=False` を渡す |
| `tests/test_ai_responder.py` | 新プロンプトとエントリ数の検証テスト追加 |
| `docs/speech-generation-flow.md` | Hook読み上げフローの記述更新 |

## 完了条件

- `notify-prompt.py` / `notify-stop.py` / `long-execution-timer.py` 経由の発話が常に2〜4エントリの掛け合いになる
- TTSテスト / 感情テスト / ボイスサンプルは単独発話のまま動く
- `python3 -m pytest tests/` が全通過
- サーバー起動確認（`curl /api/status`）OK
