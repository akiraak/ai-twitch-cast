# 授業生成でv5を作るとv4の音声が消えるバグ

## ステータス: 完了

## 現象

授業生成モードでv5を生成したら、v4の音声が全て消えていた。

## 音声ファイルの保存構造

```
resources/audio/lessons/{lesson_id}/{lang}/{generator}/v{version_number}/
  section_00_part_00.wav   # 単話者モード
  section_00_dlg_00.wav    # 対話モード
```

各バージョンのTTS音声はバージョン別サブディレクトリ（`v1/`, `v2/`, ...）に保存される。

## 原因分析

### 問題箇所1: `extract_lesson_text` が全バージョンのセクションを削除（最有力）

**ファイル**: `scripts/routes/teacher.py:813`

```python
# テキスト変更でセクションを無効化
db.delete_lesson_sections(lesson_id)  # ← lang/generator/version フィルターなし
```

`extract_lesson_text` は教材画像からテキストを抽出するエンドポイント。呼ばれると **全バージョン・全言語・全generatorのセクションをDBから一括削除** する。

v5生成前に画像追加やテキスト再抽出を行うと、v4を含む全バージョンのDBレコードが消える → v4の音声ファイルは残っているがシステムから参照不能になる。

### 問題箇所2: `_clear_lesson_data` も全バージョン削除

**ファイル**: `scripts/routes/teacher.py:727`

```python
db.delete_lesson_sections(lesson_id)  # ← 同様にフィルターなし
```

ソース全削除（`delete_all_sources`, `clear_sources`）で呼ばれる。画像入れ替え時に全バージョンのセクションが消失する。

### 問題箇所3: `delete_version` APIが音声ファイルを削除しない

**ファイル**: `scripts/routes/teacher.py:1284-1294`

```python
async def delete_version(...):
    db.delete_lesson_version(lesson_id, lang, generator, version_number)
    # ← clear_tts_cache() が呼ばれない
    # → DBレコードは消えるが音声ファイルは残る（孤立ファイル）
```

### 問題箇所4: `import_sections` のバージョン置換時に音声未削除

**ファイル**: `scripts/routes/teacher.py:950-957`

```python
if version is not None:
    db.delete_lesson_sections(lesson_id, lang=lang, generator=generator,
                              version_number=version_number)
    # ← 旧セクションの音声ファイルが残る
```

指定バージョンのセクションを置換する際、DBレコードだけ消して音声ファイルを削除しない。

## 修正方針

### 修正1: `extract_lesson_text` のバージョン保護（最優先）

テキスト再抽出は「教材の更新」であり、既存セクションを即座に全削除する必要はない。

**方針A（推奨）: セクション削除を廃止**

テキスト再抽出はテキストの更新のみ行い、セクション削除は行わない。セクションが古くなったかどうかはユーザーが判断する。

```python
# Before
db.delete_lesson_sections(lesson_id)

# After
# セクションは削除しない（テキスト更新のみ）
# 必要に応じてユーザーが手動でバージョン削除する
```

**方針B: バージョン単位削除への変更**

どうしても無効化が必要なら、最新バージョンのみ削除し、過去バージョンは保護する。

### 修正2: `_clear_lesson_data` のバージョン保護

ソース全削除時に全セクションを消す現行動作を見直す。

- ソース削除＝教材データの入れ替えなので、セクション削除自体は妥当
- ただし音声ファイルのクリーンアップも同時に行うべき
- `clear_tts_cache(lesson_id)` を追加

```python
def _clear_lesson_data(lesson_id):
    ...
    db.delete_lesson_sections(lesson_id)
    clear_tts_cache(lesson_id)  # 音声ファイルも削除
```

### 修正3: `delete_version` APIに音声クリーンアップ追加

```python
async def delete_version(lesson_id, version_number, lang, generator):
    ...
    clear_tts_cache(lesson_id, lang=lang, generator=generator,
                    version_number=version_number)
    db.delete_lesson_version(lesson_id, lang, generator, version_number)
```

### 修正4: `import_sections` のバージョン置換時に音声クリーンアップ追加

```python
if version is not None:
    db.delete_lesson_sections(lesson_id, lang=lang, generator=generator,
                              version_number=version_number)
    clear_tts_cache(lesson_id, lang=lang, generator=generator,
                    version_number=version_number)
```

## 実装ステップ

1. **修正1**: `extract_lesson_text` からセクション削除を除去（方針A採用時）
2. **修正2**: `_clear_lesson_data` に `clear_tts_cache` 追加
3. **修正3**: `delete_version` に `clear_tts_cache` 追加
4. **修正4**: `import_sections` に `clear_tts_cache` 追加
5. テスト追加: バージョン削除/置換時の音声クリーンアップを検証

## リスク

- 修正1で方針Aを採用すると、テキスト変更後に古いセクションが残る。ユーザーが手動でバージョン削除する必要がある
- `clear_tts_cache` を追加する各箇所でバージョンパラメータの指定を間違えると、意図しない音声削除が起きる
