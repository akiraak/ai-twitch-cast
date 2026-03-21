# DONE

## 配信言語設定の再設計

- [x] 言語モード5プリセット → 基本言語・サブ言語・混ぜ具合の3項目設定に再設計
- [x] テキスト生成プロンプトとTTSスタイルを分離（`build_language_rules()` / `build_tts_style()`）
- [x] `english` → `translation` フィールドリネーム（全レイヤー: AI出力・WebSocket・字幕・C#アプリ）
- [x] WebUIキャラクタータブをサブタブ分割（ビジュアル / セリフ）
- [x] 配信言語をセリフタブ内に配置
- [x] 言語テストをセリフタブに統合、6パターン化（言語選択UI廃止→配信言語設定を自動使用）
- [x] 読み上げテスト6パターン追加（挨拶・雑談・リアクション・質問・エピソード・解説）
- [x] 生成プロンプトプレビュー表示
- [x] 対応言語8種（日本語・English・한국어・Español・中文・Français・Português・Deutsch）
- [x] 他言語コメントには相手の言語で返答する固定ルール
- [x] DB保存を3キー方式に変更（stream_lang_primary/sub/mix）
- [x] テスト全420件更新・通過

## 右クリックメニュー設定編集（スキーマAPI＋フローティングパネル）

- [x] サーバ駆動スキーマAPI（`GET /api/items/schema`）を実装（共通＋アイテム固有プロパティ定義）
- [x] broadcast.htmlの右クリックメニューに「設定を編集...」を追加
- [x] フローティング設定パネル（ドラッグ移動・折り畳みグループ・スキーマからUI動的生成）
- [x] slider/color/toggle/select/text の全フィールドタイプ対応
- [x] デバウンス付きAPI保存（PUT /api/items/{id}）＋editSave()競合防止
- [x] スキーマAPIテスト9件追加
- [x] index.htmlの`_commonPropsHTML()`をスキーマAPIベースに統一（ハードコード排除）
- [x] C#アプリはWebView2経由で自動対応（追加実装不要）
- [x] 右クリック→設定パネル直接表示に変更（中間メニュー・Z値ダイアログ廃止）
- [x] 設定パネル上部に「テキスト子パネルを追加」/「削除」ボタン配置
- [x] C# WebView2のデフォルトコンテキストメニュー無効化
- [x] PUT /api/items/{id} でアイテム自動作成（upsert）
- [x] 設定パネルの値をDOMフォールバックで取得（broadcast_items未登録のキャプチャ対応）
- [x] settings_updateのWebSocketキー名修正（item_idリテラル→変数展開）
- [x] 設定変更のDOM即時反映（applyCommonStyle直接適用）
- [x] 設定パネルヘッダーをsticky固定（スクロール時にタイトル＋×が残る）
- [x] トグルスイッチのクリック修正（div→label化）＋サイズ固定

## WebUI TODOタブ復活＋外部ファイル対応＋複数選択

- [x] WebUIにTODOタブを復活（開発実況削除で巻き添えで消えていたHTML/タブ切替を復元）
- [x] 作業中TODOの解除機能追加（POST /api/todo/stop）
- [x] 外部TODO.mdファイルのアップロード・DB保存・切り替え対応
- [x] 複数TODOファイルをDBに保存してドロップダウンで切り替え可能
- [x] アップロード時にモーダルダイアログで名称入力（showModal汎用コンポーネント化）
- [x] 作業中タスクの複数選択対応（排他→追加方式に変更）
- [x] 全391テスト通過（新規テスト11件追加）

## 開発実況リポジトリ監視機能の完全削除

- [x] DevStreamManager・APIルート・テスト・UIタブ・JS関数を丸ごと削除
- [x] broadcast.htmlのdev-activity-panel・CSS・WebSocketハンドラを削除
- [x] overlay内のTODOソース切替（_todo_source dev:ルーティング）・/api/todo/sourceを削除
- [x] DBのdev_reposテーブル定義・全CRUD関数を削除＋DROP TABLEマイグレーション追加
- [x] repos/ディレクトリ・.gitignoreエントリを削除
- [x] 全380テスト通過

## ペルソナ生成の抽象化

- [x] generate_persona / generate_persona_from_prompt のプロンプトに抽象化ルール追加
- [x] 具体的な技術用語・固有名詞・フレーズ羅列を禁止し、性格特性として記述する指示に変更

## C#チャットのAI返信表示バグ修正

- [x] MainForm.cs: WSイベントのキー名不一致を修正（message→trigger_text, response→speech）
- [x] control-panel.html: C#→HTML受信側・fetch応答側の両方でspeechキーに修正
- [x] commentsテーブル再設計時にC#側が追従していなかったのが原因

## C#プレビューにTwitch配信情報設定＋Go Live時コメント削除＋不要なWeb preview削除

- [x] C#コントロールパネル（control-panel.html）のStreamタブにTwitch情報セクション追加（タイトル表示・編集UI）
- [x] Go Live時にcomments/avatar_commentsテーブルを自動クリア（db.clear_comments/clear_avatar_comments）
- [x] 不要なWeb版プレビューページ削除（static/preview.html + GET /preview ルート）
- [x] テスト追加（clear_comments/clear_avatar_comments）
- [x] 全433テスト通過

## commentsテーブル再設計（comments/avatar_comments分離）

- [x] commentsテーブルを視聴者コメント専用に簡素化（text, user_id, episode_id）
- [x] avatar_commentsテーブル新設（trigger_type, trigger_text, text, emotion）
- [x] 既存データのマイグレーション（RENAME COLUMN + DROP COLUMN + データコピー）
- [x] AI応答辞書のキー変更（response → speech）、Geminiプロンプト更新
- [x] 会話履歴をタイムライン形式に変更（get_recent_timeline: UNION ALL）
- [x] comment_reader: コメントとアバター発話を分離保存、_save_avatar_comment新設
- [x] WSイベントのフィールド名変更（message → trigger_text, response → speech）
- [x] APIエンドポイント更新（/api/chat/history タイムライン形式、DB viewer）
- [x] フロントエンド更新（broadcast.html, broadcast-main.js, index-app.js, CSS）
- [x] デバッグ字幕エンドポイント修正
- [x] 全431テスト通過

## キャラクター記憶システム改善

- [x] メモ更新ループのガード条件修正: ペルソナ・セルフメモの更新をユーザーコメント有無と独立に実行
- [x] セルフメモの時間情報対応: コメントにタイムスタンプ付与
- [x] ペルソナWebUI編集: PUT API追加＋編集/保存/キャンセルUI
- [x] ペルソナ初期生成: システムプロンプトからAI生成するAPI＋WebUI「AI初期生成」ボタン
- [x] セルフメモAI再生成: WebUI「AI再生成」ボタン＋API追加
- [x] ペルソナ漸進的更新: 既存ペルソナの90%を維持しつつ最近の応答で更新（400文字）
- [x] セルフメモ拡大: 直近2時間50件から生成、400文字
- [x] ユーザーメモ漸進的更新: 既存メモの90%を維持しつつ更新（200文字、直近2時間20件）
- [x] 視聴者メモWebUI表示・編集: 折りたたみ表示＋件数表示＋各メモに編集ボタン
- [x] 会話生成ドキュメント更新
- [x] テスト追加: API（layers/persona/viewer-note）+ generate_self_noteタイムスタンプ + generate_persona_from_prompt

## ちょびバージョン 0.2.0

- [x] VERSION 0.1.0 → 0.2.0（36コミット分の新機能蓄積: チャットログ・配信遅延解消・character_memory・TODO統合等）

## WebUIのTODOタブを開発実況タブに統合

- [x] TODOタブを廃止し、開発実況タブ内にTODO一覧を統合
- [x] ai-twitch-castリポジトリを先頭に常時表示（削除不可）
- [x] リポジトリクリックで選択→そのリポジトリのTODOを表示
- [x] 選択中リポジトリは紫ハイライト+「選択中」バッジ
- [x] `#todo` ハッシュは `#devstream` にリダイレクト
- [x] バックエンド変更なし（既存API再利用）

## ちょビの発話をチャットログとして表示（C#パネル + WebUI）

- [x] WebUIにチャットログタブ追加（DB履歴読み込み + WSリアルタイム追加）
- [x] `GET /api/chat/history` API追加（ページング対応、新しい順）
- [x] C#パネルにcommentイベント転送（broadcast.html → MainForm → control-panel）
- [x] コンパクト1行表示（日時 / 発言者 / コメント ← きっかけ）
- [x] 上下ページャー、URLにページ番号反映（`#chat:2`）

## Twitch配信遅延解消（NVENCハードウェアエンコーダ自動検出修正）

- [x] 遅延原因特定: FFmpegがlibx264（CPU）にフォールバックし、1080p30fpsでspeed 0.64x（19fps）しか出ず遅延蓄積
- [x] HWエンコーダprobeの改善: `nullsrc` → `color=black`、`-f null -` → `-f null NUL`（Windows互換性向上）
- [x] `-encoders` リストで事前チェック追加（probeの高速化）
- [x] FFmpegパス不在時のprobeスキップ（例外握りつぶし防止）
- [x] probe失敗時のログ出力追加（原因特定しやすく）
- [x] 結果: h264_nvenc（RTX 3090 Ti）が正常検出され、speed 0.64x → 1.01x（リアルタイム）に改善

## 会話生成ドキュメント + 5層プロンプトWebUI表示 + character_memoryテーブル

- [x] `docs/character-prompt.md` 作成（5層プロンプト構成・言語モード・感情システム等のドキュメント）
- [x] `mkdocs.yml` にキャラクターセクション追加
- [x] WebUIキャラクタータブに「会話生成の仕組み →」モーダルダイアログ（Markdown→HTML変換表示）
- [x] WebUIキャラクタータブに5層プロンプト表示（第1層〜第5層のグループ分け）
- [x] 第2〜4層のデータ表示API `GET /api/character/layers` 追加
- [x] `character_memory` テーブル新設（ペルソナ・セルフメモをキャラクターIDに紐付け）
- [x] 既存データ自動マイグレーション（settings.persona → character_memory、users.note → character_memory）
- [x] `comment_reader.py` の読み書き先を character_memory に切替（4箇所）
- [x] `db_viewer.py` の手動メモ更新も character_memory に切替
- [x] テスト追加（TestCharacterMemory 5件、全421テスト通過）

## Claude Code長時間実行時にちょびがコメント

- [x] `~/.claude/hooks/long-execution-timer.py` 作成（バックグラウンドタイマー、transcript解析）
- [x] `notify-prompt.py` にタイマー起動処理追加（マーカーファイル + Popen）
- [x] `notify-stop.py` にタイマー停止処理追加（マーカー削除 + pkill）
- [x] transcript_pathのJSONLからツール呼び出しを解析し、作業内容付きで報告
- [x] アイドル検知: transcript未更新2分でタイマー自動終了（Ctrl+C/Stopフック失敗のセーフガード）

## Claude Code実況フックのグローバル化（他リポジトリ対応）

- [x] `~/.claude/hooks/notify-stop.py` / `notify-prompt.py` をグローバルフックとして作成
- [x] `~/.claude/settings.json` にStop/UserPromptSubmitフックを `"async": true` で登録
- [x] プロジェクトローカルのフックスクリプト4ファイル（`.sh`/`.py` × 2）を削除
- [x] `.claude/settings.local.json` からStop/UserPromptSubmitフック定義を削除（PostToolUseは維持）
- [x] 他リポジトリではプロジェクト名付きで報告（例: 「作業報告（other-project）」）

## 字幕パネルの水平中央配置修正

- [x] `applySettings`の字幕中央揃えコードを常時適用に変更（`bottom != null`条件を除去）
- [x] ドラッグ時に字幕は垂直移動のみ（水平は常に中央固定、`transform: translateX(-50%)`を維持）
- [x] `editSave`で字幕の`positionX`を常に50に固定（ドラッグで不正な値が保存されるのを防止）

## WebUIポーリング負荷削減（84%削減）

- [x] `checkServerUpdate`ポーリング（3秒）をWebSocket push方式に置換（`server_restart`イベント）
- [x] `refreshStatus`ポーリング間隔を5秒→30秒に延長
- [x] `syncBgmVolumes`ポーリング間隔を3秒→30秒に延長
- [x] `captureRefreshSources`ポーリング間隔を10秒→30秒に延長
- [x] サーバー起動時に`server_restart` WebSocketイベントをbroadcast（`web.py`）
- [x] 夜の配信停止原因を特定: PCスリープによるWSL2停止（コード修正では解決不可、Windows電源設定変更が必要）

## バージョニングルール作成

- [x] `docs/versioning.md` 作成（バージョン基準: MAJOR/MINOR/PATCH/上げない、半自動提案フロー）
- [x] CLAUDE.md の開発ルールにバージョン更新ルール追記
- [x] `mkdocs.yml` の運用セクションにページ追加
- [x] `.git/hooks/post-commit` にバージョン提案ロジック追加（DONE.md変更検知 → `/api/avatar/speak` でちょびに提案依頼）

## ちょびの返信改善 Phase 1+2

- [x] A: キャラ設定全面書き直し（性格5項目+話し方5項目、AI身体体験捏造禁止）
- [x] B: 感情分布矯正（neutral 60%以上、joy乱用禁止ガイド追加）
- [x] C: 応答ルール厳格化（40文字以内、1文返し、感嘆符制限）
- [x] F: GM特別対応（開発者、敬語不要コンテキスト）
- [x] D: ペルソナ自動抽出（15分バッチ、DB保存、プロンプト注入）
- [x] G: temperature=1.0設定
- [x] E: 会話履歴5→10件、禁止パターン（直前3件の書き出し重複防止）
- [x] H: イベント応答バリエーション（直前応答を渡して繰り返し防止）
- [x] I: ユーザーメモ・自己メモに「事実のみ、キャラ口調禁止」ルール追加
- [x] J: 感情種類追加（excited/sad/embarrassed）+ BlendShapeマッピング
- [x] DB上のキャラクター設定も更新済み
- [x] プラン: plans/improve-ai-responses.md

## Claude Code 作業実況（Stopフック）

- [x] `.claude/hooks/notify-stop.py` / `notify-stop.sh` 作成（Stopフックで作業完了をちょびに自動報告）
- [x] `.claude/hooks/notify-prompt.py` / `notify-prompt.sh` 作成（UserPromptSubmitフックで指示受信をちょびに報告）
- [x] `settings.local.json` にStop/UserPromptSubmitフック追加
- [x] CLAUDE.md に実況機能セクション追加
- [x] 疎結合設計（stdlib only、サーバー側変更ゼロ、削除1手順）
- [x] shスクリプトのstdin空問題修正（`&`バックグラウンド実行でstdinが切れる→`INPUT=$(cat)`で先読みしてパイプ）
- [x] プラン: plans/claude-code-narration.md

## WebUIチャット欄追加（GM→アバター会話）

- [x] C#コントロールパネルのChatタブにチャットUI実装（メッセージ履歴+入力欄）
- [x] `POST /api/chat/webui` エンドポイント追加
- [x] `CommentReader.respond_webui()` 実装（AI応答→TTS→字幕、GMメッセージをTwitchチャット投稿）
- [x] CORSミドルウェア追加（C#パネル→WSLサーバー間の通信対応）
- [x] preview.htmlにもチャットUI追加
- [x] テスト追加（test_api_chat.py）
- [x] プラン: plans/webui-chat-input.md

## 表情・ジェスチャーシステム実装

- [x] 表情イージング遷移（300ms）実装
- [x] ジェスチャーアニメーション（AnimationMixer）実装（nod, surprise, head_tilt, happy_bounce, sad_droop, bow）
- [x] 感情→ジェスチャーのデフォルトマッピング（joy→nod, surprise→surprise等）
- [x] emotion_blendshapesをVRM 1.0名に修正（DB + DEFAULT_CHARACTER）
- [x] リップシンクと感情BlendShapeの競合修正（aa/blink/ear_standをスキップ）
- [x] WebUI感情テストボタン追加（joy/surprise/thinking/neutral）
- [x] 耳プルプル振り追加（15%確率、30-50Hz高速振動 + ear_stand/ear_droop交互 + happy表情連動）
- [x] broadcast.htmlにconsole.logキャプチャ→サーバー送信機能追加
- [x] デバッグ用API追加（expression直送・jslog保存）
- [x] プラン: plans/expression-gesture-implementation.md

## 子パネル（入れ子テキストパネル）機能

- [x] DBスキーマ拡張: broadcast_itemsにparent_idカラム追加、子パネルCRUD関数（create/get/delete + 連鎖削除）
- [x] API: POST /api/items/{parent_id}/children、GET /api/items で children ネスト、DELETE 連鎖削除
- [x] WebSocket: child_panel_add/update/remove イベント、settings_update で子パネル情報同期
- [x] broadcast.html: 子パネルのレンダリング・編集（ドラッグ＆リサイズ、相対座標、右クリックメニュー）
- [x] 管理UI: 固定パネル・カスタムテキストに子パネル管理UI（追加・編集・削除）
- [x] テスト: DB子パネルCRUD + API子パネルテスト追加
- [x] プラン: plans/child-panels.md

## パネルUI共通化（テキスト変数・テキスト編集UI）

- [x] テキスト変数定義を`lib/text-variables.js`に一元化（`replaceTextVariables()` + `TEXT_VARIABLE_HINT`）
- [x] テキスト編集UIを`panel-ui.js`に共通関数化（`renderTextEditUI()` + `injectChildPanelSection()`）
- [x] 子パネルに変数ヒント（{version} {date} 等）が表示されないバグ修正
- [x] broadcast-main.jsのバージョン再展開が`.child-text-content`にも適用されるよう修正

## 子パネルのスナップガイド対応

- [x] ドラッグ時: 親パネルの端・中央、兄弟子パネルの端・中央にスナップ吸着
- [x] リサイズ時: 同様に親パネル・兄弟子パネルにスナップ吸着
- [x] ガイド線を画面座標に変換して正しく表示

## 子パネルのスタイル適用バグ修正

- [x] `addChildPanel()`の手動スタイル適用を`applyCommonStyle()`に一本化（textStroke・backdrop等の適用漏れ修正）
- [x] `applyCommonStyle()`のtextAlign/verticalAlign/fontFamilyセレクタに`.child-text-content`を追加
- [x] `.child-text-content` CSSに`flex-direction: column`追加（垂直揃えが水平に効いていたバグ修正）

## Z値ダイアログ・コンテキストメニューの画面外はみ出し修正

- [x] 右クリックメニューとZ値ダイアログの表示位置をビューポート内にクランプ

## プレビューZ値ダイアログが9000を表示するバグ修正

- [x] 編集中のzIndex一時値(9000)がZ値ダイアログに表示される問題を修正
- [x] getElZIndex()が_savedZIndexを優先して返すよう変更
- [x] Z値変更時も_savedZIndexを更新し、編集中は常にz-index=9000を維持

## アバターVRM管理を配信画面タブに移動 + 素材タブ削除

- [x] アバターVRMのファイル追加・選択・削除を配信画面のアバターパネル内に移動（共通設定の下に「VRMファイル」セクション）
- [x] 素材タブを削除（背景・アバター両方が配信画面に移動済みのため）

## 背景画像管理を配信画面タブに移動

- [x] 素材タブの背景画像カードを配信画面タブの最上部に移動（折りたたみパネル形式）
- [x] 起動時に背景ファイル一覧を自動読み込み

## 配置画面の削除ボタンを折りたたみ時も表示

- [x] キャプチャ・テキストの削除ボタンをsummary行に移動（折りたたんだ状態でも常時表示）
- [x] summary-delete-btn CSSクラス追加（右寄せ・赤背景の小ボタン）

## WebUI右上の配信制御ボタン削除

- [x] 「配信開始」「配信停止」「再起動」ボタンをWebUIヘッダーから削除（C#パネル・preview.htmlに同等機能あり）
- [x] `/api/restart` エンドポイント削除（コミット時にpost-commit hookで自動再起動されるため不要）
- [x] 関連JS関数（doGoLive, doStop, doRestart, waitForRestart）削除

## テキストパネル フォント変更

- [x] fontFamilyを共通プロパティとして追加（DB migration、broadcast.html描画、WebUIセレクトボックス）
- [x] システムフォント6種＋Google Fonts 2種＋等幅の計9選択肢
- [x] Google Fonts（M PLUS Rounded 1c、小杉丸ゴシック）は選択時に動的読み込み

## テキストパネル文字揃え（水平・垂直）

- [x] textAlign（左/中央/右）・verticalAlign（上/中央/下）を共通プロパティとして追加
- [x] DB migration、broadcast.html描画、WebUIセレクトボックス対応

## テキストパネル変数ヘルプ表示

- [x] WebUIのテキストパネルtextarea下に使える変数一覧（{version} {date} {year} {month} {day}）を表示

## アイテム共通化バグ修正

- [x] applyCommonStyleを直接適用に変更（bgColor→background、border、textColor、textStroke、padding）
- [x] WebUI全面刷新: details廃止、共通UI(17項目)→固有UIの2段構成、配置/背景/文字のグループ化
- [x] 背景色: hex→rgba変換してbgOpacityと合成し直接適用
- [x] ふち枠: borderEnabled廃止→borderSize=0で非表示に統一
- [x] 文字色: custom-text-colorクラス+!importantでID詳細度に勝つCSS追加
- [x] 文字縁取り: 色/透明度をCSS変数に保存し全値読み出して合成適用
- [x] 幅/高さ/文字サイズを共通UIに移行、重複する固有スライダー削除
- [x] border_enabledをDB/デフォルト/マッピングから削除

## アイテム共通化 Phase 7: 動的アイテム移行

- [x] custom_textsのCRUDをbroadcast_items経由に全面書き換え（ID体系: customtext:{n}）
- [x] custom_texts/capture_windowsテーブル → broadcast_itemsへの自動マイグレーション
- [x] 旧テーブルはフォールバック用に残留（capture.pyの全面書き換えは別タスクに分離）
- [x] テスト10件追加（custom_text CRUD、API互換、マイグレーション）

## アイテム共通化 Phase 6: broadcast_itemsテーブル + 固定アイテム移行

- [x] broadcast_itemsテーブル作成（共通22カラム + properties JSON）
- [x] CRUD関数（get/upsert/update_layout + キー名↔カラム名自動マッピング）
- [x] overlay.* settings → broadcast_itemsマイグレーション（初回起動時自動実行）
- [x] 統合API `/api/items` (GET/PUT/{id}/layout/visibility)
- [x] 旧API `/api/overlay/settings` をbroadcast_items優先の互換レイヤーに更新
- [x] テスト15件追加（test_api_items.py）

## アイテム共通化 Phase 3: CSS統一

- [x] version-panel/dev-activity-panelのインラインスタイル全除去→CSSルールに移行
- [x] CSS変数（--item-border-radius, --item-padding, --item-text-color, --item-font-size）でPhase 2のapplyCommonStyleと接続
- [x] subtitle/todo/topicのborder-radiusをvar(--item-border-radius)に変更
- [x] テスト6件追加

## アイテム共通化 Phase 4: Web UI設定パネル

- [x] 全fieldsetに`data-section`属性追加、dev_activityフィールドセット新規追加
- [x] `_commonPropsHTML()`で折りたたみ「詳細設定」UI動的生成（visible, bgColor, borderRadius, border, textColor, textStroke, padding）
- [x] `onLayoutColor()`/`onLayoutToggle()`/`cssColorToHex()`ハンドラ追加
- [x] `loadLayout()`拡張（カラー・トグル初期値）、WebSocket同期にカラー・トグル対応追加
- [x] テスト6件追加

## アイテム共通化 Phase 5: 保存漏れバグ修正 + visible対応 + リアルタイム同期

- [x] editSave()保存漏れ修正: subtitle(bottom/fontSize/maxWidth/fadeDuration/bgOpacity), topic(maxWidth/titleFontSize), version(fontSize/strokeSize/strokeOpacity/format)
- [x] 全アイテムvisible対応: saveVisible(opt-in) → skipVisible(opt-out)に変更、dev_activity以外でvisible保存
- [x] プレビュー→WebUIリアルタイム反映: index-app.jsに/ws/broadcast WebSocket接続追加、settings_updateイベントでスライダー自動更新
- [x] テスト5件追加（visible保存・固有プロパティ保存・skipVisible検証）

## アイテム共通化 Phase 2: broadcast.html JS共通化

- [x] `ITEM_REGISTRY` で6アイテムをレジストリ定義（hasSize/saveVisible/defaultZ）
- [x] `applyCommonStyle()` で共通スタイル適用（position/zIndex/bgOpacity直接 + CSS変数で新規プロパティ）
- [x] `applySettings()` を applyCommonStyle + アイテム固有コードの2段階に統一
- [x] `editSave()` を ITEM_REGISTRY ループに統一（ハードコード個別保存を廃止）
- [x] dev-activity-panel に `data-editable="dev_activity"` 追加（ドラッグ・リサイズ可能に）
- [x] ソースコード解析テスト11件追加（test_broadcast_patterns.py）

## アイテム共通化 Phase 1: 共通プロパティのDB保存基盤

- [x] `_COMMON_DEFAULTS` (20プロパティ) 定義（visible, 配置, 背景, 文字）
- [x] `_make_item_defaults()` で共通デフォルト + アイテム固有オーバーライドをマージ
- [x] 全6ビジュアルアイテムに共通プロパティ追加（avatar, subtitle, todo, topic, version, dev_activity）
- [x] dev_activityをDB保存対応（`overlay.dev_activity.*` キー新設）
- [x] テスト8件追加（共通プロパティ・API・dev_activity）

## バージョン表示

- [x] VERSIONファイル新規作成（0.1.0）
- [x] /api/statusにversion・updated_at（gitコミット日時）を追加
- [x] WebUIヘッダーにバージョン・更新日付を表示

## WebUIウィンドウキャプチャ管理の改善

- [x] WebUI: キャプチャ一覧を保存済みウィンドウベースに変更、各項目にレイアウトスライダー統合
- [x] WebUI: アクティブなキャプチャは緑ボーダー+表示/非表示トグル、非アクティブは半透明表示
- [x] capture_windowsテーブル新設（settings JSONから専用テーブルに移行）
- [x] C#アプリ: キャプチャ追加/停止時にWebSocketでPython側に即時通知（BroadcastWsEvent）
- [x] サーバー: C# WebSocket接続時にキャプチャ自動復元（visible=falseはスキップ）
- [x] DB閲覧: 全テーブル自動検出対応（settingsテーブル等も閲覧可能に）
- [x] 前回のウィンドウキャプチャを覚えておき次回も最初から表示
- [x] staticファイルにno-cacheヘッダー追加

## テスト充実フェーズ1 — DB・設定・TTS・テスト基盤

- [x] conftest.py拡張: test_db / mock_gemini / mock_env フィクスチャ追加
- [x] test_db.py: 44テスト（スキーマ・チャンネル・キャラクター・番組・エピソード・ユーザー・コメント・設定・BGM・トピック・スクリプト）
- [x] test_scene_config.py: 12テスト（DB/JSON優先順位・保存読み込み）
- [x] test_tts.py: 11テスト（言語タグ変換・TTSスタイル取得）
- [x] plans/testing-strategy.md: テスト充実プラン作成
- [x] テスト数: 39 → 114（+75テスト）

## テスト充実フェーズ2+3 — AI応答・WSL・Git監視・トピック

- [x] test_ai_responder.py拡張: +22テスト（キャラクター管理・generate_response/event/notes/self_noteのGeminiモック）
- [x] test_wsl_path.py拡張: +10テスト（is_wsl・IP取得・パス変換）
- [x] test_git_watcher.py: 11テスト（コミット解析・バッチ通知・ライフサイクル）
- [x] test_topic_talker.py: 15テスト（プロパティ・should_speak・トピック管理・get_next）
- [x] conftest.py: mock_geminiがfrom import先にもパッチするよう改善
- [x] テスト数: 114 → 177（+63テスト）

## テスト充実フェーズ4 — APIエンドポイントテスト

- [x] conftest.py: api_clientフィクスチャ追加（FastAPI TestClient + stateモック）
- [x] test_api_character.py: 6テスト（キャラクター取得・更新・言語モード取得・変更）
- [x] test_api_topic.py: 11テスト（トピックCRUD・スクリプト・一時停止・設定）
- [x] test_api_stream.py: 13テスト（シーン切替・音量制御・アバター・ステータス・環境変数マスク）
- [x] テスト数: 177 → 207（+30テスト）

## 音声アーキテクチャ刷新: C#アプリ直接パイプ（WASAPI廃止）— 作業中

### 完了
- [x] TtsDecoder.cs: WAV（24kHz mono 16bit）→ 48kHz stereo f32le PCM変換 + 音量適用
- [x] FfmpegProcess.cs: タイマーベース音声ジェネレータ + TTS/BGMミキシング（WASAPI不要）
- [x] HttpServer.cs: `tts_audio`/`bgm_play`/`bgm_stop`/`bgm_volume` WebSocketアクション
- [x] MainForm.cs: TTS常時ローカル再生(PlayTtsLocally) + 配信時FFmpegパイプ
- [x] MainForm.cs: BGMダウンロード→キャッシュ→NAudioローカル再生 + パネルUI状態表示
- [x] broadcast.html: 全音声再生コード削除（`<audio>`要素・AudioContext・メーター全撤去）
- [x] comment_reader.py: 素材準備→同時発火フロー（字幕+リップシンク+TTS一斉送信）
- [x] state.py: BGMコマンドをC#アプリにWebSocket転送
- [x] capture.py: C#アプリWebSocket接続時にBGM自動復元
- [x] プラン: plans/direct-tts-audio-pipe.md

### バグ修正
- [x] BGM配信パイプ: DecodeBgmToPcmに相対WebURLを渡していた→キャッシュファイルパスを使用
- [x] TTS音声ガビガビ: AudioWriterLoopとタイマーの両方でMixTtsIntoを呼んでいた→タイマーのみに統一
- [x] BGM音量変更がFFmpegに未反映: SetBgmVolume()追加、OnBgmVolumeから転送
- [x] 配信バッファリング: 音声ジェネレータが固定10msチャンクだがWindowsタイマー解像度15.6msで発火→音声65%供給→FFmpeg speed 0.69x。壁時計時間ベースのチャンクサイズ動的計算で1.01x安定化
- [x] ボリューム調整: waveOutSetVolumeがアプリセッション共有でBGM⇔TTS干渉→WaveChannel32でサンプルレベル音量制御に移行。パネル/Web UI/起動時取得の全経路でC#音声パイプラインに即時反映。TTS/BGM再生中のリアルタイム音量変更対応。FFmpegミキサーもSetTtsVolume/SetBgmVolumeでリアルタイム反映
- [x] 音量メーター: MeteringWaveProviderでBGM/TTS再生パイプラインのRMS/peakをリアルタイム測定。配信中はFfmpegProcess.MeasureLevelで実測。50msタイマーでパネルに送信。JS側ピークホールド1.5秒

- [x] リップシンク同期: 配信時は字幕・口パクをlipsyncDelay(ms)遅延させて音声と同期。非配信時はリアルタイム(0ms)。遅延値はcontrol-panel/Web UIから設定可能、DB永続化。broadcast.htmlが設定の真のソース（_volumeSync経由でパネルに転送）
- [x] 音声先行送信: TTS音声をC#アプリに先に送信しFFmpegキュー投入完了を待ってから字幕・口パクを発火するよう変更。lipsyncDelayを500ms→100msに削減（音声パイプライン遅延が大幅に縮小）

## Go Live / Stop ボタンの即時フィードバック

- [x] ボタン押下直後にテキスト変更（「準備中…」「停止中…」）+ CSSスピナー + disabled化で押した感を実現
- [x] C#側から処理完了/失敗時に `streamResult` メッセージをパネルに送信してボタン復帰
- [x] 処理完了後 `OnTrayUpdate` 即時呼び出しでステータス即時反映（3秒タイマー待ち解消）
- [x] プラン: plans/button-instant-feedback.md

## リップシンクと音声の4秒ずれ修正（暫定対応）

- [x] 原因特定: 映像（WGC即座キャプチャ）と音声（WASAPI Loopback回収、~500ms遅延）の経路差
- [x] Phase 1: broadcast.htmlリップシンク同期修正 — 口パク開始を`play().then()`に同期（WebSocketイベント受信時ではなく音声再生開始時）
- [x] Phase 2: 音声パイプバッファ縮小 — 1MB→64KB（遅延2.7秒→170ms）
- [x] Phase 3: 初期サイレンス縮小 — 3秒→300ms（パイプバッファ満杯防止）
- [x] FFmpegエンコード開始検知→音声キューフラッシュ（起動時蓄積50チャンクの遅延を除去）
- [x] `LIPSYNC_DELAY_MS = 500` で口パク開始を遅延（音声パイプライン遅延と一致させる暫定補正）
- [x] `AudioOffset` 設定をStreamConfigに追加（CLI `--audio-offset` / 環境変数 `AUDIO_OFFSET` で調整可能）
- [x] 根本解消プラン作成: TTS音声を直接FFmpegパイプに書き込み、WASAPI迂回を解消 → plans/direct-tts-audio-pipe.md
- [x] プラン: plans/lipsync-delay-fix.md

## 配信開始後の音声途切れ修正

- [x] 原因特定: FFmpegのRTMP接続確立中（speed=0.45x→1.0x、約40秒）にパイプ書き込みがブロック → WASAPIコールバック停止 → 音声データ消失
- [x] 音声書き込みを非同期化: ConcurrentQueue + バックグラウンドスレッド（AudioPipeWriter）でWASAPIコールバックを絶対にブロックしない設計に変更
- [x] キュー上限500チャンク（約5秒）超過時は古いデータを破棄（最新音声を優先）
- [x] FFmpeg thread_queue_size 512→1024に増大
- [x] 初期サイレンス1秒→3秒に増量（AAC encoder + resamplerプライミング）
- [x] WASAPI開始前に500ms待機（FFmpegパイプ読み取り安定化）
- [x] AudioLoopback統計ログを起動後30秒間は2秒間隔に変更（診断用）
- [x] FFmpeg stderr起動後60秒間をSerilogにも出力（診断用）
- [x] AudioWriterLoop停止時のOperationCanceledException catchで停止クラッシュ修正
- [x] StopAsync順序改善: パイプ閉鎖→スレッドJoin（ブロック解除を先に行う）
- [x] プラン: plans/audio-startup-fix.md

## コントロールパネルStopボタン修正

- [x] StopStreamingAsyncでフィールド（_ffmpeg/_audio/_activeStreamKey）を即座にクリア→UI即時反映
- [x] OnFrameReady=nullを_ffmpeg=nullより先に実行（キャプチャコールバックのNREクラッシュ防止）
- [x] FrameCapture.csのOnFrameReady呼び出しにローカル変数キャプチャ+NRE catchガード追加
- [x] AudioLoopback.Stop()のManualResetEventパターン除去（using早期disposeによるクラッシュ修正）
- [x] AudioLoopback.Stop()で_silenceTimerをnull先行設定（DataAvailableとのレース防止）
- [x] DataAvailableの_silenceTimer.Change()をtry-catch(ObjectDisposedException)で防御
- [x] AudioLoopback.Dispose()でNAudioのCOM Disposeをスキップ+GC.SuppressFinalize（ハング/クラッシュ回避）
- [x] WebView2にバックグラウンドスロットリング無効化フラグ追加（音声途切れ対策）
- [x] 未処理例外ハンドラ追加（AppDomain/ThreadException/UnobservedTaskException）
- [x] 診断ログ追加（Panel送受信・Stop各ステップ・Audio統計）
- [x] プラン: plans/post-electron-bugs.md

## Twitch配信音声途切れ修正

- [x] サイレンスタイマーの二重書き込み防止（lastDataTickフラグで実データ受信200ms以内はサイレンス送信スキップ）
- [x] _silenceTimer.Change()リセット廃止（フラグ方式に置換）
- [x] WebView2バックグラウンドスロットリング無効化（--disable-background-timer-throttling等3フラグ追加）
- [x] Audio統計ログ追加（10秒ごとdata/silence/bytesカウント）
- [x] プラン: plans/post-electron-bugs.md

## Electron完全削除（Phase 8）

- [x] win-capture-app/ ディレクトリ削除
- [x] capture.py からElectronビルド・デプロイ・管理コードを削除（1362行→約500行）
- [x] stream_control.py 簡素化（_use_native_app()・Electron分岐削除）
- [x] index.html からElectron UI要素削除（サーバー起動/停止・ビルド進捗・ワンクリックプレビュー）
- [x] broadcast.html からElectron IPC死コード削除（audioCapture・captureReceiver・setupDirectCapture）
- [x] .env.example から USE_NATIVE_APP 設定削除
- [x] .gitignore から win-capture-app 関連行削除
- [x] CLAUDE.md・README.md をネイティブアプリに統一更新

## プロセス終了しない問題の修正

- [x] HttpServer.Dispose に _listenTask.Wait(2000) 追加（ListenLoopが残り続ける問題）
- [x] FfmpegProcess.StopAsync で Kill() 後に WaitForExit(3000) 追加
- [x] FfmpegProcess.LogStderrAsync に _stopping チェックと EOF break 追加
- [x] AudioLoopback.Stop でタイマーコールバック完了を待機（ManualResetEvent）
- [x] MainForm.OnFormClosing をタイムアウト付き同期処理に変更 + Environment.Exit(0) で確実終了

## コントロールパネルをタブ化（Stream / Sound / Chat）

- [x] タブバー追加（Stream / Sound / Chat の3タブ）
- [x] Stream タブ: 配信制御 + キャプチャ + ログ
- [x] Sound タブ: 音量スライダー + 音量メーター
- [x] Chat タブ: プレースホルダー（Coming soon）
- [x] UIラベルを英語表記に統一
- [x] C#側の変更不要（WebView2メッセージインターフェース維持）
- [x] プラン: plans/control-panel-tabs.md

## 音量メーター危険ゾーン表示

- [x] control-panel.htmlにHot(-12dB〜-3dB)・Danger(-3dB〜0dB)ゾーン背景と境界ラインを追加
- [x] ピークが-3dB超でメーター枠が赤く光るクリッピング警告を追加
- [x] プラン作成: plans/volume-danger-zone.md

## UIラベル「TTS」→「Voice」に変更

- [x] control-panel.html（音量スライダー・メーターソース）とpreview.html（メーターソース）の表示を「Voice」に統一

## アバターライティング起動時復元修正

- [x] broadcast.htmlの`<script type="module">`（Three.js+VRM）と`<script>`（init/applySettings）の実行順序レースコンディションを修正。module scriptのCDN読み込み遅延により`window.avatarLighting`未定義のままライティング適用がスキップされていた問題を、pending settingsパターンで解決

## ウィンドウ閉じ時の音声ミュート

- [x] ×ボタンでウィンドウ非表示後もWebView2の音声（BGM/TTS）が鳴り続ける問題を修正。Hide()直後にCoreWebView2.IsMutedで即座にミュート

## ビュワー×ボタンの閉じ遅延修正

- [x] ×クリック時にHide()を即座に呼び出し、クリーンアップはバックグラウンドで実行するよう変更（WebView2/HTTP/WGCの同期破棄によるUI遅延を解消）

## ウィンドウキャプチャ永続化 + キャプチャタブ

- [x] キャプチャ設定をDB永続化（window_nameで保存、次回起動時にウィンドウ名マッチングで自動復元）
- [x] 保存済み設定API追加（GET/DELETE /api/capture/saved、POST /api/capture/restore）
- [x] Electron起動時・ワンクリックプレビュー時にキャプチャ自動復元
- [x] レイアウト変更時に保存済み設定も同期更新
- [x] Web UIに「キャプチャ」タブ追加（サーバー管理・キャプチャ操作・保存済み設定管理）
- [x] キャプチャUI を「配信画面」タブから「キャプチャ」タブに移動

## TTS英語発音改善

- [x] 英語の発音をちゃんと英語っぽく（AI生成時に言語タグ分離+スタイルプロンプト英語化+発音ヒント挿入、サウンドテスト言語選択対応）

## C#ネイティブアプリに音量メーター追加・音量カーブ改善

- [x] broadcast.html → WebView2 postMessage → C# → control-panel.html の音量レベル転送パイプライン追加
- [x] control-panel.htmlに音量メーターUI（レベルバー・ピーク・dB表示・BGM/Voiceソース表示）
- [x] AnalyserNodeをmasterGainの後に移動し、マスター音量変更がメーターに反映されるよう修正
- [x] 全音量チャンネル（Master/TTS/BGM）に二乗カーブ（perceptualGain）適用。人間の聴覚特性に合わせた知覚的音量制御

## プレビューウィンドウに音量メーター追加

- [x] broadcast.htmlにAudioContext+AnalyserNodeで音量測定（BGM+Voice合成RMS→dBFS）
- [x] postMessageでiframe親（preview.html）にリアルタイム送信（50ms間隔）
- [x] preview.html右パネルに音量セクション追加（グラデーションバー、ピークホールド、BGM/Voiceタグ）
- [x] Electronオフスクリーン配信時はメインプロセスミキサー用の/audio/levelsエンドポイントも追加

## Live2D/VTube Studio関連コードの完全削除

- [x] VTSコントローラー・デプロイスクリプト・対話式コンソール削除
- [x] VTSエンドポイント・接続ロジック・状態変数をコードから除去
- [x] pyvts依存・VTS環境変数・AVATAR_APP設定を削除
- [x] Live2D関連ドキュメント・リソースディレクトリ削除
- [x] VRM機能は影響なし（broadcast.html内Three.js+three-vrm）

## ライティング設定の永続化

- [x] ライティング設定（明るさ・コントラスト・色温度・彩度・環境光・指向性光・ライト方向）をDB保存し、次回起動時に自動反映（broadcast.html init()で/api/overlay/settings読み込み→applySettings適用）

## アバター色味改善

- [x] ACESFilmicToneMapping → NoToneMapping（トーンマッピングなし）
- [x] ライティング調整（AmbientLight 2.0→0.75、DirectionalLight 1.5→1.0、方向修正）
- [x] Web UIにライト直接制御（環境光・指向性光・ライト方向X/Y/Z）追加
- [x] ライティングプリセット保存・読込・削除機能（DB永続化）
- [x] 汎用確認ダイアログ（showConfirm）を実装し、全confirm()を置換

## Electron配信パイプライン（Phase 1+2）

- [x] Electronオフスクリーンレンダリング＋FFmpegでTwitch直接配信（xvfb/PulseAudio不要）
- [x] broadcast.htmlをoffscreen BrowserWindowで描画→paint event→rawvideo→FFmpeg→RTMP
- [x] Electron側HTTP/WebSocket API追加（stream start/stop/status, broadcast open/close）
- [x] WSL2側API追加（POST /api/capture/stream/start|stop, GET /api/capture/stream/status）
- [x] 無音音声（anullsrc）でTwitch音声要件対応
- [x] Phase 3: TTS/BGM音声キャプチャ（AudioContext+ScriptProcessorNode→PCM→IPC→Named Pipe→FFmpeg）
- [x] broadcast-preload.js追加（contextBridge経由でaudioCapture API公開）
- [x] Windows Named Pipe経由のPCMデータ中継（非WindowsはanullsrcフォールバックFFmpeg）
- [x] Phase 5: 配信制御API統合（go-liveからElectron配信開始、統合ステータスAPI）
- [x] WSL2配信パイプライン削除（stream_controller.py全削除、xvfb/PulseAudio/Chromium依存排除、Electron一本化）
- [x] stream_control.py/state.py/index.html/preview.htmlをElectron専用に簡略化
- [x] docs/obs-free-streaming.md削除、CLAUDE.md/README.md/.env.example/mkdocs.yml更新
- [x] Phase 6: MJPEG排除（キャプチャフレームをIPC直接転送、MJPEG HTTPエンドポイント廃止、タイミング競合修正）

## 字幕デバッグ・レイアウト修正

- [x] Web UIに字幕テスト表示/非表示ボタンを追加（デバッグ用API: POST /api/debug/subtitle, /api/debug/subtitle/hide）
- [x] 字幕のbottomパラメータがドラッグ後にリアルタイム反映されないバグ修正（style.topとbottomの競合解消）

## WebSocket統合（Step 1-3）

- [x] TODO表示をWebSocket push化（30秒ポーリング廃止、mtime監視+API変更時に即座ブロードキャスト）
- [x] キャプチャ映像をMJPEG→WebSocketバイナリ送信に変更（1byte index+JPEG、バックプレッシャー制御、MJPEG互換維持）
- [x] Electron↔WSL2間の制御をWebSocket常時接続に変更（HTTPフォールバック維持、リクエスト-レスポンスマッチング）
- [x] ビルドログをbuild.logに出力＋API（`/api/capture/build-log`）追加
- [x] dist権限エラー時にPowerShellでdist削除するフォールバック追加

## プレビュー確認→配信開始UX

- [x] プレビュー起動ワンクリック化（ビルド確認→ビルド→デプロイ→起動→プレビュー表示を自動実行、進捗バー付き）
- [x] ワンクリックプレビューを毎回フルビルド方式に変更（mtime差分チェック廃止→毎回asar再パック・デプロイ・再起動で確実に反映）
- [x] package.jsonハッシュをDBに保存し、古いexeの再ビルドを自動検知
- [x] capture_launch()をヘルパー関数にリファクタ（_deploy_to_windows, _launch_electron, _wait_for_server）
- [x] Electronキャプチャアプリのビルドテスト（ワンクリックプレビューでビルド→起動確認済み）
- [x] WEB UI読み込み時にElectronプレビューを自動起動
- [x] broadcast.htmlの編集モードにGo Live/配信停止ボタン+状態表示を追加
- [x] POST /api/broadcast/go-live（Setup+配信開始をワンステップ化）
- [x] broadcast-ui.htmlをindex.htmlにリネーム、/broadcast-uiルート削除
- [x] xvfb ChromiumでVRMアバター表示（--use-gl=angle --use-angle=swiftshaderで解決）
- [x] Electron環境での配信テスト（プレビュー確認→Go Live→Twitch配信成功）
- [x] ウィンドウキャプチャの動作テスト（Electronアプリ起動→キャプチャ→broadcast.html表示確認）
- [x] Electronプレビューウィンドウのメニューバー削除（Menu.setApplicationMenu(null) + setMenu(null)）
- [x] asar再パックのサイレント失敗を修正（権限修正+mtime検証+デプロイ検証）
- [x] 各要素のZ順序変更機能（右クリックメニュー→Z値ダイアログ、WEB UIレイアウトタブにも追加）
- [x] preview.html: iframe+コントロールパネル方式でツールバーとコンテンツの重なり解消
- [x] broadcast.htmlのembeddedモード（iframe内でツールバー非表示）
- [x] ワンクリックプレビューでasar更新時にElectronアプリを自動再起動（/quit API + フォールバック）

## Electronプレビューウィンドウ改善

- [x] プレビューウィンドウの位置・サイズを永続化（preview-bounds.json、move/resize時に自動保存）
- [x] 編集モードを常時有効化（?editパラメータ廃止、ツールバー常時表示、編集終了ボタン削除）

## 設定DB移行

- [x] scenes.json設定をDB優先に移行（scene_config.pyにload_config_value/load_config_json/save_config_value/save_config_json追加）
- [x] bgm.py: BGMトラック設定のDB化
- [x] avatar.py: アバターデフォルト設定のDB化
- [x] character.py: language_mode保存のDB化
- [x] stream_control.py: avatar_capture_url・音量設定のDB化
- [x] overlay.py: 音量・オーバーレイデフォルト設定のDB化
- [x] state.py: アバターデフォルト設定読込のDB化
- [x] web.py: startup言語モード復元のDB化

## Web UI整理

- [x] 「レイアウト」タブを「配信画面」にリネーム（分かりやすい名前に変更）
- [x] ウィンドウキャプチャのカードを「配信」タブから「配信画面」タブに移動
- [x] 「ダッシュボード」タブと「配信」タブを削除（TODO/Twitch情報/シーン/診断のUI・JS・CSS含む）
- [x] キャプチャウィンドウのレイアウト設定（X/Y位置・幅・高さ・Z順序）をWeb UIの配信画面タブに追加
- [x] キャプチャレイヤーの四隅リサイズ修正（重複ハンドル防止＋overflow:hidden除去）
- [x] Go LiveでElectron未起動時にワンクリックプレビューを自動起動してから配信開始
- [x] Electron WebSocket /ws/control接続不可修正（noServerモード+手動upgrade振り分けで複数WebSocket.Server共存）
- [x] serverUrl方向修正（get_windows_host_ip→get_wsl_ip: Electron→WSL2へのアクセスに正しいIPを使用）
- [x] FFmpeg自動ダウンロード機能追加（getFfmpegPath強化+downloadFfmpeg: PowerShellでBtbN FFmpeg Buildsから自動取得）
- [x] FFmpeg起動失敗の即座検出修正（spawn後500ms待機で即座終了を検知、エラーを正しく返す）
- [x] _ws_requestにtimeoutパラメータ追加（start_streamは120秒タイムアウトでFFmpegダウンロード対応）

## プロジェクト整理

- [x] OBS関連ファイル・コード完全削除（obs_controller.py, routes/obs.py, routes/stream.py, start_stream.py, stop_stream.py, overlay.html, audio-tts.html, audio-bgm.html, index.html, design-proposal.html, OBS関連ドキュメント3件, tests/test_scene_config.py）
- [x] state.py: OBSController/overlay_clients/tts_clients/bgm_clients削除、broadcast_clientsのみに統合
- [x] overlay.py: /ws/overlay, /ws/tts, /ws/bgm WebSocket削除、OBS用ページルート削除
- [x] bgm.py: _apply_bgm_volume()（OBS音量反映）削除
- [x] console.py: OBSコマンド・stream・init全削除、アバター専用に簡素化
- [x] scene_config.py: PREFIX/SCENES/MAIN_SCENE/_load_config()/_resolve_browser_url()削除、設定値のみに簡素化
- [x] scenes.json: avatar/main_scene/scenes OBS専用キー削除
- [x] requirements.txt: obsws-python削除
- [x] CLAUDE.md/mkdocs.yml/console-commands.md/メモリファイル全更新

## 調査タスク

- [x] OBSの機能調査（WebSocket API、シーン管理、ソース操作、フィルタ、配信制御等）
- [x] アバター表示・アニメーションの調査（PNGtuber / Live2D + VTube Studio / VRM等）
- [x] 3Dモデル調査（VRM形式、表示ソフト比較、VMC Protocol制御、モデル入手方法）

## 動作確認タスク

- [x] OBSを起動してTwitchで仮配信（画面には背景画像だけ表示）
- [x] Live2D + VTube Studio + OBS で配信テスト（アバターのデモ動作確認済み）
  - Bluetoothヘッドホン使用時、OBSがマイクを掴むとHFPプロファイルに切り替わり音質劣化する問題を確認 → マイク音声を無効にして解決

## 開発タスク

- [x] OBS制御プログラムの作成（Python + obsws-python）
- [x] VTube Studio制御プログラムの作成（Python + pyvts）
- [x] 対話式コンソールの作成（OBS・VTS・配信制御）
- [x] リソース管理方針の策定（WSL一元管理、デプロイスクリプト）
- [x] コードからシーンとソースを追加する（setup/teardown、個別add/remove）
- [x] ゲームキャプチャでVTube Studioのアバターを透過表示
- [x] システム作成のシーン・ソースに「[ATC] 」プレフィックスを付与してユーザー作成物と区別
- [x] VRM形式の3Dキャラ表示に対応（ブラウザVRMビューア + scene_config切替）
- [x] console.py相当のWebインターフェースを作成（FastAPI + HTML）
- [x] シーンの設定をJSONで設定できるように（scenes.json）
- [x] アバターの配置位置を設定可能に（scenes.jsonのavatar.transform）
- [x] セットアップ後にメインシーンへ自動切替（scenes.jsonのmain_scene設定）
- [x] シーンごとのアバター位置オーバーライド対応
- [x] Webインターフェースでアバター位置調整・scenes.jsonへの保存機能
- [x] Web UIにSetup/配信開始・停止ボタン、.env設定表示を追加
- [x] Twitchコメント読み上げ機能（Gemini 2.5 Flash TTS + twitchio）
- [x] AIコメント応答システム（character.jsonでキャラ設定・ルール定義、表情連動）
- [x] コメント・配信データのDB化（SQLite: チャンネル/キャラクター/番組/エピソード/ユーザー/コメント/アクション）
- [x] AIがどのようにコメントに対応するかをルール付けする方法を構築（character.json + ai_responder）
- [x] キャラクター設定をDBに移行し、Web UIから編集可能に（character.jsonはシード用として残存）
- [x] web.pyルート分割リファクタリング（514行→118行、5つのルートモジュール+共有state）
- [x] OBSController._clientカプセル化修正（get_scene_items追加、外部からの_client直接アクセス排除）
- [x] Geminiモデル名を.env設定可能に（GEMINI_CHAT_MODEL / GEMINI_TTS_MODEL）
- [x] print()→logging置換（src/全ファイル、エントリポイントにbasicConfig追加）
- [x] Geminiクライアント共通化（ai_responder/tts重複→src/gemini_client.py抽出）
- [x] db.py update_character SQLホワイトリスト化
- [x] comment_reader._respond()分割（AI応答・DB保存・オーバーレイ・TTS再生を個別メソッドに）
- [x] vts_controller WS接続コード重複解消（_establish_websocket抽出）
- [x] TODO.mdを配信画面中央にオーバーレイ表示（Web UIからトグル）
- [x] Twitch配信情報管理（タイトル・カテゴリ・タグの取得・更新をWeb UIから操作）
- [x] ターミナルウィンドウキャプチャ対応（window_captureソース追加、メインシーンに配置）
- [x] VRMにモデル変換（FBX→VRM 0.x変換パイプライン構築、MToonシェーダ修正、サムネイル埋め込み）
- [x] Twitchコメント応答でユーザー表示名を使用（display_name優先）
- [x] ターミナルウィンドウ自動選択（window_matchキーワードマッチング）
- [x] ターミナル位置をWeb UIから調整・scenes.jsonに保存可能に
- [x] scenes.jsonのSetup時リロード対応（保存した設定が次回Setupで反映）
- [x] TODOパネルをオーバーレイ起動時に自動表示
- [x] BGM再生機能（OBSメディアソース経由、Web UIから選曲・音量調整・試聴対応）
- [x] アバターが話した内容を表示（履歴表示・英語訳・コメント見やすく・キャラ名削除）
- [x] コミットや作業開始に合わせてアバターが発話（Git監視・配信開始挨拶・手動発話API）
- [x] TODOパネルをオーバーレイに再実装（Web UIから位置・サイズ・フォント設定可能）
- [x] Git監視をSetupボタンでも起動するよう修正（配信開始ボタンのみだった問題を修正）
- [x] 現在の作業パネル（CURRENT TASK）をオーバーレイに追加（Claude Codeフック連携）
- [x] 多言語コメント対応（相手の言語で返答、英語は日本語訳・その他は英語訳）
- [x] アバターの耳ぴくぴくアニメーション（Hair_ear_1.L/Rボーン、ランダム間隔・片耳/両耳）
- [x] コメント履歴をオーバーレイから削除し、AI応答をTwitchチャットに投稿するよう変更
- [x] TODO表示が消える問題を修正（setup/teardownの安定性改善で解決）
- [x] 声を変更（Leda→Despina、スタイルプロンプト「にこにこ」追加、全30ボイス×5スタイルの比較ページ作成）
- [x] キャラクター設定をDB一本化（character.json削除、デフォルト値をai_responder.pyの定数に移動）
- [x] Web UIデザイン刷新（Lavenderライトテーマ、ヘッダー+ステータスバー+5タブ分割、15テーマ切替付きデザイン提案ページ作成）
- [x] 最初の挨拶を削除（Setup時・配信開始時の自動発話を除去）
- [x] キャラクター名を「ちょび」に全箇所統一
- [x] アバターのセリフがチャット欄に表示されない問題を解消（再起動で解決、デバッグログ追加）
- [x] Gitコミット読み上げにクールダウン60秒+バッチ通知を追加
- [x] Claude Code作業中にアバターの動きが止まる問題を修正（idle animationをasyncio taskから専用スレッドに移行）
- [x] サーバー再起動方式を改善（--reload廃止、コミット時のみ再起動、startup自動復旧）
- [x] TODO表示の作業中アイテム強調（グロー+▶矢印+ボーダー）＆左上を汎用情報パネルに刷新
- [x] BGM再生機能（overlay audio経由、Web UIから選曲・音量調整・試聴、YouTube URLダウンロード対応）
- [x] BGM再生状態の永続化・再生中ハイライト表示
- [x] OBS音声モニタリングをオフに変更（配信出力のみ、ローカルモニターなし）
- [x] TTS/BGM音声ソース分離（独立ブラウザソース化でOBSミキサー個別制御、OBS SetInputVolume APIで音量制御、scenes.json audio_volumesに保存）
- [x] マスター音量追加（master × 個別 × 曲音量の実効値をOBSに適用、Web UIでカード分離表示）
- [x] 曲別音量復活（DB保存、再生・変更時にOBSへ即反映）
- [x] 音量スライダー0〜200%対応（OBS vol_mul上限2.0）
- [x] run.sh二重起動防止（PIDファイル+ポート使用チェック、kill -9で確実停止）
- [x] ACTIVITYパネルを一時非表示（display: none、コードは保持）
- [x] 作業中タスクをTODOリストの先頭に「作業中」セクションとして表示
- [x] イベント発話（コミット・作業開始等）もTwitchチャットに投稿
- [x] 字幕と音声の同期修正（TTS生成後に字幕と音声を同時送信するよう変更）
- [x] リップシンク実装（WAV振幅解析→30fpsで口BlendShape「A」を駆動、idle loop統合）
- [x] チャット投稿と音声再生の同期（TTS生成後にまとめて発火するよう変更）
- [x] トピック自発的発話機能（コメントがない時にトピックについて自動発話、スクリプト事前生成・補充、Web UI対応）
- [x] Web UIにDB閲覧タブ追加（テーブル選択・ページング・全テーブル対応）
- [x] トピック自発的発話をSetup/配信開始では開始せず、明示的にトピック設定した時のみ開始するよう変更
- [x] トピックパネルを常に表示（会話中以外は「----」表示）
- [x] 直近2時間の会話履歴を考慮したAI応答（配信またぎ対応、マルチターン形式）
- [x] アバター発話（トピック・イベント）をDBに保存して会話履歴に含める
- [x] 配信コンテキスト（タイトル・トピック・作業中タスク）をAIプロンプトに追加
- [x] 視聴者メモ機能（15分バッチでAIがユーザー特徴を自動メモ化、応答時にメモを反映）
- [x] 視聴者への挨拶を1配信1回に制限（エピソード内コメント数でAIに挨拶済みフラグを渡す）
- [x] 言語モード切替機能（日本語/英語メイン/英語+日本語混ぜ/マルチリンガルの4プリセット、Web UIから切替、scenes.jsonに永続化）
- [x] アバター画面のUI文字がOBSに表示される問題を修正（cropTop/cropLeftでトリミング）
- [x] アバターアイドルモーションのかくつき修正（まばたきをフレームベース化、フレームタイミング安定化）
- [x] イベント発話（コミット・実装通知）が言語モード設定に従うよう修正
- [x] Web UIリロード時のタブ復元（location.hashでアクティブタブを永続化）
- [x] TTS発音を言語モードに連動（英語モード時は英語スタイルプロンプトでネイティブ発音に）
- [x] テスト基盤構築（pytest + pre-commitフック、Phase 1: 純粋ロジック30テスト）
- [x] トピック自発的発話を改善（事前一括生成→リアルタイム1件生成、前回発話の続き、30文字制限、言語モード対応）
- [x] トピック自動ローテーション（10分経過+5回発話でAIが会話・配信状況から新トピック生成）
- [x] アバター自身の記憶メモ（会話履歴からAIが自動生成、応答時にシステムプロンプトに含めて一貫性を保つ）
- [x] トピック自動生成（トピック未設定時にAIが自動生成、会話ベース50%+キャラ記憶ベース50%の混合）
- [x] アバター発話のDB保存修正（comment_count未加算、トピック発話の保存漏れ、デバッグログ追加）
- [x] 手動メモ更新ボタンでアバター自身のnoteも更新するよう修正
- [x] Web UIのBGMトラック削除ボタン追加（確認ダイアログ付き、再生中は自動停止）
- [x] 英語+日本語混合の単調パターン改善（語尾だけ日本語→文中どこでも配置、ローマ字禁止、履歴5件に削減、多様性指示追加）
- [x] OBS不要配信システム構築（xvfb+Chromium+PulseAudio+FFmpegによるWSL2完結配信）
- [x] 配信合成ページ broadcast.html（overlay+TTS+BGM+VRMアバター統合、WebSocket統合接続）
- [x] 配信制御UI broadcast-ui.html（Setup/Start/Stop/Scene/Volume/Diag）
- [x] StreamController（xvfb/Chromium/PulseAudio/FFmpegプロセス管理、WSLg自動検出）
- [x] 配信制御API stream_control.py（/api/broadcast/*エンドポイント群）
- [x] ブラウザVRMアバター（Three.js+three-vrm、アイドルアニメーション移植）
- [x] VRMアバターWebSocket連携（blendshape/lipsync/lipsync_stopイベントでブラウザ側アバター制御）
- [x] レイアウトエディタ（broadcast-ui.htmlにアバター/字幕/TODO/トピックの位置・サイズ・透明度をスライダー+数値入力で調整、DB自動保存、リアルタイムプレビュー反映）
- [x] レイアウト設定をDB移行（scenes.jsonは初期値のみ、overlay.*キーでDB保存）
- [x] レイアウト単位を%/vwに全面変換（px→%/vw、解像度非依存）
- [x] アバター位置を中心座標+スケール方式に変更（right/bottom→positionX/Y+scale）
- [x] アバターライティング調整（明るさ/コントラスト/色温度/彩度、ACESトーンマッピング+ライト比率制御）
- [x] VRMレンダリング画質改善（pixelRatio最低2倍、SRGBColorSpace、ACESFilmicToneMapping）
- [x] 配信プレビューを別ウィンドウ化（iframe埋め込み廃止、ポップアップウィンドウ+別タブリンク）
- [x] パネル背景透明度をCSS変数化（--bg-opacity、字幕/TODO/トピック個別制御）
- [x] broadcast-ui.htmlをルート（/）に変更
- [x] サーバー再起動ボタン+更新検知ダイアログ（server_started_atポーリング、コミット再起動も検知）
- [x] DB名をcomments.db→app.dbにリネーム（実態に合わせて改名）
- [x] WEBUI全機能移植（OBS版→broadcast-ui統合：タブ化、TODO表示、Twitch配信情報、トピック管理、キャラクター設定、サウンド詳細、DB閲覧、環境変数表示、リンクバー整理）
- [x] Windowsウィンドウキャプチャシステム（Electronアプリ: desktopCapturer+MJPEGサーバー、WSL2側API+WebSocket連携、broadcast.htmlドラッグ&リサイズ編集モード、broadcast-ui.htmlキャプチャ管理UI）
- [x] レイアウト編集にスナップガイド線追加（ドラッグ・リサイズ時に画面中央・他パーツ端/中央への補助線表示+自動スナップ、グロー付き目立つデザイン）
- [x] プレビュー画面でカーソルキーによる要素移動（通常0.1%、Shift+1.0%、500msデバウンスDB保存）
- [x] プレビュー画面で辺リサイズハンドル追加（上下左右の辺中央につまみ、1軸のみリサイズ可能）
- [x] カスタムテキストアイテム（WebUIから自由に追加・編集・削除、broadcast.htmlでドラッグ＆リサイズ、DB永続化、WebSocketリアルタイム同期）
- [x] プレビューウィンドウの配信画面を16:9レターボックス表示（ウィンドウ自由リサイズ対応）
- [x] Electronプレビューウィンドウの検証ウィンドウ（DevTools）自動表示を削除
- [x] 配信音声: FFmpegの音声入力をanullsrc→ローカルHTTPストリーム（broadcast.htmlのPCM音声）に変更、backgroundThrottling無効化+AudioContext監視+診断ログ追加
- [x] 配信音声: メインプロセス直接WAVバイパス（broadcast.html AudioContext不使用、IPC経由でmain.jsが直接WAV取得→リサンプル→FFmpegストリーム書き込み）
- [x] 音声診断ログAPI追加（Electron側 `/audio/log`、WSL2プロキシ `/api/broadcast/audio-log`）
- [x] 配信遅延改善: FFmpeg低遅延フラグ追加（`-flush_packets 1`, `-flags +low_delay`, `-fflags nobuffer`, bufsize半減, thread_queue_size縮小, バックプレッシャー閾値8MB化）
- [x] 配信解像度を1920x1080→1280x720に変更（ビットレート2500kに調整、エンコード負荷軽減で遅延改善）
- [x] 配信BGM音声修正: createScriptProcessorNode→createScriptProcessor修正（WebSocket接続阻害の根本原因）、MP3デコード対応、BGM+TTSミキサー、pendingBgmUrlタイミング問題解決、broadcastWindow embedded修正
- [x] 配信定期停止修正: ミキサーを壁時計追従+自己補正タイマーに改修（setInterval→setTimeout）、常時データ書き込み（無音時もギャップなし）、AudioCapture無効化、初期サイレンス縮小、TCP Nagle無効化

## 開発配信機能 Phase 1-3: リポジトリ管理 + DevStreamManager + AI実況連携

- [x] dev_reposテーブル追加（name, url, local_path, branch, last_commit_hash, active, timestamps）
- [x] CRUD関数実装（add_dev_repo, get_dev_repos, get_active_dev_repos, get_dev_repo, update_dev_repo_commit, toggle_dev_repo, delete_dev_repo）
- [x] DevStreamManager実装（src/dev_stream.py: clone・remove・fetch・diff分析・監視ループ）
- [x] shallow clone（--depth 100）、上限10リポジトリ、diff 500文字制限
- [x] state.pyにdev_stream_manager統合（コールバック→speak_event("開発実況", ...)でTTS・字幕・チャット連動）
- [x] web.pyのsetup/startup復旧/shutdownにDevStreamManager統合
- [x] APIルート実装（scripts/routes/dev_stream.py: repos CRUD・toggle・check・status・start/stop）
- [x] WebUI「開発実況」タブ追加（監視ON/OFF・リポジトリ追加フォーム・一覧表示・toggle/check/削除）
- [x] TODOソース切り替え（自プロジェクト/外部リポジトリ選択、overlay.py汎用化、WebUIセレクトボックス）
- [x] Overlay開発アクティビティパネル（broadcast.htmlにDEV ACTIVITYパネル、15秒表示→フェードアウト）
- [x] テスト追加（test_db.py: 12、test_dev_stream.py: 20、test_api_dev_stream.py: 11）
- [x] CLAUDE.mdにテストセクション追加（実行方法・構成一覧・規約）
- [x] プラン: plans/dev-stream.md

## BGMトラックにYouTubeソースURLリンク追加

- [x] bgm_tracksテーブルにsource_urlカラム追加（マイグレーション付き）
- [x] YouTubeダウンロード時にソースURLをDBに保存（既存トラックへの再ダウンロードでも補完）
- [x] BGM一覧APIがsource_urlを返すよう変更
- [x] Web UIのBGMトラック名をYouTubeリンク化（source_urlがある場合のみ、点線下線付き）

## 素材ファイル管理（著作権物のWebUI管理）

- [x] 素材管理API追加（`scripts/routes/files.py`: アバターVRM・背景画像のアップロード/一覧/選択/削除）
- [x] Web UIに「素材」タブ追加（複数ファイルアップロード、プレビュー付き一覧、使用中表示、選択・削除）
- [x] broadcast.htmlで選択された素材を動的読み込み（起動時API確認＋WebSocketリアルタイム切替）
- [x] `python-multipart`依存追加（ファイルアップロード対応）
- [x] 著作権物（アバターVRM・背景画像）は`.gitignore`で既にgit管理から除外済み
- [x] git履歴にも著作権物が含まれていないことを確認済み（一度もコミットされていない）

## C#ネイティブ配信アプリ（Phase 1: 基盤）

- [x] .NET 8 SDK インストール（Windows側 dotnet.exe 8.0.419）
- [x] C# WinFormsプロジェクト作成（WebView2 + Vortice.Direct3D11 + Serilog）
- [x] WebView2オフスクリーンレンダリング（隠しウィンドウ -32000,-32000 で正常描画確認）
- [x] WGCフレームキャプチャ実装（TryCreateFromWindowId + Direct3D11CaptureFramePool で1920x1080/30fps取得）
- [x] D3D11テクスチャ→BGRA→PNG保存パイプライン（CsWinRT COM interop解決）
- [x] シンボリックリンクでgit管理統合（/mnt/c/Users/akira/Downloads/win-native-app → win-native-app/）

## C#ネイティブ配信アプリ（Phase 2: FFmpeg配信パイプライン）

- [x] FfmpegProcess: FFmpeg子プロセス管理（rawvideo stdin + 名前付きパイプ音声入力 → RTMP出力）
- [x] AudioLoopback: NAudio WasapiLoopbackCapture によるシステム音声キャプチャ
- [x] FrameCapture改修: OnFrameReadyコールバック、FPSスロットル、ステージングテクスチャ再利用
- [x] StreamConfig: 環境変数ベースの配信設定（STREAM_KEY/STREAM_RESOLUTION/STREAM_FPS/STREAM_BITRATE/FFMPEG_PATH）
- [x] MainForm統合: --stream フラグで自動配信パイプライン開始（WGC→FFmpeg stdin、WASAPI→named pipe→FFmpeg）
- [x] FFmpeg stderr → logs/ffmpeg.log 自動保存

## C#ネイティブ配信アプリ（Phase 3: ウィンドウキャプチャ）

- [x] WindowEnumerator: Win32 EnumWindows P/Invokeでウィンドウ一覧取得（自プロセス・最小化・タイトルなし除外）
- [x] WindowCapture: WGC CreateFreeThreadedで任意HWND→D3D11テクスチャ→BGRA→JPEG変換（FPSスロットル付き）
- [x] CaptureManager: ConcurrentDictionaryで複数キャプチャセッション管理（スレッドセーフ）
- [x] HttpServer: HttpListenerベースのHTTP API（/status, /windows, /capture, /captures, /snapshot/{id}）
- [x] MainForm統合: WebView2 JS injection（addCaptureLayer/removeCaptureLayer）でbroadcast.htmlにキャプチャ表示
- [x] stream.sh: Server/ディレクトリのビルドコピー追加

## C#ネイティブ配信アプリ（Phase 4: サーバー通信）

- [x] WebSocket `/ws/control` 実装（HttpListenerベースのWebSocketアップグレード、JSON RPCプロトコル）
- [x] 制御アクション実装（status, windows, start_capture, stop_capture, captures, start_stream, stop_stream, stream_status, screenshot, quit）
- [x] Electron互換レスポンス（broadcast/preview系アクションに互換応答、配列は{data:[...]}形式）
- [x] HTTPストリーミング制御エンドポイント追加（POST /stream/start|stop, GET /stream/status, POST /quit）
- [x] MainForm: WebSocket経由の動的streamKey配信開始、WebView2 CapturePreviewAsyncスクリーンショット
- [x] WSL2 FastAPIサーバーとの通信互換確認（既存の`_ws_request()`がそのまま動作）

## C#ネイティブ配信アプリ（Phase 5: 統合・移行）

- [x] stream_control.py: Electron固有コード→アプリ非依存化（`_ensure_capture_app()`でネイティブ/Electron自動選択）
- [x] ネイティブアプリ自動起動（`USE_NATIVE_APP=1`時にstream.sh経由で自動起動、90秒タイムアウト）
- [x] Electron自動起動はフォールバックとして維持（`USE_NATIVE_APP=0`で既存ワンクリックプレビュー）
- [x] Go Live/Stop/Status APIをアプリ非依存に統一（WebSocketプロトコルは既に共通）
- [x] システムトレイアイコン追加（NotifyIcon: 配信状態表示、右クリックメニューで配信開始/停止/終了）
- [x] トレイアイコン定期更新（3秒間隔: 配信中=赤、待機中=緑、uptime/frames/captures表示）
- [x] トレイからの配信開始/停止（バルーン通知付き）
- [x] .env.example に `USE_NATIVE_APP` 設定追加
- [x] FFmpegパス解決確認（stream.shがElectronダウンロード済FFmpegを`--ffmpeg-path`で渡す、PATHフォールバック有り）
- [x] Twitch配信テスト成功（Go Live API→FFmpeg→RTMP→Twitch映像確認）
- [x] UIスレッドエラー修正（HandleStartStream/StopStreamをBeginInvokeでマーシャリング）
- [x] WGCフレーム停止修正（Direct3D11CaptureFramePool.Create→CreateFreeThreadedに変更）
- [x] オフスクリーン描画停止修正（ウィンドウを-32000,-32000から画面中央CenterScreenに移動）
- [x] FFmpeg stdin書き込みブロック修正（WriteVideoFrameを非同期バックグラウンドスレッドに変更）
- [x] FFmpeg音声入力不足修正（初期サイレンス1秒送信 + WASAPIデータ未着時100msサイレンスフォールバックタイマー）
- [x] FFmpegに`-y -nostdin`フラグ追加（プロンプト防止）
- [x] stream.sh: `--ffmpeg-path`を常に渡すよう変更（配信モード以外でもGo Live API対応）
- [x] StreamConfigデフォルト解像度を1280x720に変更

## フレームレート最適化 Step 1-3（4fps → 18fps）

- [x] 映像入力をstdin匿名パイプ→名前付きパイプ（8MBバッファ）に変更（パイプ書き込み250ms→1ms）
- [x] BGRA→NV12 CPU変換追加（ColorConverter.cs新規、パイプ転送量3.7MB→1.4MBで63%削減）
- [x] HWエンコーダ自動検出（NVENC→AMF→QSV→libx264の優先順probe、`--encoder`オプション追加）
- [x] ダブルバッファ方式でGCプレッシャー回避（毎フレームnew byte[]廃止）
- [x] `-flush_packets 1`除去（RTMP出力のフレーム毎フラッシュが全体を0.748xに制限していた）
- [x] サイレンスフォールバック修正（10ms/100ms→100ms/100ms、音声不足でFFmpegが0.1x speedに制限されていた根本原因）
- [x] デフォルトフレームレートを30→20fpsに変更（GPU readbackが55ms/frameのため暫定対応）
- [x] フレームレート最適化プラン作成（plans/framerate-optimization.md）

## フレームレート最適化 Step 4（18fps → 30fps達成）

- [x] ダブルステージングテクスチャ・パイプライン化（CopyResourceとMapを1フレームずらし、GPU readback 55ms→0msに解消）
- [x] RowPitch一括コピー最適化（行ごとMemoryCopy 720回→一括コピー1回）
- [x] FPSスロットルを固定間隔ベースに変更（スレッドプールジッターによる30fps→22fps低下を解消）
- [x] デフォルトフレームレートを20fps→30fpsに復帰
- [x] Map計測ログ追加（Map=0ms readback=0ms を確認）
- [x] 結果: 30fps / speed=1.01x / drops固定（初期のみ）/ パイプwrite=1ms安定

## C#ネイティブ配信アプリ（Phase 6: プレビューウィンドウ統合）

- [x] FormBorderStyle.None → FixedSingle に変更（タイトルバー＋閉じる/最小化ボタン表示、リサイズ不可）
- [x] MaximizeBox = false（最大化ボタン無効化）
- [x] ウィンドウタイトルに配信状態をリアルタイム表示（「待機中」「配信中 HH:MM:SS」、トレイ更新タイマーで同期）
- [x] 配信中の閉じるボタン → トレイに最小化（誤終了防止、バルーン通知付き）
- [x] トレイの「終了」メニューとQuit APIは _forceClose フラグで強制終了を維持
- [x] トレイアイコンダブルクリックでウィンドウ復元（Show + Normal + Activate）
- [x] アプリ表示名を「WinNativeApp」→「AI Twitch Cast」に変更（ウィンドウタイトル・トレイ・バルーン・ログ・HTTPバージョン文字列）
- [x] タイトルバーをダークモードに変更（DwmSetWindowAttribute DWMWA_USE_IMMERSIVE_DARK_MODE）
- [x] broadcast.htmlからウィンドウ追加UI（セレクトボックス・追加ボタン・editLoadWindows/editAddCapture関数・10秒ポーリング）を完全削除
- [x] ClientSize修正（Size→ClientSize: タイトルバー分のクライアント領域縮小を解消）
- [x] 検証完了: FixedSingleウィンドウでWGCキャプチャ正常動作
- [x] 検証完了: ClientSize修正後、WebView2描画サイズが正確に1280x720
- [x] 検証完了: ウィンドウが最背面でもキャプチャ継続

## C#ネイティブ配信アプリ（Phase 7: UIパネル検証・修正）

- [x] ビルド成功確認（stream.sh でビルドエラーなし）
- [x] ウィンドウが1680x720で表示される（左1280: broadcast.html、右400: パネル）
- [x] パネルがダークテーマで表示される（control-panel.html読み込み成功）
- [x] WGCクロップ修正: クライアント領域オフセット計算（GetWindowRect+ClientToScreen）でタイトルバー・枠を除外
- [x] 配信制御: Go Liveボタンで配信開始 → Stopボタンで停止
- [x] 配信制御: 配信中にステータス表示（uptime）が更新される
- [x] ストリームキーをstream.shで常に渡すよう修正（パネルGo Live対応）
- [x] キャプチャ: ↻ボタンでウィンドウ一覧取得 → 開始 → broadcast.htmlに表示（layout null修正）
- [x] キャプチャ: 各アイテムに✕ボタンで個別停止（選択式UI廃止）
- [x] ログエリアのテキスト選択・コピー対応（user-select: text）
- [x] 音量スライダー: パネル操作でbroadcast.htmlの音量が変わる（JS変数名修正: broadcastState→volumes）
- [x] 音量スライダー: サーバーAPI経由でDB保存・WebSocket配信（共有HttpClient+デバウンス）
- [x] 音量スライダー: パネル初期表示でサーバーから現在値を取得
- [x] 音量スライダー: Web UI→パネル同期（broadcast.html applyVolumeからWebView2 postMessage通知）
- [x] Master音量200%対応（AudioContext GainNode経由、TTS/BGMは100%上限）
- [x] WebView2 autoplay音声許可（--autoplay-policy=no-user-gesture-required）
- [x] WebView2 JSコンソールログをアプリログに転送（console.log/error → postMessage → Serilog）
- [x] frames/drops表示をパネルから削除
- [x] 音量スライダー: HTTP POST→WebSocket経由に変更（POSTタイムアウト問題を解消、broadcast.htmlのWebSocket接続を利用してDB保存）
- [x] トレイアイコン: 既存のトレイ機能（配信開始/停止/最小化）が正常動作確認
- [x] Go Live API: WebSocket /ws/control経由での配信開始が正常動作確認
- [x] ウィンドウ閉じ修正: OnFormClosingにtry-catch追加+CleanupResourcesで_ffmpeg強制クリーンアップ（配信停止失敗時もウィンドウが閉じるように）

## FFmpegビルド時自動ダウンロード・同梱

- [x] ビルド前にffmpeg.exeが無ければBtbN/FFmpeg-Buildsから自動DL（download-ffmpeg.ps1）
- [x] csprojのMSBuild TargetでDL→ビルド出力にコピー（resources/ffmpeg/ffmpeg.exe）
- [x] FindFfmpeg()が自動検出するためstream.shの--ffmpeg-path指定不要に
- [x] Electron FFmpegフォールバック（ハードコードパス）を削除
- [x] .gitignoreにresources/ffmpeg/追加

## WebSocket SendAsync同時呼び出しエラー修正

- [x] SendWsResponseにSemaphoreSlimによる排他制御を追加（起動時の同時リクエストによるSendAsync競合を解消）

## Phase 0: 環境構築・基盤

- [x] GitHubリポジトリ作成
- [x] CLAUDE.md 作成
- [x] GitHub Pages自動デプロイ環境構築（MkDocs + GitHub Actions）
- [x] OGP設定
