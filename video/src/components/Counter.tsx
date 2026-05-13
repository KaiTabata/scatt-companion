import React from "react";
import { interpolate, useCurrentFrame } from "remotion";

/** 数値カウンタアニメ (from → to に 1.2 秒で補間)。
 *  撃発時速度 12.0 → 8.2 mm/s のような数値変化を強調する場面で使う。 */
export const Counter: React.FC<{
  from: number;
  to: number;
  digits?: number;
  durationFrames?: number;
  prefix?: string;
  suffix?: string;
  color?: string;
  size?: number;
  endColor?: string;  // 終端で色変化 (例: 赤→緑)
}> = ({
  from,
  to,
  digits = 1,
  durationFrames = 36,
  prefix = "",
  suffix = "",
  color = "#fff",
  size = 100,
  endColor,
}) => {
  const frame = useCurrentFrame();
  // easeOutCubic
  const t = Math.min(1, frame / durationFrames);
  const eased = 1 - Math.pow(1 - t, 3);
  const value = from + (to - from) * eased;
  const c = endColor && t > 0.85 ? endColor : color;
  return (
    <span
      style={{
        fontSize: size,
        fontWeight: 700,
        color: c,
        fontVariantNumeric: "tabular-nums",
        fontFamily: "-apple-system, 'SF Mono', monospace",
      }}
    >
      {prefix}{value.toFixed(digits)}{suffix}
    </span>
  );
};
