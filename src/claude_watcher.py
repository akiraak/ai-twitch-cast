"""Claude Code作業監視 — transcript解析・会話生成

Claude Codeのtranscript（JSONL）を解析し、作業内容のサマリを生成する。
"""

import json
import logging
import os
from dataclasses import dataclass, field

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
