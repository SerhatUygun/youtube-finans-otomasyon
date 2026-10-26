import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {BG, DOWN, GRID, INK, MUTED, UP, fmtNum} from './theme';

export type MarketChartProps = {
  name: string;
  currency: string;
  closes: number[];
  last: number;
  changePct: number;
  range: string;
  source?: string;
  // seconds/fps sadece calculateMetadata icin okunur (durationInFrames hesaplamak icin);
  // bilesenin kendisi useVideoConfig() uzerinden gelen degeri kullanir.
  seconds?: number;
  fps?: number;
};

export const defaultMarketChartProps: MarketChartProps = {
  name: 'Altin (ons/USD)',
  currency: 'USD',
  closes: [4200, 4230, 4180, 4260, 4300, 4280, 4350],
  last: 4350,
  changePct: 1.2,
  range: '6mo',
  source: 'Yahoo Finance',
  seconds: 5,
  fps: 30,
};

function buildPoints(closes: number[], w: number, h: number, padding: number): [number, number][] {
  if (closes.length === 0) return [];
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1;
  return closes.map((c, i) => {
    const x = closes.length > 1 ? padding + (i / (closes.length - 1)) * (w - padding * 2) : w / 2;
    const y = h - padding - ((c - min) / span) * (h - padding * 2);
    return [x, y] as [number, number];
  });
}

function pointsToPath(points: [number, number][]): string {
  return points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
}

export const MarketChart: React.FC<MarketChartProps> = ({name, currency, closes, last, changePct, range, source}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width, height} = useVideoConfig();

  const up = changePct >= 0;
  const accent = up ? UP : DOWN;
  const padding = Math.round(width * 0.047);

  const points = buildPoints(closes, width, height, padding);
  const path = pointsToPath(points);
  const pathLength = points.reduce((acc, [x, y], i) => {
    if (i === 0) return acc;
    const [px, py] = points[i - 1];
    return acc + Math.hypot(x - px, y - py);
  }, 0) || 1;

  // Cizgi ilk %65'te kendini cizer; fiyat sayaci ayni pencerede ilk degerden son degere sayar.
  const drawEnd = Math.max(Math.round(durationInFrames * 0.65), 1);
  const drawProgress = interpolate(frame, [0, drawEnd], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const priceNow = interpolate(frame, [0, drawEnd], [closes[0] ?? last, last], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const dotIn = interpolate(frame, [drawEnd - 10, drawEnd], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const headerIn = spring({frame, fps, config: {damping: 200}});
  const badgeIn = spring({frame: frame - 6, fps, config: {damping: 200}});
  const lastPoint = points[points.length - 1];

  return (
    <div style={{width, height, background: BG, fontFamily: '"Segoe UI", Arial, sans-serif'}}>
      <svg width={width} height={height} style={{position: 'absolute', top: 0, left: 0}}>
        {[0.25, 0.5, 0.75].map((f) => {
          const y = padding + f * (height - padding * 2);
          return <line key={f} x1={padding} x2={width - padding} y1={y} y2={y} stroke={GRID} strokeWidth={1} />;
        })}
        {path && (
          <path
            d={path}
            fill="none"
            stroke={accent}
            strokeWidth={5}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray={pathLength}
            strokeDashoffset={pathLength * (1 - drawProgress)}
          />
        )}
        {lastPoint && <circle cx={lastPoint[0]} cy={lastPoint[1]} r={12} fill={accent} opacity={dotIn} />}
      </svg>

      <div
        style={{
          position: 'absolute', top: height * 0.035, left: padding, opacity: headerIn,
          color: INK, fontSize: width * 0.027, fontWeight: 700,
        }}
      >
        {name}
      </div>
      <div
        style={{
          position: 'absolute', top: height * 0.045, right: padding, opacity: badgeIn,
          color: accent, fontSize: width * 0.02, fontWeight: 700,
        }}
      >
        {up ? '▲' : '▼'} %{Math.abs(changePct).toFixed(1)} ({range})
      </div>

      {lastPoint && (
        <div
          style={{
            position: 'absolute',
            left: Math.min(lastPoint[0] + 18, width - padding - 260),
            top: lastPoint[1] - height * 0.03,
            color: INK, fontSize: width * 0.021, fontWeight: 700, opacity: dotIn,
          }}
        >
          {fmtNum(priceNow)} {currency}
        </div>
      )}

      <div style={{position: 'absolute', bottom: height * 0.03, left: padding, color: MUTED, fontSize: width * 0.011}}>
        Kaynak: {source || 'Yahoo Finance'}
      </div>
    </div>
  );
};
