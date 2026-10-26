import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {INK, MUTED, NEUTRAL, formatWithUnit} from './theme';
import {CardBackground, panelStyle} from './cardFx';

export type CompareItem = {label: string; value: number};
export type CompareBarsProps = {
  title: string;
  unit?: string;
  items: CompareItem[];
  seconds?: number;
  fps?: number;
};

export const defaultCompareBarsProps: CompareBarsProps = {
  title: 'Analist Hedef Fiyatlari',
  unit: '$',
  items: [
    {label: 'Goldman Sachs', value: 4900},
    {label: 'JPMorgan', value: 4500},
  ],
  seconds: 5,
  fps: 30,
};

export const CompareBars: React.FC<CompareBarsProps> = ({title, unit = '', items}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width, height} = useVideoConfig();
  const safeItems = items && items.length ? items : defaultCompareBarsProps.items;
  const maxVal = Math.max(...safeItems.map((i) => i.value), 1);
  const panelIn = spring({frame, fps, config: {damping: 200, stiffness: 120}, durationInFrames: Math.round(fps * 0.5)});
  const titleIn = spring({frame: frame - 4, fps, config: {damping: 200}});
  const rowHeight = Math.min((height * 0.42) / Math.max(safeItems.length, 1), height * 0.16);
  const growEnd = Math.max(Math.round(durationInFrames * 0.5), 1);
  const panelWidth = width * 0.56;
  const barAreaWidth = panelWidth - width * 0.06;

  return (
    <div style={{width, height, position: 'relative', fontFamily: '"Segoe UI", Arial, sans-serif'}}>
      <CardBackground accent={NEUTRAL} />
      <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
        <div style={{
          width: panelWidth, padding: `${height * 0.05}px ${width * 0.03}px`,
          ...panelStyle(NEUTRAL, panelIn, false),
        }}>
          <div style={{
            color: INK, fontSize: width * 0.03, fontWeight: 700, opacity: titleIn,
            transform: `translateY(${(1 - titleIn) * -12}px)`, marginBottom: height * 0.02,
          }}>
            {title}
          </div>
          <div style={{width: barAreaWidth}}>
            {safeItems.map((item, i) => {
              const localFrame = frame - 10 - i * 7;
              const barIn = spring({frame: localFrame, fps, config: {damping: 200}});
              const frac = item.value / maxVal;
              const growProgress = interpolate(localFrame, [0, growEnd], [0, 1], {
                extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
              });
              const shownValue = interpolate(localFrame, [0, growEnd], [0, item.value], {
                extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
              });
              const isTop = item.value === maxVal;
              return (
                <div key={item.label} style={{
                  marginBottom: rowHeight * 0.4, opacity: barIn,
                  transform: `translateX(${(1 - barIn) * -24}px)`,
                }}>
                  <div style={{color: MUTED, fontSize: width * 0.017, marginBottom: 5}}>{item.label}</div>
                  <div style={{
                    width: '100%', height: rowHeight * 0.4, background: 'rgba(255,255,255,0.06)',
                    borderRadius: 8, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.08)',
                  }}>
                    <div style={{
                      width: `${Math.max(frac * growProgress, 0) * 100}%`, height: '100%',
                      background: isTop
                        ? `linear-gradient(90deg, ${NEUTRAL}, #8ec9ff)`
                        : `linear-gradient(90deg, ${NEUTRAL}99, ${NEUTRAL}55)`,
                      borderRadius: 8, boxShadow: isTop ? `0 0 14px ${NEUTRAL}` : 'none',
                    }} />
                  </div>
                  <div style={{color: INK, fontSize: width * 0.019, fontWeight: 700, marginTop: 5}}>
                    {formatWithUnit(shownValue, unit)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
