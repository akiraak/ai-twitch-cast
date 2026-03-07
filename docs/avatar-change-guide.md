# アバター変更ガイド

VTube Studioで使用するLive2Dアバターを変更する方法と、選定時の注意点をまとめる。

---

## アバター変更の手順

### 1. モデルファイルの準備

Live2Dモデルは以下のファイルで構成される:

| ファイル | 必須 | 説明 |
|---------|:----:|------|
| `*.model3.json` | ○ | モデル定義ファイル（エントリポイント） |
| `*.moc3` | ○ | モデルデータ本体 |
| `*.png` (テクスチャ) | ○ | テクスチャ画像 |
| `*.motion3.json` | - | モーションデータ |
| `*.exp3.json` | - | 表情データ |
| `*.physics3.json` | - | 物理演算設定 |
| `*.pose3.json` | - | ポーズ設定 |

### 2. VTube Studioへのインポート

1. VTube Studioを起動
2. 画面をダブルクリック → メニューを開く
3. 人型アイコン（モデル選択）をクリック
4. 「自分のモデルをインポート」→「フォルダを開く」
5. 開いたフォルダにモデルファイル一式をコピー
6. VTube Studioに戻り、モデルをクリックして読み込む

### 3. 自動セットアップ

モデル読み込み時に「自動セットアップ」を選択すると、Live2Dの標準パラメータ名に基づいてトラッキング設定が自動構成される。その後、手動で微調整を行う。

### 4. API経由でのモデル切替

VTube Studio APIを使えば、プログラムからモデルを切り替えることもできる。

```python
# 利用可能なモデル一覧を取得
response = await vts._request(
    vts._vts.vts_request.BaseRequest("AvailableModelsRequest")
)
models = response["data"]["availableModels"]

# モデルをロード
request = vts._vts.vts_request.BaseRequest(
    "ModelLoadRequest",
    {"modelID": "ターゲットのmodelID"}
)
await vts._request(request)
```

---

## モデル選定時の注意点

### パラメータの充実度が最重要

本プロジェクトではAPI経由でパラメータを直接制御してアバターを動かす。モデルが持つパラメータの数と種類がアバターの表現力に直結する。

#### 最低限必要なパラメータ

| パラメータ | 用途 | 重要度 |
|-----------|------|:------:|
| `MouthOpen` / `ParamMouthOpenY` | 口の開閉（リップシンク） | 必須 |
| `EyeOpenLeft` / `EyeOpenRight` | まばたき | 必須 |
| `FaceAngleX` / `FaceAngleY` / `FaceAngleZ` | 顔の向き・傾き | 高 |
| `MouthSmile` / `ParamMouthForm` | 口の形（笑顔等） | 高 |
| `EyeBallX` / `EyeBallY` | 視線の方向 | 中 |
| `BodyAngleX` / `BodyAngleY` / `BodyAngleZ` | 体の傾き | 中 |
| `BrowLeftY` / `BrowRightY` | 眉の上下 | 中 |

#### あると表現力が上がるパラメータ

- 頬染め（`CheekPuff`等）
- 舌出し
- 衣装切替用パーツ表示/非表示
- 手・腕の動き

### モーション・表情ファイルの有無

!!! warning "モーションが少ないモデルの懸念"
    安価なモデルや無料モデルでは、モーション（`.motion3.json`）や表情（`.exp3.json`）ファイルが付属していないことがある。この場合:

    - **ホットキーで表情を切り替えられない**（表情データがないため）
    - **アイドルモーション（待機動作）がない**（呼吸・揺れ等の自然な動きが出ない）
    - パラメータ制御のみで動かすことになり、**自然な動きを再現するためのコード量が増える**

    モーション・表情ファイルが豊富なモデルを選ぶと、API制御がシンプルになる。

### パラメータの段階数（メッシュ分割の細かさ）

同じ「口の開閉」パラメータでも、モデルによって滑らかさが異なる:

- **安価なモデル**: 開/閉の2段階のみ → パクパクした動き
- **高品質なモデル**: 4〜6段階の中間状態 → 滑らかな口の動き

眉・目・口など感情表現に関わるパーツは中間状態が多いほど自然に見える。

### 物理演算の有無

`physics3.json` が付属しているモデルは、髪や衣装の揺れが自動計算される。パラメータを動かすだけで髪が自然に揺れるため、API制御の手間が大幅に減る。

### ライセンス

| 確認項目 | 内容 |
|---------|------|
| 商用利用 | Twitch配信での使用が許可されているか |
| 改変の可否 | パラメータの追加・表情の編集が許可されているか |
| クレジット表記 | 配信画面やプロフィールへの表記が必要か |
| 再配布 | モデルファイルをリポジトリに含めてよいか（通常は不可） |

!!! note "モデルファイルの管理"
    ほとんどのモデルはライセンス上リポジトリへの同梱が不可。VTube Studioのモデルフォルダに直接配置し、`.gitignore` で除外すること。

---

## モデルの入手先

詳細は[アバター表示・アニメーション調査](avatar-research.md#live2d)を参照。

| 入手先 | 特徴 | モーション充実度 |
|--------|------|:----------------:|
| [nizima](https://nizima.com/) | Live2D公式。購入前にパラメータをプレビュー可能 | 高（確認しやすい） |
| [BOOTH](https://booth.pm/) | 品揃え豊富。無料モデルあり。品質はピンキリ | モデルによる |
| VTube Studio内蔵 | テスト用に最適。パラメータ豊富 | 中 |
| オーダーメイド | 要件を指定できる。パラメータ・モーション数を依頼可能 | 指定次第 |

**nizimaの利点**: 購入前にモデルのパラメータを実際に操作して動きを確認できるプレビュー機能がある。モーションや表情の充実度を事前に把握できるため、API制御前提の本プロジェクトには特に有用。

---

## 本プロジェクトでの推奨チェックリスト

モデル選定時に確認すべき項目:

1. **口の開閉が滑らか**か（2段階でなく中間状態があるか）
2. **まばたき・眉・視線**のパラメータがあるか
3. **表情ファイル（`.exp3.json`）が付属**しているか
4. **モーションファイル（`.motion3.json`）が付属**しているか（特にアイドルモーション）
5. **物理演算（`physics3.json`）が付属**しているか
6. **体の傾き**パラメータがあるか
7. ライセンスがTwitch配信に対応しているか

---

## 参考資料

- [VTube Studio - モデルの読み込み](https://github.com/DenchiSoft/VTubeStudio/wiki/Loading-your-own-Models)
- [VTube Studio - モデル設定](https://github.com/DenchiSoft/VTubeStudio/wiki/VTS-Model-Settings)
- [VTube Studio - アニメーションとトラッキングの相互作用](https://github.com/DenchiSoft/VTubeStudio/wiki/Interaction-between-Animations,-Tracking,-Physics,-etc.)
- [Live2D 標準パラメータ一覧](https://docs.live2d.com/en/cubism-editor-manual/standard-parameter-list/)
- [VTube Studio API](https://github.com/DenchiSoft/VTubeStudio)
