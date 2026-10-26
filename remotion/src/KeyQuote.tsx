import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {INK, MUTED, NEUTRAL} from './theme';
import {CardBackground, panelStyle} from './cardFx';

export type KeyQuoteProps = {
  quote: string;
  attribution?: string;
  seconds?: number;
  fps?: number;
};

export const defaultKeyQuoteProps: KeyQuoteProps = {
  quote: 'Bu, son on yilin en sert faiz kararlarindan biri.',
  attribution: '',
  seconds: 4,
  fps: 30,
};

export const KeyQuote: React.FC<KeyQuoteProps> = ({quote, attribution}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();

  const panelIn = spring({frame, fps, config: {damping: 200, stiffness: 120}, durationInFrames: Math.round(fps * 0.5)});
  const markIn = spring({frame: frame - 6, fps, config: {damping: 10, stiffness: 200}});
  const quoteIn = spring({frame: frame - 12, fps, config: {damping: 200}});
  const attributionIn = spring({frame: frame - 24, fps, config: {damping: 200}});
  const lineProgress = interpolate(frame, [10, 34], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  return (
    <div style={{width, height, position: 'relative', fontFamily: '"Segoe UI", Arial, sans-serif'}}>
      <CardBackground accent={NEUTRAL} />
      <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
        <div style={{
          width: width * 0.62, padding: `${height * 0.06}px ${width * 0.05}px`,
          display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center',
          ...panelStyle(NEUTRAL, panelIn),
        }}>
          <div style={{
            fontSize: width * 0.065, fontWeight: 800, color: NEUTRAL, lineHeight: 1,
            transform: `scale(${markIn}) translateY(${(1 - markIn) * -14}px)`,
            textShadow: `0 0 22px ${NEUTRAL}66`,
          }}>
            &ldquo;
          </div>
          <div style={{
            fontSize: width * 0.03, fontWeight: 700, color: INK, opacity: quoteIn,
            transform: `translateY(${(1 - quoteIn) * 20}px) scale(${0.94 + quoteIn * 0.06})`,
            maxWidth: width * 0.52, marginTop: height * 0.008,
          }}>
            {quote}
          </div>
          <div style={{
            height: 4, width: width * 0.09 * lineProgress, background: `linear-gradient(90deg, ${NEUTRAL}, transparent)`,
            margin: `${height * 0.024}px 0`, borderRadius: 2, boxShadow: `0 0 10px ${NEUTRAL}`,
          }} />
          {attribution && (
            <div style={{
              fontSize: width * 0.018, color: MUTED, opacity: attributionIn,
              transform: `translateY(${(1 - attributionIn) * 14}px)`, maxWidth: width * 0.4,
            }}>
              {attribution}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
