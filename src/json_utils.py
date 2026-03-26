"""LLMレスポンス用JSON修復パーサー"""

import json
import logging
import re

from json_repair import repair_json

logger = logging.getLogger(__name__)


def parse_llm_json(text: str):
    """LLMレスポンスからJSONをパースする。壊れたJSONは自動修復する。

    1. ```json ... ``` コードブロックを除去
    2. json.loads() を試行
    3. 失敗したら json_repair.repair_json() で修復してリトライ

    Returns:
        パースされたJSON（dict, list, 等）

    Raises:
        json.JSONDecodeError: 修復後もパースに失敗した場合
    """
    text = text.strip()
    # ```json ... ``` コードブロックを除去
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    text = re.sub(r'^```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?\s*```$', '', text)

    # まず通常のパースを試行
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # 修復してリトライ
    logger.info("[json-repair] JSON修復を試行中... (先頭200文字: %s)", text[:200])
    repaired = repair_json(text, return_objects=True)
    logger.info("[json-repair] 修復成功 (type=%s)", type(repaired).__name__)
    return repaired
