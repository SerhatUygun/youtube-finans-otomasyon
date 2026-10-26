import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {INK, MUTED, NEUTRAL} from './theme';
import {CardBackground, panelStyle} from './cardFx';

export type TitleCardProps = {
  title: string;
  subtitle?: string;
  seconds?: number;
  fps?: number;
};

export const defaultTitleCardProps: TitleCardProps = {
  title: 'Saglam Para',
  subtitle: 'Fed Faiz Karari Oncesi: Altin, Gumus ve Bitcoin',
  seconds: 4,
  fps: 30,
};

export const TitleCard: React.FC<TitleCardProps> = ({title, subtitle}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const panelIn = spring({frame, fps, config: {damping: 200, stiffness: 120}, durationInFrames: Math.round(fps * 0.5)});
  const titleIn = spring({frame: frame - 6, fps, config: {damping: 13, stiffness: 160}});
  const subtitleIn = spring({frame: frame - 18, fps, config: {damping: 200}});
  const lineProgress = interpolate(frame, [8, 30], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  return (
    <div style={{width, height, position: 'relative', fontFamily: '"Segoe UI", Arial, sans-serif'}}>
      <CardBackground accent={NEUTRAL} />
      <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
        <div style={{
          width: width * 0.7, padding: `${height * 0.07}px ${width * 0.06}px`,
          display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center',
          ...panelStyle(NEUTRAL, panelIn),
        }}>
          <div style={{
            fontSize: width * 0.05, fontWeight: 800, color: INK,
            transform: `translateY(${(1 - titleIn) * 26}px) scale(${0.9 + titleIn * 0.1})`,
          }}>
            {title}
          </div>
          <div style={{
            height: 4, width: width * 0.11 * lineProgress,
            background: `linear-gradient(90deg, ${NEUTRAL}, transparent)`,
            margin: `${height * 0.022}px 0`, borderRadius: 2, boxShadow: `0 0 10px ${NEUTRAL}`,
          }} />
          {subtitle && (
            <div style={{
              fontSize: width * 0.021, color: MUTED, opacity: subtitleIn,
              transform: `translateY(${(1 - subtitleIn) * 18}px)`, maxWidth: width * 0.55,
            }}>
              {subtitle}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
