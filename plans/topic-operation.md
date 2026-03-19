# トピック発話モード運用プラン

## 背景

トピック発話機能（コメントが途切れたらちょびが自発的に話す）は実装・テスト済みだが、
本格運用に向けた調整・検証がまだ行われていない。

## 現状分析

### 動作フロー

```
コメントが30秒途切れる
  → CommentReader._should_auto_speak() = True
  → _auto_speak()
    1. maybe_rotate_topic() — トピック自動生成 or ローテーション
    2. get_next() — Geminiで1発話リアルタイム生成
    3. TTS → 字幕 → Twitchチャット投稿 → DB保存
  → idle_since リセット（45秒後まで次の発話なし）
```

### 実装済みの機能

| 機能 | 状態 | 備考 |
|------|------|------|
| トピック手動設定・解除 | OK | WebUI + API |
| トピック自動生成 | OK | Gemini、配信コンテキスト参照 |
| トピック自動ローテーション | OK | 10分 & 5発話で切替 |
| リアルタイム発話生成 | OK | Gemini、直前3発話+直近5コメント参照 |
| TTS・字幕・チャット投稿 | OK | SpeechPipeline経由 |
| 一時停止・再開 | OK | API + WebUI |
| broadcast.htmlパネル | OK | WebSocket同期 |
| テスト | OK | 31件（unit + API） |

### 問題点・運用上の課題

#### 1. デフォルトで停止（paused=True）

`TopicTalker.__init__()` で `self._paused = True`。
サーバー再起動のたびに手動でWebUIから「再開」する必要がある。

**影響**: コミット時にサーバーが自動再起動 → トピック発話が勝手に止まる

```python
# src/topic_talker.py:27
self._paused = True
```

#### 2. 設定値がメモリのみ（永続化されない）

`idle_threshold`(30秒) と `min_interval`(45秒) はインスタンス変数。
WebUIで変更してもサーバー再起動でデフォルトに戻る。

```python
# src/topic_talker.py:23-24
self._idle_threshold = DEFAULT_IDLE_THRESHOLD  # 30
self._min_interval = DEFAULT_MIN_INTERVAL      # 45
```

#### 3. ローテーション条件がハードコード

`TOPIC_ROTATE_INTERVAL = 10 * 60`（10分）、`TOPIC_ROTATE_SPEECHES = 5`（5発話）は
定数で変更不可。実運用で適切な値かは未検証。

#### 4. トピック自動生成のトリガー

トピック未設定かつ paused=False のとき `maybe_rotate_topic()` が自動生成する。
つまり **paused=False に一度もならない限り、トピック自動生成は発動しない**。

#### 5. _restore_session でトピック状態が復旧しない

`_restore_session()` は Reader・Git監視・配信状態を復旧するが、
TopicTalkerの paused 状態は復旧しない。

```python
# scripts/web.py:191-224 (_restore_session)
# → topic_talkerの復旧処理がない
```

#### 6. set_topic()でpaused=Falseになるが、既存トピックで再開できない

`set_topic()` は新規トピック作成 → `_paused = False`。
しかし既にアクティブなトピックがある状態でサーバー再起動した場合、
トピックはDBに残っているが `_paused = True` のまま。

#### 7. トピック発話の頻度感が未検証

- idle_threshold=30秒: コメントが30秒途切れたら発話 → 短すぎる可能性
- min_interval=45秒: 最低45秒間隔 → 妥当か？
- 実配信で試さないとわからない

### コードの依存関係

```
state.py
  └── topic_talker = TopicTalker()  ← メモリのみ、再起動で初期化
  └── reader = CommentReader(topic_talker=topic_talker)
        └── _process_loop()
              └── _should_auto_speak() → topic_talker.should_speak()
              └── _auto_speak() → topic_talker.maybe_rotate_topic() + get_next()

routes/topic.py
  └── 全エンドポイントが state.topic_talker を参照

web.py
  └── _restore_session()  ← topic_talker の復旧なし
```

### WebUI（トピックタブ）の現状

- トピック設定（タイトル・説明入力）
- 解除ボタン
- 今すぐ発話ボタン（テスト用）
- 停止/再開ボタン
- idle_threshold / min_interval の設定UI
- 発話履歴表示

UIは完成しており、追加作業は不要。

## 運用開始に必要な改修

### 必須（これがないと実用にならない）

#### A. paused状態の永続化 + 起動時復旧

サーバー再起動でトピック発話が止まらないようにする。

**方針**: DB の `settings` テーブル（`volume.*` キーと同じ仕組み）を使う

```
キー: topic.paused → "true" / "false"
キー: topic.idle_threshold → "30"
キー: topic.min_interval → "45"
```

- `TopicTalker.__init__()` で DB から読み込み
- `pause()` / `resume()` / settings更新時に DB 保存
- アクティブなトピックがDBにあり、paused=false なら自動的に発話再開

#### B. _restore_session でトピック状態復旧

`_restore_session()` に以下を追加:
1. DBからトピック設定を読み込み
2. `topic_talker._paused` を復旧
3. アクティブトピックがあれば `_topic_set_time` もリセット

### 推奨（運用しながら調整）

#### C. デフォルト値の調整

実配信で試して適切な値を決める。初期値案:
- idle_threshold: 30秒 → **60秒**（もう少し待ってから話し始める）
- min_interval: 45秒 → **60秒**（間隔を広げる）

#### D. ログの充実

運用中に挙動を追跡するため:
- `should_speak()` が True/False を返したタイミングのログ
- トピック自動生成・ローテーションのログ（既にある）
- 発話スキップ理由のログ

### 将来検討（今回はやらない）

- ローテーション条件のUI化
- トピック履歴の表示（過去のトピック一覧）
- トピック発話のON/OFFをWebUIのトップレベルに出す

## 実装ステップ

### Step 1: 設定の永続化
- `db.py` に `get_setting()` / `set_setting()` がなければ確認
- `TopicTalker` の init で DB から設定読み込み
- pause/resume/settings更新時に DB 保存

### Step 2: 起動時復旧
- `_restore_session()` にトピック状態復旧を追加
- アクティブトピック + paused=false → 発話自動再開

### Step 3: デフォルト値調整
- idle_threshold / min_interval のデフォルトを調整

### Step 4: 実配信テスト
- サーバー起動 → トピック設定 → コメントなし30秒 → 発話確認
- サーバー再起動 → 自動復旧 → 発話継続確認
- コメント応答中にトピック発話が割り込まないか確認

## ステータス: 未着手
