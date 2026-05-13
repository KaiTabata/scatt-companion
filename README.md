# SCATT Companion

SCATT Expert の補助分析ツール。伏射(prone)に特化、本家 SCATT が出さない補助指標を提供する。

**紹介ページ**: <https://kaitabata.github.io/scatt-analyzer/>

**SCATT Electronics の公式ソフトではありません**。SCATT が保存した個人射撃データ(`storage.dat`)をローカルで読み取って解析する非公式の補助ツール。

## 機能

### SCATT 互換指標(本家と同じ命名)
- **10a / 10a-0.5** — 10点圏内 滞在時間(1s / 0.5s)
- **10b / 10b-0.5** — 10点中央(inner-10)内 滞在時間
- **9c** — 9点圏内 滞在時間
- **S1 / S2** — 直前 1秒 / 0.5秒のホールド円(R95、mm)

### 本家にない補助情報
- **z-score ランキング** — 過去 shot の μ/σ で「今回特にダメな指標」を浮かび上がらせる
- **周波数 4 帯域**(呼吸 / 心拍由来 / 力み / 全体) — 力みや息止め失敗の診断
- **反動詳細** — 振幅 / 戻り時間 / フォロースルー / 方向のばらつき
- **銃の傾き(Cant)詳細** — shot 間ドリフト・狙い中の揺れ
- **心拍 / HRV(BLE)** — Apple Watch + HeartCast、胸ベルト等
- **ローカル自然言語フィードバック** — API 不要、ルールベース所見生成
- **異常 shot 自動検出 + 物理削除** — SCATT 側 DB と同期削除
- **CSV / JSON エクスポート** — pandas/Excel/R 解析用

### GUI 構成(5 タブ)
- **Dashboard** — 主役 KPI 4 枚(自由選択) + ミニターゲット + 指標表(z-score 順) + NLG フィードバック + 4 枠グラフ
- **Sessions** — 上=セッション一覧、下=サブタブ(Overview / Recoil / Cant / Drift / Spectrum)
- **Shots** — Series 10 発ごとにブロック化(本家風、ターゲット + 着弾 + 集計)
- **Help** — 全機能の説明
- **Settings** — 永続化された動作 / 閾値 / レイアウト / 心拍 / エクスポート

### キーボードショートカット
| キー | 動作 |
|---|---|
| ↑ / ↓ | shot 一覧で前後の shot へ(Dashboard 連動) |
| ⌘1〜5 | タブ切替 |
| Space | Live 監視 ON/OFF |
| ⌘E / ⌘⇧E | 現セッション shots を CSV / JSON 出力 |
| ⌘R | 一覧の再読込 |
| F1 | Help へ |

## インストール

### 必要環境
- macOS 11 以降
- Python 3.10 以上(`/opt/homebrew/bin/python3.10`)
- 依存: PyQt6 / numpy / pyqtgraph / bleak

```sh
brew install python@3.10
git clone https://github.com/KaiTabata/scatt-analyzer.git
cd scatt-analyzer
make install
```

## 起動

### Finder からダブルクリック
- `scatt-gui.command` をダブルクリック → Live モードで起動
- `scatt-watch.command` → JSONL を Terminal に流す

### ターミナル
```sh
make help           # コマンド一覧
make gui            # GUI 起動
make watch          # JSONL 監視
make ble-scan       # BLE 心拍デバイスをスキャン
make app            # .app バンドルを生成
```

## 心拍連携

Apple Watch から心拍を受けるには Watch + iPhone に [HeartCast](https://apps.apple.com/) などの BLE Heart Rate ブロードキャストアプリを入れ、**iPhone から放送**(バックグラウンドでも安定) → Mac で `bleak` 経由で受信。胸ベルト(Polar H10 等)も同じ。

`make ble-scan` で動作確認可能。

## データ仕様(SCATT trace.data の独自復号)

1. 固定 XOR キー(16B): `e3 00 e9 00 34 85 1d 04 f0 95 c0 70 0e 1e b9 f3`
2. CBC 風 XOR デコード(`out[i] = in[i] ^ in[i-1] ^ key[i % 16]`)
3. 1B drop → 2B qChecksum → qUncompress(zlib + 4B BE length)
4. QDataStream 形式、各サンプル 12B = `(X float32 BE, Y float32 BE, Cant float32 BE)`

詳細は Help タブ参照。

## ライセンス

[Apache License 2.0](LICENSE)

## 注意

- SCATT Expert はサードパーティ製品(SCATT Electronics)。本ツールは公式ではない。
- 本ツールは `storage.dat` を **読み取る** ことに加え、明示的な操作で `shots` / `traces` 行を **物理削除** する機能を持つ。削除は取り消し不可。
- 復号キーとアルゴリズムは SCATT Expert v20.05.31(Qt 5.9.9, macOS x86_64)で確認。他バージョンで挙動が変わる可能性。
