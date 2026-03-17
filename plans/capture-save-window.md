# キャプチャウィンドウの永続保存

## ステータス: 完了

## 背景

キャプチャ開始時に`capture.saved_configs`にウィンドウ設定が保存されるはずだが、C#アプリの`HandleStartCapture`レスポンスに`name`フィールドがないため、Python側で`window_name`が常に空文字になり保存がスキップされている。

### 現状のフロー
1. preview.html → `POST /api/capture/start { sourceId, label }` → Python
2. Python → `POST /capture { sourceId }` → C#アプリ
3. C# → `{ ok, id, stream_url }` を返す（**nameがない**）
4. Python: `window_name = data.get("name", "")` → 空文字
5. `_upsert_saved_config("", label, layout)` → 空文字なので即return

## 修正方針

### Step 1: C#アプリのレスポンスにウィンドウ名を追加

**対象**: `win-native-app/WinNativeApp/Server/HttpServer.cs` `HandleStartCapture`

- `OnStartCapture`の戻り値からキャプチャIDを取得後、キャプチャ一覧から該当のName取得
- レスポンスに`name`フィールドを追加: `{ ok, id, name, stream_url }`

### Step 2: C#アプリのソースIDからウィンドウ名を解決

**対象**: `win-native-app/WinNativeApp/Server/HttpServer.cs` または `Capture/CaptureManager.cs`

- `HandleStartCapture`でsourceIdからウィンドウ名を引くか、`OnStartCapture`の戻り値にウィンドウ名を含める
- 最もシンプルな方法: キャプチャ開始後に`OnListCaptures`で該当IDのNameを取得

## 影響範囲

- `win-native-app/WinNativeApp/Server/HttpServer.cs` — レスポンス変更
- Python側・JS側の変更なし（既にnameを使うコードがある）
