import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";
import { AnimatedShot } from "./components/AnimatedShot";

const FPS = 30;
const s = (sec: number) => Math.round(sec * FPS);

/**
 * 30 秒マーケティング PV — Kamenskiy S. の実 10m AR データを使用
 * (5 個の clean shots、fire_r < 0.4mm, すべて 10 点圏内)
 */
export const MarketingPV: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: "#0c0d10" }}>
      <Audio src={staticFile("bgm.mp3")} volume={0.45} />

      {/* 0–2.5s: Intro */}
      <Sequence from={s(0)} durationInFrames={s(2.5)}>
        <Intro />
      </Sequence>

      {/* 2.5–8s: shot 1 (5.5s, データ 151 frames ≈ 5s) */}
      <Sequence from={s(2.5)} durationInFrames={s(5.5)}>
        <AnimatedShot dataPath="data/shot_1.json" durationFrames={s(5.5)} zoomMm={9} />
      </Sequence>

      {/* 8–13s: shot 2 */}
      <Sequence from={s(8)} durationInFrames={s(5)}>
        <AnimatedShot dataPath="data/shot_2.json" durationFrames={s(5)} zoomMm={9} />
      </Sequence>

      {/* 13–18s: shot 3 */}
      <Sequence from={s(13)} durationInFrames={s(5)}>
        <AnimatedShot dataPath="data/shot_3.json" durationFrames={s(5)} zoomMm={9} />
      </Sequence>

      {/* 18–23s: shot 4 */}
      <Sequence from={s(18)} durationInFrames={s(5)}>
        <AnimatedShot dataPath="data/shot_4.json" durationFrames={s(5)} zoomMm={9} />
      </Sequence>

      {/* 23–27.5s: shot 5 */}
      <Sequence from={s(23)} durationInFrames={s(4.5)}>
        <AnimatedShot dataPath="data/shot_5.json" durationFrames={s(4.5)} zoomMm={9} />
      </Sequence>

      {/* 27.5–30s: Outro */}
      <Sequence from={s(27.5)} durationInFrames={s(2.5)}>
        <Outro />
      </Sequence>
    </AbsoluteFill>
  );
};

const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const ringScale = interpolate(frame, [0, 24], [3, 1], { extrapolateRight: "clamp" });
  const ringOpacity = interpolate(frame, [0, 20, 24], [0.6, 1, 0], { extrapolateRight: "clamp" });
  const titleStart = 18;
  const titleOp = interpolate(frame, [titleStart, titleStart + 10], [0, 1],
                              { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ background: "#0c0d10" }}>
      <div
        style={{
          position: "absolute", left: "50%", top: "50%",
          width: 360, height: 360, marginLeft: -180, marginTop: -180,
          borderRadius: "50%", border: "3px solid #f0d050",
          opacity: ringOpacity, transform: `scale(${ringScale})`,
        }}
      />
      <h1 style={{
        position: "absolute", inset: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 96, fontWeight: 800, color: "#fff", letterSpacing: "-0.02em",
        fontFamily: "-apple-system, 'Hiragino Sans', sans-serif", margin: 0,
        opacity: titleOp,
      }}>
        SCATT Companion
      </h1>
    </AbsoluteFill>
  );
};

const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 12, s(2.5) - 8, s(2.5)], [0, 1, 1, 0],
                              { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{
      background: "radial-gradient(ellipse at center, #1a2030 0%, #0c0d10 70%)",
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center", gap: 14, opacity,
    }}>
      <h1 style={{
        fontSize: 96, fontWeight: 800, color: "#fff", margin: 0,
        letterSpacing: "-0.02em",
        fontFamily: "-apple-system, 'Hiragino Sans', sans-serif",
      }}>
        SCATT Companion
      </h1>
      <p style={{ fontSize: 28, color: "#9aa3b2", margin: "4px 0",
                  fontFamily: "-apple-system, monospace" }}>
        kaitabata.github.io/scatt-analyzer
      </p>
      <p style={{ fontSize: 16, color: "#5a6170", marginTop: 12,
                  fontFamily: "-apple-system, 'Hiragino Sans', sans-serif" }}>
        Apache 2.0 ·  Kai Tabata + Claude Opus 4.7
      </p>
    </AbsoluteFill>
  );
};
