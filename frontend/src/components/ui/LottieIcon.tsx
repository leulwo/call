"use client";

import React, { useEffect, useState } from "react";
import Lottie from "lottie-react";

interface LottieIconProps {
  src: string; // e.g. "/wired-outline-19-magnifier-hover-spin.json" or "/loading.lottie"
  width?: number | string;
  height?: number | string;
  autoplay?: boolean;
  loop?: boolean;
  className?: string;
}

export const LottieIcon: React.FC<LottieIconProps> = ({
  src,
  width = 24,
  height = 24,
  autoplay = true,
  loop = true,
  className = "",
}) => {
  const [animationData, setAnimationData] = useState<any>(null);

  useEffect(() => {
    if (src.endsWith(".json")) {
      fetch(src)
        .then((res) => res.json())
        .then((data) => setAnimationData(data))
        .catch((err) => console.error(`Error loading animation from ${src}:`, err));
    }
  }, [src]);

  if (!animationData) {
    return <div style={{ width, height }} className={className} />;
  }

  return (
    <div style={{ width, height }} className={className}>
      <Lottie
        animationData={animationData}
        autoPlay={autoplay}
        loop={loop}
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
};
