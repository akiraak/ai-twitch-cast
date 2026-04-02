"""Claude Code作業監視 — transcript解析・会話生成・二人実況

Claude Codeのtranscript（JSONL）を解析し、作業内容のサマリを生成する。
ClaudeWatcherサービスが定期的に二人の会話を生成・再生する。
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field

from src import db

logger = logging.getLogger(__name__)

# transcript JSONLの既知エントリtype
KNOWN_TYPES = {"user", "assistant", "system", "file-history-snapshot", "attachment"}


@dataclass
class TranscriptSummary:
    """transcript解析結果のサマリ"""

    user_prompt: str  # ユーザーの最新の指示テキスト
    actions: list[str] = field(default_factory=list)  # 実行されたアクション一覧
    assistant_texts: list[str] = field(default_factory=list)  # アシスタントのテキスト応答
    line_count: int = 0  # 解析した行数


class TranscriptParser:
    """Claude Code transcript (JSONL) を解析して作業サマリを生成する。

    前回解析位置を記憶し、差分のみを解析する。
    """

    def __init__(self):
        self._last_line: int = 0  # 前回解析済み行数

    def parse(self, transcript_path: str) -> TranscriptSummary | None:
        """transcript_pathを前回位置以降から読み、サマリを返す。

        変化がなければNoneを返す。ファイルが存在しない場合もNone。
        """
        if not transcript_path or not os.path.exists(transcript_path):
            return None

        try:
            with open(transcript_path) as f:
                all_lines = f.readlines()
        except (OSError, PermissionError) as e:
            logger.warning("[watcher] transcript読み込み失敗: %s", e)
            return None

        total_lines = len(all_lines)
        if total_lines <= self._last_line:
            return None  # 変化なし

        new_lines = all_lines[self._last_line :]
        prev_last_line = self._last_line
        self._last_line = total_lines

        # 新しい行を解析
        user_prompt = ""
        actions: list[str] = []
        assistant_texts: list[str] = []
        parsed_ok = 0
        parsed_fail = 0

        for line in new_lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                parsed_ok += 1
            except (json.JSONDecodeError, ValueError):
                parsed_fail += 1
                continue

            entry_type = entry.get("type")
            if entry_type not in KNOWN_TYPES:
                continue

            if entry_type == "user":
                user_prompt = self._extract_user_prompt(entry, user_prompt)

            elif entry_type == "assistant":
                self._extract_assistant_content(entry, actions, assistant_texts)

        # パース成功率チェック
        total_parsed = parsed_ok + parsed_fail
        if total_parsed > 0 and parsed_ok / total_parsed < 0.5:
            logger.warning(
                "[watcher] transcript解析成功率が低い: %d/%d (%.0f%%)",
                parsed_ok,
                total_parsed,
                parsed_ok / total_parsed * 100,
            )
            # 位置を戻さない（次回リトライしても同じ結果になるため）
            return None

        line_count = total_lines - prev_last_line
        if not user_prompt and not actions and not assistant_texts:
            return None

        return TranscriptSummary(
            user_prompt=user_prompt,
            actions=actions,
            assistant_texts=assistant_texts,
            line_count=line_count,
        )

    def reset(self):
        """解析位置をリセットする"""
        self._last_line = 0

    def _extract_user_prompt(self, entry: dict, current_prompt: str) -> str:
        """userエントリからユーザーの指示テキストを抽出する。

        isMeta=true やコマンド(<command-name>)、ツール結果はスキップ。
        最後に見つかったユーザー指示を返す。
        """
        if entry.get("isMeta"):
            return current_prompt

        content = entry.get("message", {}).get("content", "")

        # 文字列コンテンツ（直接の指示テキスト）
        if isinstance(content, str):
            text = content.strip()
            # コマンド系やシステムメッセージはスキップ
            if text.startswith("<command-name>") or text.startswith("<local-command"):
                return current_prompt
            if len(text) > 0:
                return text

        # リスト形式（tool_resultなど）はスキップ
        return current_prompt

    def _extract_assistant_content(
        self,
        entry: dict,
        actions: list[str],
        assistant_texts: list[str],
    ):
        """assistantエントリからツール使用とテキスト応答を抽出する"""
        content = entry.get("message", {}).get("content", [])
        if not isinstance(content, list):
            return

        for item in content:
            if not isinstance(item, dict):
                continue

            item_type = item.get("type")

            if item_type == "tool_use":
                action = self._describe_tool_use(item)
                if action:
                    actions.append(action)

            elif item_type == "text":
                text = item.get("text", "").strip()
                if len(text) > 10:
                    assistant_texts.append(text)

    def _describe_tool_use(self, item: dict) -> str:
        """ツール使用を人間可読な説明文に変換する"""
        tool = item.get("name", "")
        tool_input = item.get("input", {})

        if tool == "Bash":
            cmd = tool_input.get("command", "")
            return f"コマンド実行: {cmd[:80]}"
        elif tool == "Edit":
            path = tool_input.get("file_path", "")
            return f"ファイル編集: {os.path.basename(path)}"
        elif tool == "Write":
            path = tool_input.get("file_path", "")
            return f"ファイル作成: {os.path.basename(path)}"
        elif tool == "Read":
            path = tool_input.get("file_path", "")
            return f"ファイル読み取り: {os.path.basename(path)}"
        elif tool in ("Grep", "Glob"):
            pattern = tool_input.get("pattern", "")
            return f"コード検索: {pattern[:50]}"
        elif tool == "Agent":
            desc = tool_input.get("description", "")
            return f"サブエージェント: {desc[:50]}"
        elif tool:
            return f"{tool}を使用"
        return ""


class ClaudeWatcher:
    """Claude Codeの作業を監視し、定期的に二人で会話する。

    /tmp/claude_working マーカーファイルをポーリングし、transcript JSONL を
    定期的に解析して、十分な作業変化があれば二人の会話を生成・再生する。
    """

    MARKER_FILE = "/tmp/claude_working"
    ACTIVE_FLAG = "/tmp/claude_watcher_active"  # long-execution-timer抑制用
    INTERVAL = 480  # 会話生成間隔（秒、デフォルト8分）
    POLL_INTERVAL = 10  # マーカーファイル監視間隔（秒）
    MIN_ACTIONS = 3  # 会話を生成する最低アクション数
    MAX_UTTERANCES = 4  # 1回の会話の最大発話数（2往復）

    def __init__(self, speech, comment_reader=None, on_overlay=None):
        """
        Args:
            speech: SpeechPipeline インスタンス
            comment_reader: CommentReader インスタンス（コメント割り込み判定用）
            on_overlay: オーバーレイ送信コールバック
        """
        self._speech = speech
        self._comment_reader = comment_reader
        self._on_overlay = on_overlay
        self._parser = TranscriptParser()
        self._running = False
        self._task = None
        self._last_conversation: list[str] = []  # 前回会話内容（繰り返し防止）
        self._transcript_path: str | None = None
        self._start_time: float | None = None

    async def start(self):
        """監視ループを開始する"""
        if self._running:
            return
        self._running = True
        # ACTIVE_FLAG作成（long-execution-timerを抑制）
        try:
            with open(self.ACTIVE_FLAG, "w") as f:
                f.write(str(os.getpid()))
        except OSError:
            pass
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("[watcher] ClaudeWatcher開始")

    async def stop(self):
        """監視を停止する"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        # ACTIVE_FLAG削除（long-execution-timerのフォールバック復帰）
        try:
            os.remove(self.ACTIVE_FLAG)
        except FileNotFoundError:
            pass
        self._parser.reset()
        self._transcript_path = None
        self._start_time = None
        logger.info("[watcher] ClaudeWatcher停止")

    async def _monitor_loop(self):
        """マーカーファイルをポーリングし、INTERVAL間隔で解析・会話する"""
        last_converse_time = 0.0

        try:
            while self._running:
                if os.path.exists(self.MARKER_FILE):
                    try:
                        with open(self.MARKER_FILE) as f:
                            marker = json.loads(f.read())
                        new_path = marker.get("transcript_path", "")
                        new_start = marker.get("start_time", 0)

                        # セッションが変わったらパーサーリセット
                        if new_path and new_path != self._transcript_path:
                            self._parser.reset()
                            self._last_conversation = []
                            last_converse_time = 0.0
                            logger.info("[watcher] 新セッション検出: %s", os.path.basename(new_path))

                        self._transcript_path = new_path
                        self._start_time = new_start
                    except (json.JSONDecodeError, OSError) as e:
                        logger.debug("[watcher] マーカーファイル読み込み失敗: %s", e)

                    # INTERVAL経過したら会話生成を試行
                    now = time.time()
                    if self._transcript_path and (now - last_converse_time) >= self.INTERVAL:
                        await self._check_and_converse()
                        last_converse_time = time.time()
                else:
                    # マーカーファイルなし → セッションリセット
                    if self._transcript_path:
                        logger.info("[watcher] セッション終了")
                        self._parser.reset()
                        self._transcript_path = None
                        self._start_time = None
                        self._last_conversation = []

                await asyncio.sleep(self.POLL_INTERVAL)
        except asyncio.CancelledError:
            pass

    async def _check_and_converse(self):
        """transcript差分を解析し、十分な変化があれば会話を生成・再生する"""
        summary = self._parser.parse(self._transcript_path)

        if summary is None:
            logger.debug("[watcher] 変化なし → スキップ")
            return

        if len(summary.actions) < self.MIN_ACTIONS:
            logger.info(
                "[watcher] アクション数不足 (%d < %d) → スキップ",
                len(summary.actions),
                self.MIN_ACTIONS,
            )
            return

        # 経過時間
        elapsed_min = int((time.time() - self._start_time) / 60) if self._start_time else 0

        # 会話を生成（Step 3 で実装予定）
        dialogues = await self._generate_conversation(summary, elapsed_min)
        if not dialogues:
            return

        logger.info("[watcher] 会話生成OK: %d発話", len(dialogues))
        await self._play_conversation(dialogues)

        # 今回の会話を記憶（繰り返し防止）
        self._last_conversation = [d.get("speech", "") for d in dialogues]

    async def _generate_conversation(self, summary, elapsed_min):
        """作業サマリから二人の会話を生成する。

        Returns:
            list[dict] | None: [{"speaker", "speech", "tts_text", "emotion"}, ...] or None
        """
        # Step 3 で generate_claude_work_conversation() を実装する
        logger.info(
            "[watcher] 会話生成は未実装（Step 3待ち）: actions=%d, elapsed=%dm, prompt=%s",
            len(summary.actions),
            elapsed_min,
            summary.user_prompt[:60],
        )
        return None

    async def _play_conversation(self, dialogues):
        """会話を順次再生する（コメント割り込み対応）。

        各発話の前にコメントキューを確認し、コメントがあれば残り発話をスキップする。
        """
        from src.ai_responder import get_chat_characters

        try:
            characters = get_chat_characters()
        except Exception:
            characters = {}

        for i, dlg in enumerate(dialogues):
            # コメント割り込みチェック
            if self._comment_reader and self._comment_reader.queue_size > 0:
                logger.info(
                    "[watcher] コメント到着 → 残り%d発話をスキップ",
                    len(dialogues) - i,
                )
                break

            speaker = dlg.get("speaker", "teacher")
            cfg = characters.get(speaker, characters.get("teacher", {}))

            # キャラ間の間
            if i > 0:
                await asyncio.sleep(0.3)

            try:
                self._speech.apply_emotion(
                    dlg.get("emotion", "neutral"),
                    avatar_id=speaker,
                    character_config=cfg,
                )
                await self._speech.speak(
                    dlg["speech"],
                    subtitle={
                        "author": cfg.get("name", speaker),
                        "trigger_text": "[Claude Code実況]",
                        "result": dlg,
                    },
                    tts_text=dlg.get("tts_text"),
                    voice=cfg.get("tts_voice"),
                    style=cfg.get("tts_style"),
                    avatar_id=speaker,
                )
                self._speech.apply_emotion(
                    "neutral", avatar_id=speaker, character_config=cfg,
                )
                await self._speech.notify_overlay_end()

                # DB保存（trigger_type="claude_work"）
                await self._save_avatar_comment(
                    "claude_work",
                    "[Claude Code実況]",
                    dlg["speech"],
                    dlg.get("emotion", "neutral"),
                    speaker=speaker,
                )
            except Exception as e:
                logger.error("[watcher] 発話失敗: %s", e, exc_info=True)
                break

    async def _save_avatar_comment(
        self, trigger_type, trigger_text, text, emotion="neutral", speaker=None,
    ):
        """アバターコメントをDBに保存する"""
        try:
            from scripts import state

            if state.current_episode:
                await asyncio.to_thread(
                    db.save_avatar_comment,
                    state.current_episode["id"],
                    trigger_type,
                    trigger_text,
                    text,
                    emotion,
                    speaker=speaker,
                )
        except Exception as e:
            logger.warning("[watcher] DB保存失敗: %s", e)

    @property
    def is_active(self):
        """Claude Codeセッションを監視中か"""
        return self._running and self._transcript_path is not None

    @property
    def status(self):
        """現在の監視ステータスを返す"""
        elapsed = None
        if self._start_time:
            elapsed = int(time.time() - self._start_time)
        return {
            "running": self._running,
            "active": self.is_active,
            "transcript_path": self._transcript_path,
            "start_time": self._start_time,
            "elapsed_seconds": elapsed,
            "last_conversation": self._last_conversation,
        }
