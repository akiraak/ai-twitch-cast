# commentsテーブル再設計計画

## ステータス: 完了

## 背景・問題

現在の `comments` テーブルは1行に「視聴者のコメント（message）」と「アバターの応答（response）」をペアで格納している。これは根本的に間違っている。

**問題点:**
- 視聴者のコメントは「配信中に誰かが書いたもの」であり、それ自体が独立したデータ
- アバターの発話も独立したデータ（トピック発話・イベントリアクション・コメントへの応答）
- 1:1対応の前提は実態と合わない（アバターがどのコメントに反応したかは不定）
- 現在は無関係なデータを同じ行に無理やり詰め込んでいる

## 新設計

### テーブル構成

```sql
-- 視聴者のコメント（配信中に誰かが書いたもの、それだけ）
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL REFERENCES episodes(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- アバターのコメント（配信チャットに投稿されるもの全て）
CREATE TABLE IF NOT EXISTS avatar_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL REFERENCES episodes(id),
    trigger_type TEXT NOT NULL,      -- 'comment', 'topic', 'event'
    trigger_text TEXT NOT NULL,      -- きっかけのテキスト
    text TEXT NOT NULL,              -- 発話テキスト
    emotion TEXT NOT NULL DEFAULT 'neutral',
    created_at TEXT NOT NULL
);
```

**変更点:**
- `comments` は視聴者コメントのみ。`response` / `emotion` カラムを削除
- `avatar_comments` を新設。アバターの全発話（コメント応答・トピック・イベント）を格納
- `trigger_type` で発話のきっかけを分類できる

### データ例

| テーブル | 場面 | 内容 |
|----------|------|------|
| comments | aliceがチャットに書いた | `text="こんにちは"` |
| avatar_comments | aliceのコメントに反応 | `trigger_type="comment"`, `trigger_text="aliceさんのコメント: こんにちは"`, `text="やっほー！"` |
| avatar_comments | トピック発話 | `trigger_type="topic"`, `trigger_text="[トピック] AIの話"`, `text="最近のAIすごいよね"` |
| avatar_comments | コミット通知 | `trigger_type="event"`, `trigger_text="[commit] バグ修正"`, `text="直ったー！"` |

## 影響範囲と実装ステップ

### Step 1: DBスキーマ + マイグレーション（src/db.py）

#### スキーマ変更
- `comments` テーブル: `message` → `text`、`response` / `emotion` カラム削除
- `avatar_comments` テーブル新設

#### マイグレーション
```python
# 既存データの移行
# 1. avatar_comments テーブル作成
# 2. comments の response が空でない行を avatar_comments にコピー
# 3. comments の message を text にリネーム
# 4. response / emotion カラム削除（SQLiteはDROP COLUMNを3.35.0+でサポート）
```

**SQLite バージョン注意**: `DROP COLUMN` は 3.35.0+ が必要。それ以前なら `CREATE TABLE new → INSERT → DROP old → RENAME` パターン。

#### 関数変更

| 旧関数 | 変更内容 |
|--------|----------|
| `save_comment(ep, user, message, response, emotion)` | → `save_comment(ep, user, text)` （コメントのみ保存） |
| — | → `save_avatar_comment(ep, trigger_type, trigger_text, text, emotion)` 新設 |
| `get_recent_comments(limit, hours)` | → コメントのみ返す `{user_name, text, created_at}` |
| — | → `get_recent_avatar_comments(limit, hours)` 新設 |
| — | → `get_recent_timeline(limit, hours)` 新設（コメント+発話を時系列統合） |
| `get_user_recent_comments(user, limit, hours)` | → `{text, created_at}` のみ返す |
| `count_user_comments_in_episode(ep, user)` | 変更なし（commentsテーブルのCOUNT） |

### Step 2: AI応答辞書（src/ai_responder.py）

#### `generate_response()` / `generate_event_response()` の返り値

現在: `{"response": str, "emotion": str, "english": str, "tts_text": str}`

→ `{"speech": str, "emotion": str, "english": str, "tts_text": str}`

**注意**: GeminiのJSON出力プロンプトにもキー名 `"response"` が使われている（L588等）。プロンプトも `"speech"` に変更する。

#### 会話履歴構築（L153-165）

現在: `get_recent_comments()` から `message` + `response` ペアでマルチターン構築

新設計: `get_recent_timeline()` を使い、コメントと発話を時系列で取得。
```python
for item in timeline:
    if item["type"] == "comment":
        # role="user"
        contents.append(Content(role="user", parts=[Part(text=f"{item['user_name']}さんのコメント: {item['text']}")]))
    elif item["type"] == "speech":
        # role="model"
        contents.append(Content(role="model", parts=[Part(text=item["text"])]))
```

#### ユーザーメモ生成（`generate_user_notes()` L229-239）

現在: `c["message"]` と `c["response"]` を表示

新設計: `get_user_recent_comments()` でコメントのみ取得。対応する発話が必要な場合は `get_recent_timeline()` から該当ユーザーの周辺を抽出。

→ ただし、ユーザーメモは「このユーザーがどういう発言をしたか」が重要なので、コメントだけで十分かもしれない。アバターの応答も含めたいなら、タイムライン形式で前後を見る。

#### ペルソナ生成（`generate_persona()` L374-446）

現在: `c["response"]` だけ使用（アバターの応答パターン分析）

新設計: `get_recent_avatar_comments()` から `text` を取得するだけ。こちらはシンプルになる。

#### セルフメモ生成（`generate_self_note()` L259-371）

現在: `c["user_name"]` + `c["message"]` + `c["response"]`

新設計: `get_recent_timeline()` を使用。

#### トピック生成（`generate_topic_title()` L622+、`generate_topic_line()` L449+）

現在: `c["user_name"]` + `c["message"]` + `c["response"]`

新設計: `get_recent_timeline()` を使用。

### Step 3: コメント読み上げ（src/comment_reader.py）

#### `_save_to_db()` (L246-254)
現在: `save_comment(ep, user, message, result["response"], result["emotion"])`

新設計:
```python
save_comment(ep, user, message)  # 視聴者コメント保存
save_avatar_comment(ep, "comment", f"{user['name']}さんのコメント: {message}",
            result["speech"], result["emotion"])  # アバター発話保存
```

#### `_save_avatar_speech()` (L341-355)
現在: `save_comment(ep, avatar_user, message, response, emotion)` — usersテーブルにアバターを入れて無理やりcommentsに保存

新設計: `save_avatar_comment(ep, trigger_type, trigger_text, text, emotion)` — usersテーブルを介さず直接保存。**`increment_comment_count` も不要になる。**

#### subtitle辞書
現在: `{"author": ..., "message": ..., "result": {"response": ..., "emotion": ..., "english": ...}}`

新設計: `{"author": ..., "trigger_text": ..., "result": {"speech": ..., "emotion": ..., "english": ...}}`

#### `_post_to_chat()` (L256-265)
`result["response"]` → `result["speech"]`

#### `speak_event()` 内のフィルタ (L274-275)
現在: `[c["response"] for c in recent if c.get("user_name") == "システム"]`

新設計: `get_recent_avatar_comments(type="event")` のような専用クエリに置き換え。

### Step 4: 音声パイプライン（src/speech_pipeline.py）

#### `notify_overlay()` (L32-43)
WSイベント: `"message"` → `"trigger_text"`, `"response"` → `"speech"`

#### `speak()` 内 (L114)
`subtitle["message"]` → `subtitle["trigger_text"]`

### Step 5: APIルート

#### scripts/routes/avatar.py
- `/api/chat/history` (L99-111): SQL変更。コメントと発話を統合して返すか、分離して返すか。
  - フロントのチャットログ表示用なので、**タイムライン形式**が適切
- `/api/avatar/speak` 応答: `result["response"]` → `result["speech"]`

#### scripts/routes/db_viewer.py
- CUSTOM_QUERIES (L18-24): commentsとavatar_commentsそれぞれのクエリに変更
  - avatar_commentsテーブル用のCUSTOM_QUERYを追加

### Step 6: フロントエンド

#### static/broadcast.html
- CSSクラス `.message` → `.trigger-text`, `.response` → `.speech`

#### static/js/broadcast-main.js
- `showSubtitle()`: `data.message` → `data.trigger_text`, `data.response` → `data.speech`
- DOMクエリ: `.querySelector('.message')` → `.querySelector('.trigger-text')` 等

#### static/js/index-app.js
- `chatRowHtml()`: `c.message` → `c.trigger_text`, `c.response` → `c.speech`
- `/api/chat/history` のレスポンス構造変更に合わせる

### Step 7: テスト

| ファイル | 変更内容 |
|----------|----------|
| `tests/test_db.py` | `save_comment` のテスト更新 + `save_avatar_comment` / `get_recent_timeline` のテスト追加 |
| `tests/test_ai_responder.py` | テストデータ辞書のキー変更 + タイムライン形式対応 |
| `tests/test_speech_pipeline.py` | WSイベントキー変更 |
| `tests/test_api_chat.py` | APIレスポンスキー変更 |

### Step 8: 全体確認
```bash
python3 -m pytest tests/ -q
curl -s http://localhost:$WEB_PORT/api/status
```

## リスク・注意点

- **既存DBデータ**: マイグレーションで既存commentsの `response` → `avatar_comments` にコピー。データロスなし
- **`get_recent_timeline()`**: コメントと発話を `created_at` で統合ソートする新関数が必要。UNION ALLで実装可能
- **ユーザーメモ生成**: 現在はコメント+応答をペアで見ているが、分離後はタイムラインから前後を見る形に。精度への影響を確認
- **`users` テーブルのアバターエントリ**: `_save_avatar_speech()` がアバター名でユーザーを作成している。新設計では不要になるが、既存データの `users` テーブルにアバター名が残る（害はない）
- **C#ネイティブアプリ**: WSイベントは `broadcast-main.js` 経由なのでC#側の変更は不要
- **SQLite DROP COLUMN**: 3.35.0+ 必要。`sqlite3 --version` で確認すること
