# 管理画面 授業モード: バージョン別セクション表示の修正

## ステータス: 完了

## 背景

管理画面の授業モード（teacher.js）で、授業に複数バージョン（v1, v2, v3）がある場合、初回表示時に全バージョンのセクションが混在して1画面に表示されてしまう。

例: 授業#5に ja/claude/v1(3セクション)、v2(2セクション)、v3(4セクション)がある場合、9セクションすべてが区別なく表示される。

## 原因分析

### 根本原因: 初回ロード時にバージョンフィルタが適用されない

**`static/js/admin/teacher.js` の `buildLessonItem()` (L134-158)**:

1. **L139**: `_getLessonVersion()` は `_lessonVersionTab` から取得するが、初回は空なので `null` を返す
2. **L141**: `selectedVersion` が falsy なので API に `?version=` パラメータが付かない
3. **L143**: API が全バージョンのセクションを返す（後方互換のため）
4. **L155**: `sections` のフィルタは `lang` と `generator` のみ。`version_number` でフィルタしていない
5. **L158**: `currentVersion` は計算されるが、セクションのフィルタには使われていない

### バージョン選択ボタンを押した後は正常

`_switchLessonVersion()` が `_lessonVersionTab` にバージョンを保存 → 再描画時に API に `?version=` が付く → 正しいセクションだけ返る。

## 修正方針

**最小限の修正**: L155 のフィルタに `version_number` を追加する。

### 具体的な変更

**ファイル: `static/js/admin/teacher.js`**

#### 変更1: セクションをバージョンでもフィルタする（L155付近）

現在:
```javascript
const langVersions = allVersions.filter(v => v.lang === lang && v.generator === generator);
const sections = allSections.filter(s => (s.lang || 'ja') === lang && (s.generator || 'claude') === generator);
const currentVersion = selectedVersion || (langVersions.length ? langVersions[langVersions.length - 1].version_number : 1);
```

修正後:
```javascript
const langVersions = allVersions.filter(v => v.lang === lang && v.generator === generator);
// バージョン番号確定（未選択なら最新）
const currentVersion = selectedVersion || (langVersions.length ? langVersions[langVersions.length - 1].version_number : 1);
// 現在のバージョンのセクションのみ表示
const sections = allSections.filter(s => (s.lang || 'ja') === lang && (s.generator || 'claude') === generator && s.version_number === currentVersion);
```

ポイント:
- `currentVersion` の計算を `sections` フィルタより前に移動
- フィルタ条件に `s.version_number === currentVersion` を追加
- API側の変更は不要（全セクション返す後方互換はそのまま維持）

## リスク

- **低リスク**: フィルタ条件を1つ追加するだけ
- 既存のバージョン切り替え機能（`_switchLessonVersion`）への影響なし
- `version_number` が undefined/null のセクション（古いデータ）がある場合に非表示になる可能性 → DB上は必ず `version_number` が設定されるため問題なし

## テスト

1. 複数バージョンがある授業を開き、最新バージョンのセクションだけ表示されることを確認
2. バージョンタブを切り替えて、各バージョンのセクションが正しく表示されることを確認
3. バージョンが1つだけの授業が正常に表示されることを確認
4. `python3 -m pytest tests/ -q` で既存テストが通ることを確認
