# DONE

## プレビュー確認→配信開始UX

- [x] プレビュー起動ワンクリック化（ビルド確認→ビルド→デプロイ→起動→プレビュー表示を自動実行、進捗バー付き）
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

## 設定DB移行

- [x] scenes.json設定をDB優先に移行（scene_config.pyにload_config_value/load_config_json/save_config_value/save_config_json追加）
- [x] bgm.py: BGMトラック設定のDB化
- [x] avatar.py: vsf_defaults設定のDB化
- [x] character.py: language_mode保存のDB化
- [x] stream_control.py: avatar_capture_url・音量設定のDB化
- [x] overlay.py: 音量・オーバーレイデフォルト設定のDB化
- [x] state.py: load_vsf_defaults()のDB化
- [x] web.py: startup言語モード復元のDB化

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
- [x] VRM形式の3Dキャラ表示に対応（VSFController + VMC Protocol + scene_config切替）
- [x] console.py相当のWebインターフェースを作成（FastAPI + HTML）
- [x] シーンの設定をJSONで設定できるように（scenes.json）
- [x] アバターの配置位置を設定可能に（scenes.jsonのavatar.transform）
- [x] セットアップ後にメインシーンへ自動切替（scenes.jsonのmain_scene設定）
- [x] シーンごとのアバター位置オーバーライド対応
- [x] Webインターフェースでアバター位置調整・scenes.jsonへの保存機能
- [x] Web UIにSetup/配信開始・停止ボタン、.env設定表示、VSeeFace初期値の保存・復元機能を追加
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
- [x] VSeeFace画面左上のUI文字がOBSに表示される問題を修正（cropTop/cropLeftでトリミング）
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
- [x] ブラウザVRMアバター（Three.js+three-vrmでVSeeFace不要化、アイドルアニメーション移植）
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

## Phase 0: 環境構築・基盤

- [x] GitHubリポジトリ作成
- [x] CLAUDE.md 作成
- [x] GitHub Pages自動デプロイ環境構築（MkDocs + GitHub Actions）
- [x] OGP設定
