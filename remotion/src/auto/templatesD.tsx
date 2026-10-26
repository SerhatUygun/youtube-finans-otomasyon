// Şablonlar D: gerçek 3D (@remotion/three = React Three Fiber). Render'da WebGL gerekir: --gl=angle.
//   Metal3D: dönen 3D altın/gümüş külçe ya da sikke + büyük fiyat (emtia videolarının açılış/vurgu sahnesi)
//   Globe3D: dönen dünya küresi (enlem-boylam kafesi) + işaretli şehirler / akış yayı
import React, {useMemo} from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import * as THREE from 'three';
import {T} from '../core/theme';
import {BgMesh, Counter, Label, Rise, Words, clamp, ease} from '../core/kit';
import {useCue} from '../core/timing';
import {P, col, useSeries} from './data';
import {mesh} from 'topojson-client';
import world from 'world-atlas/countries-110m.json';

// Ülke sınırları (küre üstünde çizgi) — bir kez hesaplanır.
let BORDERS: THREE.BufferGeometry | null = null;
const borders = () => {
  if (BORDERS) return BORDERS;
  const m = mesh(world as any, (world as any).objects.countries) as any;
  const pts: number[] = [];
  for (const ln of m.coordinates as number[][][]) {
    for (let i = 0; i < ln.length - 1; i++) {
      const a = toVec(ln[i][0], ln[i][1], 2.012);
      const b = toVec(ln[i + 1][0], ln[i + 1][1], 2.012);
      pts.push(a.x, a.y, a.z, b.x, b.y, b.z);
    }
  }
  BORDERS = new THREE.BufferGeometry();
  BORDERS.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  return BORDERS;
};
import {useV} from './templatesA';

export const METALS: Record<string, {color: string; rough: number}> = {
  gold: {color: '#E7B84E', rough: 0.22},
  silver: {color: '#D7DEE8', rough: 0.18},
  copper: {color: '#C8743F', rough: 0.3},
  btc: {color: '#F2A23A', rough: 0.26},
};

// 9 Eki: sembol -> 3D nesne (altın külçesi dışındaki varlıklar da kendi nesnesiyle)
export const shapeFor = (sym: string, shape?: string) =>
  shape ?? (/BRENT|WTI|BZ=F|CL=F|OIL/i.test(sym) ? 'barrel' : /USD.?TRY|EUR.?TRY|DXY|DX-Y/i.test(sym) ? 'bills' : /BTC|ETH/i.test(sym) ? 'btc' : 'bar');

export const Barrel: React.FC<{spin: number; tilt: number}> = ({spin, tilt}) => {
  const env = useEnv();
  return (
    <group rotation={[tilt * 0.5, spin * 0.6, 0.08]} scale={0.95}>
      <mesh>
        <cylinderGeometry args={[1.15, 1.15, 2.9, 64, 1, false]} />
        <meshStandardMaterial color="#1f4f8f" metalness={0.55} roughness={0.38} envMap={env} envMapIntensity={1.3} />
      </mesh>
      {[-1.45, -0.5, 0.5, 1.45].map((y) => (
        <mesh key={y} position={[0, y, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[1.16, 0.06, 12, 64]} />
          <meshStandardMaterial color="#163a6a" metalness={0.8} roughness={0.3} envMap={env} />
        </mesh>
      ))}
      <mesh position={[0, 1.451, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[1.1, 48]} />
        <meshStandardMaterial color="#2b2f36" metalness={0.9} roughness={0.25} envMap={env} />
      </mesh>
      <mesh position={[0.45, 1.47, 0.2]}>
        <cylinderGeometry args={[0.16, 0.16, 0.08, 24]} />
        <meshStandardMaterial color="#9aa3ad" metalness={1} roughness={0.2} envMap={env} />
      </mesh>
      <mesh position={[0, 0, 1.152]}>
        <planeGeometry args={[1.1, 0.75]} />
        <meshStandardMaterial color="#F3F1EA" roughness={0.7} />
      </mesh>
    </group>
  );
};

export const Bills: React.FC<{spin: number; tilt: number; intro: number}> = ({spin, tilt, intro}) => {
  const env = useEnv();
  const n = 9;
  return (
    <group rotation={[tilt + 0.25, spin * 0.5 - 0.4, 0]}>
      {Array.from({length: n}).map((_, i) => {
        const drop = Math.max(0, 1 - intro * 1.3 + i * 0.07) * 2.2; // desteler yukarıdan sırayla düşüp oturur
        return (
          <group key={i} position={[Math.sin(i * 1.7) * 0.06, -1 + i * 0.2 + drop, Math.cos(i * 2.3) * 0.05]} rotation={[0, Math.sin(i * 3.1) * 0.06, 0]}>
            <mesh>
              <boxGeometry args={[3.0, 0.18, 1.35]} />
              <meshStandardMaterial color={i % 2 ? '#6f9e6a' : '#7aab72'} roughness={0.75} metalness={0.05} />
            </mesh>
            <mesh position={[0, 0, 0]}>
              <boxGeometry args={[0.55, 0.2, 1.37]} />
              <meshStandardMaterial color="#E9DFC4" roughness={0.6} envMap={env} envMapIntensity={0.4} />
            </mesh>
          </group>
        );
      })}
    </group>
  );
};

// Stüdyo ışığı için basit ortam haritası (dışa bağımlılık yok): yumuşak gradyan küre.
export const useEnv = () =>
  useMemo(() => {
    const c = document.createElement('canvas');
    c.width = 512;
    c.height = 256;
    const g = c.getContext('2d')!;
    const grd = g.createLinearGradient(0, 0, 0, 256);
    // stüdyo: parlak tavan softbox + orta gri ortam + koyu zemin (metal yüzeyler her açıdan bir şey yansıtsın)
    grd.addColorStop(0, '#ffffff');
    grd.addColorStop(0.3, '#d4d7de');
    grd.addColorStop(0.6, '#7b808c');
    grd.addColorStop(1, '#2a2d35');
    g.fillStyle = grd;
    g.fillRect(0, 0, 512, 256);
    g.fillStyle = 'rgba(255,255,255,0.9)';
    g.fillRect(60, 40, 120, 40);
    g.fillRect(330, 60, 90, 30);
    const tex = new THREE.CanvasTexture(c);
    tex.mapping = THREE.EquirectangularReflectionMapping;
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }, []);

export const Bar: React.FC<{metal: string; spin: number; tilt: number}> = ({metal, spin, tilt}) => {
  const env = useEnv();
  const m = METALS[metal] ?? METALS.gold;
  const geo = useMemo(() => {
    // kesik piramit külçe: üst yüz daha dar
    const g = new THREE.BoxGeometry(3.2, 0.9, 1.5, 1, 1, 1);
    const pos = g.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < pos.count; i++) {
      if (pos.getY(i) > 0) {
        pos.setX(i, pos.getX(i) * 0.82);
        pos.setZ(i, pos.getZ(i) * 0.74);
      }
    }
    g.computeVertexNormals();
    return g;
  }, []);
  return (
    <mesh geometry={geo} rotation={[tilt, spin, 0]}>
      <meshStandardMaterial color={m.color} metalness={1} roughness={m.rough} envMap={env} envMapIntensity={2.2} />
    </mesh>
  );
};

export const Coin: React.FC<{metal: string; spin: number; tilt: number}> = ({metal, spin, tilt}) => {
  const env = useEnv();
  const m = METALS[metal] ?? METALS.gold;
  return (
    // yüz kameraya bakar (iç grup X ekseninde 90°), dış grup Y ekseninde döner; kabartma halka yüzün üstünde
    <group rotation={[tilt * 0.6, spin * 0.5 - 0.35, 0]}>
      <group rotation={[Math.PI / 2, 0, 0]}>
        <mesh>
          <cylinderGeometry args={[1.6, 1.6, 0.22, 96]} />
          <meshStandardMaterial color={m.color} metalness={1} roughness={m.rough} envMap={env} envMapIntensity={1.4} />
        </mesh>
        {[0.116, -0.116].map((yy) => (
          <mesh key={yy} position={[0, yy, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[1.35, 0.05, 16, 96]} />
            <meshStandardMaterial color={m.color} metalness={1} roughness={m.rough * 0.6} envMap={env} />
          </mesh>
        ))}
      </group>
    </group>
  );
};

export const Metal3D: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const t0 = at(p.cue);
  const s = useSeries(p.symbol, {last: 2});
  const intro = spring({frame: f - t0, fps, config: T.spring.heavy});
  const spin = interpolate(intro, [0, 1], [-Math.PI * 1.6, 0]) + (f - t0) * 0.012;
  const tilt = 0.32 + Math.sin(f / 40) * 0.05;
  const shape = shapeFor(String(p.symbol ?? ''), p.shape);
  const metal = p.metal ?? (shape === 'btc' ? 'btc' : /XAG|SI=F/.test(String(p.symbol)) ? 'silver' : 'gold');
  const c = shape === 'barrel' ? '#4F8EDB' : shape === 'bills' ? T.c.up : shape === 'btc' ? '#F2A23A' : col(metal === 'silver' ? 'silver' : 'gold');
  const kick = shape === 'barrel' ? 'BRENT PETROL' : shape === 'bills' ? (/EUR/.test(String(p.symbol)) ? 'EURO / TL' : /DX/.test(String(p.symbol)) ? 'DOLAR ENDEKSİ' : 'DOLAR / TL')
    : shape === 'btc' ? (/ETH/.test(String(p.symbol)) ? 'ETHEREUM' : 'BITCOIN') : metal === 'silver' ? 'ONS GÜMÜŞ' : 'ONS ALTIN';
  // "6.628 TL" gibi metin değerleri: TR sayı biçimini çöz, birimi sonek yap (NaN render'ı çökertir)
  const rawV = p.value;
  const strV = typeof rawV === 'string' && !Number.isFinite(Number(rawV));
  const parsedV = strV ? Number(String(rawV).replace(/[^\d.,-]/g, '').replace(/\./g, '').replace(',', '.')) : Number(rawV);
  const unitV = strV ? (String(rawV).match(/[^\d.,\s-]+\s*$/)?.[0] ?? '').trim() : '';
  if (strV && unitV && p.suffix === undefined) p = {...p, suffix: ' ' + (unitV === 'TL' ? '₺' : unitV), prefix: p.prefix ?? ''};
  const price = rawV !== undefined && Number.isFinite(parsedV) ? parsedV : s ? s.c[s.c.length - 1] : undefined;
  const ch = s ? (s.c[1] / s.c[0] - 1) * 100 : undefined;
  const W3 = Math.round(V ? width : width * 0.58);
  const H3 = Math.round(V ? height * 0.5 : height);
  return (
    <AbsoluteFill>
      <BgMesh tint={c} grid={false} />
      <AbsoluteFill style={{left: V ? 0 : width * 0.42, top: V ? 180 : 0, width: W3, height: H3}}>
        <ThreeCanvas width={W3} height={H3} camera={{position: [0, 1.2, 6], fov: 38}} style={{opacity: interpolate(intro, [0, 0.3], [0, 1], clamp)}}>
          <ambientLight intensity={0.9} />
          <directionalLight position={[4, 6, 5]} intensity={2.4} />
          <directionalLight position={[0, 1, 6]} intensity={1.6} />
          <directionalLight position={[-5, 2, -3]} intensity={1.2} color={c} />
          <pointLight position={[0, -3, 3]} intensity={8} distance={10} color={c} />
          <group scale={interpolate(intro, [0, 1], [0.6, 1])}>
            {shape === 'coin' || shape === 'btc' ? <Coin metal={metal} spin={spin} tilt={tilt} /> : shape === 'barrel' ? <Barrel spin={spin} tilt={tilt} />
              : shape === 'bills' ? <Bills spin={spin} tilt={tilt} intro={intro} /> : <Bar metal={metal} spin={spin} tilt={tilt} />}
          </group>
        </ThreeCanvas>
      </AbsoluteFill>
      <AbsoluteFill style={{padding: V ? '1100px 70px 0' : `0 0 0 ${T.safe.side}px`, justifyContent: V ? 'flex-start' : 'center'}}>
        <Rise delay={t0 + 6} x={V ? 0 : -60} y={V ? 40 : 0}>
          <Label size={26} color={c}>{p.kicker ?? kick}</Label>
          {price !== undefined ? (
            <Counter to={price} from={p.from ?? price * 0.97} dec={p.dec ?? (price < 100 ? 2 : 0)} prefix={p.prefix ?? (shape === 'bills' ? '' : '$')} suffix={p.suffix ?? (shape === 'bills' && !/DX/.test(String(p.symbol)) ? ' ₺' : '')}
              delay={t0 + 10} size={V ? 170 : 180} weight={900} maxW={V ? 940 : 760} style={{display: 'block', marginTop: 8, textShadow: `0 0 60px ${c}55`}} />
          ) : null}
          {p.changeText ?? (ch !== undefined && p.showChange !== false) ? (
            <div style={{fontFamily: T.f.mono, fontSize: 40, fontWeight: 800, marginTop: 10, color: (ch ?? 0) >= 0 ? T.c.up : T.c.down, opacity: ease(f, t0 + 24, t0 + 36, 0, 1)}}>
              {p.changeText ?? `${(ch ?? 0) >= 0 ? '▲' : '▼'} %${Math.abs(ch ?? 0).toFixed(2).replace('.', ',')} günlük`}
            </div>
          ) : null}
          {p.sub ? <Words text={p.sub} delay={at(p.subCue ?? p.cue) + 26} size={44} weight={600} color={T.c.dim} style={{marginTop: 24, maxWidth: V ? 940 : 760}} /> : null}
        </Rise>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ---------- Globe3D ----------
function toVec(lon: number, lat: number, r: number) {
  const phi = ((90 - lat) * Math.PI) / 180;
  const th = ((lon + 180) * Math.PI) / 180;
  return new THREE.Vector3(-r * Math.sin(phi) * Math.cos(th), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(th));
}

export const Globe3D: React.FC<{p: P}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const {at} = useCue();
  const V = useV();
  const t0 = at(p.cue);
  const intro = spring({frame: f - t0, fps, config: T.spring.heavy});
  const focusLon = Number(p.focus?.[0] ?? 35);
  const rotY = ((-focusLon - 90) * Math.PI) / 180 + (1 - intro) * 1.4 + (f - t0) * 0.0015;
  const grid = useMemo(() => {
    const pts: THREE.Vector3[][] = [];
    for (let lat = -60; lat <= 60; lat += 30) pts.push(Array.from({length: 73}, (_, i) => toVec(i * 5 - 180, lat, 2.01)));
    for (let lon = -180; lon < 180; lon += 30) pts.push(Array.from({length: 37}, (_, i) => toVec(lon, i * 5 - 90, 2.01)));
    return pts.map((a) => new THREE.BufferGeometry().setFromPoints(a));
  }, []);
  const arcs = (p.flows ?? []).map((fl: P) => {
    const a = toVec(fl.from[0], fl.from[1], 2.02);
    const b = toVec(fl.to[0], fl.to[1], 2.02);
    const mid = a.clone().add(b).multiplyScalar(0.5).normalize().multiplyScalar(2 + a.distanceTo(b) * 0.45);
    const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
    const k = ease(f, at(fl.cue ?? p.cue) + 18, at(fl.cue ?? p.cue) + 48, 0, 1, T.ease.inOut);
    const pts = curve.getPoints(64).slice(0, Math.max(2, Math.round(64 * k) + 1));
    return {geo: new THREE.BufferGeometry().setFromPoints(pts), color: col(fl.color, T.c.oil), k};
  });
  return (
    <AbsoluteFill>
      <BgMesh grid={false} />
      <ThreeCanvas width={width} height={height} camera={{position: [0, 0.6, V ? 8.5 : 6.2], fov: 40}}>
        <ambientLight intensity={0.5} />
        <directionalLight position={[5, 3, 5]} intensity={1.6} />
        <group rotation={[0.35, rotY, 0]} position={[V ? 0 : 1.2, V ? 0.6 : 0, 0]} scale={interpolate(intro, [0, 1], [0.7, 1])}>
          <mesh>
            <sphereGeometry args={[2, 64, 64]} />
            <meshStandardMaterial color="#0d1830" roughness={0.9} metalness={0.1} emissive="#0a1428" />
          </mesh>
          <lineSegments geometry={borders()}>
            <lineBasicMaterial color={T.c.text} transparent opacity={0.55} />
          </lineSegments>
          {grid.map((g, i) => (
            <primitive key={i} object={new THREE.Line(g, new THREE.LineBasicMaterial({color: T.c.accent, transparent: true, opacity: 0.12}))} />
          ))}
          {(p.markers ?? []).map((m: P, i: number) => {
            const v = toVec(m.at[0], m.at[1], 2.04);
            const k = spring({frame: f - at(m.cue ?? p.cue) - 12, fps, config: T.spring.bouncy});
            return (
              <mesh key={i} position={v} scale={k}>
                <sphereGeometry args={[0.07, 16, 16]} />
                <meshBasicMaterial color={col(m.color, T.c.hawk)} />
              </mesh>
            );
          })}
          {arcs.map((a: any, i: number) => (
            <primitive key={`a${i}`} object={new THREE.Line(a.geo, new THREE.LineBasicMaterial({color: a.color, linewidth: 3}))} />
          ))}
        </group>
        <mesh position={[V ? 0 : 1.2, V ? 0.6 : 0, -0.5]}>
          <ringGeometry args={[2.05, 2.5, 96]} />
          <meshBasicMaterial color={T.c.accent} transparent opacity={0.06} side={THREE.DoubleSide} />
        </mesh>
      </ThreeCanvas>
      <AbsoluteFill style={{padding: V ? '260px 70px' : `${T.safe.top + 40}px ${T.safe.side}px`, justifyContent: 'flex-start'}}>
        <Label size={26} color={T.c.accent} style={{opacity: ease(f, t0 + 4, t0 + 16, 0, 1)}}>{p.kicker ?? ''}</Label>
        {p.title ? <Words text={p.title} delay={t0 + 8} size={V ? 76 : 80} style={{marginTop: 12, maxWidth: V ? 940 : 820}} /> : null}
        {(p.markers ?? []).filter((m: P) => m.label).map((m: P, i: number) => (
          <Rise key={i} delay={at(m.cue ?? p.cue) + 16} x={-30} y={0} style={{marginTop: i ? 12 : 36}}>
            <div style={{display: 'flex', alignItems: 'center', gap: 14, fontFamily: T.f.display, fontSize: 34, fontWeight: 700, color: T.c.text}}>
              <span style={{width: 16, height: 16, borderRadius: 8, background: col(m.color, T.c.hawk)}} />{m.label}
            </div>
          </Rise>
        ))}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
