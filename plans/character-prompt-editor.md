# プラン: AIによるキャラクタープロンプト編集

ステータス: 未着手

## Context

管理画面のキャラクター設定で、既存のシステムプロンプトに対して修正指示を送り、AIに修正してもらう機能を追加する。

## UI

システムプロンプトtextareaの下に、折りたたみ式のAI修正パネルを配置:

```html
<details class="ai-edit-panel">
  <summary>AIに修正してもらう</summary>
  <textarea id="ai-edit-instruction" rows="3" class="text-input"
            placeholder="例: もっとツッコミを強調して / テンション高めにして / 英語に翻訳して"></textarea>
  <button onclick="aiEditPrompt()">修正を実行</button>
  <div id="ai-edit-preview" style="display:none;">
    <textarea id="ai-edit-result" rows="12" readonly></textarea>
    <button onclick="applyAiEdit()">この内容を適用</button>
    <button onclick="cancelAiEdit()">やり直し</button>
  </div>
</details>
```

## API

`POST /api/character/{character_id}/prompt/ai-edit`

```python
class PromptEditRequest(BaseModel):
    current_text: str
    instruction: str
    lang: str = "ja"  # "ja", "en", "bilingual"
```

AIが現在のテキストを修正指示に従って書き換え、修正後テキストを返す。言語に応じたシステムプロンプトで出力言語を制御。

## 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `static/index.html` | AI修正パネルUI |
| `static/js/admin/character.js` | AI修正リクエスト + プレビュー適用 |
| `scripts/routes/character.py` | `POST /api/character/{id}/prompt/ai-edit` エンドポイント追加 |
