import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {NEUTRAL, UP} from './theme';

export type PersonaABroadcastProps = {
  seconds?: number;
  fps?: number;
  accentColor?: string;
};

export const defaultPersonaABroadcastProps: PersonaABroadcastProps = {
  seconds: 5,
  fps: 30,
  accentColor: NEUTRAL,
};

// Maksimalist Broadcast Tasarimcisi prototipi -- SEFFAF overlay (Captions.tsx deseniyle
// ayni: arka plan yok, WebM alpha olarak render edilir, ffmpeg overlay ile ana SDXL
// Ken-Burns goruntusunun UZERINE bindirilir). Amac: HER segmente (sayi/alinti icermese
// bile) goze carpan, haber-kanali/broadcast hissi veren bir hareket katmani eklemek.
//
// 3 eleman:
//  1) Kosegen isik huzmesi -- ekrani bir kez capraz gecer (spring giris + interpolate pan).
//  2) Sol-ust "CANLI" nabiz rozeti -- surekli pulse (canli yayin hissi).
//  3) Alt kenar boyunca buyuyen ince accent cizgisi -- segment boyunca sabit kalir.
export const PersonaA_Broadcast: React.FC<PersonaABroadcastProps> = ({accentColor}) => {
  const frame = useCurrentFrame();
  const {fps, width, height, durationInFrames} = useVideoConfig();
  const color = accentColor || NEUTRAL;

  // 1) Isik huzmesi: ilk 1.2s'de capraz gecer, sonra kaybolur.
  const sweepFrames = Math.round(fps * 1.2);
  const sweepProgress = interpolate(frame, [0, sweepFrames], [-0.3, 1.3], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const sweepOpacity = interpolate(frame, [0, sweepFrames * 0.15, sweepFrames * 0.85, sweepFrames], [0, 0.55, 0.55, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  // 2) Nabiz rozeti: sinus tabanli surekli pulse + giris spring'i.
  const badgeIn = spring({frame, fps, config: {damping: 200, stiffness: 200}});
  const pulse = 1 + 0.12 * Math.sin((frame / fps) * Math.PI * 2.4);

  // 3) Alt accent cizgisi: 0.8s'de tam genislige ulasir, son 0.5s'de solar.
  const lineGrow = spring({frame, fps, config: {damping: 200, stiffness: 90}, durationInFrames: Math.round(fps * 0.8)});
  const fadeOutStart = durationInFrames - Math.round(fps * 0.5);
  const globalFade = interpolate(frame, [Math.max(fadeOutStart, 0), durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  return (
    <div style={{width, height, position: 'relative', overflow: 'hidden'}}>
      {/* Kosegen isik huzmesi */}
      <div
        style={{
          position: 'absolute',
          top: -height * 0.5,
          left: `${sweepProgress * 100}%`,
          width: width * 0.35,
          height: height * 2,
          background: `linear-gradient(100deg, transparent, ${color}, transparent)`,
          opacity: sweepOpacity * globalFade,
          transform: 'rotate(12deg)',
          filter: 'blur(18px)',
        }}
      />

      {/* Sol-ust nabiz rozeti */}
      <div
        style={{
          position: 'absolute',
          top: height * 0.05,
          left: width * 0.04,
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          opacity: badgeIn * globalFade,
          transform: `scale(${badgeIn})`,
        }}
      >
        <div
          style={{
            width: 16,
            height: 16,
            borderRadius: '50%',
            background: UP,
            transform: `scale(${pulse})`,
            boxShadow: `0 0 ${18 * pulse}px ${UP}`,
          }}
        />
        <div
          style={{
            color: '#fff',
            fontFamily: '"Segoe UI", Arial, sans-serif',
            fontWeight: 800,
            fontSize: width * 0.016,
            letterSpacing: 2,
            textShadow: '0 2px 10px rgba(0,0,0,0.7)',
          }}
        >
          CANLI VERİ
        </div>
      </div>

      {/* Alt kenar accent cizgisi */}
      <div
        style={{
          position: 'absolute',
          bottom: height * 0.045,
          left: width * 0.04,
          width: (width * 0.4) * lineGrow,
          height: 5,
          borderRadius: 3,
          background: `linear-gradient(90deg, ${color}, transparent)`,
          opacity: globalFade,
          boxShadow: `0 0 12px ${color}`,
        }}
      />
    </div>
  );
};
