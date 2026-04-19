# 承認待ち通知を単独発話にする

## ステータス: 完了

## 背景

現在、Claude Code の `PermissionRequest` フック（Yes/No 承認ダイアログ表示時）は `notify-permission.py` → `POST /api/avatar/speak` → `CommentReader.speak_event(event_type="承認待ち", ...)` 経路で発話する。

過去の改修（[plans/archive/claude-code-hook-dialogue.md](archive/claude-code-hook-dialogue.md)）で `speak_event()` は `multi=True` をデフォルトにして、生徒キャラがいれば常に2〜4エントリの掛け合いに変わっている。その結果、**承認待ち通知も毎回「先生と生徒の掛け合い」になってしまい、Yes/No を押すまでに発話が終わらない / 掛け合いが不要に長い** という課題がある。

TODO: 「Claude Code Hook の Yes/No の時も会話のかけあいになるけどちょびが一言言うだけでいい」

## 目的

`PermissionRequest` 由来の発話を **単独キャラのフランクな一言**（「入力を求められています、選んでください」相当）に戻す。コミット通知・指示受信・作業報告などの既存イベントは現行どおり掛け合いのまま維持する。

**合わせて**: 配信の secret 誤爆防止のため、従来どおり `tool_name` やコマンド内容は送らず、**固定の汎用 detail** だけ LLM に渡す。LLM 側の既存プロンプト（1文・40字以内・バリエーションを出す）が自動的にランダムなフランク表現を生成する。

## 現状の経路

```
notify-permission.py
  └─ POST /api/avatar/speak  (body: event_type="承認待ち", detail=tool_name, voice=None)
      └─ CommentReader.speak_event(event_type, detail)  ← multi のデフォルトは True
          └─ 生徒キャラあり → generate_multi_event_response()  ※2〜4エントリの掛け合い
```

`speak_event()` 自体は `multi=False` 引数を受け付ける作りになっていて（`src/comment_reader.py:550`）、TTSテスト系ルートが既に使っている。つまり **呼び出し側から `multi=False` を渡す経路さえ用意すれば、既存の単独発話コードパス（`generate_event_response()`）にそのまま乗る**。

## 方針比較

### 方針A（採用）: `SpeakRequest` に `multi` フィールド追加 + フック側で `multi=false` を送る

- `scripts/routes/avatar.py` の `SpeakRequest` に `multi: bool = True` を追加
- `speak_event()` に `multi=body.multi` を渡す
- `claude-hooks/global/notify-permission.py` の POST ボディに `"multi": false` を追加
- 他のフック（`notify-prompt.py` / `notify-stop.py` / `long-execution-timer.py`）は変更なし（デフォルト `multi=True` のまま掛け合い維持）

**メリット**:
- 変更が小さい（API 1箇所 + フック1箇所）
- 他フックや将来追加するイベントも個別に `multi` を選べる汎用な仕組みになる
- `speak_event()` 側の既存インターフェースをそのまま使うだけで、新規の分岐コードが不要

**デメリット**:
- 他プロジェクトの `notify-permission.py` を更新するためには `scripts/setup-hooks.sh` の再実行が必要（冪等なので問題なし）

### 方針B: `speak_event()` 内で event_type を文字列マッチして強制 `multi=False`

- `speak_event()` 内で `event_type.startswith("承認待ち")` なら `multi=False` に上書き
- API の変更不要

**不採用理由**:
- ドメインロジック（`comment_reader.py`）にUI文言のハードコードが入り、後で event_type を変えた時に壊れる
- イベント種別ごとに「掛け合いにするか否か」を決めたい場合、将来すべて文字列マッチが増えていく
- API の拡張性が得られない（他のフックが単独発話したくなっても同じパッチが必要）

### 方針C: `notify-permission.py` が `POST /api/avatar/speak` ではなく別エンドポイントを叩く

- `/api/avatar/speak_single` などを新設

**不採用理由**:
- エンドポイントが増えるだけで、本質的には方針Aと同じ（パラメータで切り替えるのが素直）

## 実装ステップ

### Step 1: API に `multi` パラメータを追加

**ファイル**: `scripts/routes/avatar.py`

```python
class SpeakRequest(BaseModel):
    event_type: str = "手動"
    detail: str
    voice: str | None = None
    multi: bool = True   # ← 追加

@router.post("/api/avatar/speak")
async def avatar_speak(body: SpeakRequest):
    await state.broadcast_overlay({"type": "current_task", "task": body.detail})
    asyncio.create_task(
        state.reader.speak_event(body.event_type, body.detail, voice=body.voice, multi=body.multi)
    )
    return {"ok": True}
```

### Step 2: 承認待ちフックで `multi=False` を送る + detail を汎用固定文に

**ファイル**: `claude-hooks/global/notify-permission.py`

- `tool_name` を読むのをやめる（どうせ渡さない）
- `detail` は固定の汎用文 `"ユーザー入力待ち。選択肢から選んでほしい"` を渡す
  - LLM が既存プロンプト（キャラ口調 + 1文40字 + バリエーション指示）でフランクな一言にランダム変換する
  - 例: 「選択肢出てるよ〜どれにする？」「入力待ちだって、選んで〜！」など毎回違う表現になる
- `event_type` は他プロジェクト時のみ `"承認待ち（{project_name}）"`（従来踏襲）

```python
payload = json.dumps({
    "event_type": event_type,   # "承認待ち" or "承認待ち（xxx）"
    "detail": "ユーザー入力待ち。選択肢から選んでほしい",
    "multi": False,
}).encode()
```

**補足**: テンプレ文字列を Python 側でランダム配列から選ぶ案もあるが、キャラ口調が固定化してしまう。LLM に任せたほうがキャラ性と毎回のバリエーションが両立する（既存イベント発話と同じ設計思想）。

### Step 3: セットアップで展開

`bash scripts/setup-hooks.sh` を実行して `~/.claude/hooks/notify-permission.py` を更新（冪等・既存通り）。

### Step 4: テスト

**ファイル**: `tests/test_api_avatar.py`

- `/api/avatar/speak` に `multi=False` を送ったら `speak_event()` が `multi=False` で呼ばれることを確認（`state.reader.speak_event` を mock する）
- デフォルト（`multi` 省略時）は `multi=True` で呼ばれることを確認

既存の `speak_event(multi=False)` の単独発話経路は `tests/test_comment_reader.py` で既にカバー済みのはずなので再確認する。

### Step 5: 動作確認

1. `./server.sh` でサーバー起動
2. 別プロジェクト／当プロジェクトで実際に承認ダイアログが出る操作を実行
3. ちょびが **先生一人の短い一言** で「選択肢出てるよ〜」系のフランクな文を言うことを確認（掛け合いにならない／tool_nameは含まない）
4. 通常のコミット・指示受信イベントは引き続き掛け合いになっていることを確認（リグレッション防止）

### Step 6: DONE.md / TODO.md / コミット

## 変更対象ファイル

| ファイル | 変更内容 |
|---|---|
| `scripts/routes/avatar.py` | `SpeakRequest` に `multi: bool = True` を追加、`speak_event()` に転送 |
| `claude-hooks/global/notify-permission.py` | POST ボディに `"multi": false` を追加 |
| `tests/test_api_avatar.py` | `multi` パラメータ経路のテスト追加 |
| `~/.claude/hooks/notify-permission.py` | `setup-hooks.sh` が展開（コミット対象外） |

## リスク / 注意点

- **他のフックは変更なし**: `notify-prompt.py` / `notify-stop.py` / `long-execution-timer.py` は引き続き `multi` を送らない → デフォルト `True` のまま掛け合い維持
- **既存APIの後方互換**: `multi` はデフォルト `True` なので、既存呼び出し（`_on_git_commit`・`/broadcast` の作業開始など）は影響なし
- **`state.reader.speak_event` が未起動の場合**: 従来通り `/api/avatar/speak` 側で `state.reader` 未初期化エラーになる可能性。既存挙動から変更なし（本タスクのスコープ外）
- **60秒クールダウン**: 既存のクールダウンはそのまま（連発防止）

## 完了条件

- 承認ダイアログが出たときの発話が常に **単独キャラのフランクな1エントリ** になる（毎回違う表現）
- 発話に `tool_name` やコマンド内容は含まれない（汎用の「入力待ち」系の文のみ）
- コミット通知・指示受信などの既存イベントは掛け合いのまま
- `python3 -m pytest tests/ -q -m "not slow"` が全通過
- `curl /api/status` OK
