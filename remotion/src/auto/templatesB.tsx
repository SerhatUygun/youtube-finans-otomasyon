// Şablonlar B: grafikler (canlı seri), karşılaştırma, hedef merdiveni, senaryo, aralık, meclis,
// çubuklar, oynaklık, takvim, madalyon, halat, varlık kartları, bölüm kartı, uyarı, anket, kapanış.
import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {T, fmtTR} from '../core/theme';
import {BgMesh, Counter, DrawLine, Label, Panel, Rise, Words, clamp, ease, fitSize, useBreath, useFloat, useSpring} from '../core/kit';
import {HBar, Hemicycle, LineChart} from '../core/charts';
import {Stage, useCue} from '../core/timing';
import {P, col, shortDate, useSeries} from './data';
import {Spark, Tag, useV} from './templatesA';
import {BrandLockup} from '../core/brand';

const last = (a: number[]) => a[a.length - 1];

// ---------- ChartScene: canlı seri çizgi grafiği ----------
export const ChartScene: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {at} = useCue();
  const V = useV();
  const s = useSeries(p.symbol, {since: p.since, last: p.last});
  const sym = String(p.symbol ?? '');
  const auto = /^(GC|XAU|GAU)/.test(sym) ? 'gold' : /^(SI|XAG)/.test(sym) ? 'silver' : /^(BTC|ETH)/.test(sym) ? 'btc' : /^(BZ|CL|BRENT|WTI)/.test(sym) ? 'oil' : 'accent';
  const c = col(p.color ?? auto, T.c.accent);
  if (!s) return <FallbackTitle p={p} />;
  const hv = (p.hlines ?? []).map((h: P) => Number(h.value));
  const dmin = Math.min(...s.c, ...hv);
  const dmax = Math.max(...s.c, ...hv);
  const pad = (dmax - dmin) * 0.06;
  const lo = Math.min(p.min ?? Infinity, dmin - pad);
  const hi = Math.max(p.max ?? -Infinity, dmax + pad);
  const idx = (m: P) => {
    if (m.at === 'max') return s.c.indexOf(Math.max(...s.c));
    if (m.at === 'min') return s.c.indexOf(Math.min(...s.c));
    if (m.at === 'last' || m.at === undefined) return s.c.length - 1;
    const i = s.d.findIndex((d) => d >= m.at);
    return i < 0 ? s.c.length - 1 : i;
  };
  const dec = p.dec ?? (last(s.c) < 20 ? 2 : 0);
  const fmtV = (v: number) => `${p.prefix ?? ''}${fmtTR(v, dec)}${p.suffix ?? ''}`;
  const badgeO = p.badge ? ease(f, at(p.badge.cue ?? p.cue), at(p.badge.cue ?? p.cue) + 18, 0, 1) : 0;
  const W = V ? 940 : 1640;
  return (
    <AbsoluteFill>
      <BgMesh tint={c} />
      <Stage>
        <Tag tag={p.tag} cue={at(p.cue)} />
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', alignItems: V ? 'flex-start' : 'flex-end', gap: V ? 10 : 50, alignSelf: 'flex-start', marginTop: p.tag ? 60 : 0}}>
          <Rise delay={at(p.cue)} y={30}>
            <Label size={22}>{p.title}</Label>
            {p.showPrice === false ? null : (
              <Counter to={last(s.c)} from={p.priceFrom ?? s.c[0]} dec={dec} prefix={p.prefix ?? ''} suffix={p.suffix ?? ''} delay={at(p.cue) + 4} size={V ? 120 : 120} weight={900} />
            )}
          </Rise>
          {p.change ? <Rise delay={at(p.change.cue ?? p.cue) + 6} y={20}>
            <div style={{fontFamily: T.f.mono, fontSize: 38, fontWeight: 800, color: col(p.change.color, T.c.down), paddingBottom: 16}}>{p.change.text}</div>
          </Rise> : null}
        </div>
        <div style={{marginTop: 26, position: 'relative'}}>
          <LineChart data={s.c} labels={s.d.map(shortDate)} w={W} h={V ? 620 : p.tag ? 360 : 400} color={c} delay={at(p.cue) + 8} dur={p.dur ?? 70}
            min={lo} max={hi} dec={dec} prefix={p.prefix ?? ''} suffix={p.suffix ?? ''} showHead={p.head !== false}
            hlines={(p.hlines ?? []).map((h: P) => ({value: Number(h.value), label: h.label ?? fmtV(Number(h.value)), color: col(h.color, T.c.hawk), delay: at(h.cue ?? p.cue) + 20, dashed: h.dashed}))}
            // 30 Eyl QA: uç etiketi (head) açıkken son-fiyat işareti aynı değeri ikinci kez yazıyordu -> atla
            markers={(p.markers ?? []).filter((m: P) => !(p.head !== false && (m.at === 'last' || m.at === undefined) && !m.label)).map((m: P) => {
              const i = idx(m);
              return {index: i, label: (m.label ?? fmtV(s.c[i])).replace('{v}', fmtV(s.c[i])), color: col(m.color, T.c.text), delay: at(m.cue ?? p.cue) + 30, above: m.above !== false};
            })}
            band={(p.bands ?? []).map((b: P) => ({from: Number(b.from), to: Number(b.to), color: col(b.color, T.c.down), delay: at(b.cue ?? p.cue) + 20, label: b.label}))} />
          {p.badge ? (
            <div style={{position: 'absolute', right: V ? 10 : 30, top: V ? -40 : 30, opacity: badgeO, transform: `scale(${0.85 + 0.15 * badgeO})`}}>
              <Panel glow={col(p.badge.color, T.c.down)} style={{padding: '20px 30px'}}>
                <div style={{fontFamily: T.f.display, fontWeight: 900, fontSize: 68, color: col(p.badge.color, T.c.down)}}>{p.badge.text}</div>
                {p.badge.sub ? <Label size={18}>{p.badge.sub}</Label> : null}
              </Panel>
            </div>
          ) : null}
        </div>
      </Stage>
    </AbsoluteFill>
  );
};

const FallbackTitle: React.FC<{p: P}> = ({p}) => {
  const {at} = useCue();
  return (
    <AbsoluteFill>
      <BgMesh />
      <Stage><Words text={p.title ?? ''} delay={at(p.cue)} size={96} align="center" /></Stage>
    </AbsoluteFill>
  );
};

// ---------- Normalized: birden çok serinin % değişimi (aynı başlangıç = 0) ----------
export const Normalized: React.FC<{p: P}> = ({p}) => {
  const {at} = useCue();
  const V = useV();
  const lines = (p.lines ?? []).map((l: P) => ({l, s: useSeries(l.symbol, {since: p.since})}));
  const ok = lines.filter((x: P) => x.s);
  const norm = ok.map((x: P) => x.s!.c.map((v: number) => (v / x.s!.c[0] - 1) * 100));
  if (!norm.length) return <FallbackTitle p={p} />;
  const lo = Math.min(...norm.flat()) - 2;
  const hi = Math.max(...norm.flat()) + 2;
  return (
    <AbsoluteFill>
      <BgMesh tint={col(ok[0].l.color)} />
      <Stage>
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', alignItems: 'center', gap: V ? 30 : 60}}>
          <div style={{width: V ? 940 : 560}}>
            {p.kicker ? <Rise delay={at(p.cue)}><Label size={22}>{p.kicker}</Label></Rise> : null}
            <Words text={p.title} delay={at(p.cue) + 4} size={V ? 80 : 92} highlight={p.highlight ?? []} hl={col(p.hl, T.c.hero)} style={{marginTop: 16}} />
            <Rise delay={at(p.cue) + 20}>
              <div style={{display: 'flex', gap: 30, marginTop: 30}}>
                {ok.map((x: P) => (
                  <div key={x.l.symbol} style={{display: 'flex', alignItems: 'center', gap: 12}}>
                    <div style={{width: 22, height: 22, borderRadius: '50%', background: col(x.l.color)}} />
                    <span style={{fontFamily: T.f.display, fontSize: 32, fontWeight: 700, color: T.c.text}}>{x.l.label}</span>
                  </div>
                ))}
              </div>
              <Label size={18} style={{marginTop: 14}}>{p.note ?? 'başlangıç = 0 · % değişim'}</Label>
            </Rise>
            {p.stat ? <Rise delay={at(p.stat.cue ?? p.cue) + 10} y={30}>
              <Panel style={{marginTop: 30, padding: '20px 28px', display: 'flex', alignItems: 'baseline', gap: 18}}>
                <span style={{fontFamily: T.f.display, fontWeight: 900, fontSize: 64, color: T.c.text}}>{p.stat.value}</span>
                <Label size={17}>{p.stat.label}</Label>
              </Panel>
            </Rise> : null}
          </div>
          <div style={{position: 'relative', width: V ? 940 : 1040, height: V ? 560 : 520}}>
            {norm.map((d: number[], i: number) => (
              <div key={i} style={{position: 'absolute', inset: 0}}>
                <LineChart data={d} w={V ? 940 : 1040} h={V ? 500 : 460} color={col(ok[i].l.color)} delay={at(p.cue) + 6 + i * 8} dur={70} min={lo} max={hi} dec={1} prefix="%" />
              </div>
            ))}
          </div>
        </div>
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Compare: yatay çubuk karşılaştırması ----------
export const Compare: React.FC<{p: P}> = ({p}) => {
  const {at} = useCue();
  const V = useV();
  const items: P[] = p.items ?? [];
  const max = p.max ?? Math.max(...items.map((x) => Math.abs(Number(x.value)))) * 1.05;
  const big = useSpring(at(p.big?.cue ?? p.cue) + 18, 'bouncy');
  return (
    <AbsoluteFill>
      <BgMesh tint={col(items[0]?.color)} />
      <Stage>
        <Tag tag={p.tag} cue={at(p.cue)} />
        {p.title ? <Rise delay={at(p.cue)} style={{alignSelf: 'flex-start', marginTop: p.tag ? 70 : 0, marginBottom: 30}}><Label size={V ? 32 : 24}>{p.title}</Label></Rise> : null}
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', alignItems: 'center', gap: 70}}>
          <div style={{display: 'flex', flexDirection: 'column', gap: 40}}>
            {items.map((it, i) => (
              <HBar key={i} label={it.label} value={Math.abs(Number(it.value))} max={max} w={V ? 560 : 900} h={V ? 104 : 84} labelSize={V ? 30 : 22} color={col(it.color)}
                delay={at(it.cue ?? p.cue) + (it.cue ? 0 : i * 6)} valueText={it.valueText ?? fmtTR(Number(it.value))} dimBar={!!it.dim} ghostFrom={at(p.cue) + 4 + i * 4} />
            ))}
          </div>
          {p.big ? (() => {
            // 30 Eyl QA bulgusu (2 videoda): uzun metin 300 px daireye sığmıyordu -> uzun metinde panel moduna geç
            const txt = String(p.big.text ?? '');
            const sub = String(p.big.sub ?? '');
            const panel = txt.length > 8 || sub.length > 22;
            const w = panel ? 440 : 300;
            return (
              <div style={{transform: `scale(${big}) rotate(${interpolate(big, [0, 1], [panel ? -8 : -20, panel ? -2 : -6])}deg)`, opacity: interpolate(big, [0, 0.2], [0, 1], clamp)}}>
                <div style={{width: w, minHeight: panel ? 0 : 300, height: panel ? undefined : 300, borderRadius: panel ? 28 : '50%', border: `4px solid ${col(p.big.color)}`,
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: `${col(p.big.color)}14`,
                  padding: panel ? '34px 30px' : 30, boxSizing: 'border-box', textAlign: 'center'}}>
                  <div style={{fontFamily: T.f.display, fontWeight: 900, fontSize: fitSize(txt.length > 14 ? txt.slice(0, Math.ceil(txt.length / 2)) : txt, panel ? 64 : 100, w - 60),
                    color: T.c.text, lineHeight: 1.05, whiteSpace: txt.length > 14 ? 'normal' : 'nowrap'}}>{txt}</div>
                  {sub ? <Label size={panel ? 20 : 18} color={col(p.big.color)} style={{marginTop: 12, letterSpacing: '0.08em', lineHeight: 1.35, whiteSpace: 'normal'}}>{sub}</Label> : null}
                </div>
              </div>
            );
          })() : null}
        </div>
        {p.chips ? (
          <div style={{position: 'absolute', bottom: 0, display: 'flex', flexDirection: V ? 'column' : 'row', gap: 20}}>
            {p.chips.map((c: P, i: number) => (
              <Rise key={i} delay={at(c.cue ?? p.cue) + 10} y={40}>
                <Panel style={{padding: '18px 30px', display: 'flex', alignItems: 'center', gap: 18}}>
                  <span style={{fontFamily: T.f.mono, fontSize: 40, fontWeight: 800, color: col(c.color, T.c.text)}}>{c.value}</span>
                  <Label size={19}>{c.label}</Label>
                </Panel>
              </Rise>
            ))}
          </div>
        ) : null}
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Ladder: hedef fiyat merdiveni ----------
export const Ladder: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const items: P[] = p.items ?? [];
  const vals = items.map((x) => Number(x.value));
  const lo = p.min ?? Math.min(...vals) * 0.95;
  const hi = p.max ?? Math.max(...vals) * 1.03;
  const H = V ? 700 : 560;
  const Y = (v: number) => H - ((v - lo) / (hi - lo)) * H;
  const ref = items.find((x) => x.ref) ?? items[0];
  const ticks = Array.from({length: 5}, (_, i) => lo + ((hi - lo) * i) / 4);
  return (
    <AbsoluteFill>
      <BgMesh tint={col(p.tint, T.c.gold)} />
      <Stage>
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', width: '100%', alignItems: 'center', gap: V ? 40 : 80}}>
          <div style={{width: V ? 940 : 680}}>
            <Words text={p.title} delay={at(p.cue) + 6} size={V ? 76 : 86} highlight={p.highlight ?? []} />
            {p.note ? <Rise delay={at(p.noteCue ?? p.cue) + 10} y={30}><Panel style={{padding: '22px 30px', marginTop: 34}}>
              <Label size={18}>{p.note.label}</Label>
              <div style={{fontFamily: T.f.display, fontWeight: 800, fontSize: 40, color: T.c.text}}>{p.note.text}</div>
            </Panel></Rise> : null}
          </div>
          <div style={{position: 'relative', width: V ? 800 : 820, height: H, marginLeft: 110}}>
            <div style={{position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, background: T.c.line}} />
            {ticks.map((v) => (
              <div key={v} style={{position: 'absolute', left: -110, top: Y(v) - 14, fontFamily: T.f.mono, fontSize: 22, color: T.c.dim, opacity: ease(f, at(p.cue), at(p.cue) + 20, 0, 1)}}>
                {p.prefix ?? ''}{fmtTR(v, p.dec ?? 0)}
              </div>
            ))}
            {items.map((r, i) => {
              const q = spring({frame: f - at(r.cue ?? p.cue) - (r.cue ? 0 : i * 8), fps, config: T.spring.heavy});
              const up = (Number(r.value) / Number(ref.value) - 1) * 100;
              const c = col(r.color, T.c.text);
              return (
                <div key={i} style={{position: 'absolute', left: 0, top: Y(Number(r.value)) - 2, display: 'flex', alignItems: 'center', opacity: interpolate(q, [0, 0.2], [0, 1], clamp)}}>
                  <div style={{width: (V ? 360 : 460) * q, height: 4, background: c}} />
                  <div style={{marginLeft: 20, display: 'flex', alignItems: 'baseline', gap: 14, transform: 'translateY(-50%)', position: 'relative', top: 2, whiteSpace: 'nowrap'}}>
                    <span style={{fontFamily: T.f.display, fontWeight: 800, fontSize: 40, color: c}}>{p.prefix ?? ''}{fmtTR(Number(r.value), p.dec ?? 0)}</span>
                    <span style={{fontFamily: T.f.display, fontSize: 26, color: T.c.dim}}>{r.label}</span>
                    {!r.ref ? <span style={{fontFamily: T.f.mono, fontSize: 22, color: up >= 0 ? T.c.up : T.c.down}}>{up >= 0 ? '+' : '−'}%{fmtTR(Math.abs(up), 1)}</span> : null}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Scenario: iki senaryo (ayı / boğa) ----------
export const Scenario: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const lp = spring({frame: f - at(p.left?.cue ?? p.cue), fps, config: T.spring.smooth});
  const rp = spring({frame: f - at(p.right?.cue ?? p.cue), fps, config: T.spring.smooth});
  const focus = p.focusCue ? ease(f, at(p.focusCue), at(p.focusCue) + 16, 0, 1) : 0;
  const Side = (q: number, d: P, c: string, arrow: string, from: number, dim: number) => (
    <div style={{flex: V ? 'none' : 1, height: V ? 540 : 600, borderRadius: 30, padding: V ? 40 : 50, position: 'relative', overflow: 'hidden',
      background: `linear-gradient(160deg, ${c}26, ${c}08 60%)`, border: `1px solid ${c}66`,
      opacity: interpolate(q, [0, 0.3], [0, 1], clamp) * (1 - dim * 0.55),
      transform: `translate${V ? 'Y' : 'X'}(${interpolate(q, [0, 1], [from, 0])}px) scale(${1 - dim * 0.04})`}}>
      <div style={{position: 'absolute', right: -30, top: -60, fontFamily: T.f.display, fontSize: 420, fontWeight: 900, color: c, opacity: 0.12}}>{arrow}</div>
      <Label size={22} color={c}>{d.label ?? 'Senaryo'}</Label>
      <div style={{fontFamily: T.f.display, fontWeight: 800, fontSize: V ? 52 : 56, color: T.c.text, marginTop: 14, lineHeight: 1.08}}>{d.cond}</div>
      {d.sub ? <div style={{fontFamily: T.f.display, fontSize: 30, color: T.c.dim, marginTop: 14}}>{d.sub}</div> : null}
      <div style={{position: 'absolute', left: V ? 40 : 50, bottom: V ? 40 : 50}}>
        <Label size={20}>{p.asset}</Label>
        <div style={{fontFamily: T.f.display, fontWeight: 900, fontSize: V ? 88 : 96, color: c, letterSpacing: '-0.03em'}}>{d.target}</div>
        {d.tsub ? <div style={{fontFamily: T.f.display, fontSize: 28, color: T.c.text}}>{d.tsub}</div> : null}
      </div>
    </div>
  );
  return (
    <AbsoluteFill>
      <BgMesh tint={col(p.tint, T.c.hero)} />
      <Stage>
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', gap: V ? 30 : 40, width: '100%'}}>
          {/* tone: 'consumer' -> fiyat artışı KÖTÜ (yukarı kart kırmızı), 'investor' (vars.) -> yükseliş iyi (30 Eyl QA) */}
          {Side(lp, p.left ?? {}, p.tone === 'consumer' ? T.c.up : T.c.down, '↓', -120, p.focus === 'right' ? focus : 0)}
          {Side(rp, p.right ?? {}, p.tone === 'consumer' ? T.c.down : T.c.up, '↑', 120, p.focus === 'left' ? focus : 0)}
        </div>
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- RangeBar: hedef aralığı + bugünkü değer ----------
export const RangeBar: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {at} = useCue();
  const V = useV();
  const W = V ? 900 : 1500;
  const lo = Number(p.min);
  const hi = Number(p.max);
  const X = (v: number) => ((v - lo) / (hi - lo)) * W;
  const pins: P[] = p.pins ?? [];
  const pv = pins.map((x) => Number(x.value));
  const a = Math.min(...pv);
  const b = Math.max(...pv);
  const rp = ease(f, at(p.cue) + 4, at(p.cue) + 40, 0, 1, T.ease.inOut);
  return (
    <AbsoluteFill>
      <BgMesh tint={col(p.tint, T.c.silver)} />
      <Stage>
        {p.headline ? <Words text={p.headline} delay={at(p.cue)} size={V ? 70 : 76} align="center" style={{marginBottom: 90}} /> : null}
        <div style={{position: 'relative', width: W, height: 280}}>
          <Rise delay={at(p.cue)}><Label size={22}>{p.title}</Label></Rise>
          <div style={{position: 'absolute', top: 120, left: X(a), width: (X(b) - X(a)) * rp, height: 24, borderRadius: 12,
            background: `linear-gradient(90deg, ${T.c.down}, ${T.c.silver}, ${T.c.up})`}} />
          <div style={{position: 'absolute', top: 131, left: 0, width: W, height: 2, background: T.c.line}} />
          {pins.map((q, i) => {
            const o = ease(f, at(q.cue ?? p.cue) + (q.cue ? 0 : 20 + i * 8), at(q.cue ?? p.cue) + (q.cue ? 14 : 34 + i * 8), 0, 1);
            return (
              <div key={i} style={{position: 'absolute', left: X(Number(q.value)) - 1, top: 60, opacity: o}}>
                <div style={{width: 3, height: 90, background: T.c.text}} />
                <div style={{position: 'absolute', top: 100, left: -130, width: 260, textAlign: 'center'}}>
                  <div style={{fontFamily: T.f.display, fontWeight: 900, fontSize: V ? 38 : 44, color: T.c.text}}>{p.prefix ?? ''}{fmtTR(Number(q.value), p.dec ?? 0)}</div>
                  <Label size={16} style={{whiteSpace: 'nowrap', letterSpacing: '0.1em'}}>{q.label}</Label>
                </div>
              </div>
            );
          })}
          {p.current !== undefined ? (
            <div style={{position: 'absolute', left: X(Number(p.current)) - 14, top: 118, opacity: ease(f, at(p.cue) + 20, at(p.cue) + 30, 0, 1)}}>
              <div style={{width: 28, height: 28, borderRadius: '50%', background: T.c.hero, boxShadow: `0 0 24px ${T.c.heroGlow}`}} />
              <div style={{position: 'absolute', top: -84, left: -100, width: 230, textAlign: 'center', fontFamily: T.f.mono, fontWeight: 800, fontSize: 28, color: T.c.hero}}>
                bugün {p.prefix ?? ''}{fmtTR(Number(p.current), p.dec ?? 0)}
              </div>
            </div>
          ) : null}
        </div>
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Vote: yarım daire meclis oylaması ----------
export const Vote: React.FC<{p: P}> = ({p}) => {
  const {at} = useCue();
  const V = useV();
  return (
    <AbsoluteFill>
      <BgMesh tint={T.c.hawk} tint2={T.c.accent} />
      <Stage>
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', alignItems: 'center', gap: V ? 150 : 80}}>
          <div style={{position: 'relative'}}>
            <Hemicycle yes={Number(p.yes)} no={Number(p.no)} delay={at(p.cue) + 6} w={V ? 860 : 820} yesColor={T.c.up} noColor={T.c.faint} />
            <div style={{position: 'absolute', bottom: -130, width: '100%', textAlign: 'center'}}>
              <Counter to={Number(p.yes)} delay={at(p.cue) + 10} size={120} weight={900} color={T.c.up} />
              <span style={{fontFamily: T.f.display, fontSize: 110, color: T.c.dim}}> – </span>
              <Counter to={Number(p.no)} delay={at(p.cue) + 16} size={120} weight={900} color={T.c.text} />
            </div>
          </div>
          <div style={{width: V ? 900 : 640}}>
            <Rise delay={at(p.cue)}><Label size={22}>{p.kicker}</Label></Rise>
            <Rise delay={at(p.cue) + 6}><div style={{fontFamily: T.f.display, fontWeight: 900, fontSize: 90, color: T.c.text}}>{p.title}</div></Rise>
            {p.stamp ? <Rise delay={at(p.stampCue ?? p.cue) + 10} scaleFrom={1.5} cfg="bouncy">
              <div style={{display: 'inline-block', marginTop: 20, padding: '10px 22px', border: `5px solid ${col(p.stampColor, T.c.down)}`, borderRadius: 12, transform: 'rotate(-4deg)',
                fontFamily: T.f.display, fontWeight: 900, fontSize: 52, color: col(p.stampColor, T.c.down)}}>{p.stamp}</div>
            </Rise> : null}
            {p.sub ? <Rise delay={at(p.stampCue ?? p.cue) + 20}><Label size={20} style={{marginTop: 20}}>{p.sub}</Label></Rise> : null}
          </div>
        </div>
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Bars: dikey çubuklar (ETF girişleri vb.) ----------
export const Bars: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const items: P[] = p.items ?? [];
  const max = Math.max(...items.map((x) => Math.abs(Number(x.value))));
  const H = V ? 520 : 420;
  const c = col(p.color, T.c.up);
  return (
    <AbsoluteFill>
      <BgMesh tint={c} />
      <Stage>
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', alignItems: 'center', gap: V ? 60 : 120}}>
          <div style={{width: V ? 900 : 640}}>
            {p.kicker ? <Rise delay={at(p.cue)}><Label size={22}>{p.kicker}</Label></Rise> : null}
            <Words text={p.title} delay={at(p.cue) + 4} size={V ? 90 : 110} />
            {p.big ? <Rise delay={at(p.big.cue ?? p.cue) + 6}>
              {/* 30 Eyl QA: uzun big yazı çubuklara taşıyordu -> sol sütuna sığdır; renk ayrı ayarlanır (olumsuz bilgi yeşil kalmasın) */}
              <div style={{fontFamily: T.f.display, fontWeight: 900, fontSize: fitSize(String(p.big.text ?? ''), V ? 110 : 100, V ? 760 : 620, T.f.display, 900),
                color: col(p.big.color, c), marginTop: 20, whiteSpace: 'nowrap'}}>{p.big.text}</div>
              <Label size={20}>{p.big.sub}</Label>
            </Rise> : null}
          </div>
          <div style={{display: 'flex', gap: 40, alignItems: 'flex-end', height: H + 80}}>
            {items.map((d, i) => {
              const q = spring({frame: f - at(p.cue) - 10 - i * 6, fps, config: T.spring.heavy});
              return (
                <div key={i} style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14}}>
                  {/* 30 Eyl galeri: 0,31 gibi değerler ondalıksız "0" görünüyordu -> ondalık büyüklüğe göre */}
                  <span style={{fontFamily: T.f.mono, fontSize: 26, fontWeight: 800, color: T.c.text, opacity: q}}>{d.valueText ?? fmtTR(Number(d.value) * q, d.dec ?? p.dec ?? (max < 10 ? 2 : max < 100 ? 1 : 0))}</span>
                  <div style={{width: V ? 120 : 140, height: (Math.abs(Number(d.value)) / max) * H * q, borderRadius: '16px 16px 4px 4px',
                    background: `linear-gradient(180deg, ${col(d.color, c)}, ${col(d.color, c)}33)`}} />
                  <Label size={18}>{d.label}</Label>
                </div>
              );
            })}
          </div>
        </div>
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Volatility: sismograf + çipler ----------
export const Volatility: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {at} = useCue();
  const V = useV();
  const W = V ? 940 : 1680;
  const amp = ease(f, at(p.cue), at(p.peakCue ?? p.cue) + 60, 10, V ? 120 : 150, T.ease.soft);
  const pts = Array.from({length: 240}, (_, i) => {
    const x = (i / 239) * W;
    const n = Math.sin(i * 0.9 + f * 0.35) * 0.5 + Math.sin(i * 0.37 - f * 0.2) * 0.35 + Math.sin(i * 2.3 + f * 0.8) * 0.25;
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${(160 + n * amp * Math.min(1, i / 60)).toFixed(1)}`;
  }).join(' ');
  const st = useSpring(at(p.stampCue ?? p.cue, 1e6), 'bouncy');
  return (
    <AbsoluteFill>
      <BgMesh tint={T.c.hawk} />
      <Stage>
        <div style={{display: 'flex', flexWrap: 'wrap', gap: 20, alignSelf: 'flex-start'}}>
          {(p.chips ?? []).map((c: P, i: number) => (
            <Rise key={i} delay={at(c.cue ?? p.cue) + (c.cue ? 0 : i * 6)} y={30}>
              <div style={{padding: '14px 26px', borderRadius: 999, border: `1px solid ${T.c.line}`, background: T.c.panel, fontFamily: T.f.display, fontWeight: 700, fontSize: 32, color: T.c.text}}>{c.text}</div>
            </Rise>
          ))}
        </div>
        <svg width={W} height={320} style={{marginTop: 60, overflow: 'visible'}}>
          <path d={pts} stroke={T.c.hawk} strokeWidth={4} fill="none" style={{filter: `drop-shadow(0 0 10px ${T.c.hawk})`}} />
        </svg>
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', alignItems: 'center', gap: 40, marginTop: 40}}>
          <Words text={p.headline ?? ''} delay={at(p.headlineCue ?? p.cue)} size={V ? 70 : 80} highlight={p.highlight ?? []} hl={T.c.hawk} align="center" />
          {p.stamp ? <div style={{transform: `scale(${st}) rotate(-5deg)`, opacity: interpolate(st, [0, 0.2], [0, 1], clamp), padding: '12px 26px', borderRadius: 14,
            background: T.c.text, color: T.c.bg, fontFamily: T.f.display, fontWeight: 900, fontSize: 48, whiteSpace: 'nowrap'}}>{p.stamp}</div> : null}
        </div>
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Timeline: takvim (tarih/saat noktaları) ----------
export const Timeline: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const items: P[] = p.items ?? [];
  const W = V ? 900 : 1680;
  const step = V ? 0 : W / items.length;
  const line = ease(f, at(p.cue) - 6, at(items[items.length - 1]?.cue ?? p.cue) + 20, 0, 1, T.ease.inOut);
  return (
    <AbsoluteFill>
      <BgMesh tint={T.c.accent} />
      <Stage>
        <Rise delay={at(p.cue) - 6} style={{alignSelf: 'flex-start'}}><Label size={24} color={T.c.accent}>{p.kicker ?? 'Takvim · Türkiye saati'}</Label></Rise>
        <div style={{position: 'relative', width: W, height: V ? items.length * 260 : 440, marginTop: 30}}>
          <div style={V ? {position: 'absolute', left: 18, top: 0, width: 4, height: `${line * 100}%`, background: `linear-gradient(180deg, ${T.c.accent}, ${T.c.hero})`}
            : {position: 'absolute', top: 90, left: 0, height: 4, width: W * line, background: `linear-gradient(90deg, ${T.c.accent}, ${T.c.hero})`, borderRadius: 2}} />
          {items.map((it, i) => {
            const q0 = spring({frame: f - at(it.cue ?? p.cue) - (it.cue ? 0 : i * 10), fps, config: T.spring.bouncy});
            const ghost = ease(f, at(p.cue) + i * 5, at(p.cue) + i * 5 + 12, 0, 0.32);
            const q = q0;
            const c = col(it.color, i === 0 ? T.c.accent : T.c.hero);
            const pos = V ? {left: 0, top: i * 260} : {left: 60 + i * step, top: 0};
            // 30 Eyl odak modu: anlatılan olay öne çıkar, geçmiş/gelecek olaylar solar (uzun takvim sahnesi tek kare gibi durmasın)
            const allCued = items.every((x) => x.cue);
            const active = allCued ? items.reduce((a, x, k) => (f >= at(x.cue) ? k : a), -1) : -1;
            const focusK = active < 0 ? 1 : i === active ? 1 : 0.42;
            const focusS = active === i ? 1 + 0.06 * ease(f, at(it.cue) , at(it.cue) + 12, 0, 1) : 1;
            return (
              <div key={i} style={{position: 'absolute', ...pos, opacity: focusK, transform: `scale(${focusS})`, transformOrigin: V ? '0% 30%' : '20% 40%'}}>
                <div style={{position: 'absolute', top: V ? 10 : 72, left: 0, width: 40, height: 40, borderRadius: '50%', background: c, transform: `scale(${Math.max(q, ghost * 1.6)})`, opacity: Math.max(interpolate(q, [0, 0.3], [0, 1], clamp), ghost),
                  boxShadow: active === i ? `0 0 0 8px ${c}33, 0 0 40px ${c}` : undefined}} />
                <div style={{position: 'absolute', top: V ? 0 : 150, left: V ? 80 : 0, width: V ? 800 : step - 60, opacity: Math.max(interpolate(q, [0, 0.3], [0, 1], clamp), ghost),
                  transform: `translateY(${q0 > 0.01 ? interpolate(q, [0, 1], [40, 0]) : 0}px)`}}>
                  <Label size={20}>{it.date}</Label>
                  {it.time ? <div style={{fontFamily: T.f.mono, fontWeight: 800, fontSize: fitSize(String(it.time), V ? 88 : 96, (V ? 800 : step - 60), T.f.mono, 800), color: c, lineHeight: 1.1}}>{it.time}</div> : null}
                  <div style={{fontFamily: T.f.display, fontWeight: 800, fontSize: 40, color: T.c.text}}>{it.title}</div>
                </div>
              </div>
            );
          })}
        </div>
        {p.footer ? <Rise delay={at(p.footerCue ?? p.cue) + 10} y={40} style={{position: 'absolute', bottom: 0}}>
          <div style={{fontFamily: T.f.display, fontSize: 46, color: T.c.text, fontWeight: 700, textAlign: 'center'}}>{p.footer}</div>
        </Rise> : null}
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- CoinFlip: "madalyonun öbür yüzü" ----------
export const CoinFlip: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const flip = spring({frame: f - at(p.cue) - 6, fps, config: {damping: 16, stiffness: 40, mass: 1.2}});
  const rot = interpolate(flip, [0, 1], [0, 900]);
  const back = Math.cos((rot * Math.PI) / 180) < 0;
  return (
    <AbsoluteFill>
      <BgMesh tint={T.c.up} tint2={T.c.hawk} />
      <Stage>
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', alignItems: 'center', gap: V ? 60 : 120}}>
          <div style={{perspective: 1200, transform: `translateY(${Math.sin(flip * Math.PI) * -120}px)`}}>
            <div style={{width: 420, height: 420, borderRadius: '50%', transform: `rotateY(${rot}deg)`, position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: back ? `radial-gradient(circle at 35% 30%, #d9fff0, ${T.c.up} 45%, #0b3a28)` : `radial-gradient(circle at 35% 30%, #ffe0e0, ${T.c.hawk} 45%, #3a0b0d)`,
              boxShadow: `0 40px 90px -20px #000, 0 0 70px ${back ? T.c.up : T.c.hawk}55`}}>
              <div style={{position: 'absolute', inset: 22, borderRadius: '50%', border: '3px dashed #ffffff66'}} />
              <span style={{fontFamily: T.f.display, fontWeight: 900, fontSize: 56, color: '#fff', transform: back ? 'scaleX(-1)' : undefined}}>{back ? p.back : p.front}</span>
            </div>
          </div>
          <div style={{width: V ? 900 : 760}}>
            <Words text={p.headline} delay={at(p.cue)} size={V ? 84 : 96} highlight={p.highlight ?? []} hl={T.c.up} align={V ? 'center' : 'left'} />
            {p.sub ? <Rise delay={at(p.cue) + 36}><Label size={24} style={{marginTop: 30}}>{p.sub}</Label></Rise> : null}
          </div>
        </div>
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Tug: iki güç arasında sıkışan özne ----------
export const Tug: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {at} = useCue();
  const V = useV();
  const enter = useSpring(at(p.cue), 'smooth');
  const sway = Math.sin(f / 18) * 40 * enter + Math.sin(f / 7) * 8 * enter;
  const breath = useBreath(20, 0.02);
  const W = V ? 940 : 1600;
  return (
    <AbsoluteFill>
      <BgMesh tint={T.c.hawk} tint2={T.c.up} />
      <Stage>
        <div style={{position: 'relative', width: W, height: 440}}>
          <svg width={W} height={440} style={{position: 'absolute'}}>
            <path d={`M ${V ? 150 : 400} 220 Q ${W / 2} ${250 + Math.sin(f / 9) * 14} ${W - (V ? 150 : 400)} 220`} stroke="#C8A06A" strokeWidth={14} fill="none" strokeDasharray="22 8" strokeDashoffset={f * 0.6} opacity={enter} />
          </svg>
          {[p.left, p.right].map((s: P, i: number) => (
            <div key={i} style={{position: 'absolute', [i ? 'right' : 'left']: 0, top: V ? 0 : 120, opacity: enter, transform: `translateX(${interpolate(enter, [0, 1], [i ? 200 : -200, 0])}px)`}}>
              <Panel style={{padding: '22px 30px', width: V ? 300 : 400}}>
                <Label size={20} color={i ? T.c.up : T.c.hawk}>{s?.label}</Label>
                <div style={{fontFamily: T.f.display, fontWeight: 800, fontSize: V ? 40 : 48, color: T.c.text, marginTop: 6}}>{s?.word}</div>
              </Panel>
            </div>
          ))}
          <div style={{position: 'absolute', left: W / 2 - 120 + sway, top: 100, width: 240, height: 240, borderRadius: '50%', background: `radial-gradient(circle at 35% 30%, #2a3350, ${T.c.bg2})`,
            border: `3px solid ${T.c.text}`, transform: `scale(${breath * enter})`, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
            <span style={{fontFamily: T.f.display, fontWeight: 900, fontSize: p.center?.length > 4 ? 52 : 80, color: T.c.text}}>{p.center}</span>
          </div>
        </div>
        {p.headline ? <div style={{position: 'absolute', bottom: 20}}><Words text={p.headline} delay={at(p.headlineCue ?? p.cue) + 10} size={V ? 60 : 70} align="center" /></div> : null}
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Varlık küresi ----------
export const AssetOrb: React.FC<{kind: string; size: number; glyph?: string}> = ({kind, size, glyph}) => {
  const f = useCurrentFrame();
  const c = col(kind === 'btc' ? 'btc' : kind === 'silver' ? 'silver' : kind === 'gold' ? 'gold' : kind, T.c.accent);
  const g = glyph ?? (kind === 'gold' ? 'Au' : kind === 'silver' ? 'Ag' : kind === 'btc' ? '₿' : '$');
  return (
    <div style={{width: size, height: size, borderRadius: '50%', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: `radial-gradient(circle at 32% 28%, #ffffffcc 0%, ${c} 22%, ${c}88 58%, #000000aa 100%)`, boxShadow: `0 0 60px ${c}55, inset 0 -18px 40px #00000066`}}>
      <div style={{position: 'absolute', inset: size * 0.09, borderRadius: '50%', border: '2px solid #ffffff55'}} />
      <span style={{fontFamily: T.f.display, fontWeight: 900, fontSize: size * (g.length > 2 ? 0.24 : 0.36), color: '#1a1206', opacity: 0.82, transform: `rotate(${Math.sin(f / 30) * 5}deg)`}}>{g}</span>
    </div>
  );
};

// ---------- AssetCards: varlıkların son fiyat + haftalık değişim ----------
export const AssetCards: React.FC<{p: P}> = ({p}) => {
  const {at} = useCue();
  const V = useV();
  const items: P[] = p.items ?? [];
  return (
    <AbsoluteFill>
      <BgMesh />
      <Stage>
        {p.title ? <Words text={p.title} delay={at(p.cue)} size={V ? 72 : 84} align="center" /> : null}
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', gap: V ? 24 : 36, marginTop: V ? 40 : 60}}>
          {items.map((c, i) => <AssetCard key={i} c={c} delay={at(c.cue ?? p.cardsCue ?? p.cue) + (c.cue ? 0 : i * 6)} w={V ? 900 : Math.min(520, 1640 / items.length - 36)} />)}
        </div>
      </Stage>
    </AbsoluteFill>
  );
};
// Sembole göre birim + rozet: BIST/DXY puan, kur ve gram ₺, faiz %, emtia/kripto $ (eski varsayılan her şeye "$" koyuyordu).
const USD = ['XAUUSD', 'XAGUSD', 'BRENT', 'WTI', 'BTCUSD', 'ETHUSD', 'GC=F', 'SI=F', 'BZ=F', 'CL=F', 'BTC-USD', 'ETH-USD'];
const TRY = ['USDTRY', 'EURTRY', 'GAUTRY', 'USDTRY=X', 'EURTRY=X'];
const YLD = ['US10Y', 'US02Y', 'TR10Y', 'TR02Y', '^TNX'];
export const unitFor = (sym?: string): {prefix: string; suffix: string; glyph: string} => {
  const k = String(sym ?? '').toUpperCase();
  if (USD.includes(k)) return {prefix: '$', suffix: '', glyph: k.startsWith('XAU') || k === 'GC=F' ? 'Au' : k.startsWith('XAG') || k === 'SI=F' ? 'Ag' : k.includes('BTC') ? '₿' : k.includes('ETH') ? 'Ξ' : '$'};
  if (TRY.includes(k)) return {prefix: '', suffix: ' ₺', glyph: k.startsWith('EUR') ? '€' : k.startsWith('GAU') ? 'Au' : '$'};
  if (YLD.includes(k)) return {prefix: '%', suffix: '', glyph: '%'};
  return {prefix: '', suffix: '', glyph: k.startsWith('XU') ? 'BIST' : k === 'DXY' ? 'DXY' : k === 'VIX' ? 'VIX' : '•'};
};
const AssetCard: React.FC<{c: P; delay: number; w: number}> = ({c, delay, w}) => {
  const s = useSeries(c.symbol, {last: 40});
  const V = useV();
  if (!s) return null;
  const lastV = last(s.c);
  const back = c.back ?? 5;
  const ch = (lastV / s.c[Math.max(s.c.length - 1 - back, 0)] - 1) * 100;
  return (
    <Rise delay={delay} y={80}>
      <Panel style={{width: w, padding: V ? 28 : 36}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 22}}>
          <AssetOrb kind={c.kind ?? 'accent'} size={V ? 76 : 86} glyph={c.glyph ?? unitFor(c.symbol).glyph} />
          <div>
            <div style={{fontFamily: T.f.display, fontWeight: 800, fontSize: V ? 58 : 44, color: T.c.text}}>{c.name}</div>
            <Label size={V ? 24 : 17}>son fiyat · {c.period ?? 'haftalık'}</Label>
          </div>
          {V ? <span style={{marginLeft: 'auto', fontFamily: T.f.mono, fontSize: 40, fontWeight: 800, color: ch >= 0 ? T.c.up : T.c.down}}>{ch >= 0 ? '▲' : '▼'} %{fmtTR(Math.abs(ch), 1)}</span> : null}
        </div>
        <div style={{display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: 22}}>
          <Counter to={lastV} dec={c.dec ?? (lastV < 20 ? 2 : lastV < 1000 ? 2 : 0)} prefix={c.prefix ?? unitFor(c.symbol).prefix} suffix={c.suffix ?? unitFor(c.symbol).suffix} delay={delay + 6} size={V ? 130 : 72} maxW={V ? w - 64 : w - 72 - 150} weight={900} />
          {!V ? <span style={{fontFamily: T.f.mono, fontSize: 30, fontWeight: 800, color: ch >= 0 ? T.c.up : T.c.down}}>{ch >= 0 ? '▲' : '▼'} %{fmtTR(Math.abs(ch), 1)}</span> : null}
        </div>
        {!V ? <div style={{marginTop: 18}}><LineChart data={s.c} w={w - 72} h={110} color={col(c.kind === 'btc' ? 'btc' : c.kind, T.c.accent)} delay={delay + 8} dur={50} showHead={false} /></div> : null}
      </Panel>
    </Rise>
  );
};

// ---------- Chapter: bölüm kartı ----------
export const Chapter: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const {dur} = useCue();
  const V = useV();
  const c = col(p.kind === 'btc' ? 'btc' : p.kind, T.c.accent);
  const wipe = ease(f, 0, 14, 0, 1, T.ease.inOut);
  const orb = spring({frame: f - 6, fps, config: T.spring.bouncy});
  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      <BgMesh tint={c} tint2={c} grid={false} />
      <AbsoluteFill style={{background: c, transform: `translateX(${interpolate(wipe, [0, 1], [-130, 140])}%) skewX(-12deg)`, opacity: 0.9}} />
      {/* 9 Eki: arka planda dev, içi boş bölüm numarası — yavaş paralaks kayması */}
      {p.n !== undefined ? (
        <div style={{position: 'absolute', right: V ? -40 : 60, bottom: V ? 120 : -60, fontFamily: T.f.display, fontWeight: 900, fontSize: V ? 640 : 760, lineHeight: 1,
          color: 'transparent', WebkitTextStroke: `3px ${c}`, opacity: 0.16 * ease(f, 6, 22, 0, 1),
          transform: `translateX(${interpolate(f, [0, Math.max(dur, 60)], [60, -40], clamp)}px)`}}>{String(p.n).padStart(2, '0')}</div>
      ) : null}
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', flexDirection: V ? 'column' : 'row', gap: 60}}>
        <div style={{transform: `scale(${orb}) rotate(${interpolate(orb, [0, 1], [-90, 0])}deg)`}}><AssetOrb kind={p.kind ?? 'accent'} size={260} glyph={p.glyph} /></div>
        <div style={{textAlign: V ? 'center' : 'left'}}>
          <Label size={28} color={c}>Bölüm {p.n} / {p.of}</Label>
          {/* 9 Eki: maskeli giriş — harfler bir çizginin arkasından bulanıklıkla yükselir, kart biterken yukarı çıkar */}
          <div style={{display: 'flex', marginTop: 6, justifyContent: V ? 'center' : 'flex-start', overflow: 'hidden', padding: '0 0.08em 0.12em', margin: '6px -0.08em 0'}}>
            {String(p.title).split('').map((ch, i, arr) => {
              // 30 Eyl QA: uzun başlık taşıyordu ve harf animasyonu 2 sn'lik kartta geç bitiyordu -> genişliğe sığdır,
              // tüm harfler ~1 sn'de (30 kare) otursun
              const step = Math.min(2, 20 / Math.max(arr.length, 1));
              const q = spring({frame: f - 10 - i * step, fps, config: T.spring.snappy});
              // harf harf span'lar kerning'siz -> ölçülenden ~%12 geniş; boşluk puntoya oranlı (galeri doğrulaması 30 Eyl)
              const fsz = fitSize(String(p.title), String(p.title).length > 9 ? 130 : 190, (V ? 940 : 1180) * 0.86, T.f.display, 900);
              const endAt = Math.min(dur, durationInFrames) - 12;
              const x = ease(f, endAt + i * 0.6, endAt + 8 + i * 0.6, 0, 1, T.ease.in);
              const y = interpolate(q, [0, 1], [110, 0]) - 110 * x;
              const bl = Math.abs(1 - q) * 10 + x * 8;
              return <span key={i} style={{fontFamily: T.f.display, fontWeight: 900, fontSize: fsz, color: T.c.text, display: 'inline-block',
                width: ch === ' ' ? fsz * 0.26 : undefined, transform: `translateY(${y}%) rotate(${(1 - q) * 6}deg)`, filter: bl > 0.4 ? `blur(${bl}px)` : undefined}}>{ch}</span>;
            })}
          </div>
          <DrawLine delay={16} width={600} color={c} thickness={6} dur={Math.max(Math.min(dur, durationInFrames) - 30, 20)} />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ---------- Disclaimer ----------
export const Disclaimer: React.FC<{p: P}> = ({p}) => {
  const {at} = useCue();
  const V = useV();
  const b = useBreath(30, 0.01);
  return (
    <AbsoluteFill>
      <BgMesh tint={T.c.accent} grid={false} />
      <Stage>
        <Rise delay={at(p.cue)} y={40}>
          <div style={{transform: `scale(${b})`}}>
            <Panel style={{padding: V ? '50px 50px' : '60px 90px', display: 'flex', flexDirection: V ? 'column' : 'row', alignItems: 'center', gap: V ? 30 : 60, maxWidth: V ? 940 : 1500}}>
              <svg width={150} height={170} viewBox="0 0 150 170">
                <path d="M75 6 L140 30 V82 C140 124 110 154 75 164 C40 154 10 124 10 82 V30 Z" fill={`${T.c.accent}22`} stroke={T.c.accent} strokeWidth={6} />
                <path d="M48 86 L68 106 L106 64" stroke={T.c.accent} strokeWidth={10} fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <div style={{textAlign: V ? 'center' : 'left'}}>
                <Words text={p.title ?? 'Yatırım tavsiyesi değildir.'} delay={at(p.titleCue ?? p.cue)} size={V ? 70 : 84} align={V ? 'center' : 'left'} />
                <Rise delay={at(p.cue) + 6}><div style={{fontFamily: T.f.display, fontSize: 36, color: T.c.dim, marginTop: 20}}>{p.sub ?? 'Oynaklığı yüksek piyasalara dair güncel bir değerlendirme.'}</div></Rise>
                <Rise delay={at(p.sub2Cue ?? p.cue) + 12}><div style={{fontFamily: T.f.display, fontSize: 36, color: T.c.text, marginTop: 12, fontWeight: 700}}>{p.sub2 ?? 'Kendi araştırmanızı yapmadan hareket etmeyin.'}</div></Rise>
              </div>
            </Panel>
          </div>
        </Rise>
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Poll: izleyiciye soru ----------
export const Poll: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const bub = spring({frame: f - at(p.ctaCue ?? p.cue) - 20, fps, config: T.spring.bouncy});
  const opts: P[] = p.options ?? [];
  return (
    <AbsoluteFill>
      <BgMesh tint={T.c.up} tint2={T.c.hawk} />
      <Stage>
        <Words text={p.question ?? 'Sizce?'} delay={at(p.cue)} size={(() => { const n = String(p.question ?? '').length; return V ? (n > 40 ? 84 : 120) : (n > 40 ? 96 : n > 26 ? 120 : 150); })()} align="center" />
        {/* 30 Eyl QA: 3 seçenek yatayda kareden taşıyordu -> 3+ seçenekte dikey liste, yazı kutuya sığar */}
        <div style={{display: 'flex', flexDirection: V || opts.length > 2 ? 'column' : 'row', gap: V ? 26 : opts.length > 2 ? 22 : 40, marginTop: opts.length > 2 ? 40 : 60}}>
          {opts.map((o, i) => {
            const q = spring({frame: f - at(o.cue ?? p.cue) - (o.cue ? 0 : 10 + i * 8), fps, config: T.spring.smooth});
            const c = opts.length > 2 ? [T.c.up, T.c.accent, T.c.hawk, T.c.hero][i % 4] : i === 0 ? T.c.up : T.c.hawk;
            const bw = V ? 900 : opts.length > 2 ? 1100 : 700;
            return (
              <div key={i} style={{width: bw, padding: opts.length > 2 ? '22px 40px' : '36px 44px', borderRadius: 26, border: `2px solid ${c}`, background: `${c}14`,
                opacity: interpolate(q, [0, 0.3], [0, 1], clamp), transform: `translateY(${interpolate(q, [0, 1], [60, 0])}px)`, display: 'flex', alignItems: 'center', gap: 22}}>
                <div style={{width: 46, height: 46, borderRadius: '50%', border: `4px solid ${c}`, flexShrink: 0}} />
                <span style={{fontFamily: T.f.display, fontWeight: 800, fontSize: fitSize(String(o.text ?? ''), opts.length > 2 ? 44 : 50, bw - 170, T.f.display, 800), color: T.c.text}}>{o.text}</span>
              </div>
            );
          })}
        </div>
        <div style={{marginTop: 60, transform: `scale(${bub})`, opacity: interpolate(bub, [0, 0.2], [0, 1], clamp), display: 'flex', alignItems: 'center', gap: 20}}>
          <svg width={70} height={64}><path d="M8 6 H62 V44 H30 L14 58 V44 H8 Z" fill="none" stroke={T.c.text} strokeWidth={5} strokeLinejoin="round" /></svg>
          <span style={{fontFamily: T.f.display, fontWeight: 700, fontSize: 46, color: T.c.text}}>{p.cta ?? 'Tahmininizi yorumlara bırakın'}</span>
        </div>
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Outro: beğen/abone + logo ----------
export const Outro: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {at, dur} = useCue();
  const V = useV();
  const likeAt = at(p.likeCue ?? p.cue) + 6;
  const subAt = at(p.subCue ?? p.cue) + 12;
  const like = spring({frame: f - likeAt, fps, config: T.spring.bouncy});
  const sub = spring({frame: f - subAt, fps, config: T.spring.bouncy});
  const pressed = f > subAt + 22;
  const logoT = p.logoCue ? at(p.logoCue) : at(p.lineCue ?? p.cue) + (dur - at(p.lineCue ?? p.cue)) * 0.45;
  const swap = ease(f, logoT, logoT + 16, 0, 1, T.ease.inOut);
  return (
    <AbsoluteFill>
      <BgMesh />
      <AbsoluteFill style={{opacity: 1 - swap}}>
        <Stage>
          <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', gap: 40, alignItems: 'center'}}>
            <div style={{transform: `scale(${like})`, opacity: like, display: 'flex', alignItems: 'center', gap: 16, padding: '26px 44px', borderRadius: 999, background: T.c.panel, border: `2px solid ${T.c.line}`}}>
              <svg width={56} height={56} viewBox="0 0 24 24"><path d="M2 21h4V9H2v12zm20-11c0-1.1-.9-2-2-2h-6.3l1-4.6v-.3c0-.4-.2-.8-.4-1.1L13.2 1 6.6 7.6C6.2 8 6 8.5 6 9v10c0 1.1.9 2 2 2h9c.8 0 1.5-.5 1.8-1.2l3-7.1c.1-.2.2-.5.2-.7v-2z" fill={T.c.text} /></svg>
              <span style={{fontFamily: T.f.display, fontWeight: 800, fontSize: 50, color: T.c.text}}>Beğen</span>
            </div>
            <div style={{transform: `scale(${sub * (pressed ? 1 : 1)})`, opacity: sub, padding: '26px 56px', borderRadius: 999, background: pressed ? T.c.faint : '#FF0033'}}>
              <span style={{fontFamily: T.f.display, fontWeight: 900, fontSize: 54, color: '#fff'}}>{pressed ? 'ABONE OLUNDU' : 'ABONE OL'}</span>
            </div>
          </div>
          {p.line ? <Rise delay={at(p.lineCue ?? p.cue)} y={30}><div style={{fontFamily: T.f.display, fontSize: V ? 44 : 50, color: T.c.text, marginTop: 70, fontWeight: 600, textAlign: 'center'}}>{p.line}</div></Rise> : null}
        </Stage>
      </AbsoluteFill>
      <AbsoluteFill style={{opacity: swap, alignItems: 'center', justifyContent: 'center', transform: `scale(${0.9 + 0.1 * swap})`}}>
        {swap > 0.01 ? (
          <>
            <BrandLockup size={V ? 260 : 240} delay={logoT} vertical={V} />
            <Label size={24} style={{marginTop: 14}}>Veriyle konuşur · Yatırım tavsiyesi değildir</Label>
          </>
        ) : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ---------- DateQuestion: takvim yaprağı + büyük soru + hafta şeridi ----------
export const DateQuestion: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {at} = useCue();
  const V = useV();
  const qm = useSpring(at(p.qCue ?? p.cue) + 10, 'bouncy');
  return (
    <AbsoluteFill>
      <BgMesh />
      <Stage>
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', alignItems: 'center', gap: V ? 40 : 70}}>
          <Rise delay={at(p.cue)} y={60} scaleFrom={0.8}>
            <div style={{width: 300, borderRadius: 26, overflow: 'hidden', border: `1px solid ${T.c.line}`, boxShadow: '0 40px 90px -30px #000'}}>
              <div style={{background: T.c.hawk, padding: '14px 0', textAlign: 'center', fontFamily: T.f.display, fontWeight: 800, fontSize: 40, color: '#fff', letterSpacing: '0.1em'}}>{p.month}</div>
              <div style={{background: '#F3F1EA', padding: '6px 0 16px', textAlign: 'center'}}>
                <div style={{fontFamily: T.f.display, fontWeight: 900, fontSize: 170, color: T.c.bg, lineHeight: 1}}>{p.day}</div>
                <div style={{fontFamily: T.f.mono, fontSize: 22, color: '#555', letterSpacing: '0.16em'}}>{p.weekday}</div>
              </div>
            </div>
          </Rise>
          <div style={{display: 'flex', alignItems: 'flex-end', gap: 10}}>
            {/* 30 Eyl QA: uzun soru 4 satıra taşıp nota biniyordu -> uzunluğa göre punto (en fazla ~3 satır) */}
            <Words text={p.question} delay={at(p.qCue ?? p.cue) + 4} size={(() => { const n = String(p.question ?? '').length; return V ? (n <= 20 ? 110 : n <= 34 ? 88 : 70) : (n <= 20 ? 130 : n <= 34 ? 104 : 84); })()} highlight={p.highlight ?? []} style={{maxWidth: V ? 760 : 820}} />
            <span style={{display: 'inline-block', fontFamily: T.f.display, fontWeight: 900, fontSize: V ? 200 : 260, color: T.c.text, lineHeight: 0.8, transformOrigin: '50% 90%',
              transform: `scale(${qm}) rotate(${interpolate(qm, [0, 1], [-40, 0]) + Math.sin(f / 14) * 4}deg)`}}>?</span>
          </div>
        </div>
        {p.note ? <Rise delay={at(p.noteCue ?? p.cue) + 10} y={40} style={{marginTop: 44}}>
          <Panel style={{padding: '20px 34px', border: `1px solid ${T.c.accent}`}}>
            <Label size={20} color={T.c.accent}>{p.note.label}</Label>
            <div style={{fontFamily: T.f.display, fontWeight: 800, fontSize: 40, color: T.c.text}}>{p.note.text}</div>
          </Panel>
        </Rise> : null}
      </Stage>
    </AbsoluteFill>
  );
};
