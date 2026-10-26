import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {NEUTRAL, UP} from './theme';

/** 17 Eyl eklendi -- 3 personayla (Maksimalist Broadcast / Sinematik Minimalist / Hız
 * Öncelikli Pragmatist) paralel prototip denemesinin harmanı. Amaç: sadece StatCallout/
 * CompareBars/KeyQuote/MarketChart/TitleCard'ın kapsadığı (sayı/alıntı içeren) segmentler
 * değil, TÜM segmentler (düz Ken-Burns statik görsel olanlar dahil) "gelişmiş/gözle görülür"
 * bir animasyon katmanına sahip olsun -- kullanıcı isteği.
 *
 * Üç ajanın da bağımsız vardığı ortak sonuç: her segment için Chromium'u ayrı ayrı
 * çalıştırmak (70+ segmentlik gerçek scriptlerde) maliyetli. Bu yüzden bu bileşen KUSURSUZ
 * DÖNGÜLENEBİLİR (frame % durationInFrames -> loop noktasında sıçrama yok, Persona C'nin
 * kanıtlanmış tekniği): sabit süreli (örn. 8s) TEK bir klip render edilip
 * s07_edit.py'de ffmpeg -stream_loop ile her segmentin kendi süresine uzatılır/kırpılır --
 * render maliyeti segment sayısından bağımsız, SABİT kalır.
 *
 * Tekrar/monoton hissini önlemek için (Persona A/C'nin ikisinin de belirttiği risk):
 * `variantColor` + `label` prop'ları ile 3 farklı renk/etiket varyasyonu üretilir
 * (round-robin, bkz. s05b_motion_graphics._render_accent_overlays), TEK bir sabit görsel
 * motif tekrarlanmaz.
 *
 * Şeffaf (alpha) arka plan -- Captions.tsx ile AYNI desen (yuva420p WebM, vp8/libvpx) --
 * SDXL foto-gerçekçi Ken-Burns görselini DEĞİŞTİRMEZ, üzerine ince bir katman bindirir. */
export type AccentOverlayProps = {
  seconds?: number;
  fps?: number;
  variantColor?: string;
  label?: string;
};

export const defaultAccentOverlayProps: AccentOverlayProps = {
  seconds: 8,
  fps: 30,
  variantColor: NEUTRAL,
  label: 'CANLI VERİ',
};

export const AccentOverlay: React.FC<AccentOverlayProps> = ({variantColor, label}) => {
  const frame = useCurrentFrame();
  const {fps, width, height, durationInFrames} = useVideoConfig();
  const color = variantColor || NEUTRAL;

  // Periyot TAM klip süresine eşit -> loop noktasında (frame=0 <-> frame=durationInFrames)
  // matematiksel özdeşlik, sıçrama yok (Persona C tekniği).
  const cyclePos = (frame % durationInFrames) / durationInFrames;
  const angle = cyclePos * Math.PI * 2;

  // 1) Köşegen ışık huzmesi: periyodik olarak ekranı çapraz geçer (Persona A'nın
  // görsel gücü + Persona C'nin döngü-güvenli matematiği).
  const sweepX = interpolate(cyclePos, [0, 1], [-0.3, 1.3]) * width;

  // 2) Köşe vinyeti nefes alma (Persona C) -- derinlik/sinematik his.
  const breathe = 0.22 + Math.sin(angle) * 0.08;

  // 3) Sol-üst nabız rozeti (Persona A) -- sürekli/periyodik pulse, giriş spring'i ile.
  const badgeIn = spring({frame, fps, config: {damping: 200, stiffness: 200}, durationInFrames: Math.round(fps * 0.6)});
  const pulse = 1 + 0.12 * Math.sin(angle * 3);

  // 4) Alt kenar accent çizgisi -- periyodik nefes alan opaklık (loop-güvenli).
  const lineOpacity = 0.55 + Math.sin(angle * 2) * 0.25;

  return (
    <div style={{width, height, position: 'relative', overflow: 'hidden'}}>
      <div
        style={{
          position: 'absolute', inset: 0,
          background: `radial-gradient(circle at 15% 85%, rgba(0,0,0,${(breathe * 0.9).toFixed(3)}) 0%, rgba(0,0,0,0) 45%),`
            + `radial-gradient(circle at 85% 15%, rgba(0,0,0,${(breathe * 0.9).toFixed(3)}) 0%, rgba(0,0,0,0) 45%)`,
        }}
      />
      <div
        style={{
          position: 'absolute', top: 0, left: sweepX - width * 0.18, width: width * 0.32, height,
          transform: 'skewX(-18deg)',
          background: `linear-gradient(90deg, rgba(255,255,255,0) 0%, ${color}33 45%, ${color}55 50%, ${color}33 55%, rgba(255,255,255,0) 100%)`,
          mixBlendMode: 'screen',
        }}
      />
      <div
        style={{
          position: 'absolute', top: height * 0.05, left: width * 0.04,
          display: 'flex', alignItems: 'center', gap: 10,
          opacity: badgeIn, transform: `scale(${badgeIn})`,
        }}
      >
        <div
          style={{
            width: 14, height: 14, borderRadius: '50%', background: UP,
            transform: `scale(${pulse})`, boxShadow: `0 0 ${16 * pulse}px ${UP}`,
          }}
        />
        <div
          style={{
            color: '#fff', fontFamily: '"Segoe UI", Arial, sans-serif', fontWeight: 800,
            fontSize: width * 0.014, letterSpacing: 2, textShadow: '0 2px 10px rgba(0,0,0,0.7)',
          }}
        >
          {label || 'CANLI VERİ'}
        </div>
      </div>
      <div
        style={{
          position: 'absolute', bottom: height * 0.045, left: width * 0.04,
          width: width * 0.32, height: 4, borderRadius: 3,
          background: `linear-gradient(90deg, ${color}, transparent)`,
          opacity: lineOpacity, boxShadow: `0 0 10px ${color}`,
        }}
      />
    </div>
  );
};
