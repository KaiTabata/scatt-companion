# SCATT Prone Analyzer

SCATT Expert の補助分析ツール。伏射(prone)に特化、本家 SCATT が出さない補助指標(振戦/呼吸 FFT、Pre-trigger 安定度、反動詳細、心拍/HRV、approach パターン等)を提供する。

**SCATT Electronics の公式ソフトではありません**。SCATT が保存した個人射撃データ(`storage.dat`)をローカルで読み取って解析する補助ツール。

## 機能

### SCATT 互換指標(本家の表記をそのまま)
- **10a / 10a-0.5** — 10-ring 内滞在時間(1s / 0.5s)
- **10b / 10b-0.5** — Inner-10 内滞在時間
- **9c** — 9-ring 内滞在時間
- **S1 / S2** — Pre-trigger 1秒 / 0.5秒のホールド円(R95、mm)

### 本家にない補助指標
- **Pre-trigger 安定度の z-score ランキング** — 個人の過去 shot から μ/σ を計算、悪い順に色付け
- **振戦・呼吸 FFT** — 8-12Hz 生理振戦、0.15-0.5Hz 呼吸の帯域パワー
- **反動詳細(Recoil タブ)** — Peak amplitude / Settle time / Follow-through R95 / Direction σ
- **Cant 詳細(Cant タブ)** — 発射時 cant 平均、pre-trigger σ、shot 間ドリフト
- **心拍 / HRV(BLE Heart Rate Profile 受信)** — Apple Watch + HeartCast や胸ベルト対応
- **自然言語フィードバック** — ローカル動作(API 不要)、shot/session 単位で所見生成
- **異常 shot 自動検出と削除** — 200mm 以上の誤反応を SCATT 側 DB ごと物理削除
- **データの永続化** — SCATT が保存しない心拍などを別 SQLite (`extra.db`) に保存

### GUI 構成
- **Dashboard** — 主役 4 KPI(10a/10a-0.5/S1/S2)+ 全指標表 + 選択可能グラフ枠
- **Sessions** — 上=セッション一覧、下=サブタブ(Overview / Recoil / Cant / Drift / Spectrum)
- **Shots** — Series 10 発ごとにブロック化(本家風、ターゲット+着弾点+集計テーブル)
- **Target** — ISSF 50m ライフルターゲット + 軌跡
- **Settings** — 永続化された動作 / 閾値 / レイアウト / 心拍設定
- **Help** — 各機能の説明

## インストール

### 必要環境
- macOS (Darwin)
- Python 3.10 以上 (`/opt/homebrew/bin/python3.10` を想定)
- 依存パッケージ: PyQt6, numpy, pyqtgraph, bleak

```sh
# brew で Python 3.10
brew install python@3.10

# 依存
make install
# または
/opt/homebrew/bin/python3.10 -m pip install --user -r requirements.txt
```

## 起動

### Finder からダブルクリック(推奨)
- `scatt-gui.command` をダブルクリック → GUI が Live モードで起動
- `scatt-watch.command` → ターミナルに新規 trace の JSONL が流れる

### ターミナル
```sh
make help           # コマンド一覧
make gui            # GUI 起動
make watch          # JSONL 監視
make ble-scan       # BLE 心拍デバイスをスキャン
```

## データ仕様(SCATT trace.data の復号)

SCATT Expert の `trace.data` BLOB を独自リバースで完全復号:

1. 固定 XOR キー(16 バイト): `e3 00 e9 00 34 85 1d 04 f0 95 c0 70 0e 1e b9 f3`
2. CBC 風 XOR デコード: `out[i] = in[i] ^ in[i-1] ^ key[i % 16]`
3. 1B drop → 2B qChecksum → qUncompress(zlib + 4B BE length)
4. 結果は QDataStream 形式、各サンプル 12B = `(X float32 BE, Y float32 BE, Cant float32 BE)`

詳しくは `README.html` 参照。

## 心拍連携

Apple Watch から心拍を受けるには、Watch + iPhone に [HeartCast](https://apps.apple.com/) などの BLE Heart Rate ブロードキャストアプリを入れ、iPhone から放送 → Mac で `bleak` 経由で受信。胸ベルト(Polar H10 等)も同じインターフェースで動く。

`make ble-scan` で確認可能。

## ライセンス

[Apache License 2.0](LICENSE)

## 注意

- SCATT Expert はサードパーティ製品(SCATT Electronics)。本ツールは公式ではない。
- 本ツールはローカルに保存された自分の射撃データを **読み取る** ことに加え、明示的な操作で `storage.dat` の `shots` / `traces` 行を **削除** する機能を持つ。削除は取り消し不可。
- 復号キーとアルゴリズムは SCATT Expert v20.05.31(Qt 5.9.9, macOS x86_64)で確認。他バージョンで挙動が変わる可能性。
