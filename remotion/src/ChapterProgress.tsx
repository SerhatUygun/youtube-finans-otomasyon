import React from 'react';
import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {INK, MUTED, NEUTRAL} from './theme';

export type Chapter = {label: string; startSeconds: number};
export type ChapterProgressProps = {
  chapters: Chapter[];
  totalSeconds?: number;
  fps?: number;
};

export const defaultChapterProgressProps: ChapterProgressProps = {
  chapters: [
    {label: '01. Olay', startSeconds: 0},
    {label: '02. Neden-Sonuc', startSeconds: 15},
    {label: '03. Etki', startSeconds: 30},
    {label: '04. Buyuk Resim', startSeconds: 45},
  ],
  totalSeconds: 60,
  fps: 30,
};

// 18 Eyl eklendi (SIFIR_MALIYET rehberi Modul 6) -- VIDEO BOYUNCA ustte ince, yari-seffaf
// bolum cubugu. animated_captions ile AYNI desen: seffaf WebM olarak render edilip
// s07_edit.py tarafindan en ust katman olarak overlay edilir (bkz. edit.chapter_bar).
// Diger sablonlarin aksine TEK segment degil, videonun TAMAMI kadar surer.
export const ChapterProgress: React.FC<ChapterProgressProps> = ({chapters, totalSeconds}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const t = frame / fps;
  const total = Math.max(totalSeconds ?? 60, 1);

  // Giris: ilk 20 kare boyunca ustten kayarak belirir, sonra sabit kalir.
  const barIn = interpolate(frame, [0, 20], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  const activeIdx = (() => {
    let idx = 0;
    for (let i = 0; i < chapters.length; i++) {
      if (t >= chapters[i].startSeconds) idx = i;
    }
    return idx;
  })();

  const barHeight = Math.round(height * 0.008);
  const barY = height * 0.035;

  return (
    <div style={{width, height, position: 'relative', fontFamily: '"Segoe UI", Arial, sans-serif'}}>
      <div style={{
        position: 'absolute', left: width * 0.06, right: width * 0.06, top: barY,
        opacity: barIn, transform: `translateY(${(1 - barIn) * -14}px)`,
      }}>
        {/* Ince zemin cizgisi */}
        <div style={{
          position: 'relative', height: barHeight, borderRadius: barHeight,
          background: 'rgba(255,255,255,0.14)', display: 'flex', overflow: 'hidden',
        }}>
          {chapters.map((c, i) => {
            const segStart = c.startSeconds;
            const segEnd = i + 1 < chapters.length ? chapters[i + 1].startSeconds : total;
            const segFrac = Math.max((segEnd - segStart) / total, 0.001);
            const filled = i < activeIdx ? 1 : i === activeIdx
              ? interpolate(t, [segStart, segEnd], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})
              : 0;
            return (
              <div key={i} style={{width: `${segFrac * 100}%`, position: 'relative', marginRight: 2}}>
                <div style={{
                  position: 'absolute', inset: 0, borderRadius: barHeight,
                  background: NEUTRAL, opacity: 0.22,
                }} />
                <div style={{
                  position: 'absolute', top: 0, bottom: 0, left: 0, width: `${filled * 100}%`,
                  background: NEUTRAL, borderRadius: barHeight, boxShadow: `0 0 8px ${NEUTRAL}`,
                }} />
              </div>
            );
          })}
        </div>
        {/* Etiketler: sadece aktif bolum tam opak, digerleri sonuk. */}
        <div style={{display: 'flex', marginTop: height * 0.012}}>
          {chapters.map((c, i) => {
            const segStart = c.startSeconds;
            const segEnd = i + 1 < chapters.length ? chapters[i + 1].startSeconds : total;
            const segFrac = Math.max((segEnd - segStart) / total, 0.001);
            const active = i === activeIdx;
            return (
              <div key={i} style={{
                width: `${segFrac * 100}%`, textAlign: 'left',
                fontSize: width * 0.011, fontWeight: active ? 800 : 500,
                color: active ? INK : MUTED, opacity: active ? 1 : 0.55,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                letterSpacing: 0.4,
              }}>
                {c.label}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
