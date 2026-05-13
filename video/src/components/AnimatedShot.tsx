import React, { useEffect, useState } from "react";
import { AbsoluteFill, interpolate, staticFile, useCurrentFrame } from "remotion";
import { Target } from "./Target";

type ShotData = {
  title: string;
  discipline: string;
  sample_rate_video: number;
  fire_frame: number;
  samples: [number, number][];   // mm, SCATT 座標 (Y は下向き)
  fire_x: number;
  fire_y: number;
  s1_mm_s: number;
};

/**
 * 実 SCATT データ (JSON) を読み込んで 30fps で再生するアニメーション。
 *
 * 視覚要素:
 *  - 10m AR ターゲット (中心ズーム表示)
 *  - 軌跡 polyline (発射前=緑、発射後=赤)
 *  - 現在の照準点 (黄色丸)
 *  - 撃発フラッシュ + 弾着リング拡散
 *  - 右上 HUD (S1 / R95 / 10a-0.5 が時系列で変化)
 */
export const AnimatedShot: React.FC<{
  dataPath: string;            // public/data/shot_1.json への相対パス
  durationFrames: number;      // この shot を描画する総 frame 数 (>= samples 長)
  targetSize?: number;
  zoomMm?: number;             // viewbox に映す中心からの距離 (mm)
  showHud?: boolean;
}> = ({
  dataPath,
  durationFrames,
  targetSize = 760,
  zoomMm = 10,
  showHud = true,
}) => {
  const frame = useCurrentFrame();
  const [data, setData] = useState<ShotData | null>(null);

  useEffect(() => {
    fetch(staticFile(dataPath))
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData(null));
  }, [dataPath]);

  if (!data) {
    return <AbsoluteFill style={{ background: "#0c0d10" }} />;
  }

  // 入退場フェード
  const fadeOp = interpolate(
    frame,
    [0, 10, durationFrames - 14, durationFrames],
    [0, 1, 1, 0],
    { extrapolateRight: "clamp" }
  );

  const N = data.samples.length;
  // この shot の長さに合わせて再生 (durationFrames が長ければ余りは hold)
  const playableFrames = Math.min(N, durationFrames);
  const idx = Math.min(frame, playableFrames - 1);
  const fire = data.fire_frame;

  // 軌跡 polyline (現在まで)。Y を反転 (SCATT y↓ → 画面 y↓ のままで OK、ターゲットも同様)
  const ptStr = (i: number) => `${data.samples[i][0]},${data.samples[i][1]}`;
  const prePoints = Array.from(
    { length: Math.min(idx + 1, fire + 1) },
    (_, i) => ptStr(i)
  ).join(" ");
  const postPoints =
    idx > fire
      ? Array.from({ length: idx - fire + 1 }, (_, k) => ptStr(fire + k)).join(" ")
      : "";

  // 現在位置
  const cur = data.samples[idx];

  // 撃発演出
  const sinceFire = idx - fire;
  const ringT = sinceFire >= 0 ? Math.min(1, sinceFire / 10) : 0;
  const ringR = ringT > 0 ? 0.5 + ringT * 8 : 0;
  const ringOpacity = ringT > 0 ? 1 - ringT : 0;
  const flashOpacity =
    sinceFire >= 0 && sinceFire <= 4
      ? Math.max(0, 1 - sinceFire / 4) * 0.6
      : 0;

  // HUD 値 (累積)
  const liveStats = computeLiveStats(data, idx);

  return (
    <AbsoluteFill
      style={{
        background: "radial-gradient(ellipse at center, #1a2030 0%, #0c0d10 80%)",
        opacity: fadeOp,
      }}
    >
      {/* ターゲット + 軌跡 (中央配置、中心 ±zoomMm にズーム) */}
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          width: targetSize,
          height: targetSize,
          marginLeft: -targetSize / 2,
          marginTop: -targetSize / 2,
        }}
      >
        {/* ターゲット (中心 zoomMm × 2 を viewbox 全体に) */}
        <svg
          viewBox={`${-zoomMm} ${-zoomMm} ${zoomMm * 2} ${zoomMm * 2}`}
          style={{
            position: "absolute",
            inset: 0,
            width: targetSize,
            height: targetSize,
          }}
        >
          {/* 10m AR ターゲット: 外径 45.5mm、ring step 2.5mm 半径、10-ring 0.25mm dot
              中心 zoomMm の範囲しか映らないので外側リングはクリップされる */}
          <TargetSvg />
          {/* 軌跡: 発射前 (緑) */}
          {prePoints && (
            <polyline
              points={prePoints}
              fill="none"
              stroke="#56c459"
              strokeWidth={0.1}
              strokeLinejoin="round"
              strokeLinecap="round"
              opacity={0.95}
            />
          )}
          {/* 発射後 (赤) */}
          {postPoints && (
            <polyline
              points={postPoints}
              fill="none"
              stroke="#e76060"
              strokeWidth={0.08}
              strokeLinejoin="round"
              opacity={0.9}
            />
          )}
          {/* 弾着リング (撃発) */}
          {ringR > 0 && (
            <circle
              cx={data.fire_x}
              cy={data.fire_y}
              r={ringR}
              fill="none"
              stroke="#f0d050"
              strokeWidth={0.08}
              opacity={ringOpacity * 0.9}
            />
          )}
          {/* 弾着十字 */}
          {idx >= fire && (
            <g>
              <line
                x1={data.fire_x - 0.5}
                y1={data.fire_y}
                x2={data.fire_x + 0.5}
                y2={data.fire_y}
                stroke="#f0d050"
                strokeWidth={0.05}
              />
              <line
                x1={data.fire_x}
                y1={data.fire_y - 0.5}
                x2={data.fire_x}
                y2={data.fire_y + 0.5}
                stroke="#f0d050"
                strokeWidth={0.05}
              />
              <circle
                cx={data.fire_x}
                cy={data.fire_y}
                r={0.12}
                fill="#f0d050"
              />
            </g>
          )}
          {/* 現在位置: ハロー + 黄丸 */}
          <circle cx={cur[0]} cy={cur[1]} r={0.4} fill="#f0d050" opacity={0.4} />
          <circle cx={cur[0]} cy={cur[1]} r={0.2} fill="#fff8b0" />
        </svg>
        {/* 撃発フラッシュ */}
        {flashOpacity > 0 && (
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: `radial-gradient(circle at 50% 50%, rgba(255,240,180,${flashOpacity}) 0%, transparent 60%)`,
              pointerEvents: "none",
            }}
          />
        )}
      </div>

      {/* HUD */}
      {showHud && (
        <div
          style={{
            position: "absolute",
            top: 60,
            right: 80,
            display: "flex",
            flexDirection: "column",
            gap: 12,
            fontFamily: "-apple-system, 'SF Mono', monospace",
            color: "#fff",
            textAlign: "right",
          }}
        >
          <HudMetric
            label="S1"
            value={liveStats.s1}
            digits={1}
            unit="mm/s"
            color={
              liveStats.s1 > 15
                ? "#e76060"
                : liveStats.s1 > 8
                ? "#f0d050"
                : "#56c459"
            }
          />
          <HudMetric
            label="R95 0.5s"
            value={liveStats.r95_05}
            digits={2}
            unit="mm"
            color={
              liveStats.r95_05 > 1.5
                ? "#e76060"
                : liveStats.r95_05 > 0.8
                ? "#f0d050"
                : "#56c459"
            }
          />
          <HudMetric
            label="10a-0.5"
            value={liveStats.ten_a_05}
            digits={0}
            unit="%"
            color={
              liveStats.ten_a_05 < 30
                ? "#e76060"
                : liveStats.ten_a_05 < 60
                ? "#f0d050"
                : "#56c459"
            }
          />
        </div>
      )}

      {/* タイトル (shot ラベル) */}
      <div
        style={{
          position: "absolute",
          bottom: 60,
          left: 80,
          fontFamily: "-apple-system, monospace",
          color: "#9aa3b2",
          fontSize: 16,
        }}
      >
        SCATT real data · Kamenskiy S. · 10m AR
      </div>
    </AbsoluteFill>
  );
};

/** Inline で 10m AR ターゲットを描画。中心の小さな 10-ring まで含む。 */
const TargetSvg: React.FC = () => {
  // ISSF 10m AR: 外径 45.5mm, 1 ring 半径 22.75, ring step 2.5mm, 10 ring=0.25mm
  // 黒地は 7-10 ring (半径 ~ 12.75mm まで)
  const outer = 22.75; // 1-ring 半径
  const black = 12.75; // 黒地半径 (6-ring 半径 = 5*2.5 + 0.25 ≈ 12.75 補正)
  const stepR = 2.5;
  return (
    <g>
      <circle cx={0} cy={0} r={outer} fill="#e8e7e2" stroke="#666" strokeWidth={0.05} />
      <circle cx={0} cy={0} r={black} fill="#171717" stroke="#000" strokeWidth={0.05} />
      {Array.from({ length: 10 }).map((_, i) => {
        const ring = i + 1;
        const r = outer - (ring - 1) * stepR;
        if (r <= 0) return null;
        const insideBlack = r <= black;
        return (
          <circle
            key={ring}
            cx={0}
            cy={0}
            r={r}
            fill="none"
            stroke={insideBlack ? "#cccccc" : "#7a7a7a"}
            strokeWidth={0.05}
          />
        );
      })}
      {/* 10-ring の dot (0.25mm) を強調表示 */}
      <circle cx={0} cy={0} r={0.25} fill="#f6e7a8" opacity={0.7} />
      {/* 中心十字 */}
      <line x1={-1.5} y1={0} x2={1.5} y2={0} stroke="#fff" strokeWidth={0.04} />
      <line x1={0} y1={-1.5} x2={0} y2={1.5} stroke="#fff" strokeWidth={0.04} />
    </g>
  );
};

const HudMetric: React.FC<{
  label: string;
  value: number;
  digits: number;
  unit: string;
  color: string;
}> = ({ label, value, digits, unit, color }) => (
  <div
    style={{
      background: "rgba(20, 24, 32, 0.78)",
      backdropFilter: "blur(10px)",
      padding: "10px 18px",
      borderRadius: 10,
      border: "1px solid rgba(255,255,255,0.08)",
      minWidth: 220,
    }}
  >
    <div
      style={{ fontSize: 14, color: "#9aa3b2", letterSpacing: "0.05em" }}
    >
      {label}
    </div>
    <div
      style={{
        fontSize: 36,
        fontWeight: 700,
        color,
        marginTop: 2,
        fontVariantNumeric: "tabular-nums",
      }}
    >
      {value.toFixed(digits)}
      <span
        style={{
          fontSize: 16,
          marginLeft: 6,
          color: "#9aa3b2",
          fontWeight: 400,
        }}
      >
        {unit}
      </span>
    </div>
  </div>
);

/** 累積データから現フレームの S1 / R95 / 10a-0.5 を計算。 */
function computeLiveStats(data: ShotData, idx: number) {
  const fps = 30;
  // S1: 直前 1 秒の平均速度
  const winS1 = fps;
  const s1Start = Math.max(1, idx - winS1);
  let dist = 0;
  let count = 0;
  for (let i = s1Start; i <= idx; i++) {
    if (i < 1) continue;
    const dx = data.samples[i][0] - data.samples[i - 1][0];
    const dy = data.samples[i][1] - data.samples[i - 1][1];
    dist += Math.sqrt(dx * dx + dy * dy);
    count++;
  }
  const s1 = count > 0 ? (dist / count) * fps : 0;
  // R95 0.5s: 直前 0.5s の重心からの距離 p95
  const win05 = Math.round(fps * 0.5);
  const r05Start = Math.max(0, idx - win05);
  const xs = [],
    ys = [];
  for (let i = r05Start; i <= idx; i++) {
    xs.push(data.samples[i][0]);
    ys.push(data.samples[i][1]);
  }
  const cx = avg(xs);
  const cy = avg(ys);
  const rs = xs.map((x, k) => Math.hypot(x - cx, ys[k] - cy));
  rs.sort((a, b) => a - b);
  const r95_05 = rs.length > 0 ? rs[Math.min(rs.length - 1, Math.floor(rs.length * 0.95))] : 0;
  // 10a-0.5: 直前 0.5s で r ≤ 0.25mm (10m AR 10-ring) の割合
  const ten_a_05 = xs.length > 0
    ? (xs.filter((x, k) => Math.hypot(x, ys[k]) <= 0.25).length / xs.length) * 100
    : 0;
  return { s1, r95_05, ten_a_05 };
}

function avg(arr: number[]) {
  return arr.reduce((a, b) => a + b, 0) / Math.max(1, arr.length);
}
