import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {BG, GRID} from './theme';

/** 17 Eyl eklendi -- kullanıcı geri bildirimi: mevcut kartlar (StatCallout/CompareBars/
 * KeyQuote/TitleCard) düz koyu arka plan + sade spring-giriş kullanıyordu, "dikkat çekici
 * ileri seviye editörlük" hissi vermiyordu. Bu modül TÜM kartların paylaştığı ortak
 * görsel katmanları sağlar: hareketli glow arka plan + kayan ızgara + vinyet + camsı
 * panel çerçevesi -- her template kendi içeriğini bu ortak "sahne"nin üzerine koyar. */

export const CardBackground: React.FC<{accent: string}> = ({accent}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const t = (frame / Math.max(durationInFrames, 1)) * Math.PI * 2;
  const glowX = 30 + Math.sin(t) * 22;
  const glowY = 68 + Math.cos(t * 0.8) * 18;
  const gridDrift = (frame * 0.35) % 54;

  return (
    <div style={{position: 'absolute', inset: 0, background: BG, overflow: 'hidden'}}>
      <div style={{
        position: 'absolute', inset: 0,
        background: `radial-gradient(circle at ${glowX}% ${glowY}%, ${accent}26 0%, transparent 58%)`,
      }} />
      <div style={{
        position: 'absolute', inset: -60, opacity: 0.28,
        backgroundImage: `linear-gradient(${GRID} 1px, transparent 1px), `
          + `linear-gradient(90deg, ${GRID} 1px, transparent 1px)`,
        backgroundSize: '54px 54px',
        transform: `translate(${gridDrift}px, ${gridDrift * 0.6}px)`,
      }} />
      <div style={{
        position: 'absolute', inset: 0,
        background: 'radial-gradient(circle at 50% 45%, transparent 50%, rgba(0,0,0,0.55) 100%)',
      }} />
    </div>
  );
};

export function panelStyle(accent: string, entrance: number, tilt = true, extraScale = 1): React.CSSProperties {
  // NOT: bu tek 'transform' burada TÜM panel hareketini (giriş + varsa sürekli nefes
  // alma) birleştirir -- çağıran taraf panelStyle'ı spread ettikten SONRA kendi
  // 'transform'unu eklerse (aynı CSS anahtarı) birbirini ezer ve panel ORTALAMASI
  // bozulur (17 Eyl'de tam bu yüzden panel ekrandan taştı). Ekstra ölçek gerekiyorsa
  // extraScale parametresiyle buraya geçilmeli, ayrı bir transform ile DEĞİL.
  const scale = (0.88 + entrance * 0.12) * extraScale;
  return {
    background: 'linear-gradient(160deg, rgba(255,255,255,0.07), rgba(255,255,255,0.015))',
    border: `1px solid ${accent}66`,
    borderRadius: 28,
    boxShadow: `0 24px 70px rgba(0,0,0,0.5), 0 0 46px ${accent}26, inset 0 1px 0 rgba(255,255,255,0.08)`,
    opacity: entrance,
    transform: tilt
      ? `translateY(${(1 - entrance) * 46}px) scale(${scale}) rotateX(${(1 - entrance) * 8}deg)`
      : `translateY(${(1 - entrance) * 46}px) scale(${scale})`,
  };
}
