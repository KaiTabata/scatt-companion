# GitHub Pages 用紹介サイト

このディレクトリは GitHub Pages 配信用。`docs/` フォルダがそのまま `https://kaitabata.github.io/scatt-analyzer/` で公開される設定。

## ローカル確認

```sh
# シンプルな python http サーバで確認
cd docs
/opt/homebrew/bin/python3.10 -m http.server 8000
# ブラウザで http://localhost:8000/ を開く
```

## 公開手順

1. GitHub repo を **public** に変更
   ```sh
   gh repo edit --visibility public --accept-visibility-change-consequences
   ```
2. GitHub Pages を有効化(repo Settings → Pages):
   - Source: **Deploy from a branch**
   - Branch: **main**, Folder: **/docs**
3. 数分後に `https://kaitabata.github.io/scatt-analyzer/` で公開

## スクショの差し替え

`img/` に以下を入れると HTML が自動で表示する(無くても `onerror` で非表示):

| ファイル名 | 内容 |
| --- | --- |
| `dashboard.png` | Dashboard タブのスクショ |
| `sessions.png` | Sessions タブ |
| `shots.png` | Shots タブ (Series ブロック表示) |
| `target.png` | Target タブ |

macOS の `Cmd+Shift+4` で範囲スクショ → ファイル名を上記に変更してここに置く。

## 構成

- `index.html` メインページ
- `style.css` 配色・レイアウト(本体 GUI と同じ白基調)
- `img/icon.png` アプリアイコン(setup_app で焼き込んだものと同一)
