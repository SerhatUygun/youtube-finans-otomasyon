// Hareket kiti: arka plan, grade/grain/vignette, girişler, kelime açılışı, sayaç.
import React from 'react';
import {AbsoluteFill, continueRender, delayRender, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {fitText} from '@remotion/layout-utils';
import {T, fmtTR} from './theme';

export const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const ease = (f: number, a: number, b: number, from: number, to: number, e = T.ease.out) =>
  interpolate(f, [a, b], [from, to], {...clamp, easing: e});

export const useSpring = (delay: number, cfg: keyof typeof T.spring = 'smooth') => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return spring({frame: frame - delay, fps, config: T.spring[cfg]});
};

// ---------- Katman 1: arka plan (asla düz renk değil) ----------
export const BgMesh: React.FC<{tint?: string; tint2?: string; grid?: boolean}> = ({
  tint = T.c.hero,
  tint2 = T.c.accent,
  grid = true,
}) => {
  const f = useCurrentFrame();
  const d1 = Math.sin(f / 70) * 60;
  const d2 = Math.cos(f / 90) * 50;
  return (
    <AbsoluteFill style={{background: `radial-gradient(ellipse at 50% 40%, ${T.c.bg2} 0%, ${T.c.bg} 70%)`}}>
      <div
        style={{
          position: 'absolute', width: 1500, height: 1500, borderRadius: '50%', top: -700, left: -500 + d1,
          background: `radial-gradient(circle, ${tint}24 0%, transparent 60%)`,
        }}
      />
      <div
        style={{
          position: 'absolute', width: 1300, height: 1300, borderRadius: '50%', bottom: -700, right: -450 - d2,
          background: `radial-gradient(circle, ${tint2}1c 0%, transparent 62%)`,
        }}
      />
      {grid ? <PerspectiveGrid /> : null}
      <Dust tint={tint} />
    </AbsoluteFill>
  );
};

// Silik ışık tozları (30 Eyl): yavaşça yükselen 16 parçacık -> derinlik. Deterministik (her render aynı).
const Dust: React.FC<{tint: string}> = ({tint}) => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{pointerEvents: 'none', overflow: 'hidden'}}>
      {Array.from({length: 16}).map((_, i) => {
        const r = (k: number) => (Math.sin(i * 12.9898 + k * 78.233) * 43758.5453) % 1;
        const rx = Math.abs(r(1));
        const speed = 0.35 + Math.abs(r(2)) * 0.6;
        const size = 2 + Math.abs(r(3)) * 4;
        const y = 1100 - ((f * speed + Math.abs(r(4)) * 1200) % 1250);
        const x = rx * 1920 + Math.sin((f + i * 40) / 60) * 18;
        const o = (0.08 + Math.abs(r(5)) * 0.18) * Math.min(1, Math.max(0, (1100 - y) / 200));
        return <div key={i} style={{position: 'absolute', left: x, top: y, width: size, height: size, borderRadius: '50%',
          background: i % 3 === 0 ? tint : T.c.text, opacity: o, filter: `blur(${size > 4 ? 1 : 0}px)`}} />;
      })}
    </AbsoluteFill>
  );
};

// Zeminde yavaşça akan perspektif ızgara — derinlik hissi.
const PerspectiveGrid: React.FC = () => {
  const f = useCurrentFrame();
  const off = (f * 0.6) % 80;
  return (
    <AbsoluteFill style={{perspective: 900, overflow: 'hidden', opacity: 0.55}}>
      <div
        style={{
          position: 'absolute', left: -1200, right: -1200, height: 1400, bottom: -760,
          transform: 'rotateX(74deg)', transformOrigin: '50% 0%',
          backgroundImage: `linear-gradient(${T.c.line} 1px, transparent 1px), linear-gradient(90deg, ${T.c.line} 1px, transparent 1px)`,
          backgroundSize: '80px 80px', backgroundPosition: `0px ${off}px`,
          maskImage: 'linear-gradient(180deg, transparent 0%, black 35%, black 60%, transparent 100%)',
          WebkitMaskImage: 'linear-gradient(180deg, transparent 0%, black 30%, black 55%, transparent 95%)',
        }}
      />
    </AbsoluteFill>
  );
};

// ---------- Katman 4-5: grade, grain, vignette ----------
export const Grade: React.FC = () => (
  <AbsoluteFill style={{pointerEvents: 'none'}}>
    <AbsoluteFill style={{backgroundColor: T.c.hero, mixBlendMode: 'soft-light', opacity: 0.08}} />
    <AbsoluteFill
      style={{background: 'linear-gradient(180deg, rgba(0,0,0,0.25), transparent 22%, transparent 70%, rgba(0,0,0,0.45))'}}
    />
  </AbsoluteFill>
);

const NOISE = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='240' height='240' filter='url(%23n)' opacity='0.6'/%3E%3C/svg%3E")`;
export const Grain: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill
      style={{
        pointerEvents: 'none', backgroundImage: NOISE, backgroundSize: '240px',
        backgroundPosition: `${(f * 37) % 240}px ${(f * 53) % 240}px`, opacity: 0.07, mixBlendMode: 'overlay',
      }}
    />
  );
};

export const Vignette: React.FC = () => (
  <AbsoluteFill
    style={{pointerEvents: 'none', background: 'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.55) 100%)'}}
  />
);

// ---------- Girişler ----------
export const Rise: React.FC<{
  delay?: number; y?: number; x?: number; scaleFrom?: number; cfg?: keyof typeof T.spring;
  style?: React.CSSProperties; children: React.ReactNode; blur?: boolean;
}> = ({delay = 0, y = 40, x = 0, scaleFrom = 0.94, cfg = 'smooth', style, children, blur}) => {
  const p = useSpring(delay, cfg);
  return (
    <div
      style={{
        opacity: interpolate(p, [0, 0.6], [0, 1], clamp),
        transform: `translate(${interpolate(p, [0, 1], [x, 0])}px, ${interpolate(p, [0, 1], [y, 0])}px) scale(${interpolate(p, [0, 1], [scaleFrom, 1])})`,
        filter: blur ? `blur(${interpolate(p, [0, 1], [12, 0], clamp)}px)` : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

// Kelime kelime açılış (maske içinden yukarı kayar).
export const Words: React.FC<{
  text: string; delay?: number; per?: number; size: number; weight?: number; color?: string;
  highlight?: string[]; hl?: string; style?: React.CSSProperties; font?: string; gap?: number; align?: 'left' | 'center';
}> = ({text, delay = 0, per = 3, size, weight = 800, color = T.c.text, highlight = [], hl = T.c.hero, style, font = T.f.display, gap, align = 'left'}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const words = String(text ?? '').split(' ');
  // Plan JSON'unda highlight bazen dizi yerine tek dizge gelebiliyor — ikisini de kabul et.
  const hlList: string[] = Array.isArray(highlight) ? highlight : highlight ? [String(highlight)] : [];
  return (
    <div
      style={{
        display: 'flex', flexWrap: 'wrap', columnGap: gap ?? size * 0.26, rowGap: size * 0.02,
        justifyContent: align === 'center' ? 'center' : 'flex-start', ...style,
      }}
    >
      {words.map((w, i) => {
        const p = spring({frame: frame - delay - i * per, fps, config: T.spring.snappy});
        const isHl = hlList.some((h) => w.toLocaleLowerCase('tr').startsWith(h.toLocaleLowerCase('tr')));
        return (
          <span key={i} style={{display: 'inline-block', overflow: 'hidden', paddingBottom: size * 0.08, marginBottom: -size * 0.08}}>
            <span
              style={{
                display: 'inline-block', fontFamily: font, fontSize: size, fontWeight: weight,
                letterSpacing: '-0.035em', lineHeight: 1.04, color: isHl ? hl : color,
                transform: `translateY(${interpolate(p, [0, 1], [size * 1.05, 0])}px) rotate(${interpolate(p, [0, 1], [6, 0])}deg)`,
                opacity: interpolate(p, [0, 0.3], [0, 1], clamp),
                textShadow: isHl ? `0 0 40px ${T.c.heroGlow}` : undefined,
              }}
            >
              {w}
            </span>
          </span>
        );
      })}
    </div>
  );
};

// Animasyonlu sayaç (tabular-nums).
export const Counter: React.FC<{
  to: number; from?: number; delay?: number; dec?: number; prefix?: string; suffix?: string;
  size: number; color?: string; weight?: number; font?: string; style?: React.CSSProperties; cfg?: keyof typeof T.spring; placeholder?: boolean;
  maxW?: number; // son değerin genişliği bunu aşarsa yazı küçülür (kartı taşan rakam)
}> = ({to, from = 0, delay = 0, dec = 0, prefix = '', suffix = '', size: size0, color = T.c.text, weight = 800, font = T.f.display, style, cfg = 'count', placeholder, maxW}) => {
  const size = maxW ? fitSize(prefix + fmtTR(Math.max(Math.abs(to), Math.abs(from)), dec) + suffix, size0, maxW, font, weight) : size0;
  const p = useSpring(delay, cfg);
  const frame = useCurrentFrame();
  if (placeholder && frame < delay - 1) {
    return <span style={{fontFamily: font, fontSize: size, fontWeight: weight, color: T.c.faint, lineHeight: 1, ...style}}>—</span>;
  }
  const v = interpolate(p, [0, 1], [from, to]);
  return (
    <span
      style={{
        fontFamily: font, fontSize: size, fontWeight: weight, color, letterSpacing: '-0.04em',
        fontVariantNumeric: 'tabular-nums', lineHeight: 1, ...style,
      }}
    >
      {prefix}
      {fmtTR(v, dec)}
      {suffix}
    </span>
  );
};

// Tek satır metnin kutuya sığan en büyük punto (en fazla `size`). Harf aralığı -0.04em olduğu için %4 pay.
export const fitSize = (text: string, size: number, maxW: number, font: string = T.f.display, weight: number | string = 800) => {
  try {
    const {fontSize} = fitText({text, withinWidth: maxW * 1.04, fontFamily: font, fontWeight: String(weight)});
    return Math.min(size, fontSize);
  } catch {
    return size;
  }
};

// Kutuya sığdır: içerik maxW'den genişse orantılı küçültür (taşan rakam/başlık — QA'da en sık görülen kırık kare).
// Ölçüm fontlar yüklendikten sonra yapılır; render bekletilir (delayRender) ki ilk karede de doğru boyut çıksın.
export const Fit: React.FC<{maxW: number; children: React.ReactNode; align?: 'left' | 'center' | 'right'; style?: React.CSSProperties}> = ({
  maxW, children, align = 'left', style,
}) => {
  const ref = React.useRef<HTMLDivElement>(null);
  const [k, setK] = React.useState(1);
  const [handle] = React.useState(() => delayRender('Fit ölçümü'));
  React.useLayoutEffect(() => {
    let done = false;
    const measure = () => {
      if (done) return;
      done = true;
      const w = ref.current?.scrollWidth ?? 0;
      if (w > maxW) setK(maxW / w);
      continueRender(handle);
    };
    (document as any).fonts?.ready ? (document as any).fonts.ready.then(measure) : measure();
    return () => { if (!done) { done = true; continueRender(handle); } };
  }, [maxW, handle]);
  return (
    <div style={{width: k < 1 ? maxW : undefined, maxWidth: maxW, display: 'flex', justifyContent: align === 'center' ? 'center' : align === 'right' ? 'flex-end' : 'flex-start', ...style}}>
      <div ref={ref} style={{display: 'inline-block', whiteSpace: 'nowrap', transform: `scale(${k})`, transformOrigin: align === 'center' ? '50% 50%' : align === 'right' ? '100% 50%' : '0% 50%'}}>
        {children}
      </div>
    </div>
  );
};

// Küçük etiket (mono, büyük harf, izli).
export const Label: React.FC<{children: React.ReactNode; color?: string; size?: number; style?: React.CSSProperties}> = ({
  children, color = T.c.dim, size = 22, style,
}) => (
  <div
    style={{
      fontFamily: T.f.mono, fontSize: size, fontWeight: 500, letterSpacing: '0.18em', textTransform: 'uppercase',
      color, ...style,
    }}
  >
    {children}
  </div>
);

// Cam panel kartı.
export const Panel: React.FC<{style?: React.CSSProperties; children: React.ReactNode; glow?: string}> = ({style, children, glow}) => (
  <div
    style={{
      background: 'linear-gradient(160deg, rgba(255,255,255,0.06), rgba(255,255,255,0.015))',
      border: `1px solid ${T.c.line}`, borderRadius: 28,
      boxShadow: glow ? `0 0 0 1px ${glow}55, 0 30px 80px -30px rgba(0,0,0,0.8), 0 0 80px -20px ${glow}55` : '0 30px 80px -30px rgba(0,0,0,0.8)',
      ...style,
    }}
  >
    {children}
  </div>
);

// Nefes alan boşta hareket.
export const useBreath = (speed = 24, amp = 0.012) => {
  const f = useCurrentFrame();
  return 1 + Math.sin(f / speed) * amp;
};
export const useFloat = (speed = 32, amp = 4, phase = 0) => {
  const f = useCurrentFrame();
  return Math.sin(f / speed + phase) * amp;
};

// Çizgi çekme (SVG olmayan yatay hat).
export const DrawLine: React.FC<{delay?: number; width: number; color?: string; thickness?: number; style?: React.CSSProperties; dur?: number}> = ({
  delay = 0, width, color = T.c.line, thickness = 2, style, dur = 24,
}) => {
  const f = useCurrentFrame();
  const w = ease(f, delay, delay + dur, 0, width, T.ease.inOut);
  return <div style={{width: w, height: thickness, background: color, borderRadius: thickness, ...style}} />;
};
