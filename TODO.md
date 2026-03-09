# TODO

## バグ・問題
- [ ] TODO表示が消える問題を修正
        OBS再起動・Setup再実行・コード変更後にTODOパネルが表示されなくなる
        検証手順:
        1. `curl http://localhost:8080/api/todo` → itemsが返るか
        2. `curl http://localhost:8080/overlay` → HTMLにtodo-panelが含まれるか
        3. OBS接続後: `curl http://localhost:8080/api/obs/diag` → overlay_sourceのURLとreachableを確認
        4. OBSのブラウザソースのURLがWSL2のIP（localhost不可）になっているか
        5. OBSのソース一覧に「[ATC] オーバーレイ」が存在し、有効になっているか
        6. オーバーレイがソース順で最前面（一番上）にあるか
- [ ] VSeeFace 画面左上の文字がOBSに表示されているのを修正
- [ ] アバターアイドルモーションの繋ぎでかくつくのを修正

## 機能追加
- [ ] WEB UIのデザインを修正（デザイン提案ページを作成）
- [ ] 声を変更する
- [ ] Twitch配信時の過去のコメントを削除
- [ ] 配信のネタを設定してそれについて話す
- [ ] アバターが開発のログを読んで返事できるように

