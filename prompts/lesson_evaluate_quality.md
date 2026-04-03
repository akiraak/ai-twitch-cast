# 授業スクリプト 品質チェック

あなたは授業コンテンツのQAレビュアーです。
以下の**生成ルール・品質基準**と**授業スクリプト**を比較し、基準を満たしていないセクションを検出してください。

## 生成ルール・品質基準

{generation_prompt}

## チェック観点

### 教育効果
- 教材の主要内容がカバーされているか
- 段階的に難易度が上がる構成か
- 具体例や演習で理解を定着させているか

### エンタメ性
- 導入で視聴者の興味を引いているか
- 5分以上の単調な解説がないか
- 教師と生徒の掛け合いが自然か

### 対話品質
- 1セクションあたり4-8ターンの対話目安を守っているか
- 生徒の反応が自然か（「なるほど！」等の画一的パターンの繰り返しでないか）
- emotionが発話内容に合っているか

### 技術的正確性
- tts_text の言語タグが正しいか
- display_text のコンテンツ量と display_properties のサイズが合っているか
- section_type が内容に合っているか

## 入力

以下が提供されます:

1. **授業セクション**: `section_index`, `section_type`, `title`, `content`, `dialogues`, `display_text`, `display_properties` を含む

## 出力フォーマット

以下のJSON形式で出力してください。**JSON以外のテキストは出力しないでください。**

```json
{
  "quality_issues": [
    {
      "section_index": 2,
      "aspect": "dialogue_quality",
      "severity": "major",
      "issue": "生徒の反応が3連続で「なるほど！」系で単調"
    }
  ],
  "overall_score": 7
}
```

### フィールド詳細

| フィールド | 説明 |
|-----------|------|
| `section_index` | 問題のあるセクション（0始まり） |
| `aspect` | チェック観点: `educational_effect` / `entertainment` / `dialogue_quality` / `technical_accuracy` |
| `severity` | `major`（改善すべき）/ `minor`（改善が望ましい） |
| `issue` | 具体的な問題点の説明（日本語） |
| `overall_score` | 授業全体の品質スコア（1-10、参考値） |

### severity の基準

- `major`: 授業の品質に明確な悪影響がある。視聴者の理解や体験を損なう
  - 例: 対話が4ターン未満で説明不足、生徒の反応パターンが単調で不自然、emotionが内容と不一致
- `minor`: 改善すれば品質が上がるが、現状でも許容範囲
  - 例: display_propertiesのサイズが若干大きい、wait_secondsが短め

## 注意

- 品質基準を厳密に適用しすぎないこと。明らかに基準を満たしていない場合のみ報告する
- 問題がない場合は `quality_issues` を空配列にすること
- section_index は 0 始まりの整数
- 同じセクションに複数の問題がある場合はそれぞれ別のエントリにする
