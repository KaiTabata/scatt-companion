# Changelog

すべての変更点は [Keep a Changelog](https://keepachangelog.com/) 形式に倣う。
バージョニングは [Semantic Versioning](https://semver.org/) ベース。

## [Unreleased]

### Added
- **起動時ホーム画面** (`scatt_home.py`): 射手 / 種目 / 最近のセッション / 今週・今月ダイジェストを 1 画面で確認 → 「始める」で本画面へ
  - 表示モード: 自動 (複数射手 or 初回のみ) / 毎回 / 表示しない (Settings から切替)
  - 「次回からこの画面を表示しない」チェックで即時 OFF
- **紹介ページのスクリーンショット**: GitHub Pages (https://kaitabata.github.io/scatt-analyzer/) に Dashboard / Sessions サブタブ 5 種 / Shots を掲載

### Fixed
- Settings タブで `from PyQt6.QtWidgets import QLineEdit` の局所 import が QLineEdit を関数ローカル変数化していた問題 (起動時 UnboundLocalError)

## [0.3.0] — 2026-05-13

### Added
- **射撃種目切替** (`scatt_target.py`): 50m ライフル(既存)/ 10m エアライフル / 10m エアピストル に対応
  - ターゲット幾何 (外径・リング間隔・黒地) と判定半径 (10a/10b/9c) を種目別に適用
  - Settings > 動作 > 射撃種目 から選択、再起動で反映
  - ターゲット描画のマーカー/フォント/十字を target 外径に合わせて自動スケール
- **複数射手 (Profile) 対応** (`scatt_profile.py`): 心拍/HRV/除外フラグを射手別に保存
  - ToolBar の射手コンボから切替・新規追加・改名・削除
  - 既定 (default) profile は既存 `extra.db` をそのまま継続利用
  - 新規 profile は `~/Library/Application Support/scatt-prone-analyzer/profiles/{id}/extra.db` に独立保存
- **バックアップ / インポート機能** (`scatt_backup.py`): 補助 DB (心拍・除外フラグ) と設定を zip で書き出し / 復元
  - Settings タブから操作、manifest 付き (バージョン / 作成日時 / ホスト) で zip 化
- **更新通知** (`scatt_update.py`): 公開 JSON manifest を取りに行く軽量チェッカー
  - Settings の "更新確認 URL" に manifest を指定 → "更新を確認" ボタンで新版有無を表示
- **pytest 単体テスト** (`tests/`): scatt_target / scatt_analysis / scatt_backup / scatt_feedback / scatt_update / scatt_profile を網羅
  - 計 26 ケース、`make test` で実行

### Changed
- 残っていた `print("[warn] ...")` を `LOG.warn/info/error` に統一(ログファイルへ集約)
- ツールチップの判定半径 (R≤5.2mm 等) を現在の射撃種目に応じて動的表示

### Fixed
- main() 内の `from PyQt6.QtWidgets import QApplication` で起動時に UnboundLocalError が出ていた問題

## [0.2.0] — 2026-05-12

### Added
- **5 タブ構成**: Dashboard / Sessions / Shots / Help / Settings(Target タブを Dashboard のミニターゲットに統合)
- **Sessions タブにサブタブ**: Overview / Recoil / Cant / Drift / Spectrum でセッション横断レビュー
- **本家 SCATT 互換指標**を主役 KPI に: 10a / 10a-0.5 / S1 / S2
- **Shots タブを 10 発 Series 単位**にブロック化(本家風 ターゲット + 着弾 + 集計テーブル + μ 行)
- **shot 個別の「集計から除外」機能**: 空撃ち等を右クリックで除外、z-score 計算/集計から自動排除
- **セッション PDF 出力**(`scatt_pdf.py`): 集計表 + shot 一覧 + NLG 所見を A4 PDF に
- **ローカル自然言語フィードバック**(`scatt_feedback.py`): API 不要、ルールベース所見生成
- **BLE 心拍受信**(`scatt_heart.py`): Apple Watch + HeartCast や胸ベルト対応
- **補助 DB 永続化**(`scatt_storage.py`): 心拍/HRV/除外フラグを別 SQLite に保存
- **CSV / JSON エクスポート**(`scatt_export.py`): pandas/Excel/R 解析用
- **周波数 4 帯域**: 呼吸 (0.15-0.5Hz) / 心拍由来 (0.8-2Hz) / 力み (8-12Hz) / 全体
- **ベスト/ワースト比較グラフ**、**コンディションマップ**(心拍×HRV×S2)など 23 種のグラフ
- **z-score ランキング**: 過去 shot との比較で「今回特にダメな指標」を浮かび上がらせる
- **キーボードショートカット**: ↑↓ shot 切替、⌘1〜5 タブ、Space Live、⌘E CSV、F1 Help
- **Settings タブ**でレイアウト自由度: 各セクション可視性、主役 KPI 4 枠を全 24 指標から自由選択
- **セッション切替自動追随**: SCATT 側で session 切替を検出して GUI も自動切替
- **比較範囲**(現セッション/同姿勢/全 shot)を ToolBar で切替
- **異常 shot 自動検出と物理削除**(発射点距離 ≥ 200mm)、SCATT 側 DB と連動
- **ログシステム**: `~/Library/Logs/scatt-analyzer/app.log`
- **uncaught exception ハンドラ**: 落ちる前にダイアログ + ログ
- **About ダイアログ**(メニュー / Settings タブから)
- **設定 / 補助 DB の初期化ボタン**
- **アプリアイコン**(`make_icon.py` で生成)
- **py2app `.app` ビルド設定**(`setup_app.py`, `make app`)

### Changed
- 主役 KPI ラベルを SCATT 互換略号のみに短縮(`10a` / `S1` / `S2` 等)、詳細はツールチップで
- 用語を全面日本語化(`compare:` → `比較対象:`、`Live Start` → `Live 開始` 等)
- グラフタイトル・軸を全面日本語化
- 「振戦」→ 「力み (8-12Hz)」「ふるえ」へ表記変更
- 「Cant」→ 「銃の傾き」(略号は併用)
- 配色を白基調オフィススタイルに変更(ダークから)
- Shot 一覧を session 内連番・session 限定表示に
- 指標表を z-score の悪い順にソート

### Removed
- Target タブ(Dashboard のミニターゲットに統合)
- 反動方向ヒストグラム → 反動方向 × 振幅 散布図に置換
- 銃の傾きヒストグラム → ベスト/ワースト比較に置換

### Fixed
- 軌跡の y 座標反転(pyqtgraph / QGraphicsView 座標系の差を吸収)
- セッション切替時の cache invalidate(tuple key 対応)
- 速度グラフの凡例残留バグ

## [0.1.0] — 2026-05-12

### Added
- 初回リリース。SCATT Expert の `trace.data` BLOB を完全復号
- PyQt6 デスクトップ GUI(Dashboard / Sessions / Spectrum / Shots / Recoil / Drift / Target / Help / Settings の 9 タブ)
- 主要分析: 速度、R95、Cant、tremor power、呼吸 power、approach パターン
- BLE 心拍プロファイル(`bleak`)
- リアルタイム監視(`scatt_watch.py`)
- ターゲット描画(ISSF 50m ライフル)
- 並行読み出し検証スクリプト
- `Makefile` でコマンド一括化
- Apache License 2.0
