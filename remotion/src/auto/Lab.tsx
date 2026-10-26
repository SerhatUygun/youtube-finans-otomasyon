// 17 Eki: yeni kütüphane deneme sahnesi (LabTest) — light-leaks, starburst, roughjs, d3-sankey, drei + postprocessing (bloom).
import React from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame, interpolate} from 'remotion';
import {LightLeak} from '@remotion/light-leaks';
import {Starburst} from '@remotion/starburst';
import {makeTransform, scale, translateY} from '@remotion/animation-utils';
import {ThreeCanvas} from '@remotion/three';
import {EffectComposer, Bloom} from '@react-three/postprocessing';
import {Float} from '@react-three/drei';
import rough from 'roughjs';
import {sankey, sankeyLinkHorizontal} from 'd3-sankey';

const gen = rough.generator();
const under = gen.line(40, 18, 560, 12, {stroke: '#ffd166', strokeWidth: 5, roughness: 2.2, seed: 7});
const underPath = gen.toPaths(under).map((p) => p.d).join(' ');

const SK = (() => {
  const nodes = [{name: 'Maaş'}, {name: 'Kira'}, {name: 'Gıda'}, {name: 'Birikim'}, {name: 'Altın'}, {name: 'Döviz'}];
  const links = [{source: 0, target: 1, value: 40}, {source: 0, target: 2, value: 30}, {source: 0, target: 3, value: 30}, {source: 3, target: 4, value: 20}, {source: 3, target: 5, value: 10}];
  return sankey<any, any>().nodeWidth(18).nodePadding(24).extent([[0, 0], [760, 300]])({nodes: nodes.map((d) => ({...d})), links: links.map((d) => ({...d}))});
})();

export const LabTest: React.FC = () => {
  const f = useCurrentFrame();
  const t = interpolate(f, [0, 30], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{background: '#0b1220', color: '#fff', fontFamily: 'Segoe UI, sans-serif'}}>
      <Starburst rays={14} colors={['#16233f', '#0b1220']} vignette={0.6} />
      <AbsoluteFill style={{padding: 60}}>
        <div style={{fontSize: 84, fontWeight: 800, transform: makeTransform([scale(0.9 + 0.1 * t), translateY((1 - t) * 40)]), opacity: t}}>Yeni araçlar</div>
        <svg width={600} height={30}><path d={underPath} fill="none" stroke="#ffd166" strokeWidth={5} strokeLinecap="round" /></svg>
        <svg width={780} height={320} style={{marginTop: 30}}>
          {SK.links.map((l: any, i: number) => <path key={i} d={sankeyLinkHorizontal()(l) as string} fill="none" stroke="#4da3ff" strokeOpacity={0.5} strokeWidth={Math.max(l.width, 1)} />)}
          {SK.nodes.map((n: any, i: number) => (
            <g key={i}><rect x={n.x0} y={n.y0} width={n.x1 - n.x0} height={n.y1 - n.y0} fill="#2fd27a" /><text x={n.x1 + 6} y={(n.y0 + n.y1) / 2} fill="#fff" fontSize={18}>{n.name}</text></g>
          ))}
        </svg>
      </AbsoluteFill>
      <div style={{position: 'absolute', right: 60, top: 80, width: 700, height: 700}}>
        <ThreeCanvas width={700} height={700} camera={{position: [0, 0, 6], fov: 40}}>
          <ambientLight intensity={0.6} /><pointLight position={[4, 4, 6]} intensity={80} />
          <Float speed={0} rotationIntensity={0}>
            <mesh rotation={[0.5, f * 0.04, 0]}><torusKnotGeometry args={[1, 0.32, 160, 24]} /><meshStandardMaterial color="#ffb703" emissive="#ff8800" emissiveIntensity={1.4} metalness={0.8} roughness={0.25} /></mesh>
          </Float>
          <EffectComposer><Bloom intensity={1.2} luminanceThreshold={0.6} mipmapBlur /></EffectComposer>
        </ThreeCanvas>
      </div>
      <Sequence from={80} durationInFrames={36}><LightLeak seed={3} hueShift={20} /></Sequence>
    </AbsoluteFill>
  );
};
