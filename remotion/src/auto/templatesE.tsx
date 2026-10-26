// Şablonlar E (18 Eki): three.js sahne paketi — storyboard'daki "kahraman nesne" zinciri için.
// Tasarım rehberi kuralları: kamera HAREKET eder (zoom/fov değişmez); her şey useCurrentFrame()'den (deterministik, Math.random yok);
// giriş = nesne sahneye düşer/yükselir (yalnız opaklık giriş sayılmaz); tek anahtar ışık + yumuşak dolgu.
//   Bars3D: 2-5 kalem 3D sütun kıyası · Stack3D: önce/sonra sikke kuleleri · Object3D: fiyatsız kahraman nesne + başlık
import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {useThree} from '@react-three/fiber';
import {T} from '../core/theme';
import {BgMesh, Label, Rise, Words, ease} from '../core/kit';
import {useCue} from '../core/timing';
import {P, col} from './data';
import {useV} from './templatesA';
import {Bar, Barrel, Bills, Coin, METALS, useEnv} from './templatesD';
import {PresenterRig} from './Presenter3D';
import type {GestureCue} from './Presenter';

type V3 = [number, number, number];
const camPath = (f: number, t0: number, from: V3, to: V3, len = 150): V3 => {
  const k = ease(f, t0, t0 + len, 0, 1, T.ease.inOut);
  return from.map((v, i) => v + (to[i] - v) * k) as V3;
};
const CamSet: React.FC<{pos: V3; look: V3}> = ({pos, look}) => {
  const {camera} = useThree();
  camera.position.set(pos[0], pos[1], pos[2]);
  camera.lookAt(look[0], look[1], look[2]);
  camera.updateProjectionMatrix();
  return null;
};
const Lights: React.FC<{c: string}> = ({c}) => (
  <>
    <ambientLight intensity={0.55} />
    <directionalLight position={[4, 7, 5]} intensity={2.4} />
    <directionalLight position={[-4, 2, 4]} intensity={0.7} />
    <pointLight position={[0, -2, 3]} intensity={5} distance={9} color={c} />
  </>
);
const Floor: React.FC = () => (
  <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.5, 0]}>
    <circleGeometry args={[9, 64]} />
    <meshStandardMaterial color="#0b1020" roughness={0.85} metalness={0.2} />
  </mesh>
);
const Head: React.FC<{p: P; t0: number; V: boolean; f: number}> = ({p, t0, V, f}) => (
  <AbsoluteFill style={{padding: V ? '230px 70px' : `${T.safe.top + 20}px ${T.safe.side}px`, justifyContent: 'flex-start'}}>
    <Label size={26} color={T.c.hero} style={{opacity: ease(f, t0 + 2, t0 + 14, 0, 1)}}>{p.kicker ?? ''}</Label>
    {p.title ? <Words text={p.title} delay={t0 + 6} size={V ? 64 : 68} style={{marginTop: 10, maxWidth: V ? 940 : 1500}} /> : null}
  </AbsoluteFill>
);

// 19 Eki: sahne içi sunucu — plan.presenter3d açıksa 3D şablonların içinde durur, nesneye işaret eder / tutar.
// Ağız izi global karede: from = -sahneBaşı. Kapalıysa null (şablon eskisi gibi).
export const useHost = () => {
  const {tl, start} = useCue();
  const pl = tl as unknown as {presenter3d?: boolean; presenterVariant?: string; presenter?: {mouth: number[]; vis: string}};
  return pl.presenter3d && pl.presenter ? {mouth: pl.presenter.mouth, vis: pl.presenter.vis, from: -start, variant: pl.presenterVariant} : null;
};
const Host: React.FC<{pos: V3; scale?: number; turn?: number; acts: GestureCue[]; held?: React.ReactNode; t0: number}> = ({pos, scale = 0.55, turn = 0, acts, held, t0}) => {
  const h = useHost();
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (!h) return null;
  const k = spring({frame: f - t0 - 2, fps, config: {damping: 15, mass: 0.8}});
  return (
    <group position={[pos[0], pos[1] - (1 - k) * 0.6, pos[2]]} scale={scale * (0.85 + 0.15 * k)}>
      <PresenterRig variant={h.variant} mouth={h.mouth} vis={h.vis} from={h.from} gestures={acts} expr={[{at: 0, e: 'happy'}]} held={held} turn={turn} />
    </group>
  );
};

// Bars3D — p: {kicker, title, items:[{label, value, text?, color?, cue?}], cue}
export const Bars3D: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const t0 = at(p.cue);
  const items: P[] = (p.items ?? []).slice(0, 5);
  const max = Math.max(...items.map((x) => Math.abs(Number(x.value) || 0)), 1);
  const n = Math.max(items.length, 1);
  const gap = V ? 1.25 : 1.6;
  const H3 = Math.round(V ? height * 0.38 : height * 0.46);
  const host = useHost();
  const cam = camPath(f, t0, [V ? 1.8 : 3.2, 1.4, V ? 7.6 : 8.6], [V ? -0.5 : -1.0, 2.0, V ? 6.6 : 7.4], 180);
  return (
    <AbsoluteFill>
      <BgMesh grid={false} />
      <AbsoluteFill style={{top: V ? 380 : height * 0.2, height: H3}}>
        <ThreeCanvas width={width} height={H3} camera={{position: cam, fov: V ? 50 : 34}}>
          <CamSet pos={cam} look={[0, 0.3, 0]} />
          <Lights c={T.c.hero} />
          <Floor />
          <group position={[host ? 0.9 : 0, 0, 0]}>
          <Host t0={t0} pos={[-((n - 1) / 2) * gap - 1.55, 0.45, 0.8]} turn={0.5} acts={[{at: t0 + 8, kind: 'present', len: 70}, {at: at(items[n - 1]?.cue ?? p.cue) + 4, kind: 'point', len: 80}]} />
          {items.map((it, i) => {
            const k = spring({frame: f - at(it.cue ?? p.cue) - 8 - i * 6, fps, config: T.spring.heavy});
            const h = Math.max(0.08, (Math.abs(Number(it.value) || 0) / max) * 3.2) * Math.max(k, 0.001);
            const c = col(it.color, i === 0 ? T.c.hero : T.c.accent);
            return (
              <mesh key={i} position={[(i - (n - 1) / 2) * gap, -1.5 + h / 2, 0]}>
                <boxGeometry args={[gap * 0.62, h, gap * 0.62]} />
                <meshStandardMaterial color={c} metalness={0.35} roughness={0.32} emissive={c} emissiveIntensity={0.12} />
              </mesh>
            );
          })}
          </group>
        </ThreeCanvas>
      </AbsoluteFill>
      <Head p={p} t0={t0} V={V} f={f} />
      <AbsoluteFill style={{top: V ? 1110 : height * 0.66, height: 200, flexDirection: 'row', justifyContent: 'center', gap: V ? 26 : 60, flexWrap: 'wrap', padding: '0 60px'}}>
        {items.map((it, i) => (
          <Rise key={i} delay={at(it.cue ?? p.cue) + 20 + i * 6} y={30} x={0}>
            <div style={{textAlign: 'center', minWidth: V ? 180 : 220}}>
              <div style={{fontFamily: T.f.mono, fontSize: V ? 44 : 50, fontWeight: 800, color: col(it.color, i === 0 ? T.c.hero : T.c.accent)}}>{it.text ?? String(it.value)}</div>
              <div style={{fontFamily: T.f.display, fontSize: V ? 30 : 32, fontWeight: 700, color: T.c.dim, marginTop: 4}}>{it.label}</div>
            </div>
          </Rise>
        ))}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// Stack3D — p: {kicker, title, from:{label,value,text}, to:{label,value,text}, metal?, cue, toCue?}
export const Stack3D: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const t0 = at(p.cue);
  const t1 = p.toCue ? at(p.toCue) : t0 + 30;
  const env = useEnv();
  const m = METALS[p.metal ?? 'gold'] ?? METALS.gold;
  const a = Math.abs(Number(p.from?.value) || 1);
  const b = Math.abs(Number(p.to?.value) || 1);
  const mx = Math.max(a, b);
  const na = Math.max(2, Math.round((a / mx) * 16));
  const nb = Math.max(2, Math.round((b / mx) * 16));
  const up = b >= a;
  const tone = up ? T.c.up : T.c.down;
  const H3 = Math.round(V ? height * 0.38 : height * 0.5);
  const cam = camPath(f, t0, [0, 1.8, V ? 8 : 9], [0, 2.2, V ? 7 : 7.8], 200);
  const coins = (cnt: number, x: number, start: number) =>
    Array.from({length: cnt}).map((_, i) => {
      const k = spring({frame: f - start - i * 2, fps, config: {damping: 14, mass: 0.6}});
      return (
        <mesh key={i} position={[x + Math.sin(i * 2.1) * 0.03, -1.4 + i * 0.2 + (1 - k) * 4, Math.cos(i * 1.3) * 0.03]} visible={k > 0.01}>
          <cylinderGeometry args={[0.75, 0.75, 0.17, 48]} />
          <meshStandardMaterial color={m.color} metalness={1} roughness={m.rough} envMap={env} envMapIntensity={1.6} />
        </mesh>
      );
    });
  const lbl = (o: P, delay: number, c: string) => (
    <Rise delay={delay} y={30} x={0}>
      <div style={{textAlign: 'center'}}>
        <div style={{fontFamily: T.f.mono, fontSize: V ? 60 : 64, fontWeight: 800, color: c}}>{o?.text ?? String(o?.value ?? '')}</div>
        <div style={{fontFamily: T.f.display, fontSize: V ? 32 : 34, fontWeight: 700, color: T.c.dim}}>{o?.label ?? ''}</div>
      </div>
    </Rise>
  );
  return (
    <AbsoluteFill>
      <BgMesh grid={false} tint={tone} />
      <AbsoluteFill style={{top: V ? 380 : height * 0.14, height: H3}}>
        <ThreeCanvas width={width} height={H3} camera={{position: cam, fov: V ? 50 : 34}}>
          <CamSet pos={cam} look={[0, 0.1, 0]} />
          <Lights c={tone} />
          <Floor />
          <Host t0={t0} pos={[0, 0.3, -1.2]} scale={0.5} acts={[{at: t0 + 6, kind: 'explain', len: 60}, {at: t1 + 2, kind: 'point', len: 80}]} />
          {coins(na, -1.7, t0 + 6)}
          {coins(nb, 1.7, t1)}
        </ThreeCanvas>
      </AbsoluteFill>
      <Head p={p} t0={t0} V={V} f={f} />
      <AbsoluteFill style={{top: V ? 1110 : height * 0.66, height: 200, flexDirection: 'row', justifyContent: 'space-around', padding: V ? '0 40px' : '0 420px'}}>
        {lbl(p.from, t0 + 26, T.c.text)}
        {lbl(p.to, t1 + 24, tone)}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// Object3D — p: {object: gold|silver|coin|barrel|oil|bills|dollar|lira|btc, kicker, title, big?, cue}
export const Object3D: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const t0 = at(p.cue);
  const o = String(p.object ?? 'gold');
  const shape = o === 'barrel' || o === 'oil' ? 'barrel' : ['bills', 'dollar', 'lira'].includes(o) ? 'bills' : o === 'btc' ? 'btc' : o === 'coin' ? 'coin' : 'bar';
  const metal = o === 'silver' ? 'silver' : shape === 'btc' ? 'btc' : 'gold';
  const c = shape === 'barrel' ? '#4F8EDB' : shape === 'bills' ? T.c.up : shape === 'btc' ? T.c.btc : col(metal);
  const intro = spring({frame: f - t0, fps, config: T.spring.heavy});
  const spin = interpolate(intro, [0, 1], [-1.2, 0]) + (f - t0) * 0.008;
  const tilt = 0.3 + Math.sin(f / 45) * 0.04;
  const W3 = Math.round(V ? width : width * 0.6);
  const H3 = Math.round(V ? height * 0.42 : height);
  const cam = camPath(f, t0, [1.6, 2.6, 9.5], [0, 1.1, 6.4], 120);
  return (
    <AbsoluteFill>
      <BgMesh tint={c} grid={false} />
      <AbsoluteFill style={{left: V ? 0 : width * 0.4, top: V ? 180 : 0, width: W3, height: H3}}>
        <ThreeCanvas width={W3} height={H3} camera={{position: cam, fov: V ? 50 : 34}}>
          <CamSet pos={cam} look={[0, 0, 0]} />
          <Lights c={c} />
          {useHost() ? (
            <Host t0={t0} pos={[0.1, -0.15, 0]} scale={0.44} turn={-0.15} acts={[{at: t0, kind: 'hold', len: 9999}]}
              held={<group scale={0.32} rotation={[0.3, 0.6, 0]}>{shape === 'coin' || shape === 'btc' ? <Coin metal={metal} spin={spin} tilt={tilt} /> : shape === 'barrel' ? <Barrel spin={spin} tilt={tilt} /> : shape === 'bills' ? <Bills spin={spin} tilt={tilt} intro={intro} /> : <Bar metal={metal} spin={spin} tilt={tilt} />}</group>} />
          ) : null}
          <group position={[0, (1 - intro) * -3, 0]} visible={!useHost()}>
            {shape === 'coin' || shape === 'btc' ? <Coin metal={metal} spin={spin} tilt={tilt} /> : shape === 'barrel' ? <Barrel spin={spin} tilt={tilt} />
              : shape === 'bills' ? <Bills spin={spin} tilt={tilt} intro={intro} /> : <Bar metal={metal} spin={spin} tilt={tilt} />}
          </group>
        </ThreeCanvas>
      </AbsoluteFill>
      <AbsoluteFill style={{padding: V ? '960px 70px 0' : `0 0 0 ${T.safe.side}px`, justifyContent: V ? 'flex-start' : 'center'}}>
        <Rise delay={t0 + 8} x={V ? 0 : -50} y={V ? 30 : 0}>
          <Label size={26} color={c}>{p.kicker ?? ''}</Label>
          {p.big ? <div style={{fontFamily: T.f.display, fontSize: V ? 130 : 140, fontWeight: 900, color: T.c.text, marginTop: 6, textShadow: `0 0 50px ${c}55`}}>{p.big}</div> : null}
          {p.title ? <Words text={p.title} delay={t0 + 14} size={V ? 58 : 60} weight={700} style={{marginTop: 12, maxWidth: V ? 940 : 720}} /> : null}
        </Rise>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// Scale3D (18 Eki) — iki gücü tartan terazi. p: {kicker, title, left:{label, text?, color?}, right:{label, text?, color?},
//   tilt: -1..1 (eksi = sol ağır), tiltCue?, verdict?, cue}
export const Scale3D: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const t0 = at(p.cue);
  const L: P = p.left ?? {}, R: P = p.right ?? {};
  const tiltT = p.tiltCue ? at(p.tiltCue) : t0 + 45;
  const tk = spring({frame: f - tiltT, fps, config: {damping: 7, stiffness: 60, mass: 1.4}});
  const wob = Math.sin((f - t0) * 0.18) * 0.06 * Math.max(0, 1 - (f - t0) / 40);
  const ang = -Math.max(-1, Math.min(1, Number(p.tilt) || 0)) * 0.32 * tk + wob;
  const H3 = Math.round(V ? height * 0.42 : height * 0.6);
  const cam = camPath(f, t0, [V ? 2.2 : 3.4, 1.2, V ? 9.2 : 9.6], [V ? -1.2 : -1.8, 2.0, V ? 8.2 : 8.4], 200);
  const cL = col(L.color, T.c.accent), cR = col(R.color, T.c.hero);
  const arm = 2.3;
  const Pan: React.FC<{x: number; c: string}> = ({x, c}) => {
    const y = 1.5 + Math.sin(ang) * x;
    return (
      <group position={[Math.cos(ang) * x, y, 0]}>
        {[-1, 1].map((s) => <mesh key={s} position={[s * 0.45, -0.55, 0]} rotation={[0, 0, s * 0.38]}><cylinderGeometry args={[0.015, 0.015, 1.2, 6]} /><meshStandardMaterial color="#c9b27a" metalness={0.9} roughness={0.3} /></mesh>)}
        <mesh position={[0, -1.12, 0]}><cylinderGeometry args={[0.9, 0.7, 0.12, 40]} /><meshStandardMaterial color="#d4b25a" metalness={0.95} roughness={0.25} /></mesh>
        <mesh position={[0, -0.86, 0]}><boxGeometry args={[0.7, 0.42, 0.7]} /><meshStandardMaterial color={c} metalness={0.4} roughness={0.35} emissive={c} emissiveIntensity={0.18} /></mesh>
      </group>
    );
  };
  return (
    <AbsoluteFill>
      <BgMesh grid={false} />
      <AbsoluteFill style={{top: V ? 330 : height * 0.16, height: H3}}>
        <ThreeCanvas width={width} height={H3} camera={{position: cam, fov: V ? 48 : 34}}>
          <CamSet pos={cam} look={[0, 0.6, 0]} />
          <Lights c={T.c.hero} />
          <Floor />
          <mesh position={[0, -1.35, 0]}><cylinderGeometry args={[0.9, 1.1, 0.3, 40]} /><meshStandardMaterial color="#2a2f45" metalness={0.6} roughness={0.4} /></mesh>
          <mesh position={[0, 0.1, 0]}><cylinderGeometry args={[0.09, 0.12, 3.0, 20]} /><meshStandardMaterial color="#d4b25a" metalness={0.95} roughness={0.25} /></mesh>
          <mesh position={[0, 1.62, 0]}><sphereGeometry args={[0.16, 24, 16]} /><meshStandardMaterial color="#d4b25a" metalness={0.95} roughness={0.2} /></mesh>
          <mesh position={[0, 1.5, 0]} rotation={[0, 0, ang]}><boxGeometry args={[arm * 2 + 0.2, 0.09, 0.12]} /><meshStandardMaterial color="#d4b25a" metalness={0.95} roughness={0.25} /></mesh>
          <Host t0={t0} pos={[-arm - 1.5, 0.55, 0.9]} scale={0.55} turn={0.5} acts={[{at: t0 + 8, kind: 'present', len: 60}, {at: tiltT - 6, kind: 'point', len: 90}]} />
          <Pan x={-arm} c={cL} />
          <Pan x={arm} c={cR} />
        </ThreeCanvas>
      </AbsoluteFill>
      <Head p={p} t0={t0} V={V} f={f} />
      <AbsoluteFill style={{top: V ? 1130 : height * 0.74, height: 220, flexDirection: 'row', justifyContent: 'space-around', padding: V ? '0 40px' : '0 260px'}}>
        {[L, R].map((it, i) => (
          <Rise key={i} delay={t0 + 18 + i * 8} y={30} x={0}>
            <div style={{textAlign: 'center', maxWidth: V ? 440 : 560}}>
              <div style={{fontFamily: T.f.display, fontSize: V ? 46 : 52, fontWeight: 800, color: i ? cR : cL}}>{it.label ?? ''}</div>
              {it.text ? <div style={{fontFamily: T.f.mono, fontSize: V ? 32 : 34, fontWeight: 700, color: T.c.dim, marginTop: 6}}>{it.text}</div> : null}
            </div>
          </Rise>
        ))}
      </AbsoluteFill>
      {p.verdict ? (
        <AbsoluteFill style={{top: V ? 1010 : height * 0.29, height: 80, alignItems: V ? 'center' : 'flex-start', paddingLeft: V ? 0 : T.safe.side, opacity: ease(f, tiltT + 20, tiltT + 34, 0, 1)}}>
          <div style={{fontFamily: T.f.display, fontSize: V ? 40 : 40, fontWeight: 800, color: '#FFFFFF', background: 'rgba(0,0,0,0.45)', padding: '8px 26px', borderRadius: 14}}>{p.verdict}</div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
// HostStage (19 Eki) — imza sahne: sunucu stüdyoda, yanında konunun nesnesi (açılış/bölüm/kapanış). 3D sunucu kapalıysa nesne tek başına.
// p: {kicker, title, big?, object?: gold|silver|coin|barrel|oil|bills|dollar|btc, act?: wave|present|hold|explain|point, actCue?, cue}
export const HostStage: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const t0 = at(p.cue);
  const o = String(p.object ?? 'gold');
  const shape = o === 'barrel' || o === 'oil' ? 'barrel' : ['bills', 'dollar', 'lira'].includes(o) ? 'bills' : o === 'btc' ? 'btc' : o === 'coin' ? 'coin' : 'bar';
  const metal = o === 'silver' ? 'silver' : shape === 'btc' ? 'btc' : 'gold';
  const c = shape === 'barrel' ? '#4F8EDB' : shape === 'bills' ? T.c.up : shape === 'btc' ? T.c.btc : col(metal);
  const intro = spring({frame: f - t0 - 6, fps, config: T.spring.heavy});
  const spin = (f - t0) * 0.012;
  const act = (p.act ?? 'present') as GestureCue['kind'];
  const ta = p.actCue ? at(p.actCue) : t0 + 10;
  const hold = act === 'hold';
  const H3 = Math.round(V ? height * 0.5 : height);
  const W3 = Math.round(V ? width : width * 0.62);
  const cam = camPath(f, t0, [1.2, 1.0, V ? 10.5 : 9.5], [-0.2, 0.7, V ? 9.2 : 8.2], 220);
  const obj = shape === 'coin' || shape === 'btc' ? <Coin metal={metal} spin={spin} tilt={0.3} /> : shape === 'barrel' ? <Barrel spin={spin} tilt={0.3} />
    : shape === 'bills' ? <Bills spin={spin} tilt={0.3} intro={intro} /> : <Bar metal={metal} spin={spin} tilt={0.3} />;
  return (
    <AbsoluteFill>
      <BgMesh tint={c} grid={false} />
      <AbsoluteFill style={{left: V ? 0 : width * 0.38, top: V ? 200 : 0, width: W3, height: H3}}>
        <ThreeCanvas width={W3} height={H3} camera={{position: cam, fov: V ? 46 : 34}}>
          <CamSet pos={cam} look={[0, 0.3, 0]} />
          <Lights c={c} />
          <Floor />
          <mesh position={[0, -1.49, -0.5]} rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[2.2, 2.32, 64]} /><meshBasicMaterial color={c} transparent opacity={0.5} /></mesh>
          <Host t0={t0} pos={[hold ? 0 : -1.3, 0.15, 0.4]} scale={0.6} turn={hold ? 0 : 0.35} acts={[{at: ta, kind: act, len: hold ? 9999 : 80}]}
            held={hold ? <group scale={0.3} rotation={[0.3, 0.6, 0]}>{obj}</group> : undefined} />
          {!hold || !useHost() ? (
            <group position={[useHost() ? 1.5 : 0, -0.1 + (1 - intro) * -2.5, 0]} scale={useHost() ? 0.55 : 1}>
              <mesh position={[0, -1.1, 0]}><cylinderGeometry args={[0.9, 1.0, 0.5, 40]} /><meshStandardMaterial color="#2a2f45" metalness={0.6} roughness={0.35} /></mesh>
              {obj}
            </group>
          ) : null}
        </ThreeCanvas>
      </AbsoluteFill>
      <AbsoluteFill style={{padding: V ? '1100px 70px 0' : `0 0 0 ${T.safe.side}px`, justifyContent: V ? 'flex-start' : 'center'}}>
        <Rise delay={t0 + 10} x={V ? 0 : -50} y={V ? 30 : 0}>
          <Label size={26} color={c}>{p.kicker ?? ''}</Label>
          {p.big ? <div style={{fontFamily: T.f.display, fontSize: V ? 120 : 130, fontWeight: 900, color: '#FFFFFF', marginTop: 6, textShadow: `0 0 50px ${c}55`}}>{p.big}</div> : null}
          {p.title ? <Words text={p.title} delay={t0 + 16} size={V ? 58 : 62} weight={700} style={{marginTop: 12, maxWidth: V ? 940 : 680}} /> : null}
        </Rise>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};