// Şablonlar C (29 Eyl kütüphane turu 1): mum grafiği, sektör ısı haritası, dünya haritası + akışlar, verim eğrisi,
// son dakika bandı, geri sayım, manşet vurgusu. d3 (ölçek/şekil/coğrafya) + world-atlas.
import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {scaleLinear} from 'd3-scale';
import {line as d3line, curveMonotoneX} from 'd3-shape';
import {geoNaturalEarth1, geoPath, geoInterpolate} from 'd3-geo';
import {feature} from 'topojson-client';
import world from 'world-atlas/countries-110m.json';
import {T, fmtTR} from '../core/theme';
import {BgMesh, Counter, Label, Panel, Rise, Words, clamp, ease, fitSize, useSpring} from '../core/kit';
import {Stage, useCue} from '../core/timing';
import {P, col, shortDate, useSeries} from './data';
import {Tag, useV} from './templatesA';

const last = (a: number[]) => a[a.length - 1];

// ---------- Candles: OHLC mum grafiği (sırayla büyüyen mumlar) ----------
export const Candles: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {at} = useCue();
  const V = useV();
  const s = useSeries(p.symbol, {since: p.since, last: p.last ?? 40});
  if (!s || !s.o || !s.h || !s.l) return <Fallback p={p} />;
  const {o, h, l, c, d} = s as Required<typeof s>;
  const n = c.length;
  const W = V ? 800 : 1640; // dikeyde sağdaki fiyat etiketleri için pay (30 Eyl dikey galeri)
  const H = V ? 700 : p.tag ? 460 : 540;
  const hv = (p.hlines ?? []).map((x: P) => Number(x.value));
  const lo = Math.min(...l, ...hv);
  const hi = Math.max(...h, ...hv);
  const pad = (hi - lo) * 0.07;
  const y = scaleLinear().domain([lo - pad, hi + pad]).range([H, 0]);
  const gap = W / n;
  const bw = Math.max(gap * 0.62, 3);
  const t0 = at(p.cue) + 8;
  const per = Math.max(Math.min(60 / n, 2.2), 0.6);
  const dec = p.dec ?? (last(c) < 20 ? 2 : 0);
  const lastY = y(last(c));
  const tagO = ease(f, t0 + n * per, t0 + n * per + 12, 0, 1);
  return (
    <AbsoluteFill>
      <BgMesh tint={T.c.accent} />
      <Stage>
        <Tag tag={p.tag} cue={at(p.cue)} />
        <div style={{alignSelf: 'flex-start', display: 'flex', alignItems: 'flex-end', gap: 40, marginTop: p.tag ? 60 : 0}}>
          <Rise delay={at(p.cue)} y={30}>
            <Label size={22}>{p.title ?? p.symbol}</Label>
            <Counter to={last(c)} from={c[0]} dec={dec} prefix={p.prefix ?? ''} suffix={p.suffix ?? ''} delay={at(p.cue) + 4} size={110} weight={900} />
          </Rise>
          {p.change ? (
            <Rise delay={at(p.change.cue ?? p.cue) + 6} y={20}>
              <div style={{fontFamily: T.f.mono, fontSize: 36, fontWeight: 800, color: col(p.change.color, T.c.down), paddingBottom: 14}}>{p.change.text}</div>
            </Rise>
          ) : null}
        </div>
        <svg width={W} height={H + 40} style={{marginTop: 24, overflow: 'visible'}}>
          {y.ticks(5).map((t, i) => (
            <g key={i} opacity={ease(f, t0, t0 + 20, 0, 0.8)}>
              <line x1={0} x2={W} y1={y(t)} y2={y(t)} stroke={T.c.line} />
              <text x={W + 10} y={y(t) + 6} fill={T.c.dim} fontFamily={T.f.mono} fontSize={16}>{fmtTR(t, dec)}</text>
            </g>
          ))}
          {c.map((cv, i) => {
            const k = spring({frame: f - t0 - i * per, fps: 30, config: T.spring.snappy});
            const up = cv >= o[i];
            const color = up ? T.c.up : T.c.down;
            const x = i * gap + gap / 2;
            const top = y(Math.max(o[i], cv));
            const bot = y(Math.min(o[i], cv));
            const mid = (top + bot) / 2;
            return (
              <g key={i} opacity={interpolate(k, [0, 0.3], [0, 1], clamp)}>
                <line x1={x} x2={x} y1={mid + (y(h[i]) - mid) * k} y2={mid + (y(l[i]) - mid) * k} stroke={color} strokeWidth={2} />
                <rect x={x - bw / 2} y={mid - (mid - top) * k} width={bw} height={Math.max((bot - top) * k, 2)} fill={up ? 'transparent' : color}
                  stroke={color} strokeWidth={2} rx={2} />
              </g>
            );
          })}
          {(p.hlines ?? []).map((hl: P, i: number) => {
            const o2 = ease(f, at(hl.cue ?? p.cue) + 20, at(hl.cue ?? p.cue) + 34, 0, 1);
            const yy = y(Number(hl.value));
            const cc = col(hl.color, T.c.hawk);
            return (
              <g key={`h${i}`} opacity={o2}>
                <line x1={0} x2={W * o2} y1={yy} y2={yy} stroke={cc} strokeWidth={2} strokeDasharray="10 8" />
                <text x={12} y={yy - 10} fill={cc} fontFamily={T.f.mono} fontSize={20} fontWeight={700}>{hl.label ?? fmtTR(Number(hl.value), dec)}</text>
              </g>
            );
          })}
          <g opacity={tagO}>
            <line x1={0} x2={W} y1={lastY} y2={lastY} stroke={T.c.text} strokeOpacity={0.25} strokeDasharray="3 6" />
            <rect x={W + 4} y={lastY - 18} width={120} height={36} rx={6} fill={last(c) >= o[n - 1] ? T.c.up : T.c.down} />
            <text x={W + 64} y={lastY + 7} textAnchor="middle" fill={T.c.bg} fontFamily={T.f.mono} fontSize={19} fontWeight={800}>{fmtTR(last(c), dec)}</text>
          </g>
          {[0, Math.floor(n / 2), n - 1].map((i) => (
            <text key={`d${i}`} x={i * gap + gap / 2} y={H + 32} textAnchor="middle" fill={T.c.dim} fontFamily={T.f.mono} fontSize={16}
              opacity={ease(f, t0, t0 + 20, 0, 1)}>{shortDate(d[i])}</text>
          ))}
        </svg>
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Heatmap: sektör/varlık ısı haritası (kutu alanı = ağırlık, renk = % değişim) ----------
export const Heatmap: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {at} = useCue();
  const V = useV();
  const items: P[] = [...(p.items ?? [])].sort((a, b) => (b.weight ?? 1) - (a.weight ?? 1));
  const W = V ? 940 : 1640;
  const H = V ? 900 : 560;
  const rects = squarify(items.map((it) => Math.max(Number(it.weight ?? 1), 0.1)), 0, 0, W, H);
  const maxAbs = Math.max(...items.map((it) => Math.abs(Number(it.value))), 1);
  const t0 = at(p.cue) + 10;
  return (
    <AbsoluteFill>
      <BgMesh tint={T.c.down} tint2={T.c.up} />
      <Stage>
        <Tag tag={p.tag} cue={at(p.cue)} />
        {p.title ? <Words text={p.title} delay={at(p.cue)} size={V ? 64 : 64} align="center" style={{marginBottom: 30}} /> : null}
        <div style={{position: 'relative', width: W, height: H}}>
          {items.map((it, i) => {
            const r = rects[i];
            const v = Number(it.value);
            const k = spring({frame: f - t0 - i * 2, fps: 30, config: T.spring.smooth});
            const inten = Math.min(Math.abs(v) / maxAbs, 1);
            const base = v >= 0 ? '61,220,151' : '255,90,95';
            const big = r.w > 180 && r.h > 110;
            return (
              <div key={i} style={{position: 'absolute', left: r.x + 3, top: r.y + 3, width: r.w - 6, height: r.h - 6, borderRadius: 10,
                background: `rgba(${base},${0.18 + 0.62 * inten})`, border: `1px solid rgba(${base},0.8)`, opacity: interpolate(k, [0, 0.4], [0, 1], clamp),
                transform: `scale(${interpolate(k, [0, 1], [0.8, 1])})`, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
                overflow: 'hidden', boxShadow: at(it.cue ?? '') && f >= at(it.cue) ? `0 0 0 4px ${T.c.text}` : undefined}}>
                <div style={{fontFamily: T.f.display, fontWeight: 800, color: T.c.text, fontSize: fitSize(it.label, big ? 38 : 24, r.w - 24), textAlign: 'center'}}>{it.label}</div>
                <div style={{fontFamily: T.f.mono, fontWeight: 800, color: T.c.text, fontSize: big ? 34 : 20, marginTop: 4}}>
                  {v >= 0 ? '+' : '−'}%{fmtTR(Math.abs(v * interpolate(k, [0, 1], [0, 1], clamp)), it.dec ?? 1)}
                </div>
              </div>
            );
          })}
        </div>
        {p.source ? <Label size={16} style={{marginTop: 18, opacity: ease(f, t0 + 20, t0 + 40, 0, 1)}}>{p.source}</Label> : null}
      </Stage>
    </AbsoluteFill>
  );
};

type R = {x: number; y: number; w: number; h: number};
// Basit squarified treemap (Bruls vd.) — değerler büyükten küçüğe sıralı gelmeli.
function squarify(vals: number[], x: number, y: number, w: number, h: number): R[] {
  const total = vals.reduce((a, b) => a + b, 0);
  const areas = vals.map((v) => (v / total) * w * h);
  const out: R[] = [];
  let rect = {x, y, w, h};
  let row: number[] = [];
  const worst = (r: number[], side: number) => {
    const s = r.reduce((a, b) => a + b, 0);
    const mx = Math.max(...r);
    const mn = Math.min(...r);
    return Math.max((side * side * mx) / (s * s), (s * s) / (side * side * mn));
  };
  const layout = (r: number[]) => {
    const s = r.reduce((a, b) => a + b, 0);
    if (rect.w >= rect.h) {
      const cw = s / rect.h;
      let yy = rect.y;
      r.forEach((a) => { out.push({x: rect.x, y: yy, w: cw, h: a / cw}); yy += a / cw; });
      rect = {x: rect.x + cw, y: rect.y, w: rect.w - cw, h: rect.h};
    } else {
      const rh = s / rect.w;
      let xx = rect.x;
      r.forEach((a) => { out.push({x: xx, y: rect.y, w: a / rh, h: rh}); xx += a / rh; });
      rect = {x: rect.x, y: rect.y + rh, w: rect.w, h: rect.h - rh};
    }
  };
  areas.forEach((a) => {
    const side = Math.min(rect.w, rect.h);
    if (!row.length || worst([...row, a], side) <= worst(row, side)) row.push(a);
    else { layout(row); row = [a]; }
  });
  if (row.length) layout(row);
  return out;
}

// ---------- WorldMap: ülke vurgusu + akış okları (petrol, sermaye, ticaret) ----------
const COUNTRIES = feature(world as any, (world as any).objects.countries) as any;
export const WorldMap: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {at} = useCue();
  const V = useV();
  const W = V ? 1000 : 1680;
  const H = V ? 760 : 700;
  // dikeyde tüm dünya çok küçük kalıyordu -> odak yoksa vurgulanan ülkelere yakınlaş
  const focusNames: string[] | undefined = p.focus ?? (p.highlight?.length && p.world !== true ? p.highlight.map((h: P) => h.name) : undefined);
  // çerçeve = odak ülkeler + akış/işaret noktaları (dikeyde tüm dünya küçük, yalnız ülkeler ise okları dışarıda bırakıyordu)
  const pts: [number, number][] = [...(p.flows ?? []).flatMap((fl: P) => [fl.from, fl.to]), ...(p.markers ?? []).map((m: P) => m.at)];
  const fitObj: any = focusNames ? {type: 'FeatureCollection', features: [
    ...COUNTRIES.features.filter((c: any) => focusNames.includes(c.properties.name)),
    ...(pts.length ? [{type: 'Feature', properties: {}, geometry: {type: 'MultiPoint', coordinates: pts}}] : []),
  ]} : COUNTRIES;
  const proj = geoNaturalEarth1().fitExtent([[40, 40], [W - 40, H - 40]], fitObj);
  if (p.zoom) proj.scale(proj.scale() * Number(p.zoom));
  const path = geoPath(proj);
  const hi: Record<string, P> = {};
  (p.highlight ?? []).forEach((h: P) => { hi[h.name] = h; });
  const t0 = at(p.cue);
  const mapO = ease(f, t0, t0 + 20, 0, 1);
  return (
    <AbsoluteFill>
      <BgMesh grid={false} />
      <Stage>
        <Tag tag={p.tag} cue={at(p.cue)} />
        {p.title ? <Words text={p.title} delay={t0} size={60} align="center" style={{marginBottom: 10}} /> : null}
        <svg width={W} height={H} style={{overflow: 'visible', opacity: mapO}}>
          {COUNTRIES.features.map((c: any, i: number) => {
            const h = hi[c.properties.name];
            const on = h ? ease(f, at(h.cue ?? p.cue) + 6, at(h.cue ?? p.cue) + 22, 0, 1) : 0;
            const cc = h ? col(h.color, T.c.hero) : T.c.text;
            return <path key={i} d={path(c) ?? ''} fill={h ? cc : 'rgba(255,255,255,0.06)'} fillOpacity={h ? 0.12 + 0.6 * on : 1}
              stroke={h && on > 0 ? cc : 'rgba(255,255,255,0.14)'} strokeWidth={h ? 1 + on * 1.5 : 0.6} />;
          })}
          {(p.flows ?? []).map((fl: P, i: number) => {
            const a = proj(fl.from) as [number, number];
            const b = proj(fl.to) as [number, number];
            if (!a || !b) return null;
            const s0 = at(fl.cue ?? p.cue) + 16;
            const k = ease(f, s0, s0 + 30, 0, 1, T.ease.inOut);
            const mx = (a[0] + b[0]) / 2;
            const my = (a[1] + b[1]) / 2 - Math.hypot(b[0] - a[0], b[1] - a[1]) * 0.28;
            const d = `M${a[0]},${a[1]} Q${mx},${my} ${b[0]},${b[1]}`;
            const len = Math.hypot(b[0] - a[0], b[1] - a[1]) * 1.25;
            const cc = col(fl.color, T.c.oil);
            const pulse = (f - s0) % 40;
            return (
              <g key={`f${i}`}>
                <path d={d} fill="none" stroke={cc} strokeWidth={4} strokeDasharray={len} strokeDashoffset={len * (1 - k)} strokeLinecap="round"
                  style={{filter: `drop-shadow(0 0 8px ${cc})`}} />
                <circle cx={a[0]} cy={a[1]} r={7} fill={cc} opacity={k} />
                <circle cx={b[0]} cy={b[1]} r={7 + (k >= 1 ? pulse * 0.5 : 0)} fill="none" stroke={cc} opacity={k >= 1 ? 1 - pulse / 40 : 0} strokeWidth={3} />
                <circle cx={b[0]} cy={b[1]} r={8} fill={cc} opacity={k} />
                {fl.label ? <text x={mx} y={my + 6} textAnchor="middle" fill={T.c.text} fontFamily={T.f.mono} fontSize={22} fontWeight={800}
                  opacity={ease(f, s0 + 20, s0 + 34, 0, 1)} style={{paintOrder: 'stroke', stroke: T.c.bg, strokeWidth: 6}}>{fl.label}</text> : null}
              </g>
            );
          })}
          {(p.markers ?? []).map((m: P, i: number) => {
            const pt = proj(m.at) as [number, number];
            if (!pt) return null;
            const k = spring({frame: f - at(m.cue ?? p.cue) - 10, fps: 30, config: T.spring.bouncy});
            const cc = col(m.color, T.c.hawk);
            return (
              <g key={`m${i}`} transform={`translate(${pt[0]},${pt[1]}) scale(${k})`}>
                <circle r={10} fill={cc} />
                <circle r={22} fill="none" stroke={cc} strokeWidth={2} opacity={0.6} />
                <text x={0} y={-30} textAnchor="middle" fill={T.c.text} fontFamily={T.f.display} fontSize={28} fontWeight={800}
                  style={{paintOrder: 'stroke', stroke: T.c.bg, strokeWidth: 7}}>{m.label}</text>
              </g>
            );
          })}
        </svg>
      </Stage>
    </AbsoluteFill>
  );
};
void geoInterpolate;

// ---------- YieldCurve: vade eğrisi (bugün vs önce) ----------
export const YieldCurve: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {at} = useCue();
  const V = useV();
  const items: P[] = p.items ?? [];
  const W = V ? 900 : 1500;
  const H = V ? 620 : 440;
  const vals = items.flatMap((it) => [Number(it.v), ...(it.prev !== undefined ? [Number(it.prev)] : [])]);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = (hi - lo) * 0.25 || 0.5;
  const x = scaleLinear().domain([0, items.length - 1]).range([40, W - 40]);
  const y = scaleLinear().domain([lo - pad, hi + pad]).range([H, 0]);
  const mk = (key: 'v' | 'prev') => d3line<P>().x((_, i) => x(i)).y((it) => y(Number(it[key]))).curve(curveMonotoneX)(items) ?? '';
  const t0 = at(p.cue) + 8;
  const kNow = ease(f, t0 + 10, t0 + 50, 0, 1, T.ease.inOut);
  const kPrev = ease(f, t0, t0 + 36, 0, 1, T.ease.inOut);
  const hasPrev = items.every((it) => it.prev !== undefined);
  return (
    <AbsoluteFill>
      <BgMesh tint={T.c.accent} />
      <Stage>
        <Tag tag={p.tag} cue={at(p.cue)} />
        {p.title ? <Words text={p.title} delay={at(p.cue)} size={64} align="center" style={{marginBottom: 20}} /> : null}
        <svg width={W} height={H + 70} style={{overflow: 'visible'}}>
          {y.ticks(5).map((t, i) => (
            <g key={i} opacity={0.8}>
              <line x1={0} x2={W} y1={y(t)} y2={y(t)} stroke={T.c.line} />
              <text x={-12} y={y(t) + 6} textAnchor="end" fill={T.c.dim} fontFamily={T.f.mono} fontSize={17}>%{fmtTR(t, 1)}</text>
            </g>
          ))}
          {hasPrev ? <path d={mk('prev')} fill="none" stroke={T.c.dim} strokeWidth={3} strokeDasharray="10 10" opacity={kPrev} /> : null}
          <path d={mk('v')} fill="none" stroke={col(p.color, T.c.hero)} strokeWidth={6} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - kNow}
            style={{filter: `drop-shadow(0 0 14px ${col(p.color, T.c.hero)})`}} />
          {items.map((it, i) => {
            const o = ease(f, t0 + 14 + i * 4, t0 + 26 + i * 4, 0, 1);
            return (
              <g key={i} opacity={o}>
                <circle cx={x(i)} cy={y(Number(it.v))} r={9} fill={col(p.color, T.c.hero)} />
                <text x={x(i)} y={y(Number(it.v)) - 22} textAnchor="middle" fill={T.c.text} fontFamily={T.f.mono} fontSize={22} fontWeight={800}>%{fmtTR(Number(it.v), 2)}</text>
                <text x={x(i)} y={H + 44} textAnchor="middle" fill={T.c.dim} fontFamily={T.f.mono} fontSize={22} fontWeight={700}>{it.m}</text>
              </g>
            );
          })}
        </svg>
        {hasPrev ? (
          <div style={{display: 'flex', gap: 40, marginTop: 10, opacity: ease(f, t0 + 40, t0 + 56, 0, 1)}}>
            <Label color={col(p.color, T.c.hero)}>━ {p.nowLabel ?? 'bugün'}</Label>
            <Label>┅ {p.prevLabel ?? 'önce'}</Label>
          </div>
        ) : null}
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Breaking: "SON DAKİKA" bandı ----------
export const Breaking: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {at} = useCue();
  const V = useV();
  const t0 = at(p.cue);
  const bar = ease(f, t0, t0 + 14, 0, 1, T.ease.inOut);
  const blink = 0.55 + 0.45 * Math.abs(Math.sin(f / 7));
  return (
    <AbsoluteFill>
      <BgMesh tint={T.c.down} tint2={T.c.down} />
      <Stage>
        <div style={{width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 26}}>
          <div style={{display: 'flex', alignItems: 'stretch', transform: `translateX(${(1 - bar) * -120}%)`}}>
            <div style={{background: T.c.down, color: T.c.text, fontFamily: T.f.display, fontWeight: 900, fontSize: V ? 48 : 44, padding: '14px 28px', letterSpacing: '0.04em',
              display: 'flex', alignItems: 'center', gap: 14}}>
              <span style={{width: 16, height: 16, borderRadius: 8, background: T.c.text, opacity: blink}} />{p.kicker ?? 'SON DAKİKA'}
            </div>
            <div style={{background: T.c.text, color: T.c.bg, fontFamily: T.f.mono, fontWeight: 800, fontSize: V ? 32 : 28, padding: '14px 24px', display: 'flex', alignItems: 'center'}}>
              {p.time ?? ''}
            </div>
          </div>
          <Words text={p.headline ?? ''} delay={t0 + 10} size={V ? 84 : 92} highlight={p.highlight} hl={col(p.hl, T.c.hero)} />
          {p.sub ? <Rise delay={at(p.subCue ?? p.cue) + 18} y={20}><div style={{fontFamily: T.f.display, fontSize: V ? 40 : 38, color: T.c.dim, fontWeight: 600, maxWidth: 1400}}>{p.sub}</div></Rise> : null}
          {p.source ? <Label size={20} style={{opacity: ease(f, t0 + 30, t0 + 44, 0, 1)}}>Kaynak: {p.source}</Label> : null}
        </div>
      </Stage>
      <div style={{position: 'absolute', left: 0, right: 0, bottom: V ? 560 : 170, height: 6, background: T.c.down, transformOrigin: '0 50%', transform: `scaleX(${bar})`}} />
    </AbsoluteFill>
  );
};

// ---------- Countdown: kritik olaya kalan süre (gün/saat) ----------
export const Countdown: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {at} = useCue();
  const V = useV();
  const t0 = at(p.cue);
  const units: {v: number; l: string}[] = [
    ...(p.days !== undefined ? [{v: Number(p.days), l: 'GÜN'}] : []),
    ...(p.hours !== undefined ? [{v: Number(p.hours), l: 'SAAT'}] : []),
  ];
  return (
    <AbsoluteFill>
      <BgMesh tint={col(p.color, T.c.hero)} />
      <Stage>
        <Label size={26} color={col(p.color, T.c.hero)} style={{opacity: ease(f, t0, t0 + 12, 0, 1)}}>{p.kicker ?? 'GERİ SAYIM'}</Label>
        <Words text={p.title ?? ''} delay={t0 + 4} size={V ? 76 : 80} align="center" style={{marginTop: 16}} />
        <div style={{display: 'flex', gap: 30, marginTop: 50}}>
          {units.map((u, i) => (
            <Rise key={i} delay={t0 + 14 + i * 6} y={50} scaleFrom={0.85}>
              <Panel glow={col(p.color, T.c.hero)} style={{width: V ? 380 : 320, padding: '34px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
                <FlipNumber to={u.v} delay={t0 + 18 + i * 6} size={V ? 170 : 160} />
                <Label size={24} style={{marginTop: 8}}>{u.l}</Label>
              </Panel>
            </Rise>
          ))}
        </div>
        {p.date ? <Label size={24} style={{marginTop: 34, opacity: ease(f, t0 + 30, t0 + 44, 0, 1)}}>{p.date}</Label> : null}
      </Stage>
    </AbsoluteFill>
  );
};

const FlipNumber: React.FC<{to: number; delay: number; size: number}> = ({to, delay, size}) => {
  const f = useCurrentFrame();
  const steps = Math.min(Math.max(to, 1), 12);
  const k = ease(f, delay, delay + 24, 0, 1, T.ease.out);
  const shown = Math.round(to + (steps - k * steps));
  const flip = ((f - delay) % 3) / 3;
  return (
    <div style={{fontFamily: T.f.display, fontWeight: 900, fontSize: size, color: T.c.text, lineHeight: 1, fontVariantNumeric: 'tabular-nums',
      transform: k < 1 ? `rotateX(${flip * 60}deg)` : undefined}}>{String(Math.max(shown, to)).padStart(2, '0')}</div>
  );
};

// ---------- Headline: haber manşeti + fosforlu kalem vurgusu ----------
export const Headline: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {at} = useCue();
  const V = useV();
  const t0 = at(p.cue);
  const k = useSpring(t0, 'smooth');
  const text = String(p.text ?? '');
  const hl = String(p.highlight ?? '');
  const i = hl ? text.toLocaleLowerCase('tr').indexOf(hl.toLocaleLowerCase('tr')) : -1;
  const pre = i >= 0 ? text.slice(0, i) : text;
  const mid = i >= 0 ? text.slice(i, i + hl.length) : '';
  const post = i >= 0 ? text.slice(i + hl.length) : '';
  const mark = ease(f, at(p.hlCue ?? p.cue) + 22, at(p.hlCue ?? p.cue) + 40, 0, 100, T.ease.inOut);
  return (
    <AbsoluteFill>
      <BgMesh tint={T.c.silver} grid={false} />
      <Stage>
        <div style={{transform: `perspective(1600px) rotateX(${interpolate(k, [0, 1], [18, 6])}deg) rotateZ(${interpolate(k, [0, 1], [-4, -1.5])}deg) translateY(${interpolate(k, [0, 1], [120, 0])}px)`,
          opacity: interpolate(k, [0, 0.4], [0, 1], clamp)}}>
          <div style={{width: V ? 900 : 1300, background: '#F4F1E8', borderRadius: 6, padding: V ? '40px 44px' : '50px 64px', boxShadow: '0 50px 120px rgba(0,0,0,0.6)'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', borderBottom: '3px solid #1b1b1b', paddingBottom: 12, marginBottom: 24}}>
              <span style={{fontFamily: T.f.serif, fontSize: V ? 44 : 50, color: '#1b1b1b'}}>{p.outlet ?? 'Gazete'}</span>
              <span style={{fontFamily: T.f.mono, fontSize: 18, color: '#555', alignSelf: 'flex-end'}}>{p.date ?? ''}</span>
            </div>
            <div style={{fontFamily: T.f.display, fontWeight: 900, fontSize: V ? 62 : 72, lineHeight: 1.12, color: '#141414', letterSpacing: '-0.02em'}}>
              {pre}
              {mid ? (
                <span style={{backgroundImage: `linear-gradient(transparent 12%, ${T.c.hero}dd 12%, ${T.c.hero}dd 92%, transparent 92%)`,
                  backgroundRepeat: 'no-repeat', backgroundSize: `${mark}% 100%`, padding: '0 4px'}}>{mid}</span>
              ) : null}
              {post}
            </div>
            {p.sub ? <div style={{fontFamily: T.f.display, fontSize: V ? 30 : 32, color: '#444', marginTop: 20, fontWeight: 500}}>{p.sub}</div> : null}
          </div>
        </div>
        {p.note ? <Label size={20} style={{marginTop: 40, opacity: ease(f, t0 + 30, t0 + 44, 0, 1)}}>{p.note}</Label> : null}
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- PumpBoard: akaryakıt totemi — bugün -> yeni fiyat, tabela gibi dönen rakamlar (30 Eyl QA önerisi) ----------
export const PumpBoard: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const items: P[] = p.items ?? [];
  const t0 = at(p.cue);
  const flipAt = at(p.flipCue ?? p.cue) + (p.flipCue ? 0 : 40);
  return (
    <AbsoluteFill>
      <BgMesh tint={T.c.down} grid={false} />
      <Stage>
        <Rise delay={t0} y={80} scaleFrom={0.9}>
          <div style={{width: V ? 820 : 900, background: 'linear-gradient(180deg, #1b2230, #0e131d)', borderRadius: 26, border: '2px solid rgba(255,255,255,0.12)',
            boxShadow: '0 50px 120px -30px #000', overflow: 'hidden'}}>
            <div style={{background: col(p.color, T.c.down), padding: '18px 36px', display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
              <span style={{fontFamily: T.f.display, fontWeight: 900, fontSize: 40, color: '#fff', letterSpacing: '0.04em'}}>{p.title ?? 'AKARYAKIT'}</span>
              <span style={{fontFamily: T.f.mono, fontWeight: 700, fontSize: 22, color: '#ffffffcc'}}>{p.place ?? ''}</span>
            </div>
            {items.map((it, i) => {
              const k = spring({frame: f - flipAt - i * 8, fps, config: T.spring.snappy});
              const oldV = Number(it.from);
              const newV = Number(it.to);
              const flip = interpolate(k, [0, 0.5, 1], [0, 90, 0]);
              const shown = k < 0.5 ? oldV : newV;
              const diff = newV - oldV;
              const dc = diff >= 0 ? T.c.down : T.c.up; // tüketici açısı: artış kötü
              return (
                <div key={i} style={{display: 'flex', alignItems: 'center', padding: '22px 36px', borderTop: i ? '1px solid rgba(255,255,255,0.08)' : undefined,
                  opacity: ease(f, t0 + 6 + i * 5, t0 + 16 + i * 5, 0, 1)}}>
                  <span style={{fontFamily: T.f.display, fontWeight: 800, fontSize: 44, color: T.c.text, width: 250}}>{it.name}</span>
                  <div style={{background: '#05070b', borderRadius: 12, padding: '6px 22px', minWidth: 250, textAlign: 'right', transform: `perspective(600px) rotateX(${flip}deg)`,
                    boxShadow: 'inset 0 0 0 2px rgba(255,255,255,0.06)'}}>
                    <span style={{fontFamily: T.f.mono, fontWeight: 800, fontSize: 72, color: k < 0.5 ? T.c.text : T.c.hero, letterSpacing: '0.02em'}}>{fmtTR(shown, it.dec ?? 2)}</span>
                  </div>
                  <span style={{fontFamily: T.f.mono, fontWeight: 800, fontSize: 34, color: dc, marginLeft: 26, opacity: interpolate(k, [0.5, 1], [0, 1], clamp)}}>
                    {diff >= 0 ? '+' : '−'}{fmtTR(Math.abs(diff), it.dec ?? 2)}
                  </span>
                </div>
              );
            })}
          </div>
        </Rise>
        {p.note ? <Label size={20} style={{marginTop: 26, opacity: ease(f, flipAt + 30, flipAt + 44, 0, 1)}}>{p.note}</Label> : null}
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- Waterfall: kalem kalem toplam (ör. ÖTV + KDV = 12,47 TL) ----------
export const Waterfall: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const items: P[] = p.items ?? [];
  const total = p.total !== undefined ? Number(p.total) : items.reduce((a, it) => a + Number(it.value), 0);
  const W = V ? 900 : 1400;
  const H = V ? 560 : 440;
  const max = Math.max(total, ...items.map((it) => Number(it.value))) * 1.12;
  const y = (v: number) => H - (v / max) * H;
  const n = items.length + 1;
  const bw = Math.min(180, (W / n) * 0.6);
  const gap = W / n;
  let run = 0;
  const t0 = at(p.cue);
  return (
    <AbsoluteFill>
      <BgMesh tint={col(p.color, T.c.hero)} />
      <Stage>
        {p.title ? <Words text={p.title} delay={t0} size={64} align="center" style={{marginBottom: 30}} /> : null}
        <svg width={W} height={H + 90} style={{overflow: 'visible'}}>
          {items.map((it, i) => {
            const v = Number(it.value);
            const k = spring({frame: f - at(it.cue ?? p.cue) - (it.cue ? 0 : 10 + i * 10), fps, config: T.spring.smooth});
            const base = run;
            run += v;
            const x = i * gap + (gap - bw) / 2;
            const top = y(base + v * k);
            const bot = y(base);
            const c = col(it.color, T.c.accent);
            return (
              <g key={i} opacity={interpolate(k, [0, 0.2], [0, 1], clamp)}>
                <rect x={x} y={top} width={bw} height={Math.max(bot - top, 1)} rx={8} fill={c} fillOpacity={0.85} />
                {i > 0 ? <line x1={x - (gap - bw)} x2={x} y1={bot} y2={bot} stroke={T.c.dim} strokeDasharray="4 6" /> : null}
                <text x={x + bw / 2} y={top - 14} textAnchor="middle" fill={T.c.text} fontFamily={T.f.mono} fontSize={26} fontWeight={800}>+{fmtTR(v, it.dec ?? 2)}</text>
                <text x={x + bw / 2} y={H + 40} textAnchor="middle" fill={T.c.dim} fontFamily={T.f.display} fontSize={24} fontWeight={700}>{it.label}</text>
              </g>
            );
          })}
          {(() => {
            const kt = spring({frame: f - at(p.totalCue ?? p.cue) - (p.totalCue ? 0 : 20 + items.length * 10), fps, config: T.spring.bouncy});
            const x = items.length * gap + (gap - bw) / 2;
            const c = col(p.totalColor, T.c.down);
            return (
              <g opacity={interpolate(kt, [0, 0.2], [0, 1], clamp)}>
                <rect x={x} y={y(total * kt)} width={bw} height={H - y(total * kt)} rx={8} fill={c} />
                <text x={x + bw / 2} y={y(total * kt) - 16} textAnchor="middle" fill={c} fontFamily={T.f.display} fontSize={44} fontWeight={900}>{p.totalText ?? fmtTR(total, 2)}</text>
                <text x={x + bw / 2} y={H + 40} textAnchor="middle" fill={T.c.text} fontFamily={T.f.display} fontSize={26} fontWeight={800}>{p.totalLabel ?? 'TOPLAM'}</text>
              </g>
            );
          })()}
          <line x1={0} x2={W} y1={H} y2={H} stroke={T.c.line} />
        </svg>
        {p.source ? <Label size={18} style={{marginTop: 10}}>{p.source}</Label> : null}
      </Stage>
    </AbsoluteFill>
  );
};

// ---------- DominoChain: sebep → sonuç zinciri; taşlar sırayla devrilir, ok bir sonrakine geçer (30 Eyl QA önerisi) ----------
export const DominoChain: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const items: P[] = p.items ?? [];
  const n = Math.max(items.length, 1);
  const t0 = at(p.cue);
  const W = V ? 940 : 1640;
  const bw = V ? 820 : Math.min(360, (W - (n - 1) * 70) / n);
  return (
    <AbsoluteFill>
      <BgMesh tint={col(p.color, T.c.down)} />
      <Stage>
        {p.title ? <Words text={p.title} delay={t0} size={V ? 70 : 72} align="center" style={{marginBottom: V ? 40 : 70}} /> : null}
        <div style={{display: 'flex', flexDirection: V ? 'column' : 'row', alignItems: 'center', gap: V ? 30 : 0}}>
          {items.map((it, i) => {
            const cueAt = at(it.cue ?? p.cue) + (it.cue ? 0 : 12 + i * 22);
            const up = spring({frame: f - cueAt, fps, config: T.spring.bouncy});
            const tip = spring({frame: f - cueAt - 14, fps, config: T.spring.heavy}); // devrilme (son taş dik kalır)
            const last = i === items.length - 1;
            const c = last ? col(p.color, T.c.down) : col(it.color, T.c.accent);
            const arrow = ease(f, cueAt + 10, cueAt + 24, 0, 1, T.ease.inOut);
            return (
              <React.Fragment key={i}>
                <div style={{width: bw, opacity: interpolate(up, [0, 0.3], [0, 1], clamp), transformOrigin: V ? '0% 100%' : '100% 100%',
                  transform: `translateY(${interpolate(up, [0, 1], [60, 0])}px) ${!last && !V ? `rotate(${interpolate(tip, [0, 1], [0, 8])}deg)` : ''}`}}>
                  <div style={{borderRadius: 22, padding: V ? '24px 30px' : '30px 28px', minHeight: V ? 0 : 230, boxSizing: 'border-box',
                    background: `linear-gradient(160deg, ${c}30, ${c}0c)`, border: `2px solid ${c}${last ? 'ff' : '88'}`,
                    boxShadow: last ? `0 0 60px ${c}55` : '0 30px 60px -30px #000'}}>
                    <Label size={20} color={c}>{String(i + 1).padStart(2, '0')}{it.kicker ? ` · ${it.kicker}` : ''}</Label>
                    <div style={{fontFamily: T.f.display, fontWeight: 800, fontSize: fitSize(String(it.title ?? ''), V ? 52 : 44, bw - 60, T.f.display, 800), color: T.c.text, marginTop: 10, lineHeight: 1.1}}>{it.title}</div>
                    {it.sub ? <div style={{fontFamily: T.f.display, fontSize: V ? 30 : 26, color: T.c.dim, marginTop: 10, lineHeight: 1.25}}>{it.sub}</div> : null}
                  </div>
                </div>
                {!last ? (
                  <svg width={V ? 40 : 70} height={V ? 40 : 40} style={{flexShrink: 0, transform: V ? 'rotate(90deg)' : undefined}}>
                    <path d="M4 20 H56 M44 8 L58 20 L44 32" fill="none" stroke={c} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round"
                      strokeDasharray={80} strokeDashoffset={80 * (1 - arrow)} />
                  </svg>
                ) : null}
              </React.Fragment>
            );
          })}
        </div>
      </Stage>
    </AbsoluteFill>
  );
};

const Fallback: React.FC<{p: P}> = ({p}) => {
  const {at} = useCue();
  return (
    <AbsoluteFill>
      <BgMesh />
      <Stage><Words text={p.title ?? p.symbol ?? ''} delay={at(p.cue)} size={84} align="center" /></Stage>
    </AbsoluteFill>
  );
};
