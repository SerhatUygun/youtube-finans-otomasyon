// Finans Kanalı kurumsal kimliği (29 Eyl, kanal sahibinin logosu): beyaz amblem (güneşli klasik profil) + kalın sans
// "FİNANS" + seyrek aralıklı serif kırmızı "KANALI" + Türk bayrağı. Amblem: public/brand/emblem_white.png (şeffaf).
import React from 'react';
import {Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont as loadPlayfair} from '@remotion/google-fonts/PlayfairDisplay';
import {T} from './theme';

const playfair = loadPlayfair('normal', {weights: ['500', '600'], subsets: ['latin', 'latin-ext']});

export const BRAND = {
  navy: '#1B3246',
  red: '#C9545E', // "KANALI"
  flag: '#E30A17',
  serif: playfair.fontFamily,
  emblem: 'brand/emblem_white.png',
};

export const TurkFlag: React.FC<{h: number; style?: React.CSSProperties}> = ({h, style}) => {
  const w = h * 1.5;
  return (
    <svg width={w} height={h} viewBox="0 0 30 20" style={{borderRadius: h * 0.08, flexShrink: 0, ...style}}>
      <rect width="30" height="20" fill={BRAND.flag} />
      <circle cx="10.5" cy="10" r="5" fill="#fff" />
      <circle cx="11.75" cy="10" r="4" fill={BRAND.flag} />
      <polygon fill="#fff" transform="translate(16.9,10) rotate(-18)"
        points="2.2,0 0.68,0.49 0.68,2.09 -0.26,0.79 -1.78,1.29 -0.84,0 -1.78,-1.29 -0.26,-0.79 0.68,-2.09 0.68,-0.49" />
    </svg>
  );
};

export const Emblem: React.FC<{size: number; style?: React.CSSProperties}> = ({size, style}) => (
  <Img src={staticFile(BRAND.emblem)} style={{width: size, height: size, objectFit: 'contain', ...style}} />
);

// Yatay imza: amblem + iki satır (FİNANS / KANALI + bayrak). h = toplam yükseklik.
export const BrandMark: React.FC<{h: number; style?: React.CSSProperties}> = ({h, style}) => (
  <div style={{display: 'flex', alignItems: 'center', gap: h * 0.22, ...style}}>
    <Emblem size={h} />
    <div style={{display: 'flex', flexDirection: 'column', justifyContent: 'center', lineHeight: 1}}>
      <span style={{fontFamily: T.f.display, fontWeight: 900, fontSize: h * 0.46, color: T.c.text, letterSpacing: '0.07em'}}>FİNANS</span>
      <span style={{display: 'flex', alignItems: 'center', gap: h * 0.14, marginTop: h * 0.04}}>
        <span style={{fontFamily: BRAND.serif, fontWeight: 500, fontSize: h * 0.38, color: BRAND.red, letterSpacing: '0.28em'}}>KANALI</span>
        <TurkFlag h={h * 0.26} />
      </span>
    </div>
  </div>
);

// Açılış/kapanış kilidi: amblem güneş ışınlarıyla belirir, FİNANS harf harf, KANALI ve bayrak kayarak gelir.
export const BrandLockup: React.FC<{size: number; delay?: number; vertical?: boolean}> = ({size, delay = 0, vertical}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const e = spring({frame: f - delay, fps, config: T.spring.heavy});
  const reveal = interpolate(f - delay, [0, 26], [0, 75], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const letters = 'FİNANS'.split('');
  const para = spring({frame: f - delay - 26, fps, config: T.spring.smooth});
  const fs = size * 0.42;
  return (
    <div style={{display: 'flex', flexDirection: vertical ? 'column' : 'row', alignItems: 'center', gap: size * 0.28}}>
      <div style={{position: 'relative', width: size, height: size}}>
        <div style={{position: 'absolute', inset: -size * 0.25, borderRadius: '50%', opacity: 0.55 * e,
          background: `radial-gradient(circle, ${T.c.hero}55 0%, ${T.c.hero}00 65%)`}} />
        <Emblem size={size} style={{position: 'absolute', clipPath: `circle(${reveal}% at 50% 50%)`,
          transform: `scale(${interpolate(e, [0, 1], [0.85, 1])}) rotate(${interpolate(e, [0, 1], [-8, 0])}deg)`}} />
      </div>
      <div style={{display: 'flex', flexDirection: 'column', alignItems: vertical ? 'center' : 'flex-start', lineHeight: 1}}>
        <div style={{display: 'flex'}}>
          {letters.map((ch, i) => {
            const q = spring({frame: f - delay - 12 - i * 2.5, fps, config: T.spring.snappy});
            return (
              <span key={i} style={{fontFamily: T.f.display, fontWeight: 900, fontSize: fs, color: T.c.text, letterSpacing: '0.07em', display: 'inline-block',
                opacity: q, transform: `translateY(${interpolate(q, [0, 1], [fs * 0.5, 0])}px)`, filter: `blur(${interpolate(q, [0, 1], [8, 0])}px)`}}>{ch}</span>
            );
          })}
        </div>
        <div style={{display: 'flex', alignItems: 'center', gap: fs * 0.3, marginTop: fs * 0.12, opacity: para,
          transform: `translateX(${interpolate(para, [0, 1], [-fs * 0.6, 0])}px)`}}>
          <span style={{fontFamily: BRAND.serif, fontWeight: 500, fontSize: fs * 0.8, color: BRAND.red, letterSpacing: '0.3em'}}>KANALI</span>
          <TurkFlag h={fs * 0.55} />
        </div>
      </div>
    </div>
  );
};
