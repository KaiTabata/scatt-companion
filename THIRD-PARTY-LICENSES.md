# Third-Party Licenses

SCATT Companion は、配布バイナリ (DMG / EXE) に Python ランタイムや
複数のサードパーティパッケージを同梱する。本書はそれら同梱物の
ライセンスと出典をまとめたもの。

ソースから `make gui` で起動する場合は同梱ではなく外部依存となるが、
法的扱いは変わらない。

---

## 1. 同梱ランタイム

| コンポーネント | ライセンス | 配布元 |
| --- | --- | --- |
| Python (CPython) | PSF License 2.0 | https://www.python.org/ |
| Qt 6 | LGPL-3.0 / 商用ライセンス | https://www.qt.io/ |

---

## 2. Python パッケージ

| パッケージ | ライセンス | プロジェクト |
| --- | --- | --- |
| PyQt6 | **GPL-3.0** / 商用ライセンス | https://www.riverbankcomputing.com/software/pyqt/ |
| numpy | BSD-3-Clause | https://numpy.org/ |
| pyqtgraph | MIT | https://www.pyqtgraph.org/ |
| bleak | MIT | https://github.com/hbldh/bleak |

---

## 3. GPL / LGPL の取り扱い

### PyQt6 (GPL-3.0)

PyQt6 は **GPL-3.0** で配布されているため、PyQt6 をリンクする本ソフトの
バイナリ配布物 (DMG / EXE) は実質的に GPL-3.0 の結合物となる。
GPL-3.0 第 6 条により、利用者は対応するソースコードを取得する権利を持つ。
本ソフトの完全なソースコードは下記から取得できる:

> https://github.com/KaiTabata/scatt-companion

ソースコードはバイナリ配布物の各バージョンに対応するタグ
(`v0.4.12` 等) で参照可能。

### Qt 6 (LGPL-3.0)

Qt 6 本体は **LGPL-3.0** で配布されている。LGPL の要件として、利用者は
本ソフト内の Qt 部分を修正版の Qt と差し替えて再リンクする権利を持つ。
これは PyQt と Qt が提供する標準的なビルド機構を用いて達成可能。

---

## 4. 各パッケージの著作権表示

### Python (CPython)

```
Copyright (c) 2001-2024 Python Software Foundation. All rights reserved.
Licensed under the PSF License Agreement.
```

### Qt 6

```
Copyright (C) The Qt Company Ltd. and other contributors.
Licensed under LGPL-3.0 (or commercial license).
```

### PyQt6

```
Copyright (c) Riverbank Computing Limited.
Licensed under GPL-3.0 (or commercial license).
```

### numpy (BSD-3-Clause)

```
Copyright (c) 2005-2024, NumPy Developers.
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

* Redistributions of source code must retain the above copyright notice,
  this list of conditions and the following disclaimer.
* Redistributions in binary form must reproduce the above copyright
  notice, this list of conditions and the following disclaimer in the
  documentation and/or other materials provided with the distribution.
* Neither the name of the NumPy Developers nor the names of any
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED.
```

### pyqtgraph (MIT)

```
Copyright (c) 2012-2024 pyqtgraph contributors.

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files
(the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge,
publish, distribute, sublicense, and/or sell copies of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
```

### bleak (MIT)

```
Copyright (c) 2020 Henrik Blidh

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files
(the "Software"), to deal in the Software without restriction.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
```

---

## 5. ライセンス全文

上記は要約。各ライセンスの正式な全文は次のリンクから取得できる:

- Apache 2.0 (本ソフト本体): https://www.apache.org/licenses/LICENSE-2.0
- GPL-3.0 (PyQt6): https://www.gnu.org/licenses/gpl-3.0.html
- LGPL-3.0 (Qt 6): https://www.gnu.org/licenses/lgpl-3.0.html
- BSD-3-Clause (numpy): https://opensource.org/licenses/BSD-3-Clause
- MIT (pyqtgraph, bleak): https://opensource.org/licenses/MIT
- PSF-2.0 (Python): https://docs.python.org/3/license.html

---

## 6. 商標

"SCATT" および "SCATT Expert" は SCATT Electronics の商標であり、
本ソフトとの相互運用性を示す目的での記述的使用のみを行っている。
本ソフトは SCATT Electronics の公式ソフトではなく、同社と提携も
していない。
