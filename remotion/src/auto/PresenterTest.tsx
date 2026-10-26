// 9 Eki: 2D sunucu deneme kompozisyonu — solda karakter, sağda rakam kartı, gerçek seslendirme.
import React from 'react';
import {AbsoluteFill, Audio, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {T} from '../core/theme';
import {Presenter} from './Presenter';

export type PresenterTestProps = {voice: string; mouth: number[]; vis?: string; point: number[]; kicker: string; big: string; sub: string};

export const PresenterTest: React.FC<PresenterTestProps> = ({voice, mouth, vis, point, kicker, big, sub}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const card = spring({frame: f - 20, fps, config: T.spring.snappy});
  const enter = spring({frame: f, fps, config: {damping: 14, stiffness: 120}});
  return (
    <AbsoluteFill style={{background: `radial-gradient(ellipse 70% 80% at 30% 60%, #1b2540, ${T.c.bg})`}}>
      {/* zemin çizgisi */}
      <div style={{position: 'absolute', left: 0, right: 0, top: 930, height: 4, background: T.c.line}} />
      <div style={{position: 'absolute', left: 140, bottom: 150, transform: `translateY(${(1 - enter) * 300}px)`}}>
        <Presenter mouth={mouth} vis={vis} size={800} gestures={[{at: point[0] ?? 60, kind: 'point'}, {at: 150, kind: 'explain'}, {at: 240, kind: 'think'}, {at: point[1] ?? 300, kind: 'shrug'}, {at: 390, kind: 'up', len: 55}]} expr={[{at: 0, e: 'neutral'}, {at: 140, e: 'happy'}, {at: 230, e: 'worried'}, {at: 380, e: 'surprised'}]} />
      </div>
      <div style={{position: 'absolute', left: 860, top: 250, width: 900, opacity: card, transform: `translateX(${(1 - card) * 80}px)`,
        padding: '44px 54px', borderRadius: 28, background: 'rgba(255,255,255,0.04)', border: `2px solid ${T.c.line}`}}>
        <div style={{fontFamily: T.f.mono, fontSize: 30, letterSpacing: '0.14em', color: T.c.accent}}>{kicker}</div>
        <div style={{fontFamily: T.f.display, fontWeight: 900, fontSize: 170, color: T.c.hero, lineHeight: 1.05,
          transform: `scale(${interpolate(spring({frame: f - 30, fps, config: T.spring.bouncy}), [0, 1], [0.7, 1])})`, transformOrigin: 'left center'}}>{big}</div>
        <div style={{fontFamily: T.f.display, fontWeight: 600, fontSize: 48, color: T.c.text, marginTop: 10}}>{sub}</div>
      </div>
      <Audio src={staticFile(voice)} />
    </AbsoluteFill>
  );
};
