import React from "react";
import { AbsoluteFill, Sequence, interpolate, useCurrentFrame } from "remotion";
import { Title } from "./components/Title";
import { ScreenshotShow } from "./components/ScreenshotShow";
import { Counter } from "./components/Counter";

const FPS = 30;
const s = (sec: number) => Math.round(sec * FPS);

/**
 * 30 秒マーケティング PV
 *
 * 構成:
 *  0.0 - 3.0  Intro (タイトル)
 *  3.0 - 8.0  ホーム画面 + 「3 モード対応」
 *  8.0 -13.0  Dashboard + Live 診断 数値カウンタ
 * 13.0 -18.0  AR 相関グラフ
 * 18.0 -22.0  発射前後 軌跡 (フォロースルー)
 * 22.0 -26.0  2 shot 比較
 * 26.0 -30.0  Outro (URL)
 */
export const MarketingPV: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: "#0e1014" }}>

      {/* 0–3s: Intro */}
      <Sequence from={s(0)} durationInFrames={s(3)}>
        <Intro />
      </Sequence>

      {/* 3–8s: ホーム画面 */}
      <Sequence from={s(3)} durationInFrames={s(5)}>
        <ScreenshotShow
          src="img/home.png"
          caption="3 つの練習モード"
          subCaption="伏射 · AR · ホールド練習"
          durationFrames={s(5)}
        />
      </Sequence>

      {/* 8–13s: Dashboard + Live 診断カウンタ */}
      <Sequence from={s(8)} durationInFrames={s(5)}>
        <DashboardScene />
      </Sequence>

      {/* 13–18s: AR 相関グラフ */}
      <Sequence from={s(13)} durationInFrames={s(5)}>
        <ScreenshotShow
          src="img/s1_vs_fire_r.png"
          caption="実データで検証された相関"
          subCaption="S1 ↓ で命中 ↑ (相関 r = +0.38)"
          durationFrames={s(5)}
        />
      </Sequence>

      {/* 18–22s: フォロースルー */}
      <Sequence from={s(18)} durationInFrames={s(4)}>
        <ScreenshotShow
          src="img/followthrough.png"
          caption="発射前後 軌跡 重ね"
          subCaption="フォロースルーの一貫性が一目で"
          durationFrames={s(4)}
        />
      </Sequence>

      {/* 22–26s: 2 shot 比較 */}
      <Sequence from={s(22)} durationInFrames={s(4)}>
        <ScreenshotShow
          src="img/compare.png"
          caption="2 shot 比較"
          subCaption="ベストとワーストの差を可視化"
          durationFrames={s(4)}
        />
      </Sequence>

      {/* 26–30s: Outro */}
      <Sequence from={s(26)} durationInFrames={s(4)}>
        <Outro />
      </Sequence>

    </AbsoluteFill>
  );
};

const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  // 弾着リング: 0.3 秒で外側から中心に縮む
  const ringScale = interpolate(frame, [0, 18], [3, 1], { extrapolateRight: "clamp" });
  const ringOpacity = interpolate(frame, [0, 14, 18], [0.6, 0.9, 0], { extrapolateRight: "clamp" });
  const titleStart = 12;
  return (
    <AbsoluteFill style={{ background: "#0e1014" }}>
      {/* 弾着リング */}
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          width: 360,
          height: 360,
          marginLeft: -180,
          marginTop: -180,
          borderRadius: "50%",
          border: "3px solid #d6c560",
          opacity: ringOpacity,
          transform: `scale(${ringScale})`,
        }}
      />
      {frame > titleStart && (
        <Title
          text="SCATT Companion"
          subtitle="射撃トレーニングの「隣で使う」分析ツール"
          durationFrames={s(3) - titleStart}
        />
      )}
    </AbsoluteFill>
  );
};

const DashboardScene: React.FC = () => {
  const frame = useCurrentFrame();
  const counterStart = 24;   // ScreenshotShow が描画されてから数値を出す
  return (
    <AbsoluteFill>
      <ScreenshotShow
        src="img/dashboard.png"
        caption="Live 即時診断"
        subCaption="撃った瞬間に重要指標を信号色で"
        durationFrames={s(5)}
      />
      {frame >= counterStart && (
        <div
          style={{
            position: "absolute",
            bottom: 110,
            left: 0,
            right: 0,
            textAlign: "center",
            display: "flex",
            justifyContent: "center",
            gap: 60,
          }}
        >
          <CounterBox label="撃発時 速度" >
            <Counter from={12.0} to={8.2} digits={1} suffix=" mm/s"
                     color="#d04949" endColor="#56c459" durationFrames={36} size={80} />
          </CounterBox>
          <CounterBox label="10a-0.5">
            <Counter from={42} to={72} digits={0} suffix=" %"
                     color="#d04949" endColor="#56c459" durationFrames={36} size={80} />
          </CounterBox>
          <CounterBox label="R95 0.5s">
            <Counter from={5.6} to={2.4} digits={1} suffix=" mm"
                     color="#d04949" endColor="#56c459" durationFrames={36} size={80} />
          </CounterBox>
        </div>
      )}
    </AbsoluteFill>
  );
};

const CounterBox: React.FC<{ label: string; children: React.ReactNode }> = ({
  label,
  children,
}) => (
  <div
    style={{
      padding: "18px 28px",
      background: "rgba(255,255,255,0.08)",
      borderRadius: 12,
      backdropFilter: "blur(12px)",
      minWidth: 240,
      textAlign: "center",
      border: "1px solid rgba(255,255,255,0.12)",
    }}
  >
    <div
      style={{
        color: "#9aa3b2",
        fontSize: 18,
        fontWeight: 500,
        marginBottom: 4,
        fontFamily: "-apple-system, 'Hiragino Sans', sans-serif",
      }}
    >
      {label}
    </div>
    {children}
  </div>
);

const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 12, s(4) - 12, s(4)], [0, 1, 1, 0],
                              { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill
      style={{
        background: "radial-gradient(ellipse at center, #1a2030 0%, #0e1014 70%)",
        opacity,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 18,
      }}
    >
      <h1
        style={{
          fontSize: 96,
          fontWeight: 800,
          color: "#fff",
          margin: 0,
          letterSpacing: "-0.02em",
          fontFamily: "-apple-system, 'Hiragino Sans', sans-serif",
        }}
      >
        SCATT Companion
      </h1>
      <p
        style={{
          fontSize: 28,
          color: "#9aa3b2",
          margin: "6px 0",
          fontFamily: "-apple-system, monospace",
        }}
      >
        kaitabata.github.io/scatt-analyzer
      </p>
      <p
        style={{
          fontSize: 18,
          color: "#5a6170",
          margin: "20px 0 0",
          fontFamily: "-apple-system, 'Hiragino Sans', sans-serif",
        }}
      >
        Apache 2.0 ·  Kai Tabata + Claude Opus 4.7
      </p>
    </AbsoluteFill>
  );
};
