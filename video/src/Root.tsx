import { Composition } from "remotion";
import { MarketingPV } from "./MarketingPV";
import { WebsiteDemo } from "./WebsiteDemo";

export const Root: React.FC = () => {
  return (
    <>
      {/* 30 秒マーケティング PV */}
      <Composition
        id="MarketingPV"
        component={MarketingPV}
        durationInFrames={30 * 30}    // 30 fps × 30 秒 = 900
        fps={30}
        width={1920}
        height={1080}
      />
      {/* 60 秒 紹介サイト用 Demo */}
      <Composition
        id="WebsiteDemo"
        component={WebsiteDemo}
        durationInFrames={60 * 30}    // 30 fps × 60 秒
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
