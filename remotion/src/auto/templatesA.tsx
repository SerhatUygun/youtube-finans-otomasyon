// Şablonlar A: giriş, başlık, istatistik, gösterge, nokta ızgarası, sebep kartları, alıntı, damga.
// Her şablon props'u plan JSON'undan alır; zaman tetikleri "cue" dizgeleridir (bkz. core/timing).
import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {T, fmtTR} from '../core/theme';
import {BgMesh, Counter, DrawLine, Label, Panel, Rise, Words, clamp, ease, fitSize, useBreath, useFloat, useSpring} from '../core/kit';
import {DotGrid, Gauge} from '../core/charts';
import {Stage, useCue} from '../core/timing';
import {P, col} from './data';
import {BrandLockup} from '../core/brand';

export const useV = () => useCue().layout === 'v';
// Sayı/metin genişliğe sığsın: yaklaşık karakter genişliği 0,58em
export const fitNum = (s: string, base: number, width: number) => Math.min(base, Math.floor(width / Math.max(String(s).length * 0.58, 1)));

// ---------- Marka kıvılcımı ----------
export const Spark: React.FC<{size: number; delay?: number}> = ({size, delay = 0}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const wrap = spring({frame: frame - delay, fps, config: T.spring.bouncy});
  const rot = interpolate(spring({frame: frame - delay, fps, config: T.spring.smooth}), [0, 1], [-120, 0]);
  return (
    <div style={{width: size, height: size, position: 'relative', transform: `scale(${wrap}) rotate(${rot + frame * 0.15}deg)`,
      filter: `drop-shadow(0 0 ${size * 0.2}px ${T.c.heroGlow})`}}>
      {Array.from({length: 12}).map((_, i) => {
        const p = spring({frame: frame - delay - i * 1.2, fps, config: T.spring.snappy});
        return <div key={i} style={{position: 'absolute', left: '50%', top: '50%', width: size * 0.075, height: size * (i % 3 === 0 ? 0.46 : 0.32) * p,
          background: T.c.hero, borderRadius: size, transformOrigin: '50% 0%', transform: `translateX(-50%) rotate(${30 * i}deg) translateY(${size * 0.08}px)`}} />;
      })}
    </div>
  );
};

// Bölüm etiketi (ör. "01 · Fed tonu") — her şablonda opsiyonel `tag` prop'u
export const Tag: React.FC<{tag?: P; cue?: number}> = ({tag, cue = 0}) => {
  if (!tag) return null;
  const c = col(tag.color, T.c.accent);
  return (
    <Rise delay={cue} x={-40} y={0} style={{position: 'absolute', top: 0, left: 0, display: 'flex', alignItems: 'center', gap: 20}}>
      {tag.n ? <div style={{fontFamily: T.f.mono, fontSize: 32, fontWeight: 800, color: T.c.bg, background: c, borderRadius: 12, padding: '6px 16px'}}>{tag.n}</div> : null}
      <div style={{fontFamily: T.f.display, fontSize: 38, fontWeight: 800, color: T.c.text}}>{tag.title}</div>
      {tag.of ? (
        <div style={{display: 'flex', gap: 8, marginLeft: 12}}>
          {Array.from({length: tag.of}).map((_, i) => (
            <div key={i} style={{width: i + 1 === Number(tag.n) ? 40 : 12, height: 12, borderRadius: 6, background: i + 1 <= Number(tag.n) ? c : T.c.faint}} />
          ))}
        </div>
      ) : null}
    </Rise>
  );
};

// ---------- Intro ----------
export const Intro: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const burst = ease(f, 6, 40, 0, 1);
  const lt = useSpring(at(p.presenterCue, 60), 'smooth');
  return (
    <AbsoluteFill>
      <BgMesh grid={false} />
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', opacity: 1 - burst * 0.6}}>
        {Array.from({length: 24}).map((_, i) => (
          <div key={i} style={{position: 'absolute', width: 2, height: 1100 * burst, opacity: 0.5, transform: `rotate(${i * 15 + f * 0.2}deg)`,
            background: `linear-gradient(180deg, ${T.c.hero}00, ${T.c.hero}55, ${T.c.hero}00)`}} />
        ))}
      </AbsoluteFill>
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', transform: `translateY(${V ? -120 : -70 * ease(f, 60, 80, 0, 1)}px)`}}>
        {/* kurumsal kilit: amblem + FİNANS / KANALI + bayrak (eski kıvılcım + düz yazı yerine) */}
        <BrandLockup size={V ? 300 : 280} delay={4} vertical={V} />
        {p.subtitle ? <Rise delay={52} y={20}><Label size={V ? 24 : 26} style={{marginTop: 18, textAlign: 'center'}}>{p.subtitle}</Label></Rise> : null}
      </AbsoluteFill>
      {p.presenter ? (
        <div style={{position: 'absolute', left: V ? 80 : 140, bottom: V ? 620 : 250, opacity: lt, transform: `translateX(${interpolate(lt, [0, 1], [-60, 0])}px)`}}>
          <div style={{display: 'flex', alignItems: 'stretch', gap: 22}}>
            <div style={{width: 8, background: T.c.accent, borderRadius: 4}} />
            <div>
              <div style={{fontFamily: T.f.display, fontWeight: 800, fontSize: 56, color: T.c.text}}>{p.presenter}</div>
              <Label size={22}>{p.presenterRole ?? 'Finans Kanalı · piyasa değerlendirmesi'}</Label>
            </div>
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

// ---------- KineticTitle: büyük kelime-kelime başlık ----------
export const KineticTitle: React.FC<{p: P}> = ({p}) => {
  const {at} = useCue();
  const V = useV();
  const size = p.size ?? (V ? 118 : 150); // 9 Eki: dikeyde 130 kenarlara ~65 px kalıyordu
  return (
    <AbsoluteFill>
      <BgMesh tint={col(p.tint, T.c.hero)} />
      <Stage>
        <Tag tag={p.tag} cue={at(p.cue)} />
        <div style={{display: 'flex', flexDirection: 'column', alignItems: p.align === 'left' ? 'flex-start' : 'center', alignSelf: p.align === 'left' ? 'flex-start' : 'center', maxWidth: V ? 940 : 1500}}>
          {p.kicker ? <Rise delay={at(p.cue)} y={20}><Label size={26} color={T.c.accent}>{p.kicker}</Label></Rise> : null}
          <Words text={p.text} delay={at(p.cue) + 6} size={size} highlight={p.highlight ?? []} hl={col(p.hl, T.c.hero)} align={p.align === 'left' ? 'left' : 'center'} style={{marginTop: 16}} />
          {p.sub ? <Rise delay={at(p.subCue ?? p.cue) + 24}><div style={{fontFamily: T.f.display, fontSize: V ? 44 : 52, color: T.c.dim, fontWeight: 500, marginTop: 26,
            textAlign: p.align === 'left' ? 'left' : 'center', maxWidth: V ? 900 : 1200}}>{p.sub}</div></Rise> : null}
        </div>
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Stamp: büyük vuruş (+25 baz puan gibi) + damga ----------
export const Stamp: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const slam = spring({frame: f - at(p.bigCue ?? p.cue), fps, config: T.spring.bouncy});
  const st = spring({frame: f - at(p.stampCue ?? p.cue, 1e6), fps, config: {damping: 9, stiffness: 220, mass: 0.8}});
  const c = col(p.color, T.c.hawk);
  const shake = st > 0.05 && st < 0.98 ? Math.sin(f * 3) * (1 - st) * 10 : 0;
  return (
    <AbsoluteFill style={{transform: `translate(${shake}px, ${shake * 0.6}px)`}}>
      <BgMesh tint={c} />
      {p.watermark ? (
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', transform: `translateX(${interpolate(f, [0, 200], [60, -60], {...clamp, easing: T.ease.soft})}px)`}}>
          <div style={{fontFamily: T.f.display, fontWeight: 900, fontSize: V ? 360 : 600, color: 'transparent', WebkitTextStroke: `2px ${T.c.line}`}}>{p.watermark}</div>
        </AbsoluteFill>
      ) : null}
      <Stage>
        <Tag tag={p.tag} cue={at(p.cue)} />
        {p.kicker ? <Rise delay={at(p.cue)} y={20}><Label size={28} color={T.c.accent}>{p.kicker}</Label></Rise> : null}
        {(() => {
          // 30 Eyl QA (2 videoda): bigCue geç geliyorsa sahne boş kalıyordu -> rakamın silik dış çizgisi (hayalet) bekler,
          // cue'da dolu rakam üstüne 'slam' eder. Punto genişliğe sığar.
          const fs = fitSize(String(p.big ?? ''), V ? 260 : 300, V ? 900 : 1400 - (p.unit ? 260 : 0), T.f.display, 900);
          const ghost = at(p.bigCue ?? p.cue) - at(p.cue) > 20 ? ease(f, at(p.cue), at(p.cue) + 12, 0, 1) * (1 - interpolate(slam, [0, 0.3], [0, 1], clamp)) : 0;
          const row = (style: React.CSSProperties, fill: boolean) => (
            <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', alignItems: V ? 'center' : 'baseline', gap: V ? 0 : 30, ...style}}>
              <span style={{fontFamily: T.f.display, fontWeight: 900, fontSize: fs, letterSpacing: '-0.06em', ...(fill
                ? {color: c, textShadow: `0 0 80px ${c}66`} : {color: 'transparent', WebkitTextStroke: `2px ${c}88`})}}>{p.big}</span>
              {p.unit ? <span style={{fontFamily: T.f.display, fontWeight: 700, fontSize: V ? 70 : 80, color: fill ? T.c.text : 'transparent', WebkitTextStroke: fill ? undefined : `1px ${T.c.dim}`}}>{p.unit}</span> : null}
            </div>
          );
          // rakam oturduktan sonra üzerinden geçen ince ışık süpürmesi (premium parıltı)
          const tb = at(p.bigCue ?? p.cue);
          const gx = ease(f, tb + 14, tb + 34, -30, 130, T.ease.inOut);
          return (
            <div style={{position: 'relative', marginTop: 10}}>
              {ghost > 0.01 ? <div style={{position: 'absolute', inset: 0, opacity: ghost * 0.6}}>{row({}, false)}</div> : null}
              {row({transform: `scale(${interpolate(slam, [0, 1], [2.2, 1])})`, opacity: interpolate(slam, [0, 0.2], [0, 1], clamp)}, true)}
              {f > tb + 12 && f < tb + 36 ? (
                <div style={{position: 'absolute', inset: '-10px -20px', overflow: 'hidden', pointerEvents: 'none', mixBlendMode: 'overlay'}}>
                  <div style={{position: 'absolute', top: -40, bottom: -40, width: '18%', left: `${gx}%`, transform: 'skewX(-18deg)',
                    background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)'}} />
                </div>
              ) : null}
            </div>
          );
        })()}
        {p.label ? <Rise delay={at(p.labelCue ?? p.bigCue ?? p.cue) + 8} y={20}><Label size={28} color={T.c.dim} style={{marginTop: 8, textAlign: 'center'}}>{p.label}</Label></Rise> : null}
        {p.sub ? <Rise delay={at(p.subCue ?? p.bigCue ?? p.cue) + 12} y={20}><div style={{fontFamily: T.f.mono, fontSize: V ? 36 : 40, color: T.c.text, marginTop: 14, textAlign: 'center'}}>{p.sub}</div></Rise> : null}
        {p.stamp ? (
          <div style={{position: 'absolute', right: V ? 20 : 40, top: V ? -40 : 40, padding: '20px 34px', border: `6px solid ${T.c.hero}`, borderRadius: 16,
            transform: `rotate(-8deg) scale(${interpolate(st, [0, 1], [3, 1])})`, opacity: interpolate(st, [0, 0.15], [0, 1], clamp), color: T.c.hero,
            fontFamily: T.f.display, fontWeight: 900, fontSize: V ? 40 : 46, textAlign: 'center', lineHeight: 1.05, boxShadow: `0 0 50px ${T.c.heroGlow}`,
            whiteSpace: 'pre-line', maxWidth: V ? 520 : 600}}>
            {p.stamp}
          </div>
        ) : null}
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- StatCards: 1-4 büyük sayı kartı ----------
export const StatCards: React.FC<{p: P}> = ({p}) => {
  const {at} = useCue();
  const V = useV();
  const items: P[] = p.items ?? [];
  const n = items.length;
  const w = V ? 900 : Math.min(760, (1600 - (n - 1) * 40) / n);
  return (
    <AbsoluteFill>
      <BgMesh tint={col(p.tint, T.c.accent)} />
      <Stage>
        <Tag tag={p.tag} cue={at(p.cue)} />
        {p.title ? <Words text={p.title} delay={at(p.cue)} size={V ? 72 : 80} align="center" style={{marginBottom: 50}} /> : null}
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', gap: V ? 30 : 40}}>
          {items.map((it, i) => (
            <Rise key={i} delay={Math.min(at(it.cue ?? p.cue), at(p.cue) + i * 6)} y={60}>
              <Panel glow={it.glow ? col(it.color) : undefined} style={{width: w, padding: V ? 36 : 44, position: 'relative'}}>
                <Label size={V ? 30 : 20}>{it.label}</Label>
                {it.title ? <div style={{fontFamily: T.f.display, fontWeight: 800, fontSize: 40, color: T.c.text, marginTop: 8}}>{it.title}</div> : null}
                <Counter to={Number(it.value)} from={it.from !== undefined ? Number(it.from) : 0} dec={it.dec ?? 0} prefix={it.prefix ?? ''} suffix={it.suffix ?? ''} placeholder
                  delay={at(it.cue ?? p.cue) + 4} size={it.size ?? fitNum(`${it.prefix ?? ''}${it.value}${it.suffix ?? ''}`, V ? (n > 1 ? 150 : 200) : n > 2 ? 110 : 150, w - 90)} maxW={w - 90} weight={900} color={col(it.color, T.c.text)} style={{display: 'block', marginTop: 14}} />
                {it.note ? <Label size={18} color={col(it.noteColor, T.c.dim)} style={{marginTop: 14}}>{it.note}</Label> : null}
                {it.badge ? (
                  <Rise delay={at(it.badgeCue ?? it.cue ?? p.cue) + 6} scaleFrom={1.6} cfg="bouncy" style={{position: 'absolute', right: -16, top: -22}}>
                    <div style={{fontFamily: T.f.mono, fontSize: 22, fontWeight: 800, color: T.c.bg, background: col(it.badgeColor, T.c.hawk), padding: '8px 16px',
                      borderRadius: 8, transform: 'rotate(4deg)'}}>{it.badge}</div>
                  </Rise>
                ) : null}
              </Panel>
            </Rise>
          ))}
        </div>
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- GaugeScene: 1 ya da 2 gösterge ----------
export const GaugeScene: React.FC<{p: P}> = ({p}) => {
  const {at} = useCue();
  const V = useV();
  const g: P[] = p.gauges ?? [{value: p.value, label: p.label, cue: p.valueCue, color: p.color}];
  const breath = useBreath(26, 0.01);
  const size = g.length > 1 ? (V ? 560 : 480) : V ? 720 : 620;
  return (
    <AbsoluteFill>
      <BgMesh tint={col(g[0].color, T.c.hero)} />
      <Stage>
        <Tag tag={p.tag} cue={at(p.cue)} />
        {p.kicker ? <Rise delay={at(p.cue)}><Label size={24} color={T.c.accent} style={{marginBottom: 30, textAlign: 'center'}}>{p.kicker}</Label></Rise> : null}
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', gap: V ? 20 : 110, alignItems: 'center', transform: `scale(${breath})`}}>
          {g.map((x, i) => (
            <Gauge key={i} value={Number(x.value)} dec={x.dec ?? 0} delay={at(x.cue ?? p.cue) + 2} appearAt={at(p.cue) + i * 6} size={size} color={col(x.color, T.c.hero)} label={x.label} />
          ))}
          {p.side ? (
            <div style={{width: V ? 900 : 560}}>
              <Words text={p.side.title} delay={at(p.cue) + 6} size={V ? 64 : 76} />
              {(p.side.rows ?? []).map((r: P, i: number) => (
                <Rise key={i} delay={at(r.cue ?? p.cue) + 20 + i * 6} x={-30} y={0}>
                  <div style={{display: 'flex', justifyContent: 'space-between', borderBottom: `1px solid ${T.c.line}`, padding: '14px 0'}}>
                    <span style={{fontFamily: T.f.display, fontSize: 34, color: T.c.dim}}>{r.k}</span>
                    <span style={{fontFamily: T.f.mono, fontSize: 40, fontWeight: 800, color: col(r.color, T.c.text)}}>{r.v}</span>
                  </div>
                </Rise>
              ))}
              {p.side.source ? <Label size={18} style={{marginTop: 14}}>{p.side.source}</Label> : null}
            </div>
          ) : null}
        </div>
        {p.footer ? (
          <Rise delay={at(p.footerCue ?? p.cue) + 10} y={30} style={{marginTop: 40}}>
            <Panel style={{padding: '18px 34px'}}><span style={{fontFamily: T.f.display, fontWeight: 800, fontSize: 40, color: T.c.text}}>{p.footer}</span></Panel>
          </Rise>
        ) : null}
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- DotScene: n içinden k (ör. 16/18 üye, 12-0 oy) ----------
export const DotScene: React.FC<{p: P}> = ({p}) => {
  const {at} = useCue();
  const V = useV();
  const c = col(p.color, T.c.hero);
  return (
    <AbsoluteFill>
      <BgMesh tint={c} />
      <Stage>
        <Tag tag={p.tag} cue={at(p.cue)} />
        {p.kicker ? <Rise delay={at(p.cue)}><Label size={26} color={T.c.accent}>{p.kicker}</Label></Rise> : null}
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', alignItems: 'center', gap: V ? 40 : 90, marginTop: 40}}>
          <div style={{display: 'flex', alignItems: 'baseline', gap: 16}}>
            <Counter to={Number(p.lit)} delay={at(p.litCue ?? p.cue)} size={V ? 220 : 260} weight={900} color={c} style={{textShadow: `0 0 60px ${c}66`}} />
            <span style={{fontFamily: T.f.display, fontSize: V ? 90 : 110, fontWeight: 300, color: T.c.dim}}>/ {p.n}</span>
          </div>
          <DotGrid n={Number(p.n)} lit={Number(p.lit)} cols={p.cols ?? Math.ceil(Math.sqrt(p.n * 2))} delay={at(p.cue) + 6} litDelay={at(p.litCue ?? p.cue) + 6}
            size={p.n > 30 ? 36 : 64} gap={p.n > 30 ? 12 : 18} color={c} />
        </div>
        {p.caption ? <Rise delay={at(p.captionCue ?? p.litCue ?? p.cue) + 10}><div style={{fontFamily: T.f.display, fontSize: V ? 46 : 52, fontWeight: 600, color: T.c.text,
          marginTop: 50, textAlign: 'center'}}>{p.caption}</div></Rise> : null}
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- ReasonCards: numaralı 2-5 kart ----------
const FloatCard: React.FC<{i: number; children: React.ReactNode}> = ({i, children}) => {
  const y = useFloat(30, 6, i * 1.3);
  return <div style={{transform: `translateY(${y}px)`}}>{children}</div>;
};
export const ReasonCards: React.FC<{p: P}> = ({p}) => {
  const {at} = useCue();
  const V = useV();
  const items: P[] = p.items ?? [];
  const w = V ? 900 : Math.min(420, (1640 - (items.length - 1) * 30) / items.length);
  return (
    <AbsoluteFill>
      <BgMesh />
      <Stage>
        {p.title ? <Words text={p.title} delay={at(p.cue)} size={V ? 76 : 92} align="center" highlight={p.highlight ?? []} /> : null}
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', gap: V ? 22 : 30, marginTop: V ? 50 : 70}}>
          {items.map((r, i) => (
            <Rise key={i} delay={at(p.cardsCue ?? p.cue) + i * 5} y={90}>
              <FloatCard i={i}>
                <Panel style={{width: w, height: V ? 190 : 300, padding: V ? 28 : 34, display: 'flex', flexDirection: 'column', justifyContent: 'space-between'}}>
                  <div style={{fontFamily: T.f.mono, fontSize: 30, fontWeight: 800, color: col(r.color)}}>{r.n ?? String(i + 1).padStart(2, '0')}</div>
                  <div>
                    <div style={{fontFamily: T.f.display, fontSize: V ? 50 : 54, fontWeight: 800, color: T.c.text, letterSpacing: '-0.03em'}}>{r.title}</div>
                    {r.sub ? <div style={{fontFamily: T.f.display, fontSize: 26, color: T.c.dim, marginTop: 8}}>{r.sub}</div> : null}
                  </div>
                  <DrawLine delay={at(p.cardsCue ?? p.cue) + i * 5 + 10} width={w - 70} color={col(r.color)} thickness={4} />
                </Panel>
              </FloatCard>
            </Rise>
          ))}
        </div>
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Quote: kaynaklı alıntı (daktilo) ----------
export const Quote: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {at} = useCue();
  const V = useV();
  const q: string = p.text ?? '';
  const s0 = at(p.cue);
  const s1 = Math.max(at(p.endCue ?? p.cue) , s0 + 30);
  const chars = Math.floor(ease(f, s0, s1, 0, q.length, T.ease.soft));
  const c = col(p.color, T.c.hawk);
  return (
    <AbsoluteFill>
      <BgMesh tint={c} />
      <Stage>
        <Tag tag={p.tag} cue={at(p.tagCue ?? p.cue) - 10} />
        {/* 30 Eyl QA: alıntı cue'su geç gelince ekran boş kalıyordu -> kişi kartı sahne başında (en geç 6. karede) gelir */}
        <Rise delay={Math.min(s0 - 20, 6)}>
          <div style={{display: 'flex', alignItems: 'center', gap: 26}}>
            <div style={{width: 110, height: 110, borderRadius: '50%', border: `3px solid ${c}`, display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: T.f.display, fontWeight: 900, fontSize: 44, color: T.c.text, background: `${c}1a`}}>{p.initials}</div>
            <div>
              <div style={{fontFamily: T.f.display, fontWeight: 800, fontSize: 60, color: T.c.text}}>{p.who}</div>
              <Label size={22}>{p.role}</Label>
            </div>
          </div>
        </Rise>
        <div style={{position: 'relative', marginTop: 50, width: V ? 920 : 1400, maxWidth: V ? 920 : 1400, textAlign: 'center'}}>
          <span style={{position: 'absolute', left: -60, top: -60, fontFamily: T.f.serif, fontSize: 200, color: c, opacity: 0.6}}>“</span>
          <div style={{fontFamily: T.f.serif, fontStyle: 'italic', fontSize: V ? 76 : 88, color: T.c.text, lineHeight: 1.12, minHeight: 200, position: 'relative'}}>
            {/* yazılmadan önce alıntının silik önizlemesi (boş ekran yerine) */}
            {/* yazılan ve yazılmamış kısım AYNI akışta: silik önizleme ile hizası birebir (ayrı katman kayıyordu) */}
            <span>{q.slice(0, chars)}</span><span style={{opacity: Math.sin(f / 4) > 0 && chars < q.length ? 1 : 0, color: c}}>|</span>
            <span style={{opacity: 0.1 * ease(f, 0, 12, 0, 1)}}>{q.slice(chars)}</span>
          </div>
        </div>
        {p.note ? <Rise delay={at(p.noteCue ?? p.endCue ?? p.cue) + 6} y={40} style={{marginTop: 40}}>
          <Panel glow={T.c.hero} style={{padding: '22px 36px'}}><span style={{fontFamily: T.f.display, fontWeight: 800, fontSize: 44, color: T.c.text}}>{p.note}</span></Panel>
        </Rise> : null}
      </Stage>
    </AbsoluteFill>
  );
};

export {fmtTR};
