# Changelog

すべての変更点は [Keep a Changelog](https://keepachangelog.com/) 形式に倣う。
バージョニングは [Semantic Versioning](https://semver.org/) ベース。

## [0.4.12] — 2026-05-16

### Added
- **Windows の自動アップデート対応**: `scatt_auto_update.py` を OS 別分岐に拡張。PyInstaller bundled exe を判定 (`sys.frozen` + `_MEIPASS`)、`win_url` で配布された NSIS インストーラ `.exe` をテンポラリに DL、親プロセス終了を待つ BAT 経由で非サイレント起動して新版に置き換える
- **manifest.json の OS 別 URL**: 新フィールド `mac_url` / `win_url` を追加 (旧 `url` は Mac fallback として残し v0.4.11 Mac クライアントとも互換)
- **Web ダウンロードページに Windows .exe ボタンを追加** (`docs/index.html`)

### Changed
- 自動アップデートの進捗ダイアログ表記を「DMG をダウンロード中」→「インストーラをダウンロード中」に汎用化
- 旧 FAQ「Windows 対応は予定なし」を「Windows インストーラ配布あり / 検証は macOS 主体」に更新

## [0.4.11] — 2026-05-16

### Fixed
- **mode 切替後に軌跡サイズがズレるバグ** を修正
  - `TargetTab` / `SeriesTargetView` の `_recreate_target()` がどこからも呼ばれず、in-memory discipline が変わっても寸法属性が古いままだった
  - ホームタブ「始める」と Settings の discipline 変更で `discipline_changed` 経由で再描画されるよう配線
  - fitInView 倍率が `resizeEvent` / `_recreate_target` で別式だった → `scatt_target.view_radius_mm()` に集約 (全種目で外径 × 1.05 / 2 に統一)
- **死に Settings を撤去**: `thresh/suspicious_radius_mm` / `hold_velocity_mm_s` / `r95_good_mm` / `r95_bad_mm` は UI から書き込めても実コードで読まれていなかった (50m 決め打ち) → Settings タブから外し、種目別 (Discipline) の値を自動使用
- **50m 決め打ちの解析閾値を種目別化**: `hold_time` / `segment_phases` / `recoil_detailed` / `_gr_r95_bars` / 反動 settle 円が `T.current()` 由来になり、AR で「常に静止」「常に緑」「常に即 settle」と判定されていた問題を解消
- **`_gr_r95_history` の X 軸が他 history グラフと 1 ずれていた**問題を修正 (1-indexed → 0-indexed)
- **`_gr_cant_history`** の「全 0 なら旧フォーマット」判定を撤去 (水平を保てる射手の正常データを誤検出していた)

### Changed
- **Settings の discipline 切替が即時反映**になった (再起動不要)
- **`SeriesPanel` の異常閾値スピンボックス**: 下限を 50mm → 5mm に拡張 (AR の 25mm 設定が入るように)

### Removed
- **10m エアピストル (`pistol_10m`)** のサポートを廃止 (`scatt_target` / `scatt_i18n` / docs / Help タブ / CHANGELOG 過去エントリ全て更新)。旧版で `discipline=pistol_10m` を保存していたユーザーは次回起動時に `rifle_50m` にフォールバック

## [0.4.10] — 2026-05-16

### Added
- **水準器 (Level) タブ** — カント角を人工水平器風に可視化
  - 円形ベゼル内で水平線がカント角ぶん傾く (閾値色で着色、中央に固定マーカー)
  - 数字は計器下に控えめサイズ、shot ラベル / トレンド / 統計を併記
  - 直近 30 秒 (settings で 5〜120 秒) のライブトレンドグラフ
  - 接続状態ドット (Live / 停止中)、session 切替で shot 統計リセット
- **Settings に "Level" セクション** — 緑判定 (±°)、黄判定 (±°)、トレンド秒数

### Changed
- **全タブが横方向に自由にリサイズ可能** に — MainWindow 最小幅 1091px → 237px
  - Dashboard / グラフ / Sessions / Shots / ホーム を QScrollArea で包み、内部要素の min が外に出ないよう変更
  - ステータスバーのヒントラベルが横を引っ張らないよう SizePolicy 調整
  - 水準器タブは内部レイアウトが幅に応じて段階的に調整 (画面 1/4 幅でも崩れない)

## [0.4.9] — 2026-05-15

### Added
- **アプリ内 自動アップデート機能** (`scatt_auto_update.py`)
  - 起動 5 秒後に `docs/manifest.json` (GitHub Pages) を fetch して新版を検知
  - ダイアログ「今すぐ更新 / 後で / このバージョンをスキップ」
  - 「今すぐ更新」→ 進捗バー付きで DMG ダウンロード → installer シェルスクリプトを spawn (親 PID 終了待ち) → /Applications/ の旧 .app を新版に置き換え → quarantine 解除 → 新版を起動
  - Python 直起動 (開発実行) では自動更新スキップ
  - Settings の「自動更新を確認」(デフォルト ON) / 「更新確認 URL」(デフォルトで配布 manifest を指定) / 「このバージョンをスキップ」記憶

> 0.4.8 までは自動更新機能なし。0.4.8 → 0.4.9 への移行は最後の手動アップデートが必要 (DMG を再ダウンロード)、0.4.9 以降のリリースからは自動更新で届く。

## [0.4.8] — 2026-05-15

### Fixed
- **アプリ起動直後のハング (UI 無限ループ) を修正** (`scatt_gui.py`)
  - `TargetTab.resizeEvent` 内の `fitInView` 呼び出しがスクロールバー表示判定を変え、resize イベントが再帰発火する問題を再入ロックで防止
  - 起動後 20 秒以上応答しなくなる症状に対応

### Changed
- **ダークモードを完全削除** (使用しない方針に統一)
- **速度時系列グラフの閾値を種目別化**: 50m = 15/60 mm/s、10m AR = 3/10 mm/s
- **shot scatter にターゲットリングを薄く重ね描画** (データ範囲に合わせ自動スケール)
- **SCATT 互換 S1 を非表示化**: 本家計算式の完全特定ができていないため、誤差のある値の表示を停止 (代わりに `r95_1` を既定 KPI に)
- **discipline-aware 色判定**: 種目ごとの R95 妥当範囲に応じた良/悪判定
- **cant=0 検出**: 銃身傾斜 (Z) が 0 のデータを未取得扱いとし、cant 系指標から除外
- **所見コメントの軽微修正** + 個人データ表記の整理

### Build / Distribution
- **Makefile `app` ターゲットで pyproject.toml を一時退避**: setuptools が `[project].dependencies` を `install_requires` に変換 → py2app が `error: install_requires is no longer supported` で落ちる問題を回避 (trap で確実に復元)
- **`app-sign` で codesign の strict validation 警告を許容**: ad-hoc 署名で `liblzma.5.dylib` 警告が出ても署名は完了 → make が止まらないよう調整
- **紹介動画を実 SCATT データ + アニメーションへ刷新** + BGM (合成シネマティック ambient) 追加・autoplay 化
- **配布: GitHub Release v0.4.8 に DMG (約 260MB) を添付**

> v0.4.1 → v0.4.8 へのマイナー番号ジャンプは、間のスクショ更新・紹介サイト拡充・動画刷新・個人データ表記整理など複数のマイクロ修正を一括リリースとしてまとめたため。

## [0.4.1] — 2026-05-13

### Added
- **国際化 (i18n)**: 日本語 / 英語 切替 (`scatt_i18n.py`)
  - Settings → General に「表示言語」コンボ。変更は次回起動時に反映
  - タブラベル / About ダイアログを翻訳化

### Changed
- **所見コメントを観察事実のみに刷新** (`scatt_feedback.py`)
  - 技術前提 (「息止め失敗の兆候」「息止めが効いている」「銃の保持が良好」「グリップ統一」など) を全削除
  - 指導・処方系の文 (「〜を見直し」「〜を意識」「ルーティンを」) も削除
  - 心理推測 (「緊張・疲労」「リラックスできていました」) も削除
  - shot / session feedback は数値・単位・偏差だけ。解釈はシューター本人の領域に
  - 末尾の「→ ヒント:」アドバイス行を撤去
- **最小ウィンドウサイズを 420×380 まで縮小** (SCATT 本家の横に並べられる)
  - 各タブを `QScrollArea` でラップして縮小可能に
  - 画面幅 < 700px で左 shot 一覧を自動折り畳み、戻すと自動復元
  - `session_selector` 最小幅 280→100、`profile_selector` 120→80
  - `mini_target` 最小 200→140、`feedback_label` の最低高さ撤廃
  - 初回起動サイズも `availableGeometry × 0.92` で控えめに

## [0.4.0] — 2026-05-13

### 名称変更
- **アプリ名を SCATT Prone Analyzer → SCATT Companion へ** (伏射限定でなくなった反映)
- Bundle ID / パッケージ / パス系も `scatt-companion` に統一
- About ダイアログに「開発: Kai Tabata + Claude Opus 4.7」を明記

### Added (大きい)
- **AR モード本実装** (`scatt_modes.py`): 3 モード構成 (Prone / AR / ホールド練習)
  - ホーム画面でモード選択、SETTINGS に layout プリセットを一括書込
  - AR: 撃発時速度 / S1 / 撃発時心拍 / フォロースルー安定 を KPI
  - ホールド練習: ターゲット中心指標 (10a/R95等) を表から隠し、重心ベース指標のみ
- **AR データから実証された相関グラフ 5 種**:
  - S1 vs 着弾点距離 (r=+0.38)
  - 重心 R95 vs 10a-0.5 (r=-0.37)
  - S1 vs ホールド時間 / フォロースルー比 vs 10a / S1 推移
- **新指標 4 種** (`scatt_analysis.py`):
  - `centroid_r95_05` / `centroid_r95_full` (重心基準 R95)
  - `followthrough_ratio` (発射前後 R95 比)
  - `post_v_mean_05` (発射後 0.5s 平均速度)
- **新グラフ 2 種**:
  - 発射前後 軌跡 重ね (フォロースルー一貫性)
  - ホールド軌跡 (重心中心、ターゲット非依存)
- **shot list ミニターゲット**: 各行の右端に 16x16 ターゲット + 着弾点 (緑=10点圏 / 黄=9点 / 赤=外)
- **shot list 絞り込みフィルタ**: 「10点圏のみ」「9点以上」「★」等
- **2 shot 比較ダイアログ**: ⌘+クリック 2 発選択 → 右クリックメニューから比較
- **Live 即時診断ラベル**: 撃発時速度 / 静止 / 10a-0.5 / R95 を信号色で大きく表示
- **セッション総括カード**: Sessions タブ上部にベスト/ワースト shot + 一言コメント
- **軌跡アニメーション再生**: TargetTab 右クリック → ▶ 再生 / 0.25x-4x 速度切替
- **ダークモード**: 暗い射場用のテーマ、Settings から切替

### Changed
- **SCATT 互換 S1 を正しく実装**: 平均照準速度 (mm/s, 直前 1 秒) — 本家と完全一致
- **S2 は非表示**: 本家計算式の完全特定ができていないため、誤情報を出さない方針
- **射手名・種目を SCATT データから取得**: persons テーブル + distance/caliber から discipline 自動判定 (`10m AR (立射)` 等)
- **decode_trace 旧フォーマット対応**: 8 バイト/サンプル (cant 無し、2017 年頃のデータ) も読める

### Fixed
- shot list を再表示するときに fire_x/fire_y も取得し、ミニターゲットに反映
- `fetch_recent_sessions` の SQL バグ修正 (shots.session_id が存在しない問題)

## [Unreleased]

### Added
- **起動時ホーム画面** (`scatt_home.py`): 射手 / 種目 / 最近のセッション / 今週・今月ダイジェストを 1 画面で確認 → 「始める」で本画面へ
  - 表示モード: 自動 (複数射手 or 初回のみ) / 毎回 / 表示しない (Settings から切替)
  - 「次回からこの画面を表示しない」チェックで即時 OFF
  - 最近のセッション行をダブルクリックでそのセッションへ直接ジャンプ
- **紹介ページのスクリーンショット**: GitHub Pages (https://kaitabata.github.io/scatt-analyzer/) に Dashboard / Sessions サブタブ 5 種 / Shots を掲載
- **配布パス完成**: `make install-local` で /Applications/ への上書きインストール、`make dmg` で DMG 生成、GitHub Release v0.3.0 に DMG (157MB) を添付
- **OS 別パス抽象化** (`scatt_paths.py`): macOS / Windows / Linux でアプリ永続データ・ログ・SCATT 保存先を分岐。Windows 移植の下地

### Fixed
- Settings タブで `from PyQt6.QtWidgets import QLineEdit` の局所 import が QLineEdit を関数ローカル変数化していた問題 (起動時 UnboundLocalError)

## [0.3.0] — 2026-05-13

### Added
- **射撃種目切替** (`scatt_target.py`): 50m ライフル(既存)/ 10m エアライフル に対応
  - ターゲット幾何 (外径・リング間隔・黒地) と判定半径 (10a/10b/9c) を種目別に適用
  - Settings > 動作 > 射撃種目 から選択、再起動で反映
  - ターゲット描画のマーカー/フォント/十字を target 外径に合わせて自動スケール
- **複数射手 (Profile) 対応** (`scatt_profile.py`): 心拍/HRV/除外フラグを射手別に保存
  - ToolBar の射手コンボから切替・新規追加・改名・削除
  - 既定 (default) profile は既存 `extra.db` をそのまま継続利用
  - 新規 profile は `~/Library/Application Support/scatt-companion/profiles/{id}/extra.db` に独立保存
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
