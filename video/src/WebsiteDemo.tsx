import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { Title } from "./components/Title";
import { ScreenshotShow } from "./components/ScreenshotShow";

const FPS = 30;
const s = (sec: number) => Math.round(sec * FPS);

/**
 * 60 秒 紹介サイト埋め込み用 デモ動画
 *
 * 構成: 機能を 1 つずつ落ち着いて見せる walkthrough。
 *  0.0 -  3.0  Intro
 *  3.0 -  9.0  ホーム画面 (3 モード)
 *  9.0 - 15.0  Dashboard
 * 15.0 - 22.0  AR 相関グラフ
 * 22.0 - 28.0  発射前後 軌跡 (followthrough)
 * 28.0 - 34.0  Sessions タブ (総括カード + 推移)
 * 34.0 - 40.0  2 shot 比較
 * 40.0 - 46.0  ダークモード
 * 46.0 - 52.0  shot list ミニターゲット
 * 52.0 - 60.0  Outro + URL
 */
export const WebsiteDemo: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: "#0e1014" }}>
      <Sequence from={s(0)} durationInFrames={s(3)}>
        <AbsoluteFill style={{ background: "#0e1014" }}>
          <Title
            text="SCATT Companion"
            subtitle="本家にない指標で、射撃を読み解く"
            durationFrames={s(3)}
            color="#fff"
          />
        </AbsoluteFill>
      </Sequence>

      <Sequence from={s(3)} durationInFrames={s(6)}>
        <ScreenshotShow
          src="img/home.png"
          caption="ホーム画面 — 射手と種目を選んで始める"
          subCaption="伏射 / AR / ホールド練習 の 3 モード"
          durationFrames={s(6)}
        />
      </Sequence>

      <Sequence from={s(9)} durationInFrames={s(6)}>
        <ScreenshotShow
          src="img/dashboard.png"
          caption="Dashboard"
          subCaption="主役 KPI · 指標表 · Live 即時診断 · ISSF ターゲット"
          durationFrames={s(6)}
        />
      </Sequence>

      <Sequence from={s(15)} durationInFrames={s(7)}>
        <ScreenshotShow
          src="img/s1_vs_fire_r.png"
          caption="AR 相関グラフ"
          subCaption="速度を下げると本当に当たるか — 実データで検証"
          durationFrames={s(7)}
        />
      </Sequence>

      <Sequence from={s(22)} durationInFrames={s(6)}>
        <ScreenshotShow
          src="img/followthrough.png"
          caption="発射前後 軌跡 重ね"
          subCaption="フォロースルーの質を 1 つの図で"
          durationFrames={s(6)}
        />
      </Sequence>

      <Sequence from={s(28)} durationInFrames={s(6)}>
        <ScreenshotShow
          src="img/sessions.png"
          caption="セッション総括"
          subCaption="ベスト/ワースト + 前半→後半 トレンド"
          durationFrames={s(6)}
        />
      </Sequence>

      <Sequence from={s(34)} durationInFrames={s(6)}>
        <ScreenshotShow
          src="img/compare.png"
          caption="2 shot 比較"
          subCaption="⌘+クリックで 2 発選んで差分を可視化"
          durationFrames={s(6)}
        />
      </Sequence>

      <Sequence from={s(40)} durationInFrames={s(6)}>
        <ScreenshotShow
          src="img/dashboard-dark.png"
          caption="ダークモード"
          subCaption="暗い射場 / 夜間練習向け"
          durationFrames={s(6)}
        />
      </Sequence>

      <Sequence from={s(46)} durationInFrames={s(6)}>
        <ScreenshotShow
          src="img/home.png"
          caption="shot list ミニターゲット"
          subCaption="リスト上で着弾を一目で (緑=10点 黄=9点 赤=外)"
          durationFrames={s(6)}
        />
      </Sequence>

      <Sequence from={s(52)} durationInFrames={s(8)}>
        <AbsoluteFill
          style={{
            background: "radial-gradient(ellipse at center, #1a2030 0%, #0e1014 70%)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 18,
          }}
        >
          <h1
            style={{
              fontSize: 92,
              fontWeight: 800,
              color: "#fff",
              margin: 0,
              letterSpacing: "-0.02em",
              fontFamily: "-apple-system, 'Hiragino Sans', sans-serif",
            }}
          >
            SCATT Companion
          </h1>
          <p style={{ fontSize: 26, color: "#9aa3b2", margin: "8px 0" }}>
            kaitabata.github.io/scatt-analyzer
          </p>
          <div
            style={{
              display: "flex",
              gap: 24,
              marginTop: 28,
            }}
          >
            <Pill text="Apache 2.0" />
            <Pill text="macOS 11+" />
            <Pill text="DMG ダウンロード可" />
          </div>
          <p
            style={{
              fontSize: 18,
              color: "#5a6170",
              marginTop: 28,
              fontFamily: "-apple-system, 'Hiragino Sans', sans-serif",
            }}
          >
            開発: Kai Tabata + Claude Opus 4.7
          </p>
        </AbsoluteFill>
      </Sequence>

    </AbsoluteFill>
  );
};

const Pill: React.FC<{ text: string }> = ({ text }) => (
  <span
    style={{
      padding: "10px 24px",
      background: "rgba(255,255,255,0.08)",
      border: "1px solid rgba(255,255,255,0.12)",
      borderRadius: 999,
      color: "#dde",
      fontSize: 18,
      fontFamily: "-apple-system, 'Hiragino Sans', sans-serif",
    }}
  >
    {text}
  </span>
);
