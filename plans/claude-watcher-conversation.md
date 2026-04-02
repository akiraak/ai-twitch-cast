# Claude Code 作業実況会話プラン

## ステータス: Step 4 完了

## 背景

現在、Claude Codeの作業状況はグローバルフック（`notify-prompt.py`/`notify-stop.py`/`long-execution-timer.py`）で報告されている。しかし、これは「○分作業中。直近の作業: ファイル編集…」のような単調なステータス報告で、配信として面白みがない。

**目標**: Claude Codeの作業履歴（transcript）を常時監視し、一定間隔で先生（ちょビ）と生徒（なるこ）が作業内容について自然に会話する仕組みを作る。

## 現状の仕組み

1. `notify-prompt.py` → Claude Code開始時に `/api/avatar/speak` へイベント送信
2. `notify-stop.py` → Claude Code完了時に `/api/avatar/speak` へイベント送信
3. `long-execution-timer.py` → 3分間隔で「○分作業中」を `/api/avatar/speak` へ送信
4. `/api/avatar/speak` → `generate_multi_event_response()` → 1〜2エントリの短い応答

**課題**:
- 応答が1〜2文で短い（イベント応答向けの設計）
- transcript解析が浅い（直近3ツール使用のみ）
- 毎回同じパターン（「○分作業中。直近の作業:…」）

## 設計方針

### アーキテクチャ

```
Claude Code Session
  → notify-prompt.py → POST /api/avatar/speak (作業開始報告: 既存維持)
  → /tmp/claude_working {start_time, transcript_path}
  → notify-stop.py → POST /api/avatar/speak (作業完了報告: 既存維持)
  → long-execution-timer.py → 3分間隔ステータス報告（既存維持、フォールバック）

Web Server:
  ClaudeWatcher (バックグラウンドサービス、新規)
    ├─ /tmp/claude_working を監視
    ├─ transcript JSONL を定期読み取り
    ├─ 直近の作業をサマリ化（ユーザーの指示 + 実行されたアクション）
    ├─ LLMで2キャラ会話を生成（2〜3往復 = 4発話）
    ├─ SpeechPipeline で順次再生（コメント割り込み対応）
    ├─ avatar_comments テーブルに保存（trigger_type="claude_work"）
    └─ 稼働中は long-execution-timer の報告を抑制
```

### 既存フックとの共存

既存フックは **疎結合設計**（stdlib only、サーバー依存なし）であり、この特性を壊さない。

| 仕組み | 役割 | 変更 |
|--------|------|------|
| `notify-prompt.py` | 作業開始を即時報告 | 変更なし |
| `notify-stop.py` | 作業完了を即時報告 | 変更なし |
| `long-execution-timer.py` | 長時間作業の定期報告 | **維持**（フォールバック）。ClaudeWatcher稼働中は抑制フラグで報告スキップ |
| ClaudeWatcher（新規） | 定期的に二人で作業内容を会話 | 新規追加（サーバー内バックグラウンドタスク） |

**共存の仕組み**:
- ClaudeWatcher起動時に `/tmp/claude_watcher_active` フラグファイルを作成
- `long-execution-timer.py` はこのフラグがあれば `speak()` をスキップ
- サーバーが落ちればフラグも消える → long-execution-timerがフォールバックとして機能

### 会話の特徴

- **2〜3往復（4発話）** の自然な会話（短すぎず長すぎない）
- 先生が作業内容を説明、生徒が質問や感想を言う
- 前回の会話内容を覚えていて繰り返さない
- 作業が進んでいなければ会話しない（変化検出）
- **コメント割り込み**: 各発話の前にコメントキューを確認し、コメントがあれば残り発話をスキップ

## 実装ステップ

### Step 1: TranscriptParser（transcript解析の強化）

**ファイル**: `src/claude_watcher.py`

transcript JSONL から意味のある作業サマリを抽出するパーサーを作る。

```python
@dataclass
class TranscriptSummary:
    user_prompt: str         # ユーザーの指示テキスト
    actions: list[str]       # 実行されたアクション一覧
    assistant_texts: list[str]  # アシスタントのテキスト応答
    line_count: int          # 解析した行数

class TranscriptParser:
    """Claude Code transcript (JSONL) を解析して作業サマリを生成する"""
    
    def __init__(self):
        self._last_line = 0  # 前回解析位置
    
    def parse(self, transcript_path: str) -> TranscriptSummary | None:
        """transcript_pathを前回位置以降から読み、サマリを返す。変化なしならNone"""
        # - ユーザーの指示（type="user" のテキスト部分）
        # - 実行されたツール（Bash, Edit, Write, Read, Grep, Agent等）
        # - アシスタントのテキスト応答（作業の説明部分）
        # - 未知のtypeはスキップ（フォーマット変更耐性）
```

**フォーマット変更への耐性**:
- 既知の `type` のみ処理、未知のtypeはスキップ（クラッシュしない）
- 各行のJSONパース失敗は個別にスキップ（1行の不正が全体を壊さない）
- パース成功率が50%未満になったらログ警告 + 会話生成を一時停止
- transcript JSONL の既知エントリtype: `user`, `assistant`, `system`, `file-history-snapshot`, `attachment`

既存の `long-execution-timer.py` の `get_recent_activity()` より踏み込んだ解析:
- ユーザーの指示テキストを抽出
- ツール使用を分類（ファイル操作 / コマンド実行 / 調査）
- アシスタントのテキスト応答（作業の説明部分）も抽出
- 前回解析位置を記憶して差分のみ解析

### Step 2: ClaudeWatcher サービス

**ファイル**: `src/claude_watcher.py`

```python
class ClaudeWatcher:
    """Claude Codeの作業を監視し、定期的に二人で会話する"""
    
    MARKER_FILE = "/tmp/claude_working"
    ACTIVE_FLAG = "/tmp/claude_watcher_active"  # long-execution-timer抑制用
    INTERVAL = 480           # 8分間隔（デフォルト）
    POLL_INTERVAL = 10       # マーカーファイル監視間隔（秒）
    MIN_ACTIONS = 3          # 会話を生成する最低アクション数
    MAX_UTTERANCES = 4       # 1回の会話の最大発話数（2往復）
    
    def __init__(self, speech: SpeechPipeline, comment_reader=None, on_overlay=None):
        self._speech = speech
        self._comment_reader = comment_reader  # コメントキュー確認用
        self._parser = TranscriptParser()
        self._running = False
        self._last_conversation = []  # 前回会話内容（繰り返し防止）
    
    async def start(self):
        """監視ループを開始"""
        self._running = True
        # ACTIVE_FLAGを作成（long-execution-timer抑制）
        # /tmp/claude_working の存在をPOLL_INTERVAL間隔でポーリング
        # 存在すればtranscript_pathを取得、INTERVAL間隔で解析→会話生成
    
    async def stop(self):
        """監視を停止"""
        self._running = False
        # ACTIVE_FLAGを削除
    
    async def _check_and_converse(self):
        """transcript差分を解析し、十分な変化があれば会話を生成・再生"""
        # 1. TranscriptParserで差分解析
        # 2. summary が None（変化なし）またはアクション数 < MIN_ACTIONS ならスキップ
        # 3. 会話を生成
        # 4. _play_conversation で再生
    
    async def _play_conversation(self, dialogues: list[dict]):
        """会話を順次再生する（コメント割り込み対応）"""
        for i, dlg in enumerate(dialogues):
            # ★ 各発話の前にコメントキューを確認（既存 queue_size プロパティを利用）
            if self._comment_reader and self._comment_reader.queue_size > 0:
                logger.info("[watcher] コメント到着 → 残り%d発話をスキップ", len(dialogues) - i)
                break
            # 感情適用 → speak() → 感情リセット → overlay end
            # DB保存（trigger_type="claude_work"、state.current_episode経由）
```

### Step 3: 会話生成プロンプト ✅

**ファイル**: `src/ai_responder.py` に `generate_claude_work_conversation()` 追加

`build_multi_system_prompt()` と同様のパターンで、作業実況専用のプロンプトを独自構築する。
コメント応答用のプロンプト（ペルソナ・記憶・SE・応答分配ガイド等）とは要件が異なるため、
`build_multi_system_prompt()` を直接呼ぶのではなく、同じ構造で必要なセクションのみ組み立てる。

```python
def generate_claude_work_conversation(
    summary: dict,           # {user_prompt, actions, assistant_texts, elapsed_min}
    characters: dict,        # {"teacher": config, "student": config}
    last_conversation: list, # 前回会話の内容（繰り返し防止）
) -> list[dict]:
```

**プロンプト構成**:
- キャラクター設定・感情一覧を `build_multi_system_prompt()` と同じ形式で構築
- 作業実況専用ルール（視聴者向け・カジュアル・技術的すぎない等）
- 言語ルール（`build_language_rules()` 再利用）
- 作業コンテキストはユーザープロンプトとして送信（指示・直近10アクション・Claudeメモ3件・経過時間）
- `_validate_multi_response()` でspeaker/emotion検証（**既存再利用**）
- 日本語/英語の両言語モード対応

**`ClaudeWatcher._generate_conversation()` との接続**:
- `get_chat_characters()` でキャラ設定取得
- `asyncio.to_thread()` で同期LLM呼び出しを非ブロッキング実行
- エラー時は `None` 返却（発話スキップ）

**会話ルール**（プロンプトに含める）:
- 2〜3往復（最大4発話）の自然な会話
- 先生はプログラミングに詳しく、作業内容を自然に説明
- 生徒は興味深そうに質問したり感想を言う
- 配信を見ている視聴者にもわかるように
- 技術的すぎない、カジュアルな口調
- 各発話は1〜2文、40文字以内

**繰り返し防止**: `last_conversation` の直近4発話をプロンプトに含め「同じ表現を避ける」指示

### Step 4: CommentReaderとの統合（コメント割り込み対応） ✅

**ファイル**: `src/comment_reader.py`

```python
class CommentReader:
    def __init__(self, ...):
        ...
        self._claude_watcher = ClaudeWatcher(
            speech=self._speech,
            comment_reader=self,  # コメントキュー参照を渡す（queue_sizeプロパティを利用）
            on_overlay=on_overlay,
        )
    
    # has_pending_comments() は不要 — 既存の queue_size プロパティで判定
    
    async def start(self):
        ...
        self._watcher_task = asyncio.create_task(self._claude_watcher.start())
    
    async def stop(self):
        ...
        await self._claude_watcher.stop()
```

**コメント割り込みの仕組み**:
1. ClaudeWatcherの `_play_conversation()` は各発話の前に `queue_size > 0` を確認
2. コメントがあれば残りの発話をスキップし、SpeechPipelineのロックを解放
3. CommentReaderの `_process_loop()` が次のイテレーションでコメントを処理
4. **SpeechPipelineのロック自体は変更しない**（既存のシリアライズは維持）

**優先度**: コメント応答 > 授業 > ClaudeWatcher会話 > long-execution-timer

### Step 5: long-execution-timer.py との共存

**変更ファイル**: `~/.claude/hooks/long-execution-timer.py`（最小限の変更）

```python
# long-execution-timer.py に追加（speak()の前）
WATCHER_FLAG = "/tmp/claude_watcher_active"

def speak(message):
    # ClaudeWatcherが稼働中なら報告をスキップ
    if os.path.exists(WATCHER_FLAG):
        return
    # ... 既存のspeak処理 ...
```

- `notify-prompt.py` と `notify-stop.py` は**変更なし**
- long-execution-timerは削除せず、フラグチェックのみ追加
- サーバーが落ちた場合 → フラグが消える → long-execution-timerが自動的にフォールバック

### Step 6: 管理画面UI

**ファイル**: `scripts/routes/avatar.py`, `static/index.html`

- `GET /api/claude-watcher/status` — 現在の監視状態・直近の会話・transcript解析結果
- `POST /api/claude-watcher/config` — 間隔・有効/無効の設定
- 管理画面に監視ステータス表示

### Step 7: テスト（残り）

**ファイル**: `tests/test_claude_watcher.py`

TranscriptParser（19テスト）とClaudeWatcherサービス（20テスト）はStep 1・2で実装済み。
Step 7 では以下の残りテストを追加する:

- **会話生成**: LLMモック経由でJSON配列の検証（Step 3実装後）
- **CommentReader統合**: ClaudeWatcherの起動・停止がCommentReaderと連動（Step 4実装後）

## 設定

```python
# scenes.json または DB (settings テーブル)
{
    "claude_watcher": {
        "enabled": true,
        "interval_seconds": 480,      # 会話間隔（デフォルト8分）
        "min_actions": 3,             # 会話生成に必要な最低アクション数
        "max_utterances": 4,          # 1回の会話の最大発話数（2往復）
    }
}
```

## リスク・注意点

1. **transcript_pathはClaude Code内部ファイル** — パスや形式が変わる可能性がある。パース失敗は個別行スキップ、成功率低下で一時停止
2. **発話キューの競合** — 各発話前にコメントキューを確認し、コメント優先でスキップ。SpeechPipelineのロック自体は変更しない
3. **会話の品質** — 前回会話と差分情報をプロンプトに含めて繰り返しを防止
4. **ClaudeCode非稼働時** — マーカーファイルがなければ何もしない。LLM呼び出しコストを無駄にしない
5. **サーバー停止時のフォールバック** — long-execution-timerが自動復帰（フラグファイル消失で抑制解除）

## ファイル変更一覧

| ファイル | 変更内容 |
|---------|---------|
| `src/claude_watcher.py` | TranscriptParser（Step 1済）+ ClaudeWatcher（Step 2済） |
| `src/ai_responder.py` | `generate_claude_work_conversation()` 追加（`build_multi_system_prompt()` ベース） |
| `src/comment_reader.py` | ClaudeWatcher統合（既存 `queue_size` で割り込み判定） |
| `scripts/routes/avatar.py` | `/api/claude-watcher/*` エンドポイント追加 |
| `static/index.html` | 監視ステータスUI |
| `~/.claude/hooks/long-execution-timer.py` | フラグチェック追加（ACTIVE_FLAG存在時はスキップ） |
| `tests/test_claude_watcher.py` | TranscriptParser 19テスト（Step 1済）+ ClaudeWatcher 20テスト（Step 2済）+ 残りはStep 7 |
