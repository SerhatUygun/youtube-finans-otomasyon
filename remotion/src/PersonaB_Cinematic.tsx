import React from 'react';
import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {NEUTRAL} from './theme';

export type PersonaBCinematicProps = {
  seconds?: number;
  fps?: number;
  accentColor?: string;
};

export const defaultPersonaBCinematicProps: PersonaBCinematicProps = {
  seconds: 5,
  fps: 30,
  accentColor: NEUTRAL,
};

// "Sinematik Minimalist" -- her segmentin fotogerceKci SDXL gorseli UZERINE binen SEFFAF
// katman (Captions.tsx'in ayni WebM/yuva420p deseniyle). Amac gorseli degistirmek degil,
// "kaliteli prodüksiyon" hissi eklemek: yavas nefes alan vinyet + ince kose kadraj isaretleri
// + cok yavas kosegen isik taramasi + alt kenarda agirbasli bir vurgu cizgisi. Hicbir eleman
// dikkat cekmeye calismiyor -- amac "fark edilmeden" premium hissettirmek.
export const PersonaBCinematic: React.FC<PersonaBCinematicProps> = ({
  seconds = 5,
  fps = 30,
  accentColor = NEUTRAL,
}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const t = frame / fps;

  // Yavas nefes alan vinyet: 0.28-0.40 arasi ~4.5s periyotla salinir (dikkat cekmeyecek kadar yavas).
  const vignetteOpacity = 0.34 + 0.06 * Math.sin((t / 4.5) * Math.PI * 2);

  // Girisin ilk 0.7s'inde kose isaretleri yumusakca belirir, sonra sabit kalir.
  const cornersIn = interpolate(t, [0, 0.7], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const cornerOpacity = 0.55 * cornersIn;
  const cornerSize = Math.min(width, height) * 0.055;
  const cornerThickness = 2;
  const cornerMargin = width * 0.035;

  const cornerStyleBase: React.CSSProperties = {
    position: 'absolute',
    width: cornerSize,
    height: cornerSize,
    opacity: cornerOpacity,
    borderColor: accentColor,
  };

  // Cok yavas kosegen isik taramasi: tum sure boyunca TEK GECIS yapip ekrandan cikar
  // (donguye sokulmuyor cunku bu genelde her segmentte bir kez oynatilan bir klip).
  const sweepProgress = interpolate(t, [0, seconds], [-0.35, 1.15], {extrapolateRight: 'clamp'});
  const sweepX = sweepProgress * (width + height); // genis diyagonal mesafe

  // Alt kenarda agirbasli vurgu cizgisi: 0 -> %22 genislige 1.1s'de yumusakca acilir, sabit kalir.
  const lineWidthPct = interpolate(t, [0.15, 1.25], [0, 22], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const lineOpacity = interpolate(t, [0.15, 0.9], [0, 0.5], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  return (
    <div style={{width, height, position: 'relative', overflow: 'hidden'}}>
      {/* Nefes alan vinyet (kenarlar hafifce kararir) */}
      <div
        style={{
          position: 'absolute', inset: 0,
          boxShadow: `inset 0 0 ${width * 0.22}px rgba(0,0,0,${vignetteOpacity})`,
        }}
      />

      {/* Cok yavas kosegen isik taramasi -- dusuk opaklikli, genis, yumusak kenarli */}
      <div
        style={{
          position: 'absolute',
          top: -height * 0.5,
          left: sweepX - height * 0.6,
          width: height * 1.2,
          height: height * 2.2,
          transform: 'rotate(18deg)',
          background:
            'linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.05) 45%, ' +
            'rgba(255,255,255,0.09) 50%, rgba(255,255,255,0.05) 55%, rgba(255,255,255,0) 100%)',
          pointerEvents: 'none',
        }}
      />

      {/* Ince kose kadraj isaretleri (4 kose, L-seklinde) */}
      <div style={{...cornerStyleBase, top: cornerMargin, left: cornerMargin, borderTop: `${cornerThickness}px solid`, borderLeft: `${cornerThickness}px solid`}} />
      <div style={{...cornerStyleBase, top: cornerMargin, right: cornerMargin, borderTop: `${cornerThickness}px solid`, borderRight: `${cornerThickness}px solid`}} />
      <div style={{...cornerStyleBase, bottom: cornerMargin, left: cornerMargin, borderBottom: `${cornerThickness}px solid`, borderLeft: `${cornerThickness}px solid`}} />
      <div style={{...cornerStyleBase, bottom: cornerMargin, right: cornerMargin, borderBottom: `${cornerThickness}px solid`, borderRight: `${cornerThickness}px solid`}} />

      {/* Alt kenar vurgu cizgisi, ortalanmis */}
      <div
        style={{
          position: 'absolute', bottom: height * 0.055, left: '50%',
          width: `${lineWidthPct}%`, height: 2,
          transform: 'translateX(-50%)',
          backgroundColor: accentColor,
          opacity: lineOpacity,
          boxShadow: `0 0 12px ${accentColor}`,
        }}
      />
    </div>
  );
};
