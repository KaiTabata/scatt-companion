"""BLE Heart Rate Profile (0x180D) を受信して心拍と RR interval を取得する。

使い方:
  client = HeartRateClient()
  client.on_data = lambda d: print(d)   # {"hr": int, "rr_intervals_s": [..], "timestamp": float}
  client.on_status = lambda s: print(s)
  client.start()              # スキャンして最初に見つけた HR デバイスに接続
  ...
  client.stop()

Apple Watch から心拍を Mac に送る場合は、Watch 側に
  HeartCast (App Store) / BlueHeart / HRMonitor 等
の BLE Heart Rate Profile ブロードキャストアプリが必要。
胸ベルト (Polar H10, Wahoo TICKR, Garmin HRM-Dual 等) も同じインターフェースで動く。

mock_source() で擬似データソースとしても利用可能。
"""

from __future__ import annotations

import asyncio
import random
import threading
import time
from typing import Callable, Optional

try:
    from bleak import BleakClient, BleakScanner
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False

HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"


def parse_hr_measurement(data: bytes) -> dict:
    """HR Measurement (0x2A37) data をパース。

    Bluetooth SIG 仕様 (Heart Rate Service):
      byte[0] flags:
        bit 0: HR value format (0=uint8, 1=uint16)
        bit 1-2: sensor contact status
        bit 3: energy expended present
        bit 4: RR-interval present
      続いて HR、energy、RR intervals が並ぶ。RR は 1/1024 秒単位 uint16 LE。
    """
    if not data:
        return {"hr": None, "rr_intervals_s": []}
    flags = data[0]
    hr_uint16 = bool(flags & 0x01)
    has_energy = bool(flags & 0x08)
    has_rr = bool(flags & 0x10)
    idx = 1
    if hr_uint16:
        hr = int.from_bytes(data[idx:idx + 2], "little")
        idx += 2
    else:
        hr = data[idx]
        idx += 1
    if has_energy:
        idx += 2
    rr_intervals: list[float] = []
    if has_rr:
        while idx + 1 < len(data):
            rr_raw = int.from_bytes(data[idx:idx + 2], "little")
            rr_intervals.append(rr_raw / 1024.0)
            idx += 2
    return {"hr": hr, "rr_intervals_s": rr_intervals}


def rmssd(rr_intervals_s: list[float]) -> Optional[float]:
    """連続する RR interval の差分 RMS (ms)。HRV の代表的指標。

    伏射では交感神経優位 → RMSSD が低くなる傾向。
    一般成人安静時で 30〜80ms 程度が典型。
    """
    if len(rr_intervals_s) < 2:
        return None
    diffs = [(rr_intervals_s[i + 1] - rr_intervals_s[i]) * 1000.0
             for i in range(len(rr_intervals_s) - 1)]
    if not diffs:
        return None
    return (sum(d * d for d in diffs) / len(diffs)) ** 0.5


class HeartRateClient:
    """BLE 心拍クライアント。別スレッドの asyncio loop で動かす。

    on_data:  notify を受信するたびに dict を渡す (UI スレッドに postEvent 要)
    on_status: スキャン/接続/エラー等の状態文字列
    """

    def __init__(self, mock: bool = False):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self.mock = mock
        self.on_data: Optional[Callable[[dict], None]] = None
        self.on_status: Optional[Callable[[str], None]] = None
        self._device_address: Optional[str] = None

    @staticmethod
    def is_ble_available() -> bool:
        return BLEAK_AVAILABLE

    def _emit_status(self, s: str):
        if self.on_status:
            try:
                self.on_status(s)
            except Exception:
                pass

    def _emit_data(self, d: dict):
        if self.on_data:
            try:
                self.on_data(d)
            except Exception:
                pass

    def _notify_cb(self, _sender, data: bytes):
        try:
            parsed = parse_hr_measurement(data)
            parsed["timestamp"] = time.time()
            self._emit_data(parsed)
        except Exception as e:
            self._emit_status(f"parse error: {e}")

    async def _scan_for_device(self) -> Optional[str]:
        self._emit_status("scanning for heart rate device (5 sec)...")
        # 新しい bleak は return_adv=True で {address: (device, AdvertisementData)} を返す
        try:
            try:
                results = await BleakScanner.discover(timeout=5.0, return_adv=True)
                items = list(results.items())  # [(addr, (device, adv))]
            except TypeError:
                # 古い bleak: device.metadata 経由
                devices = await BleakScanner.discover(timeout=5.0)
                items = [(d.address, (d, None)) for d in devices]
        except Exception as e:
            self._emit_status(f"scan failed: {e}")
            return None

        for addr, pair in items:
            device, adv = pair
            uuids: list = []
            if adv is not None and getattr(adv, "service_uuids", None):
                uuids = list(adv.service_uuids)
            else:
                md = getattr(device, "metadata", None) or {}
                uuids = list(md.get("uuids") or [])
            for u in uuids:
                if "180d" in str(u).lower():
                    name = device.name or (adv.local_name if adv else None) or "<no name>"
                    self._emit_status(f"found: {name} [{addr}]")
                    return addr
        self._emit_status("no heart rate device found")
        return None

    async def _run_ble(self, device_address: Optional[str]):
        target = device_address or await self._scan_for_device()
        if not target:
            return
        self._emit_status(f"connecting to {target}...")
        try:
            async with BleakClient(target) as client:
                await client.start_notify(HEART_RATE_MEASUREMENT_UUID, self._notify_cb)
                self._emit_status(f"connected: {target}")
                while self._running:
                    await asyncio.sleep(0.5)
                await client.stop_notify(HEART_RATE_MEASUREMENT_UUID)
            self._emit_status("disconnected")
        except Exception as e:
            self._emit_status(f"connection error: {e}")

    async def _run_mock(self):
        """擬似 HR データ: 60-90 BPM をランダム揺らぎで、約 1秒ごとに発行。"""
        self._emit_status("mock heart rate source started")
        base = 72.0
        prev_rr = 60.0 / base
        while self._running:
            base += random.gauss(0, 0.4)
            base = max(55, min(95, base))
            hr = int(base + random.gauss(0, 1.5))
            rr = 60.0 / hr + random.gauss(0, 0.02)
            self._emit_data({
                "hr": hr,
                "rr_intervals_s": [rr],
                "timestamp": time.time(),
            })
            prev_rr = rr
            await asyncio.sleep(rr)
        self._emit_status("mock stopped")

    def start(self, device_address: Optional[str] = None):
        if self._running:
            return
        self._running = True
        self._device_address = device_address

        def runner():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                if self.mock or not BLEAK_AVAILABLE:
                    if not BLEAK_AVAILABLE and not self.mock:
                        self._emit_status("bleak not installed — falling back to mock")
                    self._loop.run_until_complete(self._run_mock())
                else:
                    self._loop.run_until_complete(self._run_ble(self._device_address))
            except Exception as e:
                self._emit_status(f"loop error: {e}")
            finally:
                try:
                    self._loop.close()
                except Exception:
                    pass

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        self._thread = None
        self._loop = None
