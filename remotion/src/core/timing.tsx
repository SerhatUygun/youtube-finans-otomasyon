// Veri güdümlü zamanlama: zaman çizelgesi (seslendirme segmentleri + kelime zamanları) props'tan
// gelir; sahneler "cue" dizgeleriyle seslendirmeye kilitlenir.
//   "12"          -> 12. segmentin başı
//   "12:yüzde"    -> 12. segmentte "yüzde" ile başlayan ilk kelime
//   "12:yüzde#2"  -> ... ikinci eşleşme
//   "12:3"        -> 12. segmentin 3. kelimesi (0 tabanlı; 1-2 hane)
//   "12:4147"     -> 3+ haneli rakam: ekranda "4.147…" ile başlayan kelime (nokta/virgül yok sayılır)
//   "12:end"      -> 12. segmentin sonu
//   "+15"/"-6" son ek: kare ofseti ("12:yüzde+10")
import React, {createContext, useContext} from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {clamp} from './kit';
import {T} from './theme';

export type Word = {w: string; s: number; e: number};
export type Seg = {i: number; s: number; e: number; text: string; words: Word[]};
export type Timeline = {fps: number; total: number; outroStart: number; segments: Seg[]};
export type Cue = string | number | undefined;

const norm = (s: string) => s.toLocaleLowerCase('tr').replace(/[^\p{L}\p{N}]/gu, '');

export function cueAbs(tl: Timeline, c: Cue, lead = 4): number {
  if (c === undefined || c === null || c === '') return 0;
  const m = String(c).trim().match(/^(\d+)(?::(.+?))?([+-]\d+)?$/);
  if (!m) return 0;
  const off = m[3] ? Number(m[3]) : 0;
  const key = m[2];
  const seg = tl.segments[Math.max(0, Math.min(Number(m[1]), tl.segments.length - 1))];
  if (!seg) return 0;
  if (key === undefined || key === '') return seg.s - lead + off;
  if (key === 'end') return seg.e + off;
  // 1-2 hane = kelime indeksi; 3+ hane (fiyat, yıl: "12:4147") ekrandaki rakamla eşleşir
  if (/^\d{1,2}$/.test(key)) {
    const w = seg.words[Math.min(Number(key), seg.words.length - 1)];
    return (w ? w.s : seg.s) - 3 + off;
  }
  const [word, nth] = key.split('#');
  const want = norm(word);
  // 30 Eyl QA bulgusu: 'tam' -> 'tampon' kilitleniyordu. Segmentte TAM eşleşen kelime varsa onu, yoksa öneki kullan
  // (Türkçe ekler için önek gerekli: 'petrol' -> 'petrolün').
  const exact = seg.words.some((w) => norm(w.w) === want);
  let count = 0;
  for (const w of seg.words) {
    if (exact ? norm(w.w) === want : norm(w.w).startsWith(want)) {
      count++;
      if (count >= (Number(nth) || 1)) return w.s - 3 + off;
    }
  }
  return seg.s - lead + off; // bulunamadı: segment başı
}

type Ctx = {tl: Timeline; start: number; dur: number; layout: 'h' | 'v'};
const SceneCtx = createContext<Ctx>({tl: {fps: 30, total: 1, outroStart: 1, segments: []}, start: 0, dur: 1, layout: 'h'});

export const SceneProvider: React.FC<Ctx & {children: React.ReactNode}> = ({children, ...v}) => (
  <SceneCtx.Provider value={v}>{children}</SceneCtx.Provider>
);

// Sahne içi: cue -> sahneye göreli kare
export const useCue = () => {
  const {tl, start, dur, layout} = useContext(SceneCtx);
  const at = (c: Cue, fallback = 0) => (c === undefined ? fallback : cueAbs(tl, c) - start);
  return {at, dur, layout, tl, start};
};

export const SceneExit: React.FC<{children: React.ReactNode; exit?: number}> = ({children, exit = 10}) => {
  const f = useCurrentFrame();
  const {dur} = useContext(SceneCtx);
  const o = interpolate(f, [dur - exit, dur], [1, 0], {...clamp, easing: T.ease.in});
  const s = interpolate(f, [dur - exit, dur], [1, 1.05], {...clamp, easing: T.ease.in});
  const b = interpolate(f, [dur - exit, dur], [0, 10], {...clamp, easing: T.ease.in});
  return <AbsoluteFill style={{opacity: o, transform: `scale(${s})`, filter: b > 0.1 ? `blur(${b}px)` : undefined}}>{children}</AbsoluteFill>;
};

// Güvenli alan: yatayda üst HUD/alt altyazı+ticker; dikeyde platform arayüzü (üst %12, alt %22).
export const Stage: React.FC<{children: React.ReactNode; style?: React.CSSProperties; center?: boolean}> = ({children, style, center = true}) => {
  const {layout} = useContext(SceneCtx);
  const box = layout === 'v'
    ? {top: 250, left: 70, width: 1080 - 140, height: 1920 - 250 - 520}
    : {top: T.safe.top, left: T.safe.side, width: 1920 - 2 * T.safe.side, height: T.safe.bottom - T.safe.top};
  return (
    <div style={{position: 'absolute', ...box, display: 'flex', flexDirection: 'column', justifyContent: center ? 'center' : 'flex-start',
      alignItems: center ? 'center' : 'stretch', ...style}}>
      {children}
    </div>
  );
};
