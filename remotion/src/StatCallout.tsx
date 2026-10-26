import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {INK, MUTED, accentFor, fmtNum} from './theme';
import {CardBackground, panelStyle} from './cardFx';

export type StatCalloutProps = {
  label: string;
  value: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  trend?: 'up' | 'down' | 'neutral';
  seconds?: number;
  fps?: number;
};

export const defaultStatCalloutProps: StatCalloutProps = {
  label: 'Faiz artis ihtimali',
  value: 70,
  prefix: '',
  suffix: '%',
  decimals: 0,
  trend: 'up',
  seconds: 4,
  fps: 30,
};

// 17 Eyl (kullanıcı geri bildirimi -- "kartların ortaya çıkması", ileri seviye editörlük):
// düz arka plan + tek spring yerine, sahneli/katmanlı bir giriş: panel süzülerek belirir ->
// yön oku sekerek gelir -> sayı OVERSHOOT ile sayarak büyür (spring damping düşük -> hafif
// zıplama) -> etiket kayar -> çizgi büyür -> tüm kart sürekli hafif "nefes alır" (statik
// kalmaz). CardBackground (hareketli glow + kayan ızgara) tüm kartlarda paylaşılan sahne.
export const StatCallout: React.FC<StatCalloutProps> = ({
  label, value, prefix = '', suffix = '', decimals = 0, trend = 'neutral',
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width, height} = useVideoConfig();
  const accent = accentFor(trend);
  const arrow = trend === 'up' ? '▲' : trend === 'down' ? '▼' : '●';

  const panelIn = spring({frame, fps, config: {damping: 200, stiffness: 120}, durationInFrames: Math.round(fps * 0.5)});
  const arrowIn = spring({frame: frame - 6, fps, config: {damping: 9, stiffness: 180}});
  const countEnd = Math.max(Math.round(durationInFrames * 0.5), 1);
  const shown = interpolate(frame, [10, countEnd], [0, value], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  // Overshoot: sayı hedefi geçip geri döner (damping düşük) -> "çarpıcı" his.
  const numberPunch = spring({frame: frame - 10, fps, config: {damping: 11, stiffness: 140}});
  const labelIn = spring({frame: frame - 20, fps, config: {damping: 200}});
  const lineProgress = interpolate(frame, [16, countEnd], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  // Sürekli nefes alma (sayaç bittikten sonra da kart cansız kalmasın).
  const breathe = 1 + Math.sin((frame / fps) * Math.PI * 1.6) * 0.015;

  return (
    <div style={{width, height, position: 'relative', fontFamily: '"Segoe UI", Arial, sans-serif'}}>
      <CardBackground accent={accent} />
      {/* 17 Eyl düzeltildi: panel ORTALAMA (flex) ve GİRİŞ ANİMASYONU (panelStyle'ın
          transform'u) artık AYRI katmanlarda -- ikisi de 'transform' özelliğini kullanıp
          birbirini ezdiği için panel ekranın ortasından SAĞA taşıp kırpılıyordu (kullanıcı
          ekran görüntüsüyle bildirdi). */}
      <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
        <div style={{
          width: width * 0.56, padding: `${height * 0.06}px ${width * 0.04}px`,
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          ...panelStyle(accent, panelIn, true, breathe),
        }}>
        <div style={{
          fontSize: width * 0.1, fontWeight: 800, color: INK,
          display: 'flex', alignItems: 'baseline', gap: width * 0.014,
          transform: `scale(${0.7 + numberPunch * 0.3 + Math.max(numberPunch - 1, 0) * 0.08})`,
        }}>
          <span style={{
            color: accent, fontSize: width * 0.05,
            transform: `scale(${arrowIn}) translateY(${(1 - arrowIn) * -10}px)`,
            display: 'inline-block', textShadow: `0 0 18px ${accent}`,
          }}>{arrow}</span>
          <span>{prefix}{fmtNum(shown, decimals)}{suffix}</span>
        </div>
        <div style={{
          marginTop: height * 0.022, fontSize: width * 0.024, color: MUTED, opacity: labelIn,
          transform: `translateY(${(1 - labelIn) * 18}px)`, textAlign: 'center', maxWidth: width * 0.5,
          letterSpacing: 0.3,
        }}>
          {label}
        </div>
        <div style={{
          marginTop: height * 0.02, height: 4, width: width * 0.16 * lineProgress,
          background: `linear-gradient(90deg, ${accent}, transparent)`, borderRadius: 2,
          boxShadow: `0 0 10px ${accent}`,
        }} />
        </div>
      </div>
    </div>
  );
};
