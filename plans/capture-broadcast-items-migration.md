# capture.py broadcast_items全面移行プラン

## ステータス: 計画中

## 背景

Phase 7でcapture_windowsのデータ移行は完了したが、capture.pyは依然として旧構造（`capture_windows`テーブル + `capture.sources` settingsキー）を使用している。二重管理による同期バグのリスクがある。

### 現在の二重管理

| データソース | キー | 用途 | 問題 |
|-------------|------|------|------|
| `capture_windows`テーブル | window_name | 永続保存・復元用 | 停止時にvisibleが更新されないケースあり |
| `capture.sources` settingsキー | capture_id (UUID) | セッション中のアクティブ一覧 | JSON配列全件書き換え、線形探索 |

### 同期ポイント（5箇所）

1. `capture_start()` — 二重書き込み（capture_windows + capture.sources）
2. `capture_restore()` — capture_windowsから読み、capture.sourcesに書く
3. `_update_capture_layout()` — capture.sources更新 + capture_windows同期（window_nameがある時のみ）
4. `_remove_capture_layout()` — capture.sourcesのみ更新（capture_windowsは未更新）
5. `capture_client.py` — capture.sourcesからwindow_name逆引き

## ゴール

`broadcast_items`テーブルを唯一の真のソースにし、二重管理を解消する。

## 方針

### ID戦略

- broadcast_items.id: `capture:{window_name}` をベースにする（window_nameが永続的なキー）
- C#アプリのcapture_id（セッション固有UUID）はproperties JSONの`capture_id`に格納
- 復元時はproperties.window_nameでマッチング

### broadcast_items構造

```
broadcast_items:
  id: "capture:Terminal"
  type: "capture"
  label: "Terminal"
  x, y, width, height, z_index, visible: 共通カラム
  properties: {"window_name": "Terminal", "capture_id": "cap_abc123"}
```

## 実装ステップ

### Step 1: capture.pyのDB関数書き換え

#### 廃止する関数
- `_load_capture_sources()` — settings JSONを全件読み
- `_save_capture_sources(sources)` — JSON全件書き
- `_save_capture_layout(capture_id, layout, label, window_name)` — JSON配列内を線形探索+更新

#### 新しいパターン

```python
def _get_capture_items():
    """アクティブなキャプチャアイテム一覧をbroadcast_itemsから取得"""
    return [i for i in db.get_broadcast_items() if i["type"] == "capture"]

def _save_capture_to_item(capture_id, layout, label="", window_name=""):
    """キャプチャレイアウトをbroadcast_itemsに保存"""
    item_id = f"capture:{window_name}" if window_name else f"capture:{capture_id}"
    data = {
        "positionX": layout.get("x", 5),
        "positionY": layout.get("y", 10),
        "width": layout.get("width", 40),
        "height": layout.get("height", 50),
        "zIndex": layout.get("zIndex", 10),
        "visible": 1 if layout.get("visible", True) else 0,
        "window_name": window_name,
        "capture_id": capture_id,
    }
    db.upsert_broadcast_item(item_id, "capture", {**data, "label": label})
```

### Step 2: 各関数の書き換え

| 関数 | 変更内容 |
|------|----------|
| `_update_capture_layout()` | `db.update_broadcast_item_layout()` のみ（二重書き込み廃止） |
| `_remove_capture_layout()` | `db.upsert_broadcast_item(visible=0)` に変更 |
| `capture_start()` | 二重書き込み → `_save_capture_to_item()` 1回のみ |
| `capture_restore()` | `db.get_capture_windows()` → broadcast_itemsから type='capture' でフィルタ |
| `capture_sources()` | `_load_capture_sources()` → broadcast_itemsから読み込み |
| `capture_saved_list()` | `db.get_capture_windows()` → broadcast_itemsから読み込み |
| `capture_saved_delete()` | `db.delete_capture_window()` → broadcast_itemsから削除 |

### Step 3: capture_client.pyの逆引き修正

```python
# 旧: capture.sourcesからwindow_nameを逆引き
raw = db.get_setting("capture.sources")
for s in json.loads(raw):
    if s.get("id") == cap_id: ...

# 新: broadcast_itemsからcapture_idで検索
items = [i for i in db.get_broadcast_items() if i.get("capture_id") == cap_id]
```

### Step 4: 旧構造の廃止

1. `capture.sources` settingsキーを削除
2. `capture_windows` テーブルをDROP（または互換期間後に削除）
3. db.pyから旧CRUD関数を削除: `get_capture_windows`, `upsert_capture_window`, `update_capture_window_layout`, `get_capture_window_by_name`, `delete_capture_window`

## テスト

- capture CRUD via broadcast_items
- capture_start → broadcast_itemsに1回のみ書き込み確認
- capture_restore → broadcast_itemsから読み込み+名前マッチング
- capture停止 → visible=0に更新
- capture_client.py 逆引き

## リスク

1. **ID戦略**: window_nameが変わるとbroadcast_itemsのIDも変わる。復元時に旧名→新名のマッピングが必要
2. **レース条件**: ドラッグとC#通知の同時更新。SQLite WALモードで安全だが要テスト
3. **既存テストが少ない**: capture関連のDB直接テストを追加してから移行すべき

## 工数見積

| タスク | 見積 |
|--------|------|
| capture.pyの6関数書き換え | 2-3時間 |
| capture_client.pyの逆引き修正 | 30分 |
| テスト追加 | 1-2時間 |
| 手動テスト（配信アプリ接続確認） | 1時間 |
| **合計** | **半日程度** |
