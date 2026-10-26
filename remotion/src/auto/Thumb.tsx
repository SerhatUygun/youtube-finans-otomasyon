// Parametrik kapak (1280×720): A = iki satır başlık + rozet + fiyat çipleri, B = gösterge,
// C = iki satır yön okları. Spec Claude'un yazdığı thumb.json'dan gelir.
import React from 'react';
import {AbsoluteFill, Img, staticFile} from 'remotion';
import {loadFont as loadAnton} from '@remotion/google-fonts/Anton';
import {BrandMark} from '../core/brand';
import {ProSpec, ThumbPro} from './ThumbPro';
import {loadFont as loadArchivo} from '@remotion/google-fonts/Archivo';
import {loadFont as loadMono} from '@remotion/google-fonts/JetBrainsMono';

const anton = loadAnton('normal', {subsets: ['latin', 'latin-ext']}).fontFamily;
const archivo = loadArchivo('normal', {weights: ['700', '900'], subsets: ['latin', 'latin-ext']}).fontFamily;
const mono = loadMono('normal', {weights: ['700', '800'], subsets: ['latin', 'latin-ext']}).fontFamily;

const C: Record<string, string> = {gold: '#F2B84B', red: '#FF3B45', green: '#2EE59D', silver: '#D5DDEA', btc: '#F7931A', text: '#FFFFFF', blue: '#5CC8FF', oil: '#8B7CFF'};
const c = (k?: string, d = C.text) => (k && C[k]) || d;
const BG = '#070A12';
const STROKE = '0 6px 0 rgba(0,0,0,0.55), 0 0 40px rgba(0,0,0,0.6)';

export type ThumbSpec = {
  variant: 'A' | 'B' | 'C';
  kicker?: string; kickerColor?: string;
  headline?: string[]; headlineColors?: string[];
  badge?: string;
  chips?: {name: string; price: string; dir: 'up' | 'down'; color?: string}[];
  gauge?: number; gaugeLabel?: string;
  rows?: {text: string; dir: 'up' | 'down'; color?: string}[];
  footer?: string;
  glow?: string;
  image?: string;
};

const Arrow: React.FC<{dir: 'up' | 'down'; color: string; size: number}> = ({dir, color, size}) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={3.6} strokeLinecap="round" strokeLinejoin="round">
    <path d={dir === 'down' ? 'M12 4 L12 20 M5 13 L12 20 L19 13' : 'M12 20 L12 4 M5 11 L12 4 L19 11'} />
  </svg>
);

const Pill: React.FC<{text: string; bg: string; fg?: string; size?: number}> = ({text, bg, fg = '#fff', size = 30}) => (
  <div style={{display: 'inline-flex', padding: '8px 18px', borderRadius: 10, background: bg, color: fg, fontFamily: archivo, fontWeight: 900, fontSize: size,
    letterSpacing: '0.02em', boxShadow: '0 8px 24px rgba(0,0,0,0.45)'}}>{text}</div>
);

export const AutoThumb: React.FC<{spec: ThumbSpec}> = ({spec}) => {
  // 30 Eyl: 'style' alanı varsa Kapak 2.0 (az yazı, tek nesne) — bkz. ThumbPro.tsx
  if ((spec as any).style) return <ThumbPro spec={spec as unknown as ProSpec} />;
  const glow = c(spec.glow, C.gold);
  const h = spec.headline ?? [];
  const hc = spec.headlineColors ?? ['gold', 'text'];
  const fit = (s: string, base: number, width: number) => Math.min(base, Math.floor(width / Math.max(s.length * 0.52, 1)));
  return (
    <AbsoluteFill style={{background: BG, overflow: 'hidden'}}>
      <AbsoluteFill style={{background: 'radial-gradient(ellipse 900px 700px at 78% 45%, #1B2A55 0%, #0B1226 45%, #070A12 80%)'}} />
      <AbsoluteFill style={{opacity: 0.35, backgroundImage: 'linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px)', backgroundSize: '64px 64px'}} />
      <div style={{position: 'absolute', right: 30, top: 120, width: 520, height: 520, borderRadius: '50%', background: `radial-gradient(circle, ${glow}66 0%, ${glow}00 68%)`}} />
      <Img src={staticFile(spec.image ?? 'auto/host_cut.png')} style={{position: 'absolute', right: -30, bottom: 0, width: 640, height: 720, objectFit: 'cover', objectPosition: '50% 0%',
        filter: 'drop-shadow(-18px 0 30px rgba(0,0,0,0.6)) contrast(1.06) saturate(1.05)'}} />
      <div style={{position: 'absolute', right: 0, bottom: 0, width: 700, height: 140, background: `linear-gradient(0deg, ${BG} 0%, rgba(7,10,18,0) 100%)`}} />
      <div style={{position: 'absolute', left: 48, top: 40, display: 'flex', alignItems: 'center', gap: 12}}>
        <BrandMark h={58} />
      </div>
      {spec.kicker ? <div style={{position: 'absolute', left: 48, top: 116}}><Pill text={spec.kicker} bg={c(spec.kickerColor, C.red)} /></div> : null}

      {spec.variant === 'A' ? (
        <>
          <div style={{position: 'absolute', left: 44, top: 178, fontFamily: anton, lineHeight: 0.94, textShadow: STROKE}}>
            {h.slice(0, 2).map((l, i) => <div key={i} style={{fontSize: fit(l, 176, 600), color: c(hc[i], i ? C.text : C.gold)}}>{l}</div>)}
          </div>
          {spec.badge ? (
            <div style={{position: 'absolute', left: 600, top: 420, transform: 'rotate(-7deg)', padding: '6px 22px 2px', borderRadius: 16, background: C.red,
              boxShadow: '0 14px 40px rgba(255,59,69,0.55), 0 0 0 5px #fff'}}>
              <div style={{fontFamily: anton, fontSize: fit(spec.badge, 118, 420), lineHeight: 1, color: '#fff'}}>{spec.badge}</div>
            </div>
          ) : null}
          <div style={{position: 'absolute', left: 48, bottom: 36, display: 'flex', gap: 14}}>
            {(spec.chips ?? []).slice(0, 3).map((ch, i) => (
              <div key={i} style={{display: 'flex', alignItems: 'center', gap: 10, padding: '10px 18px 10px 14px', borderRadius: 14, background: 'rgba(7,10,18,0.82)', border: `2px solid ${c(ch.color, C.gold)}`}}>
                <div style={{width: 16, height: 16, borderRadius: '50%', background: c(ch.color, C.gold)}} />
                <div style={{fontFamily: archivo, fontWeight: 900, fontSize: 30, color: '#fff'}}>{ch.name}</div>
                <div style={{fontFamily: mono, fontWeight: 800, fontSize: 26, color: '#fff'}}>{ch.price}</div>
                <Arrow dir={ch.dir} color={ch.dir === 'down' ? C.red : C.green} size={34} />
              </div>
            ))}
          </div>
        </>
      ) : null}

      {spec.variant === 'B' ? (
        <>
          <div style={{position: 'absolute', left: 40, top: 160, fontFamily: anton, lineHeight: 0.95, textShadow: STROKE}}>
            {h.slice(0, 2).map((l, i) => <div key={i} style={{fontSize: fit(l, 118, 640), color: c(hc[i], i ? C.red : C.text)}}>{l}</div>)}
          </div>
          <div style={{position: 'absolute', left: 70, top: 400, width: 520, height: 300}}>
            <svg width={520} height={290} viewBox="0 0 520 290">
              <path d="M 40 260 A 220 220 0 0 1 480 260" fill="none" stroke="rgba(255,255,255,0.14)" strokeWidth={44} strokeLinecap="round" />
              {(() => {
                const v = Math.max(0, Math.min(100, spec.gauge ?? 50));
                const a = Math.PI + (Math.PI * v) / 100;
                return <path d={`M 40 260 A 220 220 0 0 1 ${260 + 220 * Math.cos(a)} ${260 + 220 * Math.sin(a)}`} fill="none" stroke={C.gold} strokeWidth={44} strokeLinecap="round" />;
              })()}
            </svg>
            <div style={{position: 'absolute', left: 0, right: 0, top: 118, textAlign: 'center', fontFamily: anton, fontSize: 140, lineHeight: 1, color: '#fff', textShadow: STROKE}}>%{spec.gauge}</div>
          </div>
          {spec.gaugeLabel ? <div style={{position: 'absolute', left: 610, bottom: 60}}><Pill text={spec.gaugeLabel} bg={C.gold} fg="#111" size={34} /></div> : null}
        </>
      ) : null}

      {spec.variant === 'C' ? (
        <>
          <div style={{position: 'absolute', left: 40, top: 170, display: 'flex', flexDirection: 'column', gap: 6, fontFamily: anton, textShadow: STROKE}}>
            {(spec.rows ?? []).slice(0, 2).map((r, i) => (
              <div key={i} style={{display: 'flex', alignItems: 'center', gap: 18}}>
                <div style={{fontSize: fit(r.text, 150, 520), lineHeight: 1, color: c(r.color, C.gold)}}>{r.text}</div>
                <Arrow dir={r.dir} color={r.dir === 'down' ? C.red : C.green} size={150} />
              </div>
            ))}
          </div>
          {spec.footer ? <div style={{position: 'absolute', left: 48, bottom: 44, fontFamily: archivo, fontWeight: 900, fontSize: 40, color: '#fff', textShadow: STROKE}}>{spec.footer}</div> : null}
        </>
      ) : null}
    </AbsoluteFill>
  );
};
