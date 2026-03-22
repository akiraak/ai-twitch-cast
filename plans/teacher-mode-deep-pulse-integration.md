# 教師モード改善 — deep-pulse機能の統合

## ステータス: 設計中

## 背景

`repos/deep-pulse` は記事生成プログラムで、以下の機能を持つ:
- **Webソース取得**: `fetch_source.py` がURL→クリーンMarkdown変換（curl + BeautifulSoup + pandoc）
- **マルチソースリサーチ**: 1つの記事に30〜50+のURLから情報収集
- **ソース管理**: `sources/` ディレクトリに番号付きMarkdown保存、YAML frontmatter付き
- **Chart.js / Mermaid.js**: 記事内にグラフ・フローチャート等のビジュアル要素
- **構造化ワークフロー**: テーマ→ソース収集→プラン作成→記事生成→ファクトチェック
- **HTML変換**: Markdown→高品質HTMLレンダリング（マガジンスタイルCSS）

現在の教師モードとの差分:

| 項目 | 現在の教師モード | deep-pulse |
|------|----------------|------------|
| URLソース | 1つのみ（上書き式） | 30〜50+ URL対応 |
| テキスト抽出 | 生HTML→Geminiに丸投げ（30k文字制限） | curl→BeautifulSoup→pandoc→クリーンMarkdown |
| ビジュアル | テキストのみ | Chart.js, Mermaid.js対応 |
| リサーチ | なし | テーマから自動でURL収集 |
| プラン | なし | 記事構成プラン→承認→生成 |

---

## 機能1: 三者視点プラン生成（最優先）

### 概要

スクリプト生成を「一発生成」から「3段階プラン生成→スクリプト生成」に変更。
3人の架空の先生がそれぞれの視点で授業プランを作り、最終的に統合する。

### 三者の役割

#### 知識先生（教科主任）
- 教材の内容を分析し、**教えるべき要点**を整理
- 論理的な学習順序（前提知識→核心→応用）を設計
- よくある誤解・注意点を洗い出す
- 出力: 要点リスト + 推奨セクション構成 + 各セクションで扱うべき内容

#### エンタメ先生（人気講師）
- 知識先生の構成を受け取り、**起承転結**の物語構造で再構成
- **起**: 視聴者の興味を引くフック（意外な事実、身近な問い）
- **承**: 知識を段階的に積み上げ、伏線を張る
- **転**: 常識を覆す展開、驚きの事実、「実はこうだった」
- **結（オチ）**: 学んだことが繋がる瞬間、腹落ちする締め。「だから○○なんです！」
- クイズ・例え話・視聴者参加ポイントの配置
- 感情の起伏設計（どこで盛り上げ、どこで考えさせるか）
- 出力: 起承転結の構成案 + 各パートの演出提案 + オチの設計

#### 監督（バランサー）
- 知識先生の正確性 × エンタメ先生の起承転結を統合
- 全体の時間配分を調整（詰め込みすぎ防止）
- 知識の正確性を損なわずエンタメ要素を活かす判断
- 最終的なセクション構成を決定（セクション数・各セクションの概要・type・emotion）
- 出力: 最終プラン（JSON形式のセクション骨格）

### 実装: 3回のLLM呼び出し

```
呼び出し1: 知識先生
  入力: 教材テキスト + 画像
  出力: 要点リスト + 推奨構成（テキスト形式）

呼び出し2: エンタメ先生
  入力: 教材テキスト + 知識先生の出力
  出力: 起承転結の構成案 + 演出提案 + オチ設計（テキスト形式）

呼び出し3: 監督
  入力: 知識先生の出力 + エンタメ先生の出力
  出力: 最終プラン（JSON配列）
    [{section_type, title, summary, emotion, has_question}, ...]
```

### プランの保存と利用

- プランは `lessons` テーブルに `plan_json` カラムとして保存
  - 各視点の生テキストも保存（`plan_knowledge`, `plan_entertainment`）で確認・再生成に利用
- 管理画面のStep 2を分割:
  - **Step 2a: プラン生成** — ボタンでプラン生成→3視点の内容を表示→編集可能
  - **Step 2b: スクリプト生成** — プランに基づいてセクション詳細を生成
- プランだけ再生成（スクリプトはそのまま）も可能
- スクリプト生成時、監督のプランをシステムプロンプトに含めて制約として渡す

### UIフロー

```
Step 1: ソース追加（現状と同じ）
    ↓
Step 2a: プラン生成
    [プラン生成] ボタン → 3回のLLM呼び出し → 結果表示
    ┌─────────────────────────────────────┐
    │ 📚 知識先生の分析                      │
    │  ・要点1: ...                         │
    │  ・要点2: ...                         │
    │  ・推奨構成: ...                       │
    ├─────────────────────────────────────┤
    │ 🎭 エンタメ先生の構成                   │
    │  【起】フック: ...                     │
    │  【承】展開: ...                       │
    │  【転】驚き: ...                       │
    │  【結】オチ: ...                       │
    ├─────────────────────────────────────┤
    │ 🎓 監督の最終プラン                  │
    │  1. introduction: ... (excited)       │
    │  2. explanation: ... (thinking)       │
    │  3. example: ... (joy)               │
    │  ...                                 │
    └─────────────────────────────────────┘
    ↓
Step 2b: スクリプト生成（プランに基づく）
    ↓
Step 3: 授業開始（現状と同じ）
```

### 技術詳細

**lesson_generator.py に追加する関数:**

```python
def generate_lesson_plan(lesson_name, extracted_text, source_images=None):
    """3視点でプランを生成する（3回のLLM呼び出し）"""
    # → dict: {knowledge, entertainment, plan_sections}

def generate_lesson_script_from_plan(lesson_name, extracted_text, plan_sections, source_images=None):
    """プランに基づいてスクリプトを生成する"""
    # → list[dict]: セクション配列（現在のgenerate_lesson_scriptと同じ出力形式）
```

**DBスキーマ変更:**

```sql
ALTER TABLE lessons ADD COLUMN plan_knowledge TEXT DEFAULT '';
ALTER TABLE lessons ADD COLUMN plan_entertainment TEXT DEFAULT '';
ALTER TABLE lessons ADD COLUMN plan_json TEXT DEFAULT '';
```

**APIエンドポイント追加:**

```
POST /api/lessons/{lesson_id}/generate-plan    → プラン生成（3視点）
PUT  /api/lessons/{lesson_id}/plan             → プラン手動編集
POST /api/lessons/{lesson_id}/generate-script  → 既存（プランがあればプランに基づいて生成）
```

---

## 機能2: URL テキスト抽出の改善（fetch_source.py流用）

**優先度: 高** / **難易度: 低**

**現状の問題**: URL追加時、`httpx`でHTML取得→生HTMLをGeminiに送信（最初の30k文字のみ）。広告・ナビゲーション等のノイズが多く、抽出品質が低い。

**改善案**: deep-pulseの`fetch_source.py`のアプローチを教師モードに導入
- BeautifulSoupで`<article>`, `<main>`, `.entry-content`等のセマンティック要素を優先抽出
- `<script>`, `<style>`, `<nav>`, `<iframe>`等を除去
- HTML→Markdown変換でクリーンなテキストを取得
- Geminiへの入力品質が向上し、スクリプト生成の精度も上がる

**実装方法**:
- `src/lesson_generator.py` の `extract_text_from_url()` を改善
- BeautifulSoup依存追加（requirements.txt）
- pandocはオプション（なくてもBeautifulSoup→テキスト変換で十分改善）

---

## 機能3: マルチURLソース対応

**優先度: 高** / **難易度: 中**

**現状の問題**: URLソースは1つしか追加できない（新しいURL追加で既存ソースを全削除）。画像は複数可。

**改善案**: 画像と同様にURLも複数追加可能にする
- 管理画面にURL追加ボタン（既存のURLを消さず追加）
- 各URLからテキスト抽出→統合して`extracted_text`に結合
- ソース一覧でURL個別の削除が可能

**実装方法**:
- `scripts/routes/teacher.py` の `add_url` エンドポイントを変更（既存ソースを削除しない）
- `extract_text` エンドポイントを画像+URL両方に対応
- 管理画面UIで複数URL入力対応

---

## 機能4: 授業スクリプトにビジュアル要素追加（Chart.js / Mermaid.js）

**優先度: 中** / **難易度: 中**

**現状の問題**: 授業中の`display_text`はプレーンテキストのみ。

**改善案**: セクションに`visual`フィールドを追加
- `chart`: Chart.jsのJSON設定 → 配信画面にグラフ表示
- `mermaid`: Mermaidの定義 → 配信画面にフローチャート/図表表示
- `display_text`と併用可能

**実装方法**:
- `lesson_sections`テーブルに`visual_type`と`visual_data`カラム追加
- broadcast.htmlにChart.js/Mermaid.jsを組み込み（CDN）
- `lesson_text_show`イベントに`visual`データを追加

---

## 機能5: テーマからの自動ソース収集（Webリサーチ）

**優先度: 低** / **難易度: 高**

トピック名入力→関連URLを自動検索→候補提示→ユーザー選択→ソース追加

**課題**: Web検索APIの選定・コスト・品質管理

---

## 推奨実装順序

1. **三者視点プラン生成**（授業品質の根本改善）
2. **URL テキスト抽出の改善**（ソース品質向上）
3. **マルチURLソース対応**（リッチなソース構築）
4. **ビジュアル要素追加**（配信の見栄え向上）
5. **テーマからの自動ソース収集**（高度な機能）

## リスク

- 3回のLLM呼び出しでプラン生成に時間がかかる（各呼び出し5〜15秒 × 3 = 15〜45秒）
  → 管理画面で非同期実行＋進捗表示で対応
- エンタメ先生のオチ設計がLLMの創造性に依存
  → プロンプトで起承転結の具体例を示して品質を安定させる
- BeautifulSoup追加は依存関係の増加（ただし標準的なライブラリ）
- Chart.js/Mermaid.jsをbroadcast.htmlに追加するとページ重量が増える（CDN使用で軽減）
- Web検索API統合はコスト・レート制限の考慮が必要
