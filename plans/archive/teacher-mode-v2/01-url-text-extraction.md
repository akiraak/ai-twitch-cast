# URLテキスト抽出改善

## ステータス: 未着手

## 背景

`extract_text_from_url()` は httpx で生HTML取得→先頭30,000文字をGeminiに丸投げしている。
広告・ナビ・スクリプト等のノイズがGeminiのトークンを浪費し、抽出品質も不安定。

## 現状のコード（`src/lesson_generator.py:69-89`）

```python
async def extract_text_from_url(url: str) -> str:
    async with httpx.AsyncClient(...) as http:
        resp = await http.get(url, ...)
        html = resp.text
    # 生HTMLの先頭30kをGeminiに投げる
    response = client.models.generate_content(
        model=_get_model(),
        contents=f"...HTMLからテキストを抽出...\n\n{html[:30000]}",
    )
    return response.text.strip()
```

## 改善内容

BeautifulSoup（requirements.txtに `beautifulsoup4>=4.12.0` として既存）でHTML前処理してからGeminiに送信する。

### 処理フロー

```
URL → httpx取得 → BeautifulSoup前処理 → クリーンテキスト → Gemini整形 → 結果
```

### BeautifulSoup前処理の詳細

1. **除去する要素**: `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`, `<iframe>`, `<aside>`, `<form>`, `.sidebar`, `.ad`, `.advertisement`, `.menu`, `.breadcrumb`
2. **優先抽出**: `<article>`, `<main>`, `[role="main"]`, `.entry-content`, `.post-content`, `.article-body` を探す。見つかればそこだけ使う
3. **テキスト取得**: `.get_text(separator='\n', strip=True)` でプレーンテキスト化
4. **フォールバック**: セマンティック要素が見つからない場合は `<body>` 全体から除去後のテキストを使用
5. **結果が十分なら**（例: 200文字以上）Gemini呼び出しをスキップして直接返す。短すぎる場合のみGeminiで補完

### 変更対象

- `src/lesson_generator.py` — `extract_text_from_url()` の内部ロジック変更のみ
- テスト追加: `tests/test_api_teacher.py` にURL抽出のモックテスト

## リスク

- サイトによってはセマンティック要素がなくフォールバックに頼る → 現行より悪化はしない
- JavaScript描画のSPA系サイトはhttpxでは取得できない → 現状と同じ制約
