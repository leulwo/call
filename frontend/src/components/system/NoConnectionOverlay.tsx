"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";

/** Full-screen state shown while the device has no internet connection. */
export const NoConnectionOverlay: React.FC = () => {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const update = () => setOffline(!navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  if (!offline) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-[#fbfaf7]/95 p-6 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-2xl border border-[#e6e9e5] bg-white px-8 py-10 text-center shadow-[0_12px_40px_rgba(36,55,42,0.12)]">
        <Image
          src="/No-Files-3--Streamline-Brooklyn.svg"
          alt="No connection"
          width={140}
          height={140}
          className="mx-auto h-32 w-32 object-contain opacity-90"
        />
        <h2 className="mt-4 text-[17px] font-bold text-[#2a3a3a]">You are offline</h2>
        <p className="mt-1.5 text-[12px] leading-5 text-[#7f8a87]">
          PaperFlow needs an internet connection to reach the library. Check your Wi-Fi or data, and this page will pick up automatically.
        </p>
      </div>
    </div>
  );
};
