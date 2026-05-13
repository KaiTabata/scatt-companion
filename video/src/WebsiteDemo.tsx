import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";
import { AnimatedShot } from "./components/AnimatedShot";
import { ScreenshotShow } from "./components/ScreenshotShow";

const FPS = 30;
const s = (sec: number) => Math.round(sec * FPS);

/**
 * 60 秒 紹介サイト埋め込み用デモ動画
 *
 * 構成: 実 SCATT データ (Kamenskiy S., 10m AR) のアニメーションが軸。
 * 機能スクショは合間に挟む程度。
 */
export const WebsiteDemo: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: "#0c0d10" }}>
      <Audio src={staticFile("bgm.mp3")} volume={0.35} />

      {/* 0–3s: Intro */}
      <Sequence from={s(0)} durationInFrames={s(3)}>
        <Intro />
      </Sequence>

      {/* 3–8s: shot 1 アニメ */}
      <Sequence from={s(3)} durationInFrames={s(5)}>
        <AnimatedShot dataPath="data/shot_1.json" durationFrames={s(5)} zoomMm={9} />
      </Sequence>

      {/* 8–13s: shot 2 */}
      <Sequence from={s(8)} durationInFrames={s(5)}>
        <AnimatedShot dataPath="data/shot_2.json" durationFrames={s(5)} zoomMm={9} />
      </Sequence>

      {/* 13–18s: shot 3 */}
      <Sequence from={s(13)} durationInFrames={s(5)}>
        <AnimatedShot dataPath="data/shot_3.json" durationFrames={s(5)} zoomMm={9} />
      </Sequence>

      {/* 18–25s: AR 相関グラフ */}
      <Sequence from={s(18)} durationInFrames={s(7)}>
        <ScreenshotShow
          src="img/s1_vs_fire_r.png"
          caption="実データで検証された相関"
          subCaption="S1 ↓ で命中 ↑ (r = +0.38)"
          durationFrames={s(7)}
        />
      </Sequence>

      {/* 25–31s: Dashboard */}
      <Sequence from={s(25)} durationInFrames={s(6)}>
        <ScreenshotShow
          src="img/dashboard.png"
          caption="撃発時 Live 即時診断"
          subCaption="撃発時速度・10a-0.5・R95 を信号色で"
          durationFrames={s(6)}
        />
      </Sequence>

      {/* 31–36s: shot 4 アニメ */}
      <Sequence from={s(31)} durationInFrames={s(5)}>
        <AnimatedShot dataPath="data/shot_4.json" durationFrames={s(5)} zoomMm={9} />
      </Sequence>

      {/* 36–42s: ホーム画面 (モード選び) */}
      <Sequence from={s(36)} durationInFrames={s(6)}>
        <ScreenshotShow
          src="img/home.png"
          caption="3 つの練習モード"
          subCaption="伏射 · AR · ホールド練習"
          durationFrames={s(6)}
        />
      </Sequence>

      {/* 42–48s: 2 shot 比較 */}
      <Sequence from={s(42)} durationInFrames={s(6)}>
        <ScreenshotShow
          src="img/compare.png"
          caption="2 shot 比較"
          subCaption="⌘+クリックで 2 発選んで差分を可視化"
          durationFrames={s(6)}
        />
      </Sequence>

      {/* 48–53s: shot 5 アニメ */}
      <Sequence from={s(48)} durationInFrames={s(5)}>
        <AnimatedShot dataPath="data/shot_5.json" durationFrames={s(5)} zoomMm={9} />
      </Sequence>

      {/* 53–60s: Outro */}
      <Sequence from={s(53)} durationInFrames={s(7)}>
        <Outro />
      </Sequence>
    </AbsoluteFill>
  );
};

const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 18, s(3) - 12, s(3)], [0, 1, 1, 0],
                              { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{
      background: "#0c0d10",
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center", gap: 16, opacity,
    }}>
      <h1 style={{
        fontSize: 96, fontWeight: 800, color: "#fff", margin: 0,
        letterSpacing: "-0.02em",
        fontFamily: "-apple-system, 'Hiragino Sans', sans-serif",
      }}>
        SCATT Companion
      </h1>
      <p style={{ fontSize: 24, color: "#9aa3b2", margin: 0,
                  fontFamily: "-apple-system, 'Hiragino Sans', sans-serif" }}>
        射撃トレーニングを「数字」で読み解く
      </p>
    </AbsoluteFill>
  );
};

const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 12, s(7) - 18, s(7)], [0, 1, 1, 0],
                              { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{
      background: "radial-gradient(ellipse at center, #1a2030 0%, #0c0d10 70%)",
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center", gap: 16, opacity,
    }}>
      <h1 style={{ fontSize: 92, fontWeight: 800, color: "#fff", margin: 0,
                   letterSpacing: "-0.02em",
                   fontFamily: "-apple-system, 'Hiragino Sans', sans-serif" }}>
        SCATT Companion
      </h1>
      <p style={{ fontSize: 26, color: "#9aa3b2", margin: "6px 0" }}>
        kaitabata.github.io/scatt-analyzer
      </p>
      <div style={{ display: "flex", gap: 16, marginTop: 22 }}>
        {["Apache 2.0", "macOS 11+", "DMG 配布"].map((t) => (
          <span key={t} style={{
            padding: "8px 18px", background: "rgba(255,255,255,0.08)",
            border: "1px solid rgba(255,255,255,0.12)", borderRadius: 999,
            color: "#dde", fontSize: 16,
            fontFamily: "-apple-system, 'Hiragino Sans', sans-serif",
          }}>{t}</span>
        ))}
      </div>
      <p style={{ fontSize: 16, color: "#5a6170", marginTop: 22,
                  fontFamily: "-apple-system, 'Hiragino Sans', sans-serif" }}>
        開発: Kai Tabata + Claude Opus 4.7
      </p>
    </AbsoluteFill>
  );
};
