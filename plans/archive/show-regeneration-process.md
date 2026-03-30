# 再生成過程の管理画面表示

## ステータス: 完了

## 背景

監督レビュー（Phase B-3）で不合格になったセクションは Phase B-4 で再生成されるが、現状では管理画面で以下が確認できない：

- 再生成**前**のセリフ（元のセリフ）
- 再生成に使われた `revised_directions`（監督が書き換えた演出指示）
- 再生成時の各セリフの generation メタデータ（プロンプト・LLM出力）
- 元のセリフと再生成後のセリフの比較

現状表示できているもの：
- 監督レビューの合格/不合格・フィードバック
- レビュープロンプト（system/user/raw_output）

## 方針

データ保存（バックエンド）→ 管理画面表示（フロントエンド）の順で実装。

## 実装ステップ

### Step 1: 元のセリフを保存（バックエンド）

`src/lesson_generator.py` の Phase B-4（`regen_worker`）で、再生成**前**のセリフを `original_dialogues` として保存する。

```python
# regen_worker 内
original = section_dialogues[idx]  # 再生成前を退避
new_dialogues = _generate_section_dialogues(...)
return idx, new_dialogues, original  # 元セリフも返す
```

結果の組み立てで `dialogues_with_meta` に追加：
```python
dialogues_with_meta = {
    "dialogues": dialogues,           # 再生成後（最終版）
    "original_dialogues": original,   # 再生成前（不合格だったセリフ）
    "review": review_data,
    ...
}
```

### Step 2: revised_directions を保存（バックエンド）

`review_data` に `revised_directions` も含める：

```python
review_data = {
    "approved": ...,
    "feedback": ...,
    "is_regenerated": ...,
    "revised_directions": review_info.get("revised_directions", []),  # 追加
}
```

### Step 3: 再生成セリフの generation メタデータ保存（バックエンド）

`_generate_section_dialogues` → `_generate_single_dialogue` は既に各セリフに `generation` キーを埋め込んでいる。再生成セリフにも同じメタデータが含まれるので、追加作業は不要（確認のみ）。

### Step 4: 管理画面に「再生成過程」セクション表示（フロントエンド）

`static/js/admin/teacher.js` の監督レビュー表示部分を拡張。不合格＋再生成済みのセクションに以下を表示：

1. **revised_directions**（監督が書き換えた演出指示）を折りたたみで表示
2. **元のセリフ**（`original_dialogues`）を折りたたみで表示（薄い背景で「再生成前」ラベル付き）
3. 現在の最終セリフは既存表示のまま（「再生成後」ラベル追加）

表示イメージ：
```
❌ 監督レビュー: 不合格 (再生成済み)
  フィードバック: display_textの例文が読まれていない
  ▶ 監督の修正指示 (revised_directions)
    🎓 teacher: 例文を読み上げて解説する / key: "Good morning"
    🙋 student: リアクション / key: ...
  ▶ 再生成前のセリフ
    🎓先生: （元のセリフ内容）
    🙋生徒: （元のセリフ内容）
[現在のセリフ一覧（既存表示）]
```

### Step 5: テスト更新

- `tests/test_api_teacher.py`: 不合格→再生成のケースで `original_dialogues` と `revised_directions` がレスポンスに含まれることを検証
- `tests/test_lesson_generator.py`: `regen_worker` が元セリフを正しく返すことを検証

## リスク

- dialogues JSON のサイズ増大（元セリフ分）→ 1セクションあたりせいぜい数KB、問題にならない
- 既存データとの互換性 → `original_dialogues` がない場合は表示しないだけなので問題なし
