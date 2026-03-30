# セクション間の会話つながり改善プラン

## Context
TODO 1.4「セクションごとの会話のつながりが不自然なのを解決する」

**問題**: Phase B-2（セリフ生成）で各セクションが完全に独立して並列生成されるため、前後のセクションとの会話のつながりが不自然になる。

**原因**: `_generate_single_dialogue()` のプロンプトに前後セクションの情報が一切含まれていない。Phase Aの監督は全セクションを一括設計しているが、実際のセリフ生成時にその「つながり」の意図が失われる。

**方針**: 2つの相補的アプローチで対応
1. **Phase A強化**: 監督プロンプトに「セクション間のつなぎ指示を dialogue_directions に含めよ」と明記
2. **Phase B-2強化**: セリフ生成時のプロンプトに前後セクションのメタデータ（title + display_text）を注入

**並列生成は維持**: 前後セクションの title/display_text/section_type は Phase A で確定済みの静的データなので、並列生成を壊さない。

---

## 実装ステップ

### Step 1: ヘルパー関数 `_build_adjacent_sections()` を追加 ✅ 完了
**ファイル**: `src/lesson_generator.py:1709` (`_generate_single_dialogue`の直前)

### Step 2: `_generate_single_dialogue()` に `adjacent_sections` パラメータ追加 ✅ 完了
**ファイル**: `src/lesson_generator.py:1734`

- 引数に `adjacent_sections: dict | None = None` を追加
- EN/JAの両方のプロンプト構築部分で、`# Section:` の直後に前後セクション情報を注入

注入するプロンプト（JA版、`section_type` の後）:
```
# セクション位置: 2 / 8
# 前のセクション [introduction]: 英語の挨拶
#   内容: 今日のテーマ: 英語の挨拶...（display_text先頭200文字）
# 次のセクション [example]: カジュアル表現
#   内容: カジュアルな挨拶表現の比較...（display_text先頭200文字）
```

display_textは200文字で切り詰め（プロンプト肥大化防止）。

### Step 3: `_generate_section_dialogues()` に `adjacent_sections` パラメータを通す ✅ 完了
**ファイル**: `src/lesson_generator.py:1878`

- 引数に `adjacent_sections: dict | None = None` を追加
- `_generate_single_dialogue()` 呼び出し時に渡す

### Step 4: `section_worker()` と `regen_worker()` で隣接情報を構築・渡す ✅ 完了
**ファイル**: `src/lesson_generator.py`
- `section_worker()` (line 2294): `_build_adjacent_sections(structure_sections, sec_idx)` を呼んで `_generate_section_dialogues()` に渡す
- `regen_worker()` (line 2370): 同様

### Step 5: 監督 Phase A プロンプトに「つなぎ指示」を追加 ✅ 完了
**ファイル**: `src/lesson_generator.py`

EN版 (line 710 の後、Output format の前に挿入):
```
### Section transitions (IMPORTANT)
- For sections after the first: include a transition cue in the FIRST dialogue_direction entry that references the previous section
  - Example: direction: "Briefly reference the greeting patterns from the previous section, then transition to informal alternatives"
- For sections before the last: include a forward-looking cue in the LAST dialogue_direction entry
  - Example: direction: "Wrap up and tease the next topic — casual slang expressions"
- These cues ensure natural flow when each section's dialogue is generated independently
```

JA版 (line 805 の後、出力形式の前に挿入):
```
### セクション間のつなぎ（重要）
- 最初以外のセクション: 最初の dialogue_direction に、前セクションの内容を参照するつなぎを含めること
  - 例: direction: 「先ほどの挨拶パターンに軽く触れつつ、カジュアルな表現の説明へ移る」
- 最後以外のセクション: 最後の dialogue_direction に、次セクションへの予告を含めること
  - 例: direction: 「まとめた上で、次のスラング表現について軽く予告する」
- セリフは各セクション独立で生成されるため、これらのつなぎ指示が自然な流れを作る鍵となる
```

### Step 6: テスト追加
**ファイル**: `tests/test_lesson_generator.py`

- `test_build_adjacent_sections`: ヘルパーのユニットテスト（先頭/中間/末尾）
- `test_adjacent_sections_in_prompt_ja`: JA版プロンプトに前後情報が含まれるか
- `test_adjacent_sections_in_prompt_en`: EN版同様
- `test_adjacent_sections_none_no_change`: None の場合に余計な情報が含まれないか
- `test_adjacent_sections_first_no_prev`: 先頭セクションは prev なし
- `test_adjacent_sections_last_no_next`: 末尾セクションは next なし

---

## 検証方法

1. `python3 -m pytest tests/ -q` — 全テスト通過
2. 管理画面から授業を生成し、生成されたセリフの `generation.user_prompt` に前後セクション情報が含まれていることを確認
3. 生成されたセリフを通して読み、セクション間のつながりが自然になったか手動確認

## 修正対象ファイル
- `src/lesson_generator.py` — メイン変更（Step 1-5）
- `tests/test_lesson_generator.py` — テスト追加（Step 6）
