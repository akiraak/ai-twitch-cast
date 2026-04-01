"""プロンプトファイル管理ルート（prompts/ ディレクトリの閲覧・編集・AI編集）"""

import difflib
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Body
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"


def _validate_name(name: str) -> Path | None:
    """ファイル名を検証し、安全なPathを返す。不正ならNone"""
    if not name or ".." in name or not name.endswith(".md"):
        return None
    target = (PROMPTS_DIR / name).resolve()
    if not str(target).startswith(str(PROMPTS_DIR.resolve())):
        return None
    return target


@router.get("/api/prompts")
async def list_prompts():
    """prompts/ 内のmdファイル一覧を返す"""
    if not PROMPTS_DIR.is_dir():
        return {"ok": True, "files": []}

    files = []
    for p in sorted(PROMPTS_DIR.rglob("*.md")):
        rel = p.relative_to(PROMPTS_DIR)
        stat = p.stat()
        title = ""
        try:
            with p.open("r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line.startswith("# "):
                    title = first_line[2:].strip()
        except Exception:
            pass
        files.append({
            "name": str(rel),
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "title": title,
        })

    return {"ok": True, "files": files}


@router.get("/api/prompts/{name:path}")
async def get_prompt(name: str):
    """プロンプトファイルの内容を返す"""
    target = _validate_name(name)
    if target is None:
        return PlainTextResponse("不正なファイル名です", status_code=400)
    if not target.is_file():
        return PlainTextResponse("ファイルが見つかりません", status_code=404)
    return PlainTextResponse(target.read_text(encoding="utf-8"))


@router.put("/api/prompts/{name:path}")
async def update_prompt(name: str, content: str = Body(..., media_type="text/plain")):
    """プロンプトファイルの内容を上書き保存"""
    target = _validate_name(name)
    if target is None:
        return {"ok": False, "error": "不正なファイル名です"}
    if not target.is_file():
        return {"ok": False, "error": "ファイルが見つかりません"}

    target.write_text(content, encoding="utf-8")
    logger.info("プロンプト更新: %s (%d bytes)", name, len(content))
    return {"ok": True}


def _make_diff_html(original: str, modified: str) -> str:
    """unified diff をHTMLに変換する"""
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    diff = difflib.unified_diff(orig_lines, mod_lines, fromfile="変更前", tofile="変更後")

    html_parts = []
    for line in diff:
        line_stripped = line.rstrip("\n")
        if line.startswith("+++") or line.startswith("---"):
            html_parts.append(
                f'<div class="diff-line-ctx">{_escape_html(line_stripped)}</div>'
            )
        elif line.startswith("+"):
            html_parts.append(
                f'<div class="diff-line-add">{_escape_html(line_stripped)}</div>'
            )
        elif line.startswith("-"):
            html_parts.append(
                f'<div class="diff-line-del">{_escape_html(line_stripped)}</div>'
            )
        elif line.startswith("@@"):
            html_parts.append(
                f'<div class="diff-line-ctx" style="color:#7b1fa2">{_escape_html(line_stripped)}</div>'
            )
        else:
            html_parts.append(
                f'<div class="diff-line-ctx">{_escape_html(line_stripped)}</div>'
            )

    return "\n".join(html_parts)


def _escape_html(text: str) -> str:
    """HTMLエスケープ"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@router.post("/api/prompts/ai-edit")
async def ai_edit_prompt(body: dict = Body(...)):
    """AI指示でプロンプトを編集する（差分プレビュー）"""
    name = body.get("name", "")
    instruction = body.get("instruction", "")

    if not instruction:
        return {"ok": False, "error": "指示を入力してください"}

    target = _validate_name(name)
    if target is None:
        return {"ok": False, "error": "不正なファイル名です"}
    if not target.is_file():
        return {"ok": False, "error": "ファイルが見つかりません"}

    original = target.read_text(encoding="utf-8")

    try:
        from google.genai import types
        from src.gemini_client import get_client

        client = get_client()
        model = os.environ.get("GEMINI_CHAT_MODEL", "gemini-3-flash-preview")

        system_prompt = (
            "あなたはプロンプトエンジニアです。"
            "ユーザーの指示に従って、与えられたプロンプトファイルを編集してください。\n"
            "修正後のファイル全文のみを出力してください。説明やコメントは不要です。"
        )

        user_content = (
            f"## 現在のプロンプトファイル内容\n\n```\n{original}\n```\n\n"
            f"## 編集指示\n\n{instruction}"
        )

        response = client.models.generate_content(
            model=model,
            contents=[user_content],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.3,
            ),
        )

        modified = response.text.strip()
        # コードブロックで囲まれている場合は除去
        if modified.startswith("```") and modified.endswith("```"):
            lines = modified.split("\n")
            modified = "\n".join(lines[1:-1])

        diff_html = _make_diff_html(original, modified)

        return {
            "ok": True,
            "original": original,
            "modified": modified,
            "diff_html": diff_html,
        }

    except Exception as e:
        logger.exception("AI編集エラー")
        return {"ok": False, "error": str(e)}
