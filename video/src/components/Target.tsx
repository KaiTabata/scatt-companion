import React from "react";

/** ISSF 風ターゲット (SVG)。半径は viewbox 単位で正規化、scale で表示サイズ調整。 */
export const Target: React.FC<{
  size?: number;
  outerR?: number;  // 単位は SVG viewbox 内
  blackR?: number;
  ringStep?: number;
}> = ({ size = 700, outerR = 100, blackR = 72, ringStep = 10 }) => {
  // 10 ring の半径
  const tenR = (10 - 9) * ringStep;
  return (
    <svg
      viewBox={`${-outerR - 8} ${-outerR - 8} ${(outerR + 8) * 2} ${(outerR + 8) * 2}`}
      style={{ width: size, height: size, display: "block" }}
    >
      {/* 外白地 */}
      <circle cx={0} cy={0} r={outerR} fill="#e9e8e3" stroke="#666" strokeWidth={0.4} />
      {/* 黒地 */}
      <circle cx={0} cy={0} r={blackR} fill="#1a1a1a" stroke="#000" strokeWidth={0.4} />
      {/* 各リング */}
      {Array.from({ length: 10 }).map((_, i) => {
        const ring = i + 1;
        const r = outerR - (ring - 1) * ringStep;
        const insideBlack = r <= blackR;
        return (
          <circle
            key={ring}
            cx={0}
            cy={0}
            r={r}
            fill="none"
            stroke={insideBlack ? "#dddddd" : "#7a7a7a"}
            strokeWidth={0.3}
          />
        );
      })}
      {/* 数字 */}
      {Array.from({ length: 8 }).map((_, i) => {
        const ring = i + 1;
        const r = outerR - (ring - 1) * ringStep + ringStep / 2;
        const insideBlack = r - ringStep / 2 < blackR;
        return (
          <text
            key={ring}
            x={0}
            y={-r + ringStep * 0.05}
            fontSize={ringStep * 0.5}
            textAnchor="middle"
            dominantBaseline="middle"
            fill={insideBlack ? "#bbb" : "#222"}
            fontWeight={500}
          >
            {ring}
          </text>
        );
      })}
      {/* 中心十字 */}
      <line x1={-tenR * 0.8} y1={0} x2={tenR * 0.8} y2={0} stroke="#fff" strokeWidth={0.2} />
      <line x1={0} y1={-tenR * 0.8} x2={0} y2={tenR * 0.8} stroke="#fff" strokeWidth={0.2} />
    </svg>
  );
};
