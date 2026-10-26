import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {INK, MUTED} from './theme';
import {CardBackground} from './cardFx';

export type NewspaperHighlightProps = {
  headline: string;
  sourceLabel: string;
  seconds?: number;
  fps?: number;
};

export const defaultNewspaperHighlightProps: NewspaperHighlightProps = {
  headline: 'Enflasyon beklentisi %42\'ye yukseltildi',
  sourceLabel: 'TCMB Raporu',
  seconds: 5,
  fps: 30,
};

const PAPER = '#f4ecd8';
const PAPER_INK = '#2b2620';
const HILITE = '#ffe066';

// 18 Eyl eklendi (SIFIR_MALIYET rehberi Modul 2) -- resmi rapor/haber cumlesi hafif 3B
// egimle gelen bir "kagit" kart uzerinde, kritik cumle soldan saga fosforlu kalemle
// cizilir, sonra kart hafifce kameraya yaklasir. StatCallout/TitleCard ile aynı giris
// (panelIn spring) + CardBackground sahnesini paylasir, sadece panel PAPER renginde.
export const NewspaperHighlight: React.FC<NewspaperHighlightProps> = ({headline, sourceLabel}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width, height} = useVideoConfig();

  const panelIn = spring({frame, fps, config: {damping: 200, stiffness: 110}, durationInFrames: Math.round(fps * 0.6)});
  const tiltSettle = spring({frame, fps, config: {damping: 26, stiffness: 90}});
  // Fosforlu kalem: 12. kareden itibaren, sayacın bitimine kadar soldan sağa cizilir.
  const highlightStart = 14;
  const highlightEnd = Math.max(Math.round(durationInFrames * 0.55), highlightStart + 10);
  const strokeProgress = interpolate(frame, [highlightStart, highlightEnd], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  // Vurgu bitince kart hafifce kameraya yaklasir (Vox tarzi punch-in).
  const punchIn = interpolate(frame, [highlightEnd, highlightEnd + 20], [1, 1.06], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const sourceIn = spring({frame: frame - 6, fps, config: {damping: 200}});

  const tiltDeg = (1 - tiltSettle) * -9;

  return (
    <div style={{width, height, position: 'relative', fontFamily: '"Segoe UI", Arial, sans-serif'}}>
      <CardBackground accent={HILITE} />
      <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', perspective: 1400}}>
        <div
          style={{
            width: width * 0.62,
            padding: `${height * 0.06}px ${width * 0.05}px`,
            background: `linear-gradient(165deg, ${PAPER}, #e8ddc0)`,
            borderRadius: 10,
            boxShadow: '0 30px 80px rgba(0,0,0,0.55), inset 0 0 40px rgba(120,100,60,0.12)',
            opacity: panelIn,
            transform:
              `translateY(${(1 - panelIn) * 50}px) `
              + `scale(${(0.86 + panelIn * 0.14) * punchIn}) `
              + `rotateX(${8 + tiltDeg}deg) rotateZ(${(1 - tiltSettle) * -2}deg)`,
            transformStyle: 'preserve-3d',
          }}
        >
          <div style={{
            fontSize: width * 0.014, fontWeight: 700, letterSpacing: 2, color: '#8a7550',
            textTransform: 'uppercase', marginBottom: height * 0.018, opacity: sourceIn,
            transform: `translateY(${(1 - sourceIn) * 12}px)`,
          }}>
            {sourceLabel}
          </div>
          <div style={{position: 'relative', display: 'inline-block'}}>
            <span style={{
              position: 'relative', zIndex: 1,
              fontSize: width * 0.032, fontWeight: 800, color: PAPER_INK, lineHeight: 1.35,
            }}>
              {headline}
            </span>
            {/* Fosforlu kalem: metnin ARKASINDA, soldan saga genisleyen bir sarit. */}
            <span style={{
              position: 'absolute', zIndex: 0, left: 0, top: '18%', bottom: '10%',
              width: `${strokeProgress * 100}%`,
              background: HILITE, opacity: 0.65, borderRadius: 3,
              boxShadow: `0 0 18px ${HILITE}88`,
            }} />
          </div>
        </div>
      </div>
      <div style={{
        position: 'absolute', bottom: height * 0.06, width, textAlign: 'center',
        fontSize: width * 0.014, color: MUTED, opacity: sourceIn,
      }}>
        resmi rapor / haber
      </div>
    </div>
  );
};
