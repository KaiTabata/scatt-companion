import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

/** 中央寄せのタイポグラフィタイトル (fade + slight scale + slight pop) */
export const Title: React.FC<{
  text: string;
  subtitle?: string;
  durationFrames?: number;
  color?: string;
  subColor?: string;
}> = ({ text, subtitle, durationFrames = 90, color = "#fff", subColor = "#bbb" }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = interpolate(
    frame,
    [0, 10, durationFrames - 12, durationFrames],
    [0, 1, 1, 0],
    { extrapolateRight: "clamp" }
  );
  const scale = spring({ frame, fps, config: { damping: 12, stiffness: 100 } });
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 18,
        opacity,
        transform: `scale(${0.97 + 0.03 * scale})`,
      }}
    >
      <h1
        style={{
          fontSize: 96,
          fontWeight: 800,
          color,
          letterSpacing: "-0.02em",
          margin: 0,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'Hiragino Sans', sans-serif",
        }}
      >
        {text}
      </h1>
      {subtitle && (
        <p
          style={{
            fontSize: 32,
            color: subColor,
            margin: 0,
            fontWeight: 300,
            fontFamily: "-apple-system, 'Hiragino Sans', sans-serif",
          }}
        >
          {subtitle}
        </p>
      )}
    </div>
  );
};
