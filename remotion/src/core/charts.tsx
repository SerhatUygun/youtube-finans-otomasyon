// Veri görselleştirme bileşenleri: çizgi grafik, gösterge, noktalı ızgara, yarım daire meclis.
import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {T, fmtTR} from './theme';
import {clamp, ease} from './kit';

// ---------------- Çizgi grafik ----------------
export type HLine = {value: number; label: string; color: string; delay: number; dashed?: boolean};
export type Marker = {index: number; label: string; color: string; delay: number; above?: boolean};

export const LineChart: React.FC<{
  data: number[]; labels?: string[]; w: number; h: number; color: string; delay?: number; dur?: number;
  min?: number; max?: number; hlines?: HLine[]; markers?: Marker[]; dec?: number; prefix?: string; suffix?: string;
  showHead?: boolean; band?: {from: number; to: number; color: string; delay: number; label?: string}[];
}> = ({data, labels = [], w, h, color, delay = 0, dur = 60, min, max, hlines = [], markers = [], dec = 0, prefix = '', suffix = '', showHead = true, band = []}) => {
  const frame = useCurrentFrame();
  const lo = min ?? Math.min(...data) * 0.995;
  const hi = max ?? Math.max(...data) * 1.005;
  const padL = 10;
  const padR = 150;
  const X = (i: number) => padL + (i / (data.length - 1)) * (w - padL - padR);
  const Y = (v: number) => h - ((v - lo) / (hi - lo)) * h;
  const pts = data.map((v, i) => [X(i), Y(v)] as const);
  // Kümülatif uzunluk -> çizim ilerlemesi
  const seg: number[] = [0];
  for (let i = 1; i < pts.length; i++) seg.push(seg[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const total = seg[seg.length - 1];
  const prog = ease(frame, delay, delay + dur, 0, 1, T.ease.inOut);
  const drawn = prog * total;
  let k = 0;
  while (k < seg.length - 1 && seg[k + 1] < drawn) k++;
  const t = k < seg.length - 1 ? (drawn - seg[k]) / Math.max(seg[k + 1] - seg[k], 0.001) : 1;
  const hx = k < pts.length - 1 ? pts[k][0] + (pts[k + 1][0] - pts[k][0]) * t : pts[k][0];
  const hy = k < pts.length - 1 ? pts[k][1] + (pts[k + 1][1] - pts[k][1]) * t : pts[k][1];
  const headIdx = Math.min(Math.round(k + t), data.length - 1);
  const headVal = data[headIdx];
  const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const area = `${d} L${pts[pts.length - 1][0]},${h} L${pts[0][0]},${h} Z`;
  const gid = `g${color.replace('#', '')}${w}${h}`;
  const pulse = 1 + Math.sin(frame / 6) * 0.25;
  return (
    <svg width={w} height={h + 40} style={{overflow: 'visible'}}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.35} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
        <clipPath id={`${gid}c`}>
          <rect x={0} y={-50} width={hx} height={h + 100} />
        </clipPath>
      </defs>
      {/* yatay ızgara */}
      {[0, 0.25, 0.5, 0.75, 1].map((g, i) => (
        <line key={i} x1={0} x2={w - padR + 20} y1={h * g} y2={h * g} stroke={T.c.line} strokeWidth={1}
          opacity={ease(frame, delay - 20 + i * 3, delay + i * 3, 0, 1)} />
      ))}
      {band.map((b, i) => {
        const o = ease(frame, b.delay, b.delay + 18, 0, 1);
        const y1 = Y(b.to);
        const y2 = Y(b.from);
        return (
          <g key={`b${i}`} opacity={o}>
            <rect x={0} y={y1} width={(w - padR + 20) * o} height={y2 - y1} fill={b.color} opacity={0.14} />
            {b.label ? (
              <text x={12} y={y1 - 10} fill={b.color} fontFamily={T.f.mono} fontSize={20} fontWeight={700} letterSpacing="0.1em">{b.label}</text>
            ) : null}
          </g>
        );
      })}
      <path d={area} fill={`url(#${gid})`} clipPath={`url(#${gid}c)`} />
      <path d={d} fill="none" stroke={color} strokeWidth={5} strokeLinejoin="round" strokeLinecap="round"
        strokeDasharray={total} strokeDashoffset={total - drawn} style={{filter: `drop-shadow(0 0 10px ${color}88)`}} />
      {hlines.map((l, i) => {
        const o = ease(frame, l.delay, l.delay + 20, 0, 1);
        const y = Y(l.value);
        return (
          <g key={`h${i}`} opacity={o}>
            <line x1={0} x2={(w - padR + 20) * o} y1={y} y2={y} stroke={l.color} strokeWidth={2.5} strokeDasharray={l.dashed === false ? undefined : '10 10'} />
            <rect x={w - padR + 28} y={y - 20} width={padR - 20} height={40} rx={10} fill={l.color} opacity={0.16} />
            <text x={w - padR + 40} y={y + 8} fill={l.color} fontFamily={T.f.mono} fontSize={22} fontWeight={700}>{l.label}</text>
          </g>
        );
      })}
      {markers.map((m, i) => {
        const p = ease(frame, m.delay, m.delay + 16, 0, 1, T.ease.out);
        const [mx, my] = pts[m.index];
        const up = m.above !== false;
        return (
          <g key={`m${i}`} opacity={p}>
            <circle cx={mx} cy={my} r={9 * p} fill={m.color} />
            <circle cx={mx} cy={my} r={9 + 14 * p} fill="none" stroke={m.color} strokeWidth={2} opacity={1 - p * 0.6} />
            <line x1={mx} x2={mx} y1={my + (up ? -14 : 14)} y2={my + (up ? -60 : 60) * p} stroke={m.color} strokeWidth={2} />
            <text x={mx} y={my + (up ? -72 : 92) * p} textAnchor="middle" fill={m.color} fontFamily={T.f.display} fontSize={28} fontWeight={800}>{m.label}</text>
          </g>
        );
      })}
      {showHead && prog > 0.01 ? (
        <g>
          <circle cx={hx} cy={hy} r={16 * pulse} fill={color} opacity={0.18} />
          <circle cx={hx} cy={hy} r={8} fill={color} stroke={T.c.bg} strokeWidth={3} />
          <g transform={`translate(${hx + 18}, ${hy - 22})`}>
            <rect width={132} height={44} rx={10} fill={T.c.bg} stroke={color} strokeWidth={1.5} />
            <text x={66} y={30} textAnchor="middle" fill={T.c.text} fontFamily={T.f.mono} fontSize={22} fontWeight={700}>
              {/* yüzde değişimde Türkçe işaret: −%10,6 / +%5,2 (eskiden "%-10,6") */}
              {prefix === '%' ? `${headVal < 0 ? '−' : headVal > 0 ? '+' : ''}%${fmtTR(Math.abs(headVal), dec)}${suffix}` : `${prefix}${fmtTR(headVal, dec)}${suffix}`}
            </text>
          </g>
        </g>
      ) : null}
      {labels.length ? (
        [0, Math.floor((labels.length - 1) / 2), labels.length - 1].map((li, i) => (
          <text key={`l${i}`} x={X(li)} y={h + 34} textAnchor={i === 0 ? 'start' : i === 2 ? 'end' : 'middle'} fill={T.c.dim}
            fontFamily={T.f.mono} fontSize={19} opacity={ease(frame, delay, delay + 20, 0, 1)}>{labels[li]}</text>
        ))
      ) : null}
    </svg>
  );
};

// ---------------- Yarım daire gösterge ----------------
export const Gauge: React.FC<{
  value: number; from?: number; delay?: number; size: number; color: string; label?: string; suffix?: string; dec?: number; appearAt?: number;
}> = ({value, from = 0, delay = 0, size, color, label, suffix = '%', dec = 0, appearAt}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = spring({frame: frame - delay, fps, config: T.spring.count});
  const v = interpolate(p, [0, 1], [from, value]);
  const r = size / 2 - 22;
  const cx = size / 2;
  const cy = size / 2;
  const arc = (a0: number, a1: number) => {
    const p0 = [cx + r * Math.cos(a0), cy + r * Math.sin(a0)];
    const p1 = [cx + r * Math.cos(a1), cy + r * Math.sin(a1)];
    return `M${p0[0]},${p0[1]} A${r},${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${p1[0]},${p1[1]}`;
  };
  const A0 = Math.PI;
  const A1 = Math.PI + Math.PI * (v / 100);
  const ap = appearAt ?? delay - 12;
  const appear = ease(frame, ap, ap + 20, 0, 1);
  const needle = A1;
  const ticks = Array.from({length: 21});
  return (
    <div style={{position: 'relative', width: size, height: size / 2 + size * 0.22 + 70, opacity: appear}}>
      <svg width={size} height={size / 2 + 20} style={{overflow: 'visible'}}>
        {ticks.map((_, i) => {
          const a = Math.PI + (Math.PI * i) / 20;
          const r1 = r + 30;
          const r2 = r + (i % 5 === 0 ? 48 : 40);
          const lit = i / 20 <= v / 100;
          return (
            <line key={i} x1={cx + r1 * Math.cos(a)} y1={cy + r1 * Math.sin(a)} x2={cx + r2 * Math.cos(a)} y2={cy + r2 * Math.sin(a)}
              stroke={lit ? color : T.c.faint} strokeWidth={i % 5 === 0 ? 4 : 2} strokeLinecap="round" />
          );
        })}
        <path d={arc(Math.PI, 2 * Math.PI - 0.0001)} stroke={T.c.faint} strokeWidth={26} fill="none" strokeLinecap="round" opacity={0.6} />
        {v > 0.2 ? (
          <path d={arc(A0, A1)} stroke={color} strokeWidth={26} fill="none" strokeLinecap="round" style={{filter: `drop-shadow(0 0 16px ${color})`}} />
        ) : null}
        <line x1={cx} y1={cy} x2={cx + (r - 50) * Math.cos(needle)} y2={cy + (r - 50) * Math.sin(needle)} stroke={T.c.text} strokeWidth={6} strokeLinecap="round" />
        <circle cx={cx} cy={cy} r={16} fill={T.c.text} />
        <circle cx={cx} cy={cy} r={7} fill={T.c.bg} />
      </svg>
      <div style={{position: 'absolute', top: size / 2 + 26, width: '100%', textAlign: 'center'}}>
        <span style={{fontFamily: T.f.display, fontWeight: 900, fontSize: size * 0.2, color: T.c.text, letterSpacing: '-0.04em', fontVariantNumeric: 'tabular-nums'}}>
          {frame < delay - 2 ? '—' : `%${fmtTR(v, dec)}`}
        </span>
        {label ? (
          <div style={{fontFamily: T.f.mono, fontSize: 22, letterSpacing: '0.16em', color: T.c.dim, marginTop: 6, textTransform: 'uppercase'}}>{label}</div>
        ) : null}
      </div>
      {suffix === '' ? null : null}
    </div>
  );
};

// ---------------- Nokta ızgarası (oy / üye sayımı) ----------------
export const DotGrid: React.FC<{
  n: number; lit: number; cols: number; delay?: number; size?: number; gap?: number; color: string; litDelay?: number; off?: string;
}> = ({n, lit, cols, delay = 0, size = 44, gap = 16, color, litDelay, off = T.c.faint}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const ld = litDelay ?? delay + 10;
  return (
    <div style={{display: 'grid', gridTemplateColumns: `repeat(${cols}, ${size}px)`, gap}}>
      {Array.from({length: n}).map((_, i) => {
        const p = spring({frame: frame - delay - i * 2, fps, config: T.spring.bouncy});
        const on = ease(frame, ld + i * 3, ld + i * 3 + 8, 0, 1) * (i < lit ? 1 : 0);
        return (
          <div key={i} style={{
            width: size, height: size, borderRadius: '50%', transform: `scale(${p})`,
            background: on > 0.5 ? color : off, boxShadow: on > 0.5 ? `0 0 ${20 * on}px ${color}` : 'none',
            border: `2px solid ${on > 0.5 ? color : 'rgba(255,255,255,0.12)'}`,
          }} />
        );
      })}
    </div>
  );
};

// ---------------- Yarım daire meclis (Senato 99 oy) ----------------
export const Hemicycle: React.FC<{yes: number; no: number; delay?: number; w: number; yesColor: string; noColor: string}> = ({
  yes, no, delay = 0, w, yesColor, noColor,
}) => {
  const frame = useCurrentFrame();
  const total = yes + no;
  const rows = 5;
  // Her sıradaki koltuk sayısı yarıçapla orantılı
  const radii = Array.from({length: rows}, (_, i) => w * 0.22 + i * (w * 0.27) / rows);
  const sumR = radii.reduce((a, b) => a + b, 0);
  const counts = radii.map((r) => Math.round((r / sumR) * total));
  counts[rows - 1] += total - counts.reduce((a, b) => a + b, 0);
  const seats: {x: number; y: number; a: number}[] = [];
  radii.forEach((r, ri) => {
    for (let j = 0; j < counts[ri]; j++) {
      const a = Math.PI - (Math.PI * (j + 0.5)) / counts[ri];
      seats.push({x: w / 2 + r * Math.cos(a), y: w / 2 - r * Math.sin(a), a});
    }
  });
  seats.sort((s1, s2) => s2.a - s1.a);
  return (
    <svg width={w} height={w / 2 + 20} style={{overflow: 'visible'}}>
      {seats.map((s, i) => {
        const o = ease(frame, delay + i * 0.5, delay + i * 0.5 + 10, 0, 1);
        const c = i < yes ? yesColor : noColor;
        return <circle key={i} cx={s.x} cy={s.y} r={w * 0.017 * o} fill={c} opacity={0.95} />;
      })}
    </svg>
  );
};

// ---------------- Yatay çubuk ----------------
export const HBar: React.FC<{
  value: number; max: number; w: number; h?: number; color: string; delay?: number; label: string; valueText: string; dimBar?: boolean; labelSize?: number; ghostFrom?: number;
}> = ({value, max, w, h = 64, color, delay = 0, label, valueText, dimBar, labelSize = 22, ghostFrom}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = spring({frame: frame - delay, fps, config: T.spring.heavy});
  const bw = (value / max) * w * p;
  return (
    <div style={{display: 'flex', flexDirection: 'column', gap: 12, opacity: Math.max(interpolate(p, [0, 0.3], [0, 1], clamp), ghostFrom !== undefined ? ease(frame, ghostFrom, ghostFrom + 12, 0, 0.55) : 0)}}>
      <div style={{fontFamily: T.f.mono, fontSize: labelSize, letterSpacing: '0.14em', color: T.c.dim, textTransform: 'uppercase'}}>{label}</div>
      <div style={{display: 'flex', alignItems: 'center', gap: 24}}>
        <div style={{width: w, height: h, background: 'rgba(255,255,255,0.04)', borderRadius: 14, overflow: 'hidden', border: `1px solid ${T.c.line}`}}>
          <div style={{
            width: bw, height: '100%', borderRadius: 14,
            background: dimBar ? `repeating-linear-gradient(135deg, ${color}55 0 10px, ${color}22 10px 20px)` : `linear-gradient(90deg, ${color}aa, ${color})`,
            boxShadow: dimBar ? 'none' : `0 0 30px ${color}66`,
          }} />
        </div>
        <div style={{fontFamily: T.f.display, fontWeight: 800, fontSize: h * 0.9, color: dimBar ? T.c.dim : T.c.text, letterSpacing: '-0.03em', fontVariantNumeric: 'tabular-nums', minWidth: 200}}>
          {p > 0.02 ? valueText : ''}
        </div>
      </div>
    </div>
  );
};
