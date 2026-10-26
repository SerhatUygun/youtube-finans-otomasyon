// 16 Eki: 3D sunucu (three.js / @remotion/three) — 2D Presenter ile AYNI kimlik (sakal, kahve saç, lacivert gömlek) ve AYNI veri
// (mouth/vis/gestures/expr), böylece Presenter yerine takılabilir. Tamamen kodla çizilmiş, toon gölgeli + kontur; model dosyası yok.
// Render'da WebGL gerekir: --gl=angle.
import React, {useMemo} from 'react';
import {useCurrentFrame} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import * as THREE from 'three';
import {EXPR, exprAt, poseAt, PresenterProps} from './Presenter';

const C0 = {suit: '#22304F', suitDk: '#162038', tie: '#C9302C', tieDk: '#8E1F1C', gold: '#E9B949', skin: '#F3C9AE', hair: '#4A3222', hairSide: '#5C4433', beard: '#4B3121', brow: '#3A2618', iris: '#6B5236', frame: '#B9A27C', blush: '#EBA79A', shirt: '#1F2C4A', collar: '#F3F1EA',
  mouth: '#4A1717', tongue: '#D9666A', ink: '#120C0A'};
// 19 Eki: karakter varyantları (kullanıcı seçecek) — palet + oran farkları; varsayılan 'sade'
export const VARIANTS: Record<string, {label: string; c: Partial<typeof C0>; noTie?: boolean; head?: number; body?: number; band?: boolean}> = {
  sade: {label: 'Sade (lacivert takım, kırmızı kravat)', c: {}},
  fume: {label: 'Füme ceket, hakim yaka (fotoğraftaki gibi)', c: {suit: '#3B3E45', suitDk: '#2B2D33', collar: '#F6F5F0'}, noTie: true, band: true},
  bankaci: {label: 'Klasik bankacı (koyu lacivert, altın kravat)', c: {suit: '#18223A', suitDk: '#0F1628', tie: '#E2B13C', tieDk: '#A87E1E', gold: '#C9302C'}},
  chibi: {label: 'Sevimli büyük kafa (bordo kravat)', c: {tie: '#7E1F2E', tieDk: '#561320'}, head: 1.28, body: 0.82},
  bej: {label: 'Açık bej ceket, lacivert kravat (yazlık/ferah)', c: {suit: '#B9A27E', suitDk: '#8F7A58', tie: '#22304F', tieDk: '#162038', gold: '#FFFFFF'}},
};
let C = C0;
let VAR = VARIANTS.sade;


let GRAD: THREE.DataTexture | null = null;
const grad = () => {
  if (GRAD) return GRAD;
  const d = new Uint8Array([90, 90, 90, 255, 175, 175, 175, 255, 255, 255, 255, 255]);
  GRAD = new THREE.DataTexture(d, 3, 1, THREE.RGBAFormat);
  GRAD.minFilter = GRAD.magFilter = THREE.NearestFilter;
  GRAD.needsUpdate = true;
  return GRAD;
};

type PartProps = {geo: (g: number) => React.ReactNode; color: string; pos?: [number, number, number]; scale?: [number, number, number]; rot?: [number, number, number];
  ol?: number; children?: React.ReactNode};
// Toon gövde + ters yüzlü (BackSide) kontur kabuğu
const Part: React.FC<PartProps> = ({geo, color, pos = [0, 0, 0], scale = [1, 1, 1], rot = [0, 0, 0], ol = 0.045, children}) => (
  <group position={pos} scale={scale} rotation={rot}>
    <mesh>{geo(0)}<meshToonMaterial color={color} gradientMap={grad()} /></mesh>
    {ol > 0 ? <mesh>{geo(ol)}<meshBasicMaterial color={C.ink} side={THREE.BackSide} /></mesh> : null}
    {children}
  </group>
);
const Sph = (r: number) => (g: number) => <sphereGeometry args={[r + g, 36, 28]} />;
const Cap = (r: number, l: number) => (g: number) => <capsuleGeometry args={[r + g, l, 8, 20]} />;

const deg = (d: number) => (d * Math.PI) / 180;
// 2D pozlardaki açı (y aşağı) -> three z-dönüşü (kapsül ekseni +y)
const zRot = (a: number) => Math.atan2(-Math.sin(deg(a)), Math.cos(deg(a))) - Math.PI / 2;

const Arm: React.FC<{x: number; a: [number, number]; open: number; side: 1 | -1; held?: React.ReactNode}> = ({x, a, open, side, held}) => {
  const U = 1.05, F = 0.95;
  const e = [U * Math.cos(deg(a[0])), -U * Math.sin(deg(a[0]))];
  return (
    <group position={[x, -0.02, 0.05]}>
      <group rotation={[0, 0, zRot(a[0])]}>
        <Part geo={Cap(0.27, U - 0.5)} color={C.suit} pos={[0, U / 2, 0]} />
      </group>
      <group position={[e[0], e[1], 0.02]}>
        <group rotation={[0, 0, zRot(a[1])]}>
          <Part geo={Cap(0.23, F - 0.44)} color={C.suit} pos={[0, F / 2, 0]} />
          <Part geo={Sph(0.24)} color={C.skin} pos={[0, F + 0.14, 0.02]} scale={[1 + 0.18 * open, 1.12, 0.8]}>
            <Part geo={Cap(0.07, 0.12)} color={C.skin} pos={[side * (0.2 + 0.07 * open), -0.04, 0.05]} rot={[0, 0, side * (0.9 + 0.3 * open)]} ol={0.03} />
          </Part>
          <Part geo={(g) => <cylinderGeometry args={[0.25 + g, 0.25 + g, 0.12, 20]} />} color={C.collar} pos={[0, F - 0.02, 0]} ol={0.03} />
          {held ? <group position={[0, F + 0.42, 0.1]} rotation={[0, 0, -zRot(a[1])]}>{held}</group> : null}
        </group>
      </group>
    </group>
  );
};

type Face = {open: number; w: number; shape: string; smile: number};
const Mouth: React.FC<Face> = ({open, w, shape, smile}) => {
  const z = 0.93;
  if (shape === 'X' || open < 0.06) {
    return <mesh position={[0, -0.42, z]} rotation={[0, 0, 0]}><boxGeometry args={[0.34 + 0.06 * smile, 0.05, 0.04]} /><meshBasicMaterial color={C.mouth} /></mesh>;
  }
  if (shape === 'M') return <mesh position={[0, -0.42, z]}><boxGeometry args={[0.3, 0.06, 0.04]} /><meshBasicMaterial color={C.mouth} /></mesh>;
  const W = shape === 'E' ? 0.5 : shape === 'O' ? 0.26 : 0.4;
  const H = (shape === 'E' ? 0.16 : shape === 'O' ? 0.3 : 0.34) * Math.min(1, 0.35 + open) + 0.04;
  return (
    <group position={[0, -0.42 - H / 2 + 0.02, z]}>
      <mesh scale={[W / 2, H / 2, 0.05]}><sphereGeometry args={[1, 24, 16]} /><meshBasicMaterial color={C.mouth} /></mesh>
      {shape !== 'O' ? <mesh position={[0, H * 0.32, 0.04]}><boxGeometry args={[W * 0.7, Math.min(0.07, H / 3), 0.03]} /><meshBasicMaterial color="#FFFFFF" /></mesh> : null}
      {H > 0.22 ? <mesh position={[0, -H * 0.28, 0.035]} scale={[W * 0.28, H * 0.16, 0.03]}><sphereGeometry args={[1, 16, 12]} /><meshBasicMaterial color={C.tongue} /></mesh> : null}
    </group>
  );
};

const Head: React.FC<{blink: number; E: (typeof EXPR)['neutral']; face: Face; rx: number; ry: number}> = ({blink, E, face, rx, ry}) => {
  const eyeH = Math.max(0.06, (1 - 0.94 * blink) * E.eye);
  return (
    <group position={[0, 1.45, 0]} rotation={[rx, ry, deg(E.tilt * 0.25)]}>
      <Part geo={Sph(1)} color={C.skin} scale={[0.9, 1.1, 0.95]} />
      {/* kulaklar */}
      {[-1, 1].map((s) => <Part key={s} geo={Sph(0.17)} color={C.skin} pos={[s * 0.92, 0, -0.05]} scale={[0.6, 1, 0.8]} ol={0.03} />)}
      {/* saç: üst kep + kakül */}
      {/* 19 Eki sade benzerlik: kısa yanlar + geriye taranmış tek hacim; çene hattını izleyen tek sakal kabuğu */}
      <Part geo={(g) => <sphereGeometry args={[1.0 + g, 36, 24, 0, Math.PI * 2, 0, Math.PI * 0.5]} />} color={C.hair} pos={[0, 0.12, -0.05]} scale={[1.05, 1.0, 1.07]} rot={[-0.55, 0, 0]} ol={0.03} />
      {/* 19 Eki: sade — abartılı saç hacmi ve sakal kaldırıldı */}
      {/* burun */}
      <Part geo={Sph(0.16)} color={C.skin} pos={[0, -0.02, 0.96]} scale={[0.95, 1.25, 0.95]} ol={0.03} />
      {/* gözler + kaşlar */}
      {[-1, 1].map((s) => (
        <group key={s} position={[s * 0.36, 0.2, 0.84]}>
          <mesh scale={[1, eyeH, 0.5]}><sphereGeometry args={[0.15, 24, 18]} /><meshBasicMaterial color="#FFFFFF" /></mesh>
          <mesh position={[0, 0, 0.05]} scale={[1, eyeH, 0.5]}><sphereGeometry args={[0.095, 20, 16]} /><meshBasicMaterial color={C.iris} /></mesh>
          <mesh position={[0, 0, 0.09]} scale={[1, eyeH, 0.5]}><sphereGeometry args={[0.045, 16, 12]} /><meshBasicMaterial color={C.ink} /></mesh>
          <mesh position={[s * 0.02, 0.27 - E.brow * 0.012, 0.05]} rotation={[0, 0, s * deg(E.tilt) * -1]}>
            <boxGeometry args={[0.38, 0.1, 0.07]} /><meshBasicMaterial color={C.brow} />
          </mesh>
        </group>
      ))}
      {/* yuvarlak ince metal gözlük */}
      {[-1, 1].map((s) => (
        <group key={`g${s}`}>
          <mesh position={[s * 0.36, 0.19, 0.98]}><torusGeometry args={[0.24, 0.022, 10, 40]} /><meshStandardMaterial color={C.frame} metalness={0.8} roughness={0.3} /></mesh>
          <mesh position={[s * 0.36, 0.19, 0.97]}><circleGeometry args={[0.235, 40]} /><meshBasicMaterial color="#ffffff" transparent opacity={0.08} /></mesh>
          <mesh position={[s * 0.66, 0.22, 0.55]} rotation={[0, s * 0.12, 0]}><boxGeometry args={[0.025, 0.025, 0.85]} /><meshStandardMaterial color={C.frame} metalness={0.8} roughness={0.3} /></mesh>
        </group>
      ))}
      <mesh position={[0, 0.2, 1.0]}><torusGeometry args={[0.07, 0.016, 8, 16, Math.PI]} /><meshStandardMaterial color={C.frame} metalness={0.8} roughness={0.3} /></mesh>
      <Mouth {...face} />
    </group>
  );
};

export type Presenter3DProps = PresenterProps & {width?: number; height?: number; zoom?: number; bg?: boolean; lift?: number};

// 19 Eki: kanvassız gövde — 3D şablonların kendi sahnesine konur (sunucu nesneyle etkileşir). held: sağ elde tutulan nesne.
export type RigProps = PresenterProps & {held?: React.ReactNode; turn?: number; variant?: string};
export const PresenterRig: React.FC<RigProps> = ({mouth = [], vis = '', from = 0, gestures = [], expr, held, turn = 0, variant = 'sade'}) => {
  VAR = VARIANTS[variant] ?? VARIANTS.sade;
  C = {...C0, ...VAR.c};
  const f = useCurrentFrame();
  const i = Math.max(0, f - from);
  const m = (k: number) => mouth[Math.min(Math.max(k, 0), mouth.length - 1)] ?? 0;
  const amp = mouth.length ? (m(i - 1) + 2 * m(i) + m(i + 1)) / 4 : 0;
  const shape = vis ? vis[Math.min(i, vis.length - 1)] ?? 'X' : amp > 0.06 ? 'A' : 'X';
  const talking = mouth.length ? Array.from({length: 12}, (_, j) => m(i - j)).reduce((a, b) => a + b, 0) / 12 : 0;
  const E = EXPR[exprAt(f, expr)];
  const blinkCycle = [97, 143, 71, 188, 120, 64, 151];
  let t = 0, bi = 0, blink = 0;
  while (t <= f + from) {
    const d = f + from - t;
    if (d < 5) blink = Math.sin((d / 5) * Math.PI);
    t += blinkCycle[bi++ % blinkCycle.length];
  }
  const p = poseAt(f, gestures);
  const breath = Math.sin((f + from) * 0.085) * 0.014;
  const ry = Math.sin((f + from) * 0.043) * 0.1 + Math.sin(f * 0.31) * 0.035 * talking;
  const rx = -0.04 + Math.sin(f * 0.27) * 0.04 * talking + (E.tilt > 5 ? 0.06 : 0);
  const face = useMemo(() => ({open: amp, w: 1, shape, smile: E.smile}), [amp, shape, E.smile]);
  const shirt = C.suit;
  return (
    <group position={[0, -0.75, 0]} rotation={[0, ry * 0.5 + turn, 0]}>
      <group scale={[VAR.body ?? 1, (VAR.body ?? 1) * (1 + breath), VAR.body ?? 1]}>
        <Part geo={Cap(0.78, 0.7)} color={shirt} pos={[0, -0.9 + p.sh * 0.004, 0]} scale={[1.1, 1, 0.62]} />
        <Part geo={Sph(0.62)} color={shirt} pos={[0, -0.08 + p.sh * 0.008, 0]} scale={[1.5, 0.52, 0.8]} ol={0.04} />
        <Part geo={(g) => <cylinderGeometry args={[0.34 + g, 0.38 + g, 0.5, 20]} />} color={C.skin} pos={[0, 0.5, 0]} ol={0.035} />
        <Part geo={(g) => <torusGeometry args={[0.46 + g * 0.6, 0.09, 12, 28]} />} color={C.collar} pos={[0, 0.34, 0.08]} rot={[Math.PI / 2 - 0.25, 0, 0]} ol={0.02} />
        <group position={[0, p.sh * 0.006, 0]}>
          <mesh position={[0, -0.12, 0.5]} rotation={[-0.18, 0, Math.PI]}><coneGeometry args={[0.42, 0.95, 3, 1]} /><meshToonMaterial color={C.collar} gradientMap={grad()} /></mesh>
          {!VAR.noTie ? <Part geo={(g) => <boxGeometry args={[0.2 + g, 0.15 + g, 0.12 + g]} />} color={C.tieDk} pos={[0, 0.27, 0.56]} rot={[-0.2, 0, Math.PI / 4]} ol={0.02} /> : null}
          {!VAR.noTie ? <Part geo={(g) => <cylinderGeometry args={[0.07 + g, 0.17 + g, 0.95, 4]} />} color={C.tie} pos={[0, -0.27, 0.6]} rot={[-0.16, Math.PI / 4, 0]} scale={[1, 1, 0.45]} ol={0.02} /> : null}
          {!VAR.noTie ? <mesh position={[0, -0.8, 0.66]} rotation={[-0.16, 0, Math.PI / 4]}><boxGeometry args={[0.17, 0.17, 0.05]} /><meshToonMaterial color={C.tie} gradientMap={grad()} /></mesh> : null}
          {[-1, 1].map((s) => (
            <React.Fragment key={s}>
              <Part geo={(g) => <boxGeometry args={[0.26 + g, 1.15 + g, 0.06 + g]} />} color={C.suitDk} pos={[s * 0.36, -0.2, 0.55]} rot={[-0.2, s * 0.25, s * 0.42]} ol={0.02} />
              <mesh position={[s * 0.4, 0.2, 0.6]} rotation={[-0.2, 0, s * -0.5]}><boxGeometry args={[0.22, 0.1, 0.04]} /><meshToonMaterial color={C.suitDk} gradientMap={grad()} /></mesh>
            </React.Fragment>
          ))}
          <Part geo={(g) => <coneGeometry args={[0.11 + g, 0.16 + g, 3]} />} color={C.gold} pos={[0.66, -0.36, 0.47]} rot={[0, 0, Math.PI]} ol={0.02} />
          <mesh position={[0.66, -0.47, 0.5]}><boxGeometry args={[0.3, 0.025, 0.02]} /><meshBasicMaterial color={C.ink} /></mesh>
          {[-1.02, -1.35].map((y) => <Part key={y} geo={Sph(0.055)} color={C.ink} pos={[0.04, y, 0.47]} ol={0} />)}
        </group>
      </group>
      <group scale={VAR.body ?? 1}>
        <Arm x={-1.0} a={p.L} open={p.open} side={-1} />
        <Arm x={1.0} a={p.R} open={p.open} side={1} held={held} />
      </group>
      <group position={[0, VAR.head ? -0.35 : 0, 0]} scale={VAR.head ?? 1}><Head blink={blink} E={E} face={face} rx={rx} ry={ry} /></group>
    </group>
  );
};

export const Presenter3D: React.FC<Presenter3DProps & {held?: React.ReactNode}> = ({width = 600, height = 600, zoom = 0.78, lift = 0, ...rest}) => (
  <ThreeCanvas width={width} height={height} camera={{position: [0, 0.35 + lift, 10.5 / zoom], fov: 30}} gl={{alpha: true}}>
    <ambientLight intensity={1.15} />
    <directionalLight position={[3, 5, 6]} intensity={1.9} />
    <directionalLight position={[-5, 1, -2]} intensity={0.9} color="#7ea6ff" />
    <PresenterRig {...rest} />
  </ThreeCanvas>
);

// Sahne içi ışık (toon malzeme için): 3D şablonların kendi ışığına ek, yalnız sunucuyu aydınlatır gibi yumuşak
export const RigLights: React.FC = () => <hemisphereLight args={['#ffffff', '#3a4466', 0.9]} />;