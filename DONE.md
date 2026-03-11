# DONE

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

## Phase 0: 環境構築・基盤

- [x] GitHubリポジトリ作成
- [x] CLAUDE.md 作成
- [x] GitHub Pages自動デプロイ環境構築（MkDocs + GitHub Actions）
- [x] OGP設定
