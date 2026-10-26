import React from 'react';
import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';

// Hiz-Oncelikli Pragmatist prototipi: HER segment icin Chromium render etmek yerine
// TEK BIR jenerik, DONGULENEBILIR (seamless loop) animasyonlu katman -- render maliyeti
// segment sayisindan BAGIMSIZ, sabit. ffmpeg -stream_loop ile herhangi bir uzunluga
// uzatilip video/ses senkronunu bozmadan tum segmentlerin ustune tek bir kez overlay
// edilebilir. Seffaf arka plan (WebM, yuva420p) -- SDXL foto-gerceklik gorseli DEGISTIRMEZ,
// uzerine ince bir "canli/hareketli" his katar.
export type PersonaCSpeedProps = {
  seconds?: number;
  fps?: number;
  accentColor?: string;
};

export const defaultPersonaCSpeedProps: PersonaCSpeedProps = {
  seconds: 6,
  fps: 30,
  accentColor: '#58a6ff',
};

export const PersonaC_Speed: React.FC<PersonaCSpeedProps> = ({accentColor = '#58a6ff'}) => {
  const frame = useCurrentFrame();
  const {durationInFrames, width, height} = useVideoConfig();

  // Periyot TAM klip suresine esit -> frame=0 ve frame=durationInFrames durumlari
  // matematiksel olarak ozdes (mod/sin periyodik), loop noktasinda goze batan bir
  // atlama/sicrama OLMAZ.
  const cyclePos = (frame % durationInFrames) / durationInFrames; // 0 -> 1 -> (0)
  const angle = cyclePos * Math.PI * 2;

  // 1) Kose vinyeti "nefes alma" -- yavas sinuzoidal opaklik pulsu (0.15-0.35 arasi).
  const breathe = 0.25 + Math.sin(angle) * 0.10;

  // 2) Ince isik cizgisi -- ekranin genisligi boyunca capraz kayan, yumusak (blur'lu)
  // bir gradyan bar. cyclePos 0->1 dongusunde ekrani bir kez bastan sona gecer.
  const sweepX = interpolate(cyclePos, [0, 1], [-0.3, 1.3]) * width;

  return (
    <div style={{width, height, position: 'relative', overflow: 'hidden'}}>
      {/* Kose vinyeti: nefes alan koyu kose gradyani -- SDXL gorselinin uzerinde
          fark edilmeden derinlik/sinematik his katar. */}
      <div
        style={{
          position: 'absolute', inset: 0,
          background: `radial-gradient(circle at 15% 85%, rgba(0,0,0,${(breathe * 0.9).toFixed(3)}) 0%, rgba(0,0,0,0) 45%),`
            + `radial-gradient(circle at 85% 15%, rgba(0,0,0,${(breathe * 0.9).toFixed(3)}) 0%, rgba(0,0,0,0) 45%)`,
        }}
      />
      {/* Capraz isik sweep -- ince, yumusak, dusuk opakli. */}
      <div
        style={{
          position: 'absolute', top: 0, left: sweepX - width * 0.18, width: width * 0.36, height,
          transform: 'skewX(-18deg)',
          background: `linear-gradient(90deg, rgba(255,255,255,0) 0%, ${accentColor}22 45%, ${accentColor}33 50%, ${accentColor}22 55%, rgba(255,255,255,0) 100%)`,
          mixBlendMode: 'screen',
        }}
      />
    </div>
  );
};
