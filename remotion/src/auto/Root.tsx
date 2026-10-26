// Otomasyon kompozisyonları — props (plan JSON) `--props` dosyasıyla verilir; süre plandan okunur.
import React from 'react';
import {Composition} from 'remotion';
import {AutoVideo, Plan} from './AutoVideo';
import {AutoThumb, ThumbSpec} from './Thumb';
import {PresenterTest, PresenterTestProps} from './PresenterTest';
import {Presenter3D} from './Presenter3D';
import {AbsoluteFill} from 'remotion';
import {LabTest} from './Lab';

const M3 = Array.from({length: 300}, (_, i) => Math.max(0, Math.sin(i * 0.55) * 0.5 + Math.sin(i * 0.17) * 0.4 + 0.1));
const P3Test: React.FC<{variant?: string}> = ({variant}) => (
  <AbsoluteFill style={{background: 'radial-gradient(ellipse 80% 70% at 50% 40%, #2a3a66, #121a30)', alignItems: 'center', justifyContent: 'center'}}>
    <Presenter3D variant={variant} mouth={M3} width={1080} height={1080} gestures={[{at: 30, kind: 'explain', len: 70}, {at: 120, kind: 'point', len: 60}, {at: 200, kind: 'shrug', len: 60}]} expr={[{at: 0, e: 'neutral'}, {at: 110, e: 'happy'}, {at: 200, e: 'worried'}]} />
  </AbsoluteFill>
);

const EMPTY: Plan = {fps: 30, total: 90, outroStart: 90, segments: [{i: 0, s: 0, e: 60, text: 'Finans Kanalı', words: [{w: 'Sağlam', s: 0, e: 20}, {w: 'Para', s: 20, e: 60}]}],
  scenes: [{t: 'Intro', p: {subtitle: 'önizleme'}}]};

const meta = async ({props}: {props: {plan: Plan}}) => ({durationInFrames: Math.max(props.plan.total, 1), fps: props.plan.fps ?? 30});

export const AutoRoot: React.FC = () => (
  <>
    <Composition id="AutoShowreel" component={AutoVideo} width={1920} height={1080} fps={30} durationInFrames={90}
      defaultProps={{plan: EMPTY}} calculateMetadata={meta} />
    <Composition id="AutoReel" component={AutoVideo} width={1080} height={1920} fps={30} durationInFrames={90}
      defaultProps={{plan: {...EMPTY, layout: 'v'}}} calculateMetadata={meta} />
    <Composition id="PresenterTest" component={PresenterTest} width={1920} height={1080} fps={30} durationInFrames={450}
      defaultProps={{voice: '', mouth: [], point: [], kicker: '', big: '', sub: ''} as PresenterTestProps} />
    <Composition id="LabTest" component={LabTest} width={1920} height={1080} fps={30} durationInFrames={120} />
    <Composition id="Presenter3DTest" component={P3Test} defaultProps={{variant: 'sade'}} width={1080} height={1080} fps={30} durationInFrames={300} />
    <Composition id="AutoThumb" component={AutoThumb} width={1280} height={720} fps={30} durationInFrames={1}
      defaultProps={{spec: {variant: 'A', headline: ['İKİNCİ', 'ARTIŞ?'], badge: '%75'} as ThumbSpec}} />
  </>
);
