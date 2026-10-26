import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {INK, NEUTRAL} from './theme';

// 18 Eyl eklendi (SIFIR_MALIYET rehberi Modul 4) -- kinetik altyazi renklendirmesi +
// tetikleyici-kelime emoji'si. Kucuk/basit tutulur: uzun bir sozluk yerine birkac
// belirgin finans terimi. Sayi/yuzde regex'i her zaman kontrol edilir (ondalik/binlik
// ayraciyla -- "42", "%42", "4.900" gibi).
const NUMBER_RE = /[\d]+([.,]\d+)?%?/;
const RISK_WORDS = ['dusus', 'düşüş', 'risk', 'kriz', 'cokus', 'çöküş', 'kayip', 'kayıp'];
const CURRENCY_WORDS = ['dolar', 'lira', 'altin', 'altın', 'tl', 'euro', 'gumus', 'gümüş'];
const EMOJI_BY_WORD: Record<string, string> = {
  dolar: '💵', faiz: '📈', altin: '🪙', altın: '🪙', dusus: '📉', düşüş: '📉', risk: '⚠️',
};
const GREEN = '#10B981';
const RED = '#EF4444';
const GOLD = '#F59E0B';

function normalizeWord(raw: string): string {
  return raw.toLocaleLowerCase('tr-TR').replace(/[^a-zçğıöşü0-9%]/g, '');
}

function colorForWord(raw: string, fallback: string): string {
  const w = normalizeWord(raw);
  if (NUMBER_RE.test(w) && /\d/.test(w)) return GREEN;
  if (RISK_WORDS.includes(w)) return RED;
  if (CURRENCY_WORDS.includes(w)) return GOLD;
  return fallback;
}

function emojiForWord(raw: string): string | null {
  return EMOJI_BY_WORD[normalizeWord(raw)] ?? null;
}

export type CueWord = {text: string; start: number; end: number};
export type Cue = {start: number; end: number; text?: string; words?: CueWord[]};
export type CaptionsProps = {
  cues: Cue[];
  totalSeconds?: number;
  fps?: number;
};

export const defaultCaptionsProps: CaptionsProps = {
  cues: [
    {start: 0, end: 1.2, text: 'Merhaba millet'},
    {start: 1.2, end: 2.6, text: 'bugun konumuz altin'},
  ],
  totalSeconds: 3,
  fps: 30,
};

// TikTok/CapCut tarzi animasyonlu altyazi -- SEFFAF arka plan (transparan WebM olarak render
// edilir, pipeline/stages/s07_edit.py ffmpeg overlay ile ana video uzerine bindirir). ffmpeg'in
// libass/drawtext tabanli altyazi motorunu HIC KULLANMAZ -> bu makinede libass ACCESS_VIOLATION
// ile cokuyor (bkz. config.yaml edit.burn_subtitles notu), bu yontem o sorunu tamamen atlar.
//
// cue.words varsa (s06_subtitles.py'nin ürettiği captions_words.json), her kelime kendi
// [start,end] penceresinde tek tek renklenip hafifçe büyür -- karaoke/CapCut tarzi aktif-kelime
// vurgusu. words yoksa (eski/yedek yol) tüm blok tek parça pop-in yapar (önceki davranış).
export const Captions: React.FC<CaptionsProps> = ({cues}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const t = frame / fps;

  const idx = cues.findIndex((c) => t >= c.start && t < c.end);
  if (idx === -1) {
    return <div style={{width, height}} />;
  }
  const cue = cues[idx];
  const localFrame = Math.round((t - cue.start) * fps);
  const cueDurFrames = Math.max(Math.round((cue.end - cue.start) * fps), 1);

  const popIn = spring({frame: localFrame, fps, config: {damping: 200, stiffness: 260}});
  const fadeOut = interpolate(localFrame, [Math.max(cueDurFrames - 4, 0), cueDurFrames], [1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const opacity = Math.min(popIn, fadeOut);

  const containerStyle: React.CSSProperties = {
    width, height, display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
    paddingBottom: height * 0.14,
  };
  const textStyle: React.CSSProperties = {
    fontFamily: '"Segoe UI", Arial, sans-serif',
    fontWeight: 800,
    fontSize: width * 0.032,
    textAlign: 'center',
    WebkitTextStroke: `${Math.max(width * 0.0022, 2)}px rgba(0,0,0,0.9)`,
    paintOrder: 'stroke fill',
    transform: `scale(${0.85 + opacity * 0.15})`,
    opacity,
    maxWidth: width * 0.85,
    lineHeight: 1.25,
    textShadow: '0 6px 18px rgba(0,0,0,0.55)',
  };

  if (!cue.words || cue.words.length === 0) {
    return (
      <div style={containerStyle}>
        <div style={{...textStyle, color: INK}}>{cue.text}</div>
      </div>
    );
  }

  return (
    <div style={containerStyle}>
      <div style={textStyle}>
        {cue.words.map((w, i) => {
          const wordFrame = Math.round((t - w.start) * fps);
          const active = t >= w.start && t < w.end;
          const spoken = t >= w.end;
          const pop = active
            ? spring({frame: wordFrame, fps, config: {damping: 12, stiffness: 220}})
            : 0;
          // Rehber Modul 4: aktif kelime ~1.15x ziplama (mevcut 0.16 zaten bu araliktaydi).
          const scale = 1 + Math.max(Math.min(pop, 1), 0) * 0.15;
          const baseColor = active || spoken ? NEUTRAL : INK;
          const color = colorForWord(w.text, baseColor);
          const emoji = active ? emojiForWord(w.text) : null;
          const emojiIn = emoji
            ? spring({frame: wordFrame - 2, fps, config: {damping: 10, stiffness: 200}})
            : 0;
          return (
            <span
              key={i}
              style={{
                position: 'relative',
                display: 'inline-block',
                marginLeft: i === 0 ? 0 : '0.28em',
                color,
                transform: `scale(${scale})`,
              }}
            >
              {emoji && (
                <span style={{
                  position: 'absolute', left: '50%', bottom: '100%', marginBottom: 6,
                  transform: `translateX(-50%) scale(${emojiIn}) translateY(${(1 - emojiIn) * 10}px)`,
                  fontSize: '0.9em', opacity: emojiIn, WebkitTextStroke: 0,
                }}>
                  {emoji}
                </span>
              )}
              {w.text}
            </span>
          );
        })}
      </div>
    </div>
  );
};
