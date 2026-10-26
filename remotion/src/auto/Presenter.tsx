// 9 Eki: 2D çizim sunucu v2 — kanal sahibinin stilize karakteri (Casual Finance sadeliği, kalın kontur).
//  - Ağız: kelime zamanlarından ağız şekli (vis: kare başına harf X/M/A/E/O/F) × ses enerjisi (mouth 0..1)
//  - İfade: neutral | happy | worried | surprised (sahne yönünden)
//  - Jest: point | explain | think | shrug | up — iki parçalı kollar, pozlar arası yumuşak geçiş
//  - Göz kırpma, nefes, konuşurken kafa sallama/kaş. Tamamen SVG: keskin, hızlı, GPU yok.
import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';

const C = {
  skin: '#F2C7A5', skinShade: '#E0A988', blush: '#E99A86',
  hair: '#5A3A24', hairHi: '#76503A', beard: '#5E3D27', brow: '#3F2716',
  eyeW: '#FFFFFF', iris: '#5B3A22', mouth: '#4A1717', tongue: '#D9666A', teeth: '#FFFFFF',
  shirt: '#1F2C4A', shirtHi: '#2A3B63', collar: '#F3F1EA', ink: '#1A1210',
};
const INK = 5; // kontur kalınlığı (viewBox biriminde)
// v3: sakal dokusu — sabit (deterministik) tüy konumları [x, y, açı]
const BEARD_STROKES: [number, number, number][] = [
  [128, 262, 0.3], [140, 284, 0.5], [156, 302, 0.8], [174, 318, 1.1], [196, 326, 1.5], [218, 318, 2.0], [238, 304, 2.3], [256, 286, 2.6],
  [270, 264, 2.8], [120, 236, 0.2], [282, 238, 2.9], [148, 266, 0.6], [252, 268, 2.5], [182, 296, 1.2], [214, 296, 1.9], [166, 280, 0.9], [236, 282, 2.2],
];

export type Expr = 'neutral' | 'happy' | 'worried' | 'surprised';
export type Gesture = 'point' | 'explain' | 'think' | 'shrug' | 'up' | 'hold' | 'present' | 'wave';
export type GestureCue = {at: number; kind: Gesture; len?: number};

export type PresenterProps = {
  mouth?: number[];          // kare başına ses enerjisi 0..1
  vis?: string;              // kare başına ağız şekli harfi
  from?: number;             // mouth[0]'ın denk geldiği kare
  gestures?: GestureCue[];
  expr?: Expr | {at: number; e: Expr}[];
  size?: number;             // piksel yükseklik
  mirror?: boolean;          // true: sola bakar
  crop?: number;             // 0..1: alttan kırpma (bel üstü görünüm) — sadece görsel kesim
};

// Kol pozları: [omuz->dirsek açısı, dirsek->el açısı] (derece, y aşağı, 0 = sağ). L: izleyicinin solu.
type Pose = {L: [number, number]; R: [number, number]; sh: number; open: number};
const POSES: Record<'rest' | Gesture, Pose> = {
  rest: {L: [104, 96], R: [76, 84], sh: 0, open: 0},
  point: {L: [104, 96], R: [-8, -14], sh: -2, open: 0},
  explain: {L: [122, 215], R: [58, -35], sh: -3, open: 1},
  think: {L: [104, 96], R: [122, 255], sh: 0, open: 0},
  shrug: {L: [158, 222], R: [22, -42], sh: -12, open: 1},
  up: {L: [104, 96], R: [-58, -84], sh: -4, open: 0},
  hold: {L: [104, 96], R: [62, -38], sh: -2, open: 1}, // 19 Eki: nesneyi göğüs önünde avuçta tutar
  present: {L: [104, 96], R: [18, -4], sh: -3, open: 1}, // yana açık avuç: 'işte bu'
  wave: {L: [104, 96], R: [-62, -100], sh: -4, open: 1},
};
const lerpA = (a: number, b: number, k: number) => a + (b - a) * k;
const smooth = (k: number) => k * k * (3 - 2 * k);

export const poseAt = (f: number, gs: GestureCue[]): Pose => {
  let best: {k: number; g: Gesture} | null = null;
  for (const g of gs) {
    const len = g.len ?? 70;
    const d = f - g.at;
    if (d < 0 || d > len) continue;
    const k = smooth(d < 9 ? d / 9 : d > len - 12 ? (len - d) / 12 : 1);
    if (!best || k > best.k) best = {k, g: g.kind};
  }
  const r = POSES.rest;
  if (!best) return r;
  const t = POSES[best.g];
  const k = best.k;
  return {L: [lerpA(r.L[0], t.L[0], k), lerpA(r.L[1], t.L[1], k)], R: [lerpA(r.R[0], t.R[0], k), lerpA(r.R[1], t.R[1], k)],
    sh: lerpA(r.sh, t.sh, k), open: t.open * k};
};

export const EXPR: Record<Expr, {brow: number; tilt: number; smile: number; eye: number}> = {
  neutral: {brow: 0, tilt: 0, smile: 0.25, eye: 1},
  happy: {brow: -5, tilt: 0, smile: 1, eye: 0.85},
  worried: {brow: 2, tilt: 9, smile: -0.7, eye: 1},
  surprised: {brow: -13, tilt: 0, smile: 0, eye: 1.18},
};
export const exprAt = (f: number, e: PresenterProps['expr']): Expr => {
  if (!e) return 'neutral';
  if (typeof e === 'string') return e;
  let cur: Expr = 'neutral';
  for (const x of e) if (f >= x.at) cur = x.e;
  return cur;
};

const Arm: React.FC<{x: number; y: number; a: [number, number]; open: number; side: 1 | -1}> = ({x, y, a, open, side}) => {
  const U = 92, F = 84;
  const r = (d: number) => (d * Math.PI) / 180;
  const ex = x + U * Math.cos(r(a[0])), ey = y + U * Math.sin(r(a[0]));
  const hx = ex + F * Math.cos(r(a[1])), hy = ey + F * Math.sin(r(a[1]));
  const d = `M${x} ${y} L${ex} ${ey} L${hx} ${hy}`;
  return (
    <g>
      <path d={d} stroke={C.ink} strokeWidth={34 + INK * 2} strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <path d={d} stroke={C.shirt} strokeWidth={34} strokeLinecap="round" strokeLinejoin="round" fill="none" />
      {/* el: açıkken avuç + başparmak, kapalıyken yumruk */}
      <g transform={`translate(${hx} ${hy}) rotate(${a[1] - 90})`}>
        <ellipse cx={0} cy={6} rx={17 + 3 * open} ry={19} fill={C.skin} stroke={C.ink} strokeWidth={INK} />
        {/* v3: parmak çizgileri + manşet */}
        {[-7, 0, 7].map((dx) => <path key={dx} d={`M${dx * (1 + 0.3 * open)} ${14} l ${dx * 0.2} ${8 + 4 * open}`} stroke={C.ink} strokeWidth={2.2} opacity={0.55} strokeLinecap="round" />)}
        <rect x={-19} y={-20} width={38} height={9} rx={4} fill={C.collar} stroke={C.ink} strokeWidth={3} />
        <path d={`M${side * (12 + 6 * open)} ${-2} L${side * (24 + 8 * open)} ${-12 - 4 * open}`} stroke={C.ink} strokeWidth={14 + INK} strokeLinecap="round" />
        <path d={`M${side * (12 + 6 * open)} ${-2} L${side * (24 + 8 * open)} ${-12 - 4 * open}`} stroke={C.skin} strokeWidth={14} strokeLinecap="round" />
      </g>
    </g>
  );
};

const Mouth: React.FC<{shape: string; amp: number; smile: number}> = ({shape, amp, smile}) => {
  const y = 262;
  const a = Math.min(1, 0.35 + amp); // şekil varsa en az biraz açık
  if (shape === 'X' || amp < 0.06) {
    const c = 6 * smile;
    return <path d={`M181 ${y} Q 200 ${y + c + 4} 219 ${y}`} stroke={C.mouth} strokeWidth={6} strokeLinecap="round" fill="none" />;
  }
  if (shape === 'M') return <path d={`M183 ${y + 2} L 217 ${y + 2}`} stroke={C.mouth} strokeWidth={8} strokeLinecap="round" />;
  if (shape === 'F') {
    return (
      <g>
        <path d={`M182 ${y} Q 200 ${y + 14} 218 ${y} Z`} fill={C.mouth} stroke={C.ink} strokeWidth={3} />
        <rect x={188} y={y - 2} width={24} height={7} rx={2} fill={C.teeth} />
      </g>
    );
  }
  const W = shape === 'E' ? 46 : shape === 'O' ? 26 : 38;
  const H = (shape === 'E' ? 16 : shape === 'O' ? 30 : 36) * a + 4;
  const rx = shape === 'O' ? W / 2 : W / 2;
  return (
    <g>
      <ellipse cx={200} cy={y + H / 2 - 2} rx={rx} ry={H / 2} fill={C.mouth} stroke={C.ink} strokeWidth={3} />
      {shape !== 'O' ? <rect x={200 - W / 2 + 6} y={y - 2} width={W - 12} height={Math.min(8, H / 3)} rx={3} fill={C.teeth} /> : null}
      {H > 18 ? <ellipse cx={200} cy={y + H * 0.78} rx={W * 0.28} ry={H * 0.18} fill={C.tongue} /> : null}
    </g>
  );
};

export const Presenter: React.FC<PresenterProps> = ({mouth = [], vis = '', from = 0, gestures = [], expr, size = 760, mirror = false, crop = 0}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const i = Math.max(0, f - from);
  const m = (k: number) => mouth[Math.min(Math.max(k, 0), mouth.length - 1)] ?? 0;
  const amp = mouth.length ? (m(i - 1) + 2 * m(i) + m(i + 1)) / 4 : 0;
  const shape = vis ? vis[Math.min(i, vis.length - 1)] ?? 'X' : amp > 0.06 ? 'A' : 'X';
  const talking = mouth.length ? Array.from({length: 12}, (_, j) => m(i - j)).reduce((a, b) => a + b, 0) / 12 : 0;
  const E = EXPR[exprAt(f, expr)];

  const blinkCycle = [97, 143, 71, 188, 120, 64, 151];
  let t = 0, bi = 0, blink = 0;
  while (t <= f) {
    const d = f - t;
    if (d < 5) blink = Math.sin((d / 5) * Math.PI);
    t += blinkCycle[bi++ % blinkCycle.length];
  }
  const eyeH = (1 - 0.92 * blink) * E.eye * (E.smile > 0.8 && talking < 0.2 ? 0.9 : 1);

  const P = poseAt(f, gestures);
  const breath = Math.sin((f / fps) * 2 * Math.PI * 0.25);
  const nod = Math.sin(f / 5.5) * 3.2 * talking + Math.sin(f / 23) * 1.2;
  const tilt = Math.sin(f / 41) * 2 + Math.sin(f / 9) * 1.4 * talking + (P.open > 0.5 && P.sh < -8 ? 6 : 0);
  const brow = E.brow - 5 * Math.min(talking * 1.6, 1) + Math.max(0, Math.sin(f / 13)) * 3 * talking;
  const pointing = gestures.some((g) => g.kind === 'point' && f >= g.at && f <= g.at + (g.len ?? 70));
  const lookX = pointing ? 7 : 0;
  const sh = P.sh + breath * 2;
  const H = 600 * (1 - crop);

  return (
    <svg viewBox={`0 0 400 ${H}`} width={(size * 400) / H} height={size} style={{overflow: 'visible', transform: mirror ? 'scaleX(-1)' : undefined}}>
      <g transform={`translate(0 ${breath * 2.5})`}>
        {/* gövde */}
        <path d={`M70 640 C 66 470, 105 ${398 + sh}, 200 ${392 + sh} C 295 ${398 + sh}, 334 470, 330 640 Z`} fill={C.shirt} stroke={C.ink} strokeWidth={INK} />
        <path d={`M200 ${394 + sh} C 250 ${398 + sh}, 290 425, 308 480 C 280 445, 245 425, 200 422 Z`} fill={C.shirtHi} opacity={0.55} />
        {/* v3: gövde gölgesi (sol yan), düğme patı, düğmeler, göğüs cebi, kırışıklıklar */}
        <path d={`M74 640 C 72 500, 96 ${430 + sh}, 128 ${408 + sh} C 112 470, 108 560, 112 640 Z`} fill={C.ink} opacity={0.16} />
        <path d={`M200 ${442 + sh} L 200 640`} stroke={C.ink} strokeWidth={3} opacity={0.55} />
        {[478, 530, 582].map((y) => <circle key={y} cx={207} cy={y + sh * 0.5} r={4.5} fill={C.collar} stroke={C.ink} strokeWidth={2} />)}
        <path d={`M232 ${492 + sh * 0.5} L 282 ${490 + sh * 0.5} L 280 ${532 + sh * 0.5} C 266 ${537 + sh * 0.5}, 248 ${537 + sh * 0.5}, 234 ${532 + sh * 0.5} Z`} fill={C.shirtHi} stroke={C.ink} strokeWidth={3} strokeLinejoin="round" />
        <path d={`M150 ${470 + sh * 0.5} C 160 ${500 + sh * 0.5}, 158 ${540 + sh * 0.5}, 150 ${570 + sh * 0.5}`} stroke={C.ink} strokeWidth={2.5} fill="none" opacity={0.35} strokeLinecap="round" />
        <path d={`M262 ${560 + sh * 0.5} C 272 ${580 + sh * 0.5}, 290 ${592 + sh * 0.5}, 304 ${596 + sh * 0.5}`} stroke={C.ink} strokeWidth={2.5} fill="none" opacity={0.3} strokeLinecap="round" />
        {/* boyun + yaka */}
        <path d={`M178 360 L 178 ${398 + sh} C 192 ${410 + sh}, 208 ${410 + sh}, 222 ${398 + sh} L 222 360 Z`} fill={C.skinShade} stroke={C.ink} strokeWidth={INK} />
        <path d={`M178 372 C 192 386, 210 386, 222 372 L 222 360 L 178 360 Z`} fill={C.ink} opacity={0.18} />
        <path d={`M165 ${392 + sh} L 200 ${442 + sh} L 235 ${392 + sh} L 222 ${386 + sh} L 200 ${414 + sh} L 178 ${386 + sh} Z`} fill={C.collar} stroke={C.ink} strokeWidth={4} strokeLinejoin="round" />
        {/* kollar */}
        <Arm x={112} y={432 + sh} a={P.L} open={P.open} side={-1} />
      </g>

      {/* baş */}
      <g transform={`translate(${lookX} ${38 + nod + breath * 1.5 + sh * 0.6}) rotate(${tilt} 200 330)`}>
        <ellipse cx={104} cy={205} rx={16} ry={24} fill={C.skinShade} stroke={C.ink} strokeWidth={INK} />
        <ellipse cx={296} cy={205} rx={16} ry={24} fill={C.skinShade} stroke={C.ink} strokeWidth={INK} />
        <path d="M108 170 C 108 95, 150 62, 200 62 C 250 62, 292 95, 292 170 C 292 245, 262 318, 200 330 C 138 318, 108 245, 108 170 Z" fill={C.skin} stroke={C.ink} strokeWidth={INK} />
        {/* v3: kulak içi + yüzün sağ yanında yumuşak gölge + alında ışık */}
        <path d="M100 194 C 96 204, 98 216, 106 222" stroke={C.ink} strokeWidth={3} fill="none" opacity={0.45} strokeLinecap="round" />
        <path d="M300 194 C 304 204, 302 216, 294 222" stroke={C.ink} strokeWidth={3} fill="none" opacity={0.45} strokeLinecap="round" />
        <path d="M262 92 C 284 112, 292 150, 290 182 C 286 240, 262 300, 222 324 C 254 290, 270 240, 272 186 C 274 146, 270 116, 262 92 Z" fill={C.skinShade} opacity={0.55} />
        <ellipse cx={176} cy={118} rx={34} ry={12} fill="#fff" opacity={0.18} transform="rotate(-12 176 118)" />
        <ellipse cx={142} cy={226} rx={18} ry={11} fill={C.blush} opacity={0.3 + 0.25 * Math.max(0, E.smile)} />
        <ellipse cx={258} cy={226} rx={18} ry={11} fill={C.blush} opacity={0.3 + 0.25 * Math.max(0, E.smile)} />
        {/* sakal + bıyık */}
        <path d="M110 200 C 112 270, 145 335, 200 342 C 255 335, 288 270, 290 200 C 280 235, 262 250, 248 252
                 C 236 238, 222 232, 200 232 C 178 232, 164 238, 152 252 C 138 250, 120 235, 110 200 Z" fill={C.beard} stroke={C.ink} strokeWidth={INK} strokeLinejoin="round" />
        {/* v3: sakal dokusu (kısa kıvrık tüyler, iki ton) */}
        {BEARD_STROKES.map(([x, y, r], k) => (
          <path key={k} d={`M${x} ${y} q ${3 * Math.cos(r)} ${7} ${6 * Math.cos(r)} ${12}`} stroke={k % 3 ? C.hair : C.brow} strokeWidth={2.4} fill="none" strokeLinecap="round" opacity={0.7} />
        ))}
        <Mouth shape={shape} amp={amp} smile={E.smile} />
        <path d="M156 247 C 172 231, 190 233, 200 239 C 210 233, 228 231, 244 247 C 228 245, 214 247, 200 251 C 186 247, 172 245, 156 247 Z" fill={C.beard} stroke={C.ink} strokeWidth={3} />
        {/* burun */}
        <path d="M200 168 C 196 194, 184 210, 191 218 C 198 225, 207 223, 213 218" stroke={C.ink} strokeWidth={4.5} strokeLinecap="round" fill="none" opacity={0.75} />
        {/* gözler */}
        {[150, 250].map((x) => (
          <g key={x}>
            <ellipse cx={x} cy={170} rx={22} ry={18 * eyeH} fill={C.eyeW} stroke={C.ink} strokeWidth={4} />
            {eyeH > 0.25 ? <circle cx={x + 3 + lookX * 0.8} cy={172} r={10.5 * Math.min(1, eyeH * 1.3)} fill={C.iris} stroke="#3b2414" strokeWidth={2} /> : null}
            {eyeH > 0.25 ? <circle cx={x + 1 + lookX * 0.8} cy={172} r={5 * Math.min(1, eyeH * 1.3)} fill={C.ink} /> : null}
            {eyeH > 0.25 ? <circle cx={x + 7 + lookX * 0.8} cy={166} r={3.4} fill="#fff" /> : null}
            {/* v3: kalın üst göz kapağı çizgisi + alt kapak gölgesi */}
            <path d={`M${x - 23} ${170 - 6 * eyeH} Q ${x} ${170 - 21 * eyeH} ${x + 24} ${170 - 7 * eyeH}`} stroke={C.ink} strokeWidth={5.5} fill="none" strokeLinecap="round" />
            <path d={`M${x - 15} ${188 + 2 * (eyeH - 1)} Q ${x} ${193} ${x + 15} ${188 + 2 * (eyeH - 1)}`} stroke={C.skinShade} strokeWidth={3} fill="none" strokeLinecap="round" />
          </g>
        ))}
        {/* kaşlar: endişede iç uçlar yukarı */}
        <path d={`M124 ${138 + brow} C 138 ${124 + brow}, 160 ${122 + brow - E.tilt}, 176 ${132 + brow - E.tilt}`} stroke={C.brow} strokeWidth={14} strokeLinecap="round" fill="none" />
        <path d={`M224 ${132 + brow - E.tilt} C 240 ${122 + brow - E.tilt}, 262 ${124 + brow}, 276 ${138 + brow}`} stroke={C.brow} strokeWidth={14} strokeLinecap="round" fill="none" />
        {/* saç */}
        <path d="M104 178 C 96 110, 120 52, 178 38 C 210 22, 262 30, 286 62 C 304 88, 302 140, 296 178
                 C 290 140, 280 118, 262 106 C 236 116, 206 112, 182 100 C 160 112, 138 116, 118 132 C 110 146, 106 162, 104 178 Z" fill={C.hair} stroke={C.ink} strokeWidth={INK} strokeLinejoin="round" />
        <path d="M150 58 C 180 34, 236 30, 268 52 C 238 44, 200 46, 170 64 Z" fill={C.hairHi} />
        {/* v3: yukarı taranmış saç tutamları + kısa yanlarda geçiş */}
        {[[140, 96, 168, 52], [172, 90, 196, 40], [206, 92, 226, 40], [236, 100, 256, 52], [258, 104, 280, 70]].map(([x1, y1, x2, y2], k) => (
          <path key={k} d={`M${x1} ${y1} Q ${(x1 + x2) / 2 - 6} ${(y1 + y2) / 2 - 8} ${x2} ${y2}`} stroke={k % 2 ? C.hairHi : C.brow} strokeWidth={3} fill="none" strokeLinecap="round" opacity={0.75} />
        ))}
        <path d="M108 150 C 110 166, 112 172, 116 178" stroke={C.hairHi} strokeWidth={6} fill="none" opacity={0.5} strokeLinecap="round" />
        <path d="M292 150 C 290 166, 288 172, 284 178" stroke={C.hairHi} strokeWidth={6} fill="none" opacity={0.5} strokeLinecap="round" />
      </g>

      {/* sağ kol başın önünde (düşünme: el çeneye) */}
      <g transform={`translate(0 ${breath * 2.5})`}>
        <Arm x={288} y={432 + sh} a={P.R} open={P.open} side={1} />
      </g>
    </svg>
  );
};

export default Presenter;
