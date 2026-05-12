#!/usr/bin/env python3
"""周囲の BLE デバイスをスキャンし、Heart Rate Service (0x180D) を持つものを表示する。

使い方:
  /opt/homebrew/bin/python3.10 scatt_ble_scan.py

事前準備:
  1. Apple Watch で HeartCast を起動 → "Broadcast" を ON にする
     (HeartCast の場合は Workout 開始が必要なこともある)
  2. macOS の「システム設定 > プライバシーとセキュリティ > Bluetooth」で
     Python (またはターミナル) に Bluetooth アクセスを許可

出力例:
  scanning for 10 sec...
    XX:XX:XX:XX:XX:XX  Apple Watch HRM         uuids=2  ★ Heart Rate
"""

import asyncio
import sys

try:
    from bleak import BleakScanner
except ImportError:
    print("error: bleak がインストールされていません。", file=sys.stderr)
    print("  /opt/homebrew/bin/python3.10 -m pip install --user bleak", file=sys.stderr)
    sys.exit(1)


async def main():
    print("scanning BLE devices for 10 sec...")
    print("-" * 70)
    try:
        devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
    except TypeError:
        # 古い bleak は return_adv 引数なし
        devs = await BleakScanner.discover(timeout=10.0)
        devices = {d.address: (d, None) for d in devs}

    found_hr = 0
    for addr, item in (devices.items() if isinstance(devices, dict) else
                       [(d.address, (d, None)) for d in devices]):
        if isinstance(item, tuple):
            device, adv = item
        else:
            device, adv = item, None
        name = device.name or "<no name>"
        uuids: list = []
        if adv is not None and getattr(adv, "service_uuids", None):
            uuids = list(adv.service_uuids)
        else:
            md = getattr(device, "metadata", None) or {}
            uuids = list(md.get("uuids") or [])
        is_hr = any("180d" in str(u).lower() for u in uuids)
        marker = "  ★ Heart Rate" if is_hr else ""
        print(f"  {addr}  {name[:35]:<35}  uuids={len(uuids):>2}{marker}")
        if is_hr:
            found_hr += 1
            for u in uuids:
                print(f"      service: {u}")

    print("-" * 70)
    if found_hr == 0:
        print("Heart Rate device が見つかりませんでした。\n")
        print("チェック項目:")
        print("  - Apple Watch で HeartCast を起動し、Broadcast を ON にしたか")
        print("  - HeartCast が必要に応じて Workout モードに入っているか")
        print("  - macOS のシステム設定 → Bluetooth が ON か")
        print("  - 「プライバシーとセキュリティ → Bluetooth」で Python/Terminal に許可を与えたか")
        print("  - Apple Watch を Mac から 3m 以内に置いたか")
    else:
        print(f"OK: {found_hr} 個の Heart Rate デバイスを検出。")
        print("→ GUI 側の Settings タブで device address を空欄のままにすれば自動接続、")
        print("  もしくは上記の address をコピーして指定すると接続が速い。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
