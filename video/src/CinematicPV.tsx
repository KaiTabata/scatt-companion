import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  Easing,
} from "remotion";

/**
 * 18 秒 モーショングラフィック PV
 *
 * 構成:
 *  - 1 shot ごとに 1 グラフ、3 shot を順に切替 (反動なし、pre-trigger のみ)
 *  - shot 1: 軌跡 + Velocity 時系列
 *  - shot 2: 軌跡 + FFT スペクトラム (呼吸 / 心拍 / 力み 帯ハイライト)
 *  - shot 3: 軌跡 + 照準距離 r(t) 時系列
 *  - HUD (LIVE + S1 / R95 / 10a) は通して表示
 *  - 最後 2 秒に SCATT COMPANION ロゴ
 */

const FPS = 30;
const DURATION_S = 18;

type ShotData = {
  samples: [number, number][];
  fire_frame: number;
  fire_x: number;
  fire_y: number;
  sample_rate_recorded?: number;
  s1_mm_s?: number;
};

type ChartKind = "velocity" | "spectrum" | "distance";

interface Phase {
  startFrame: number;
  endFrame: number;
  shotIdx: number;       // どの shot を描くか
  chartKind: ChartKind;
  chartLabel: string;
}

const ACCENT = "#7cd6ff";
const ACCENT_SOFT = "#aac4ff";

// シーン定義
const phases: Phase[] = [
  { startFrame: FPS * 1,  endFrame: FPS * 6,  shotIdx: 0, chartKind: "velocity", chartLabel: "VELOCITY · mm/s" },
  { startFrame: FPS * 6,  endFrame: FPS * 11, shotIdx: 1, chartKind: "spectrum", chartLabel: "SPECTRUM · 0–15 Hz" },
  { startFrame: FPS * 11, endFrame: FPS * 16, shotIdx: 2, chartKind: "distance", chartLabel: "DISTANCE · mm" },
];

export const CinematicPV: React.FC = () => {
  const [shots, setShots] = useState<(ShotData | null)[]>([null, null, null]);
  useEffect(() => {
    Promise.all(
      [1, 2, 3].map((i) =>
        fetch(staticFile(`data/shot_${i}.json`))
          .then((r) => r.json())
          .catch(() => null)
      )
    ).then((d) => setShots(d as (ShotData | null)[]));
  }, []);

  return (
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(ellipse at center, #0d1018 0%, #04060a 80%)",
        fontFamily:
          "'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Inter', system-ui, sans-serif",
      }}
    >
      <Audio src={staticFile("bgm.mp3")} volume={0.5} />
      <BackgroundRings />
      {phases.map((p, i) => {
        const shot = shots[p.shotIdx];
        if (!shot) return null;
        return <PhaseLayer key={i} phase={p} shot={shot} />;
      })}
      <Logo />
    </AbsoluteFill>
  );
};

const FADE_IN = 18;
const FADE_OUT = 18;

function phaseOpacity(frame: number, p: Phase): number {
  return interpolate(
    frame,
    [p.startFrame - FADE_IN, p.startFrame, p.endFrame - FADE_OUT, p.endFrame],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
}

/** 1 フェーズ分の Trace + HUD + Chart を opacity 連動で表示 */
const PhaseLayer: React.FC<{ phase: Phase; shot: ShotData }> = ({ phase, shot }) => {
  const frame = useCurrentFrame();
  const op = phaseOpacity(frame, phase);
  if (op <= 0) return null;

  return (
    <AbsoluteFill style={{ opacity: op }}>
      <Trace shot={shot} phase={phase} />
      <Hud shot={shot} phase={phase} />
      <ChartFrame label={phase.chartLabel}>
        {phase.chartKind === "velocity" && <VelocityChart shot={shot} phase={phase} />}
        {phase.chartKind === "spectrum" && <SpectrumChart shot={shot} phase={phase} />}
        {phase.chartKind === "distance" && <DistanceChart shot={shot} phase={phase} />}
      </ChartFrame>
    </AbsoluteFill>
  );
};

/** 進行率 0-1 (フェーズ内、ease 適用済) */
function phaseProgress(frame: number, p: Phase): number {
  if (frame <= p.startFrame) return 0;
  if (frame >= p.endFrame) return 1;
  return Easing.bezier(0.4, 0, 0.2, 1)((frame - p.startFrame) / (p.endFrame - p.startFrame));
}

/** ターゲット同心円が背景でゆっくり回転 */
const BackgroundRings: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const op = interpolate(
    frame,
    [0, 30, durationInFrames - 60, durationInFrames - 20],
    [0, 0.45, 0.35, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const rot = (frame / fps) * 2.0;
  const scale = 1 + Math.sin((frame / fps) * 0.4) * 0.015;

  const rings = Array.from({ length: 8 }, (_, i) => i + 1);

  return (
    <AbsoluteFill
      style={{
        opacity: op,
        transform: `rotate(${rot}deg) scale(${scale})`,
        transformOrigin: "50% 50%",
      }}
    >
      <svg viewBox="-50 -50 100 100" style={{ width: "100%", height: "100%" }}>
        {rings.map((i) => (
          <circle
            key={i}
            cx="0"
            cy="0"
            r={i * 4.5}
            stroke="#5a7cb0"
            strokeWidth={i === 5 ? 0.18 : 0.08}
            fill="none"
            opacity={0.5 - i * 0.04}
          />
        ))}
        <line x1="-50" y1="0" x2="50" y2="0" stroke="#5a7cb0" strokeWidth="0.04" opacity="0.25" />
        <line x1="0" y1="-50" x2="0" y2="50" stroke="#5a7cb0" strokeWidth="0.04" opacity="0.25" />
      </svg>
    </AbsoluteFill>
  );
};

/** Pre-trigger 軌跡のみ */
const Trace: React.FC<{ shot: ShotData; phase: Phase }> = ({ shot, phase }) => {
  const frame = useCurrentFrame();
  const prog = phaseProgress(frame, phase);

  const N = Math.min(shot.fire_frame + 1, shot.samples.length);
  const drawEnd = Math.max(1, Math.floor(prog * N));

  const points = shot.samples
    .slice(0, drawEnd)
    .map(([x, y]) => `${x},${y}`)
    .join(" ");

  const cur = shot.samples[Math.min(drawEnd - 1, N - 1)];
  const pulse = 0.35 + Math.sin(frame * 0.5) * 0.1;

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <svg viewBox="-12 -12 24 24" style={{ width: "100%", height: "100%" }}>
        <defs>
          <filter id={`glow-${phase.startFrame}`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="0.18" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <g filter={`url(#glow-${phase.startFrame})`}>
          <polyline
            points={points}
            fill="none"
            stroke={ACCENT}
            strokeWidth={0.08}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          <circle cx={cur[0]} cy={cur[1]} r={pulse * 0.25} fill={ACCENT} opacity={0.95} />
          <circle cx={cur[0]} cy={cur[1]} r={pulse * 0.45} fill="none" stroke={ACCENT} strokeWidth={0.04} opacity={0.6} />
        </g>
      </svg>
    </AbsoluteFill>
  );
};

/** LIVE バッジ + リアルタイム HUD */
const Hud: React.FC<{ shot: ShotData; phase: Phase }> = ({ shot, phase }) => {
  const frame = useCurrentFrame();
  const prog = phaseProgress(frame, phase);
  const N = Math.min(shot.fire_frame + 1, shot.samples.length);
  const idx = Math.max(1, Math.floor(prog * N));

  const stats = liveStats(shot, idx);

  return (
    <div
      style={{
        position: "absolute",
        top: 80,
        right: 96,
        display: "flex",
        flexDirection: "column",
        gap: 18,
        color: "#e8edf6",
      }}
    >
      <RecordingBadge />
      <HudRow label="S1" value={stats.s1.toFixed(2)} unit="mm/s" />
      <HudRow label="R95 0.5s" value={stats.r95.toFixed(2)} unit="mm" />
      <HudRow label="10a-0.5" value={stats.ten_a.toFixed(0)} unit="%" />
    </div>
  );
};

const RecordingBadge: React.FC = () => {
  const frame = useCurrentFrame();
  const blink = (Math.floor(frame / 15) % 2) === 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
      <span
        style={{
          width: 10, height: 10, borderRadius: 5,
          background: "#ff4f5e",
          boxShadow: blink ? "0 0 12px #ff4f5e" : "none",
          opacity: blink ? 1 : 0.35,
        }}
      />
      <span style={{
        fontSize: 13, letterSpacing: "0.3em",
        color: "#9aa6b8", fontFamily: "ui-monospace, SFMono-Regular, monospace",
      }}>
        LIVE
      </span>
    </div>
  );
};

const HudRow: React.FC<{ label: string; value: string; unit: string }> = ({
  label, value, unit,
}) => {
  return (
    <div style={{ textAlign: "right", lineHeight: 1.0 }}>
      <div
        style={{
          fontSize: 13,
          letterSpacing: "0.2em",
          color: "#7c8aa3",
          marginBottom: 6,
          fontFamily: "ui-monospace, SFMono-Regular, monospace",
        }}
      >
        {label.toUpperCase()}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "flex-end", gap: 8 }}>
        <span
          style={{
            fontSize: 56,
            fontWeight: 300,
            color: "#f4f6fa",
            fontVariantNumeric: "tabular-nums",
            letterSpacing: "-0.02em",
          }}
        >
          {value}
        </span>
        <span style={{ fontSize: 16, color: "#7c8aa3" }}>{unit}</span>
      </div>
    </div>
  );
};

const CHART_W = 1920 - 192;
const CHART_H = 180;
const CHART_LEFT = 96;
const CHART_TOP = 1080 - CHART_H - 96;

const ChartFrame: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => {
  return (
    <div
      style={{
        position: "absolute",
        left: CHART_LEFT,
        top: CHART_TOP,
        width: CHART_W,
        height: CHART_H,
      }}
    >
      <div
        style={{
          position: "absolute",
          top: -28,
          left: 0,
          fontSize: 13,
          color: "#7c8aa3",
          letterSpacing: "0.2em",
          fontFamily: "ui-monospace, SFMono-Regular, monospace",
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
};

/** Velocity 時系列 */
const VelocityChart: React.FC<{ shot: ShotData; phase: Phase }> = ({ shot, phase }) => {
  const frame = useCurrentFrame();
  const prog = phaseProgress(frame, phase);
  const N = Math.min(shot.fire_frame + 1, shot.samples.length);
  const drawN = Math.max(2, Math.floor(prog * N));
  const fs = shot.sample_rate_recorded ?? 100;

  const velocities: number[] = [];
  for (let i = 1; i < drawN; i++) {
    const dx = shot.samples[i][0] - shot.samples[i - 1][0];
    const dy = shot.samples[i][1] - shot.samples[i - 1][1];
    velocities.push(Math.sqrt(dx * dx + dy * dy) * fs);
  }
  const smoothed = velocities.map((_, i) => {
    const w = velocities.slice(Math.max(0, i - 4), i + 1);
    return w.reduce((a, b) => a + b, 0) / w.length;
  });

  const maxV = Math.max(20, ...smoothed);
  const totalN = N - 1;

  const pts = smoothed
    .map((v, i) => `${(i / totalN) * CHART_W},${CHART_H - (v / maxV) * CHART_H}`)
    .join(" ");
  const lastI = smoothed.length - 1;
  const lastX = lastI >= 0 ? (lastI / totalN) * CHART_W : 0;
  const lastY = lastI >= 0 ? CHART_H - (smoothed[lastI] / maxV) * CHART_H : CHART_H;

  return (
    <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} style={{ position: "absolute", inset: 0 }}>
      {[0.25, 0.5, 0.75].map((p) => (
        <line key={p} x1={0} y1={CHART_H * p} x2={CHART_W} y2={CHART_H * p}
              stroke="#2a3548" strokeWidth={0.5} opacity={0.7} />
      ))}
      <line x1={0} y1={CHART_H} x2={CHART_W} y2={CHART_H} stroke="#3a4863" strokeWidth={1} />
      <polyline points={`0,${CHART_H} ${pts} ${lastX},${CHART_H}`} fill={ACCENT_SOFT} opacity={0.08} />
      <polyline points={pts} fill="none" stroke={ACCENT} strokeWidth={2.2}
                strokeLinejoin="round" strokeLinecap="round" />
      {lastI >= 0 && (
        <>
          <circle cx={lastX} cy={lastY} r={6} fill={ACCENT} />
          <circle cx={lastX} cy={lastY} r={12} fill="none" stroke={ACCENT} strokeWidth={1.5} opacity={0.4} />
        </>
      )}
    </svg>
  );
};

/** FFT スペクトラム (簡易 DFT) — 呼吸 / 心拍 / 力み 帯ハイライト */
const SpectrumChart: React.FC<{ shot: ShotData; phase: Phase }> = ({ shot, phase }) => {
  const frame = useCurrentFrame();
  const prog = phaseProgress(frame, phase);
  const fs = shot.sample_rate_recorded ?? 100;

  const N = Math.min(shot.fire_frame + 1, shot.samples.length);
  const xs = shot.samples.slice(0, N).map((s) => s[0]);
  const meanX = xs.reduce((a, b) => a + b, 0) / xs.length;
  const xsCentered = xs.map((v) => v - meanX);

  const BINS = 60;
  const FREQS = Array.from({ length: BINS }, (_, i) => (i / BINS) * 15);
  const power = FREQS.map((f) => {
    let re = 0, im = 0;
    for (let n = 0; n < xsCentered.length; n++) {
      const phase = -2 * Math.PI * f * (n / fs);
      re += xsCentered[n] * Math.cos(phase);
      im += xsCentered[n] * Math.sin(phase);
    }
    return Math.sqrt(re * re + im * im);
  });
  const maxP = Math.max(...power) || 1;

  const colorFor = (f: number): string => {
    if (f >= 0.15 && f <= 0.5) return "#7cd6ff";
    if (f >= 0.8 && f <= 2.0)  return "#a4f08d";
    if (f >= 8.0 && f <= 12.0) return "#ff8fab";
    return "#475068";
  };

  const barW = (CHART_W / BINS) * 0.7;
  const gapW = (CHART_W / BINS) * 0.3;

  const reveal = (i: number): number => {
    const localT = prog * BINS;
    if (i + 0.5 < localT) return 1;
    if (i > localT) return 0;
    return localT - i;
  };

  return (
    <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} style={{ position: "absolute", inset: 0 }}>
      {[0.25, 0.5, 0.75].map((p) => (
        <line key={p} x1={0} y1={CHART_H * p} x2={CHART_W} y2={CHART_H * p}
              stroke="#2a3548" strokeWidth={0.5} opacity={0.7} />
      ))}
      <line x1={0} y1={CHART_H} x2={CHART_W} y2={CHART_H} stroke="#3a4863" strokeWidth={1} />
      {power.map((p, i) => {
        const h = (p / maxP) * CHART_H * 0.95 * reveal(i);
        const x = i * (barW + gapW);
        const y = CHART_H - h;
        return (
          <rect key={i} x={x} y={y} width={barW} height={h} fill={colorFor(FREQS[i])} rx={1} />
        );
      })}
      <text x={CHART_W * 0.02} y={20} fill="#7cd6ff" opacity={0.85} fontSize={12}
            fontFamily="ui-monospace, SFMono-Regular, monospace">呼吸 0.15–0.5 Hz</text>
      <text x={CHART_W * 0.12} y={20} fill="#a4f08d" opacity={0.85} fontSize={12}
            fontFamily="ui-monospace, SFMono-Regular, monospace">心拍 0.8–2 Hz</text>
      <text x={CHART_W * 0.55} y={20} fill="#ff8fab" opacity={0.85} fontSize={12}
            fontFamily="ui-monospace, SFMono-Regular, monospace">力み 8–12 Hz</text>
    </svg>
  );
};

/** 照準距離 r(t) = sqrt(x²+y²) の時系列 — ターゲット中心からの距離が時間と共に変化 */
const DistanceChart: React.FC<{ shot: ShotData; phase: Phase }> = ({ shot, phase }) => {
  const frame = useCurrentFrame();
  const prog = phaseProgress(frame, phase);
  const N = Math.min(shot.fire_frame + 1, shot.samples.length);
  const drawN = Math.max(2, Math.floor(prog * N));

  const distances: number[] = [];
  for (let i = 0; i < drawN; i++) {
    const x = shot.samples[i][0];
    const y = shot.samples[i][1];
    distances.push(Math.sqrt(x * x + y * y));
  }

  const maxD = Math.max(2, ...distances);
  const totalN = N - 1;

  const pts = distances
    .map((d, i) => `${(i / totalN) * CHART_W},${CHART_H - (d / maxD) * CHART_H}`)
    .join(" ");
  const lastI = distances.length - 1;
  const lastX = lastI >= 0 ? (lastI / totalN) * CHART_W : 0;
  const lastY = lastI >= 0 ? CHART_H - (distances[lastI] / maxD) * CHART_H : CHART_H;

  // R10 (2.5mm 仮想ライン) を引いて「中心圏内かどうか」を視覚化
  const R10 = 2.5;
  const r10Y = CHART_H - (R10 / maxD) * CHART_H;

  return (
    <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} style={{ position: "absolute", inset: 0 }}>
      {[0.25, 0.5, 0.75].map((p) => (
        <line key={p} x1={0} y1={CHART_H * p} x2={CHART_W} y2={CHART_H * p}
              stroke="#2a3548" strokeWidth={0.5} opacity={0.7} />
      ))}
      <line x1={0} y1={CHART_H} x2={CHART_W} y2={CHART_H} stroke="#3a4863" strokeWidth={1} />

      {/* R10 ライン */}
      {r10Y > 0 && r10Y < CHART_H && (
        <>
          <line x1={0} y1={r10Y} x2={CHART_W} y2={r10Y}
                stroke="#a4f08d" strokeWidth={1.2} strokeDasharray="8 6" opacity={0.5} />
          <text x={CHART_W - 12} y={r10Y - 8} textAnchor="end" fill="#a4f08d" opacity={0.7}
                fontSize={12} fontFamily="ui-monospace, SFMono-Regular, monospace">
            R10
          </text>
        </>
      )}

      {/* area fill */}
      <polyline points={`0,${CHART_H} ${pts} ${lastX},${CHART_H}`} fill={ACCENT_SOFT} opacity={0.08} />
      {/* line */}
      <polyline points={pts} fill="none" stroke={ACCENT} strokeWidth={2.2}
                strokeLinejoin="round" strokeLinecap="round" />
      {/* current dot */}
      {lastI >= 0 && (
        <>
          <circle cx={lastX} cy={lastY} r={6} fill={ACCENT} />
          <circle cx={lastX} cy={lastY} r={12} fill="none" stroke={ACCENT} strokeWidth={1.5} opacity={0.4} />
        </>
      )}
    </svg>
  );
};

/** 最後 2 秒に出るロゴ */
const Logo: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const start = durationInFrames - 60;
  const op = interpolate(
    frame,
    [start, start + 20, durationInFrames - 10, durationInFrames],
    [0, 1, 1, 0.85],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const ty = interpolate(frame, [start, start + 30], [10, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });
  return (
    <AbsoluteFill
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        opacity: op,
        transform: `translateY(${ty}px)`,
      }}
    >
      <div
        style={{
          color: "#f4f6fa",
          fontSize: 110,
          fontWeight: 600,
          letterSpacing: "-0.04em",
        }}
      >
        SCATT COMPANION
      </div>
    </AbsoluteFill>
  );
};

/** ライブ累積指標: S1 / R95 0.5s / 10a-0.5 */
function liveStats(shot: ShotData, idx: number): {
  s1: number;
  r95: number;
  ten_a: number;
} {
  const samples = shot.samples;
  const fs = shot.sample_rate_recorded ?? 100;

  let speedSum = 0;
  let speedCount = 0;
  for (let i = 1; i <= idx && i < samples.length; i++) {
    const dx = samples[i][0] - samples[i - 1][0];
    const dy = samples[i][1] - samples[i - 1][1];
    speedSum += Math.sqrt(dx * dx + dy * dy) * fs;
    speedCount++;
  }
  const s1 = speedCount > 0 ? speedSum / speedCount : 0;

  const win = Math.max(1, Math.floor(fs * 0.5));
  const start = Math.max(0, idx - win);
  const slice = samples.slice(start, idx + 1);
  let r95 = 0;
  if (slice.length > 1) {
    const cx = slice.reduce((s, p) => s + p[0], 0) / slice.length;
    const cy = slice.reduce((s, p) => s + p[1], 0) / slice.length;
    const dists = slice.map((p) =>
      Math.sqrt((p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    );
    dists.sort((a, b) => a - b);
    r95 = dists[Math.floor(dists.length * 0.95)] || 0;
  }

  const R10_DISPLAY = 2.5;
  const inRing = slice.filter((p) => Math.sqrt(p[0] ** 2 + p[1] ** 2) <= R10_DISPLAY).length;
  const ten_a = slice.length > 0 ? (inRing / slice.length) * 100 : 0;

  return { s1, r95, ten_a };
}

export const CINEMATIC_DURATION_FRAMES = DURATION_S * FPS;
