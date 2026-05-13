import React from "react";
import { Img, interpolate, useCurrentFrame, useVideoConfig, staticFile } from "remotion";

/** スクリーンショットを下からスライドイン + 軽くズーム + caption 表示 */
export const ScreenshotShow: React.FC<{
  src: string;
  caption?: string;
  subCaption?: string;
  durationFrames: number;
  panZoom?: boolean;  // true なら Ken Burns 風にゆっくり拡大
}> = ({ src, caption, subCaption, durationFrames, panZoom = true }) => {
  const frame = useCurrentFrame();
  // 入退場 opacity
  const opacity = interpolate(
    frame,
    [0, 12, durationFrames - 15, durationFrames],
    [0, 1, 1, 0],
    { extrapolateRight: "clamp" }
  );
  // 下からスライドイン
  const ty = interpolate(frame, [0, 18], [40, 0], { extrapolateRight: "clamp" });
  // Ken Burns: ゆっくり拡大
  const scale = panZoom
    ? interpolate(frame, [0, durationFrames], [1.0, 1.08])
    : 1.0;
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        opacity,
        background: "linear-gradient(180deg, #0e1014 0%, #1a1d22 100%)",
      }}
    >
      {caption && (
        <div
          style={{
            position: "absolute",
            top: 80,
            left: 0,
            right: 0,
            textAlign: "center",
            color: "#fff",
            fontSize: 44,
            fontWeight: 700,
            fontFamily: "-apple-system, 'Hiragino Sans', sans-serif",
            letterSpacing: "-0.01em",
            textShadow: "0 2px 12px rgba(0,0,0,0.5)",
          }}
        >
          {caption}
        </div>
      )}
      {subCaption && (
        <div
          style={{
            position: "absolute",
            top: 156,
            left: 0,
            right: 0,
            textAlign: "center",
            color: "#9aa3b2",
            fontSize: 24,
            fontWeight: 400,
            fontFamily: "-apple-system, 'Hiragino Sans', sans-serif",
          }}
        >
          {subCaption}
        </div>
      )}
      <div
        style={{
          marginTop: 100,
          transform: `translateY(${ty}px) scale(${scale})`,
          maxWidth: "82%",
          maxHeight: "70%",
          boxShadow: "0 30px 90px rgba(0,0,0,0.6), 0 6px 24px rgba(0,0,0,0.4)",
          borderRadius: 18,
          overflow: "hidden",
          border: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        <Img
          src={staticFile(src)}
          style={{ display: "block", width: "100%", height: "auto" }}
        />
      </div>
    </div>
  );
};
