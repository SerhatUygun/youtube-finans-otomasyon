// Kapak 2.0 (30 Eyl, CTR araştırması): az yazı (≤4 kelime, ideal <12 karakter), tek baskın nesne, 2-3 renk,
// merak boşluğu (başlığı tekrar etmez, tamamlar). Üç tarz YouTube "Test & Compare"da yarışır:
//   object: yüz yok — 3D metal külçe / dev sembol + kırmızı çöküş oku + tek rakam
//   chart : tam ekran fiyat çizgisi eşiği kırıyor, kırılma noktasında patlama + tek soru
//   face  : gerçek yüz (duygu) + tek rakam + 2 kelime
import React, {useMemo} from 'react';
import {AbsoluteFill, Img, staticFile} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import * as THREE from 'three';
import {loadFont as loadAnton} from '@remotion/google-fonts/Anton';
import {BrandMark} from '../core/brand';

const anton = loadAnton('normal', {subsets: ['latin', 'latin-ext']}).fontFamily;
const COL: Record<string, string> = {gold: '#F7C548', red: '#FF2D3D', green: '#22E58F', white: '#FFFFFF', blue: '#4FC3FF', silver: '#DDE5F0', oil: '#9B8CFF'};
const col = (k?: string, d = COL.white) => (k && COL[k]) || d;
const OUT = '0 0 0 #000, 5px 5px 0 #000, -2px -2px 0 #000, 0 10px 30px rgba(0,0,0,0.7)';

export type ProSpec = {
  style: 'object' | 'chart' | 'face';
  text?: string;            // ≤ 4 kelime, BÜYÜK HARF (ör. "ALTIN ÇÖKTÜ?")
  textColor?: string;       // tek vurgu rengi
  number?: string;          // tek rakam (ör. "−%3,2", "4.200$")
  numberColor?: string;
  dir?: 'up' | 'down';
  object?: 'gold' | 'silver' | 'oil' | 'dollar' | 'lira' | 'bist' | 'btc';
  data?: number[];          // chart: son ~60 kapanış
  threshold?: number;       // chart: kırılan seviye
  thresholdLabel?: string;
  image?: string;           // face: gerçek fotoğraf (şeffaf arka planlı)
  glow?: string;
  bg?: string;              // photo: foto-gerçekçi arka plan (public/ altı göreli yol)
  focusX?: number;          // photo: odak noktası (0-1) — kırmızı halka + ok buraya
  focusY?: number;
  layout?: 'classic' | 'hero' | 'split' | 'banner' | 'marker' | 'center' | 'stack' | 'poster' | 'tilt' | 'hazard' | 'duo'; // 15 Eki: kapak çeşitliliği (hep aynı taslak olmasın)
  accent2?: string;         // layout panel/vurgu rengi (gold|red|green|blue|white)
};

// ---------- ortak ----------
const Backdrop: React.FC<{tint: string}> = ({tint}) => (
  <>
    <AbsoluteFill style={{background: `radial-gradient(ellipse 1000px 760px at 72% 50%, ${tint}55 0%, #0b0f1c 55%, #04060b 100%)`}} />
    <AbsoluteFill style={{background: 'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.65) 100%)'}} />
  </>
);

// En fazla 2 satır, dengeli bölünür; punto genişliğe göre küçülür (Anton ≈ 0,5em/karakter). Son satır vurgu renginde.
const BigText: React.FC<{text: string; color: string; size: number; width: number; style?: React.CSSProperties}> = ({text, color, size, width, style}) => {
  const words = text.trim().split(' ').filter(Boolean);
  let best = [text];
  if (words.length > 1) {
    let bestW = Infinity;
    for (let k = 1; k < words.length; k++) {
      const a = words.slice(0, k).join(' ');
      const b = words.slice(k).join(' ');
      const w = Math.max(a.length, b.length);
      if (w < bestW) { bestW = w; best = [a, b]; }
    }
  }
  const longest = Math.max(...best.map((l) => l.length));
  const fs = Math.min(size, Math.floor(width / (longest * 0.5)));
  return (
    <div style={{fontFamily: anton, fontSize: fs, lineHeight: 0.95, textTransform: 'uppercase', textShadow: OUT, letterSpacing: '0.01em', ...style}}>
      {best.map((l, i) => <div key={i} style={{color: i === best.length - 1 && best.length > 1 ? color : best.length === 1 ? color : '#fff', whiteSpace: 'nowrap'}}>{l}</div>)}
    </div>
  );
};

const NumberTag: React.FC<{n: string; color: string; size: number; rot?: number}> = ({n, color, size, rot = -6}) => (
  <div style={{display: 'inline-block', transform: `rotate(${rot}deg)`, background: color, padding: `${size * 0.06}px ${size * 0.22}px ${size * 0.02}px`, borderRadius: size * 0.14,
    boxShadow: `0 0 0 ${Math.round(size * 0.05)}px #fff, 0 20px 60px ${color}99`}}>
    <span style={{fontFamily: anton, fontSize: size, lineHeight: 1, color: '#fff'}}>{n}</span>
  </div>
);

const CrashArrow: React.FC<{color: string; size: number; dir: 'up' | 'down'}> = ({color, size, dir}) => (
  <svg width={size} height={size} viewBox="0 0 100 100" style={{filter: `drop-shadow(0 0 30px ${color})`, transform: dir === 'up' ? 'scaleY(-1)' : undefined}}>
    <path d="M8 12 L38 44 L54 30 L86 72" fill="none" stroke={color} strokeWidth={11} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M62 74 L90 78 L86 50" fill="none" stroke={color} strokeWidth={11} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

// ---------- object ----------
const MetalBar: React.FC<{metal: 'gold' | 'silver'}> = ({metal}) => {
  const env = useMemo(() => {
    const cv = document.createElement('canvas');
    cv.width = 512;
    cv.height = 256;
    const g = cv.getContext('2d')!;
    const gr = g.createLinearGradient(0, 0, 0, 256);
    gr.addColorStop(0, '#ffffff');
    gr.addColorStop(0.3, '#d9dce3');
    gr.addColorStop(0.6, '#80858f');
    gr.addColorStop(1, '#2a2d35');
    g.fillStyle = gr;
    g.fillRect(0, 0, 512, 256);
    const t = new THREE.CanvasTexture(cv);
    t.mapping = THREE.EquirectangularReflectionMapping;
    return t;
  }, []);
  const geo = useMemo(() => {
    const b = new THREE.BoxGeometry(3.2, 0.9, 1.5);
    const p = b.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < p.count; i++) if (p.getY(i) > 0) { p.setX(i, p.getX(i) * 0.82); p.setZ(i, p.getZ(i) * 0.74); }
    b.computeVertexNormals();
    return b;
  }, []);
  const c = metal === 'gold' ? '#E7B84E' : '#D7DEE8';
  return (
    <>
      <ambientLight intensity={0.9} />
      <directionalLight position={[4, 6, 5]} intensity={2.6} />
      <directionalLight position={[0, 1, 6]} intensity={1.4} />
      <pointLight position={[0, -3, 2]} intensity={14} distance={9} color="#ff2d3d" />
      {[0, 1, 2].map((k) => (
        <mesh key={k} geometry={geo} position={[k === 1 ? 0.35 : -0.2, 0.95 * k - 0.9, -k * 0.3]} rotation={[0.38, -0.55 + k * 0.28, -0.18 - k * 0.1]}>
          <meshStandardMaterial color={c} metalness={1} roughness={0.24} envMap={env} envMapIntensity={2.2} />
        </mesh>
      ))}
    </>
  );
};

const SYMBOL: Record<string, string> = {dollar: '$', lira: '₺', bist: 'BIST', btc: '₿', oil: '🛢'};

const ObjectThumb: React.FC<{s: ProSpec}> = ({s}) => {
  const dir = s.dir ?? 'down';
  const accent = col(s.numberColor, dir === 'down' ? COL.red : COL.green);
  const metal = s.object === 'gold' || s.object === 'silver' ? s.object : null;
  return (
    <AbsoluteFill>
      <Backdrop tint={metal === 'silver' ? '#5b6b85' : metal ? '#b8860b' : accent} />
      <div style={{position: 'absolute', right: -40, top: 20, width: 760, height: 700}}>
        {metal ? (
          <ThreeCanvas width={760} height={700} camera={{position: [0, 0.6, 7], fov: 40}}>
            <MetalBar metal={metal} />
          </ThreeCanvas>
        ) : (
          <div style={{width: 760, height: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: anton,
            fontSize: (SYMBOL[s.object ?? 'dollar'] ?? '$').length > 2 ? 250 : 520, color: 'transparent',
            backgroundImage: 'linear-gradient(160deg, #ffffff 0%, #c9ced8 35%, #6b7280 60%, #e5e7eb 100%)', WebkitBackgroundClip: 'text', backgroundClip: 'text',
            filter: `drop-shadow(0 30px 60px rgba(0,0,0,0.8)) drop-shadow(0 0 40px ${accent}66)`}}>{SYMBOL[s.object ?? 'dollar'] ?? '$'}</div>
        )}
      </div>
      <div style={{position: 'absolute', right: 40, bottom: 30}}><CrashArrow color={accent} size={330} dir={dir} /></div>
      <div style={{position: 'absolute', left: 50, top: 150, width: 640}}>
        <BigText text={s.text ?? ''} color={col(s.textColor, accent)} size={150} width={600} />
      </div>
      {s.number ? <div style={{position: 'absolute', left: 58, bottom: 60}}><NumberTag n={s.number} color={accent} size={130} /></div> : null}
    </AbsoluteFill>
  );
};

// ---------- photo (3 Eki: kullanıcı "daha gerçekçi + clickbait" istedi) ----------
// Tam ekran foto-gerçekçi sahne (RealVisXL, tools/thumb_photo.py) + sol kararma + kalın konturlu sarı/beyaz yazı
// + odak noktasında kırmızı halka + dev ok + rakam etiketi. Yazı/rakam yine dürüst olmalı (prompt kuralı).
const STROKE = (w: number) => `${w}px #000`;
const PhotoThumb: React.FC<{s: ProSpec}> = ({s}) => {
  const dir = s.dir ?? 'down';
  const accent = col(s.numberColor, dir === 'down' ? COL.red : COL.green);
  const fx = s.focusX ?? 0.72;
  const fy = s.focusY ?? 0.55;
  return (
    <AbsoluteFill>
      <Img src={staticFile(s.bg!)} style={{position: 'absolute', inset: 0, width: 1280, height: 720, objectFit: 'cover',
        filter: 'contrast(1.18) saturate(1.3) brightness(1.05)'}} />
      <AbsoluteFill style={{background: 'linear-gradient(90deg, rgba(0,0,0,0.88) 0%, rgba(0,0,0,0.6) 38%, rgba(0,0,0,0) 62%)'}} />
      <AbsoluteFill style={{background: `radial-gradient(ellipse at ${fx * 100}% ${fy * 100}%, transparent 30%, rgba(0,0,0,0.45) 100%)`}} />
      {/* odak halkası (el çizimi hissi: hafif eğik elips) */}
      <svg width={1280} height={720} style={{position: 'absolute', inset: 0}}>
        <ellipse cx={fx * 1280} cy={fy * 720} rx={210} ry={150} fill="none" stroke={COL.red} strokeWidth={14}
          transform={`rotate(-8 ${fx * 1280} ${fy * 720})`} style={{filter: 'drop-shadow(0 0 14px rgba(255,45,61,0.9))'}} />
      </svg>
      <div style={{position: 'absolute', left: Math.min(fx * 1280 + 120, 1000), top: dir === 'down' ? Math.max(fy * 720 - 330, 0) : fy * 720 + 20}}>
        <CrashArrow color={accent} size={260} dir={dir} />
      </div>
      <div style={{position: 'absolute', left: 46, top: 140, width: 660}}>
        <BigText text={s.text ?? ''} color={col(s.textColor, COL.gold)} size={170} width={640}
          style={{WebkitTextStroke: STROKE(5), paintOrder: 'stroke fill'} as React.CSSProperties} />
      </div>
      {s.number ? <div style={{position: 'absolute', left: 56, bottom: 50}}><NumberTag n={s.number} color={accent} size={140} /></div> : null}
    </AbsoluteFill>
  );
};


// ---------- 15 Eki: yerleşim çeşitliliği (kullanıcı: "hep aynı taslak, ben de tıklamam") ----------
// Aynı foto-gerçekçi arka plan, ama kompozisyon farklı: hero (dev rakam), split (çapraz panel), banner (alt bant),
// marker (fosforlu kalem yazı), center (ortada yazı + yan rakam). classic = eski taslak.
const MARK = (c: string): React.CSSProperties => ({background: c, color: '#000', padding: '4px 22px 0', display: 'inline-block', textShadow: 'none', boxShadow: '8px 8px 0 #000'});
const LayoutThumb: React.FC<{s: ProSpec}> = ({s}) => {
  const dir = s.dir ?? 'down';
  const accent = col(s.numberColor, dir === 'down' ? COL.red : COL.green);
  const a2 = col(s.accent2, COL.gold);
  const L = s.layout!;
  const img = (f: string, extra?: React.CSSProperties) => (
    <Img src={staticFile(s.bg!)} style={{position: 'absolute', inset: 0, width: 1280, height: 720, objectFit: 'cover', filter: f, ...extra}} />
  );
  const lines = (s.text ?? '').trim().split(' ').filter(Boolean);
  const half = Math.ceil(lines.length / 2);
  const l1 = lines.slice(0, half).join(' ');
  const l2 = lines.slice(half).join(' ');
  if (L === 'hero') {
    return (
      <AbsoluteFill>
        {img('contrast(1.15) saturate(1.25) brightness(0.8) blur(1.5px)')}
        <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 45%, rgba(0,0,0,0.15) 0%, rgba(0,0,0,0.78) 100%)'}} />
        {s.number ? (
          <div style={{position: 'absolute', left: 0, width: 1280, top: 70, textAlign: 'center', fontFamily: anton, fontSize: 430, lineHeight: 1, color: accent,
            WebkitTextStroke: STROKE(10), paintOrder: 'stroke fill', textShadow: `0 0 80px ${accent}aa, 0 14px 0 #000`} as React.CSSProperties}>{s.number}</div>
        ) : null}
        <div style={{position: 'absolute', left: 0, width: 1280, bottom: 44, textAlign: 'center'}}>
          <BigText text={s.text ?? ''} color={a2} size={118} width={1100} style={{display: 'inline-block', textAlign: 'center'}} />
        </div>
      </AbsoluteFill>
    );
  }
  if (L === 'split') {
    return (
      <AbsoluteFill>
        {img('contrast(1.2) saturate(1.3)', {clipPath: 'polygon(0 0, 66% 0, 50% 100%, 0 100%)'})}
        <AbsoluteFill style={{background: `linear-gradient(115deg, transparent 0 48%, #000 48% 49.5%, ${accent} 49.5% 100%)`}} />
        <AbsoluteFill style={{background: 'linear-gradient(90deg, rgba(0,0,0,0) 0%, rgba(0,0,0,0.0) 60%)'}} />
        <div style={{position: 'absolute', left: 640, top: 130, width: 600}}>
          <BigText text={s.text ?? ''} color={a2} size={150} width={580} style={{WebkitTextStroke: STROKE(4), paintOrder: 'stroke fill'} as React.CSSProperties} />
        </div>
        {s.number ? <div style={{position: 'absolute', left: 120, bottom: 50}}><NumberTag n={s.number} color="#000" size={120} rot={-4} /></div> : null}
      </AbsoluteFill>
    );
  }
  if (L === 'banner') {
    return (
      <AbsoluteFill>
        {img('contrast(1.2) saturate(1.35) brightness(1.08)')}
        <AbsoluteFill style={{background: 'linear-gradient(0deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0) 45%)'}} />
        <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 270, background: '#000', borderTop: `10px solid ${a2}`, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
          <BigText text={s.text ?? ''} color={a2} size={112} width={1160} style={{textAlign: 'center'}} />
        </div>
        {s.number ? <div style={{position: 'absolute', right: 50, top: 70}}><NumberTag n={s.number} color={accent} size={150} rot={5} /></div> : null}
      </AbsoluteFill>
    );
  }
  if (L === 'marker') {
    return (
      <AbsoluteFill>
        {img('contrast(1.15) saturate(1.25) brightness(0.95)')}
        <AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(0,0,0,0.25) 0%, rgba(0,0,0,0.0) 40%, rgba(0,0,0,0.55) 100%)'}} />
        <div style={{position: 'absolute', left: 54, top: 170, fontFamily: anton, textTransform: 'uppercase', lineHeight: 1.12}}>
          <div style={{fontSize: 150}}><span style={MARK('#fff')}>{l1}</span></div>
          {l2 ? <div style={{fontSize: 150, marginTop: 14, marginLeft: 40}}><span style={MARK(a2)}>{l2}</span></div> : null}
        </div>
        {s.number ? (
          <div style={{position: 'absolute', right: 70, bottom: 60, width: 330, height: 330, borderRadius: 330, background: accent, border: '12px solid #fff', display: 'flex', alignItems: 'center',
            justifyContent: 'center', fontFamily: anton, fontSize: s.number.length > 5 ? 84 : 112, color: '#fff', transform: 'rotate(-8deg)', boxShadow: `0 0 70px ${accent}`}}>{s.number}</div>
        ) : null}
      </AbsoluteFill>
    );
  }

  if (L === 'stack') {  // dev 3 satır, kelime başına satır; sağda foto görünür
    const ws = lines.length ? lines : [''];
    return (
      <AbsoluteFill>
        {img('contrast(1.2) saturate(1.3) brightness(0.95)')}
        <AbsoluteFill style={{background: 'linear-gradient(90deg, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.7) 45%, rgba(0,0,0,0) 75%)'}} />
        <div style={{position: 'absolute', left: 50, top: 120, fontFamily: anton, textTransform: 'uppercase', lineHeight: 0.92, textShadow: OUT}}>
          {ws.slice(0, 4).map((w, i) => <div key={i} style={{fontSize: Math.min(250, Math.floor(700 / Math.max(w.length * 0.5, 3))), color: i === ws.length - 1 ? a2 : '#fff', WebkitTextStroke: STROKE(4)} as React.CSSProperties}>{w}</div>)}
        </div>
        {s.number ? <div style={{position: 'absolute', right: 50, bottom: 50}}><NumberTag n={s.number} color={accent} size={130} rot={4} /></div> : null}
      </AbsoluteFill>
    );
  }
  if (L === 'poster') {  // tam genişlik üst yazı + alt rakam şeridi
    return (
      <AbsoluteFill>
        {img('contrast(1.15) saturate(1.25) brightness(1)')}
        <AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.3) 40%, rgba(0,0,0,0) 60%, rgba(0,0,0,0.8) 100%)'}} />
        <div style={{position: 'absolute', left: 0, width: 1280, top: 112, textAlign: 'center'}}>
          <BigText text={s.text ?? ''} color={a2} size={150} width={1180} style={{display: 'inline-block', textAlign: 'center', WebkitTextStroke: STROKE(5), paintOrder: 'stroke fill'} as React.CSSProperties} />
        </div>
        {s.number ? (
          <div style={{position: 'absolute', left: 0, width: 1280, bottom: 0, height: 150, background: accent, display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: anton, fontSize: 104, paddingTop: 8, color: '#fff', textShadow: '0 6px 0 rgba(0,0,0,0.5)', borderTop: '8px solid #fff'}}>{s.number}</div>
        ) : null}
      </AbsoluteFill>
    );
  }
  if (L === 'tilt') {  // eğik dev yazı, damga hissi
    return (
      <AbsoluteFill>
        {img('contrast(1.2) saturate(1.3) brightness(0.9)')}
        <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0.5) 0%, rgba(0,0,0,0.1) 80%)'}} />
        <div style={{position: 'absolute', left: 40, width: 1200, top: 150, transform: 'rotate(-7deg)', textAlign: 'center'}}>
          <div style={{display: 'inline-block', border: `14px solid ${accent}`, padding: '6px 40px 0', background: 'rgba(0,0,0,0.55)', borderRadius: 18}}>
            <BigText text={s.text ?? ''} color={a2} size={165} width={1050} style={{textAlign: 'center'}} />
          </div>
        </div>
        {s.number ? <div style={{position: 'absolute', left: 70, bottom: 50}}><NumberTag n={s.number} color={accent} size={140} rot={-8} /></div> : null}
      </AbsoluteFill>
    );
  }
  if (L === 'hazard') {  // sarı-siyah uyarı şeridi
    return (
      <AbsoluteFill>
        {img('contrast(1.2) saturate(1.3) brightness(0.95)')}
        <AbsoluteFill style={{background: 'linear-gradient(0deg, rgba(0,0,0,0.8) 0%, rgba(0,0,0,0) 50%)'}} />
        <div style={{position: 'absolute', left: 0, right: 0, top: 120, height: 36, background: 'repeating-linear-gradient(135deg, #FFD400 0 28px, #000 28px 56px)'}} />
        <div style={{position: 'absolute', left: 0, right: 0, top: 156, background: 'rgba(0,0,0,0.88)', padding: '14px 0 0', textAlign: 'center'}}>
          <BigText text={s.text ?? ''} color={a2} size={150} width={1180} style={{display: 'inline-block', textAlign: 'center'}} />
        </div>
        {s.number ? <div style={{position: 'absolute', right: 56, bottom: 46}}><NumberTag n={s.number} color={accent} size={150} rot={-5} /></div> : null}
        <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 28, background: 'repeating-linear-gradient(135deg, #FFD400 0 28px, #000 28px 56px)'}} />
      </AbsoluteFill>
    );
  }
  if (L === 'duo') {  // üst satır beyaz bant, alt satır renkli dev yazı, foto arada
    return (
      <AbsoluteFill>
        {img('contrast(1.2) saturate(1.3)')}
        <div style={{position: 'absolute', left: 0, right: 0, top: 0, height: 250, background: accent, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
          <div style={{fontFamily: anton, fontSize: Math.min(190, Math.floor(1150 / Math.max(l1.length * 0.5, 4))), color: '#fff', textTransform: 'uppercase', lineHeight: 1, whiteSpace: 'nowrap', paddingTop: 10, textShadow: '0 6px 0 rgba(0,0,0,0.45)'}}>{l1}</div>
        </div>
        <AbsoluteFill style={{background: 'linear-gradient(0deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0) 45%)'}} />
        <div style={{position: 'absolute', left: 0, width: 1280, bottom: 40, textAlign: 'center'}}>
          <div style={{fontFamily: anton, fontSize: Math.min(220, Math.floor(1180 / Math.max((l2 || l1).length * 0.5, 4))), color: a2, textTransform: 'uppercase', lineHeight: 1, whiteSpace: 'nowrap',
            WebkitTextStroke: STROKE(6), paintOrder: 'stroke fill', textShadow: OUT} as React.CSSProperties}>{l2 || ''}</div>
        </div>
        {s.number ? <div style={{position: 'absolute', right: 40, top: 270}}><NumberTag n={s.number} color={accent} size={110} rot={6} /></div> : null}
      </AbsoluteFill>
    );
  }
  // center
  return (
    <AbsoluteFill>
      {img('contrast(1.2) saturate(1.3) brightness(0.9)')}
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0.65) 0%, rgba(0,0,0,0.15) 75%)'}} />
      <div style={{position: 'absolute', left: 0, width: 1280, top: 210, textAlign: 'center'}}>
        <BigText text={s.text ?? ''} color={a2} size={190} width={1120} style={{display: 'inline-block', textAlign: 'center', WebkitTextStroke: STROKE(6), paintOrder: 'stroke fill'} as React.CSSProperties} />
      </div>
      {s.number ? <div style={{position: 'absolute', left: 0, width: 1280, bottom: 40, textAlign: 'center'}}><NumberTag n={s.number} color={accent} size={120} rot={-3} /></div> : null}
      <div style={{position: 'absolute', right: 40, top: 40}}><CrashArrow color={accent} size={190} dir={dir} /></div>
    </AbsoluteFill>
  );
};

// ---------- chart ----------
const ChartThumb: React.FC<{s: ProSpec}> = ({s}) => {
  const data = (s.data ?? []).slice(-60);
  const dir = s.dir ?? 'down';
  const accent = col(s.numberColor, dir === 'down' ? COL.red : COL.green);
  const W = 1280;
  const H = 720;
  const vals = [...data, ...(s.threshold !== undefined ? [s.threshold] : [])];
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = (hi - lo) * 0.12 || 1;
  const x = (i: number) => 40 + (i / Math.max(data.length - 1, 1)) * (W - 200);
  const y = (v: number) => 180 + (1 - (v - (lo - pad)) / (hi + pad - (lo - pad))) * (H - 260);
  const pts = data.map((v, i) => `${x(i)},${y(v)}`).join(' ');
  // son kırılma (en güncel olay)
  let brk = -1;
  if (s.threshold !== undefined) {
    const t = s.threshold;
    for (let k = 1; k < data.length; k++) if (dir === 'down' ? data[k - 1] >= t && data[k] < t : data[k - 1] <= t && data[k] > t) brk = k;
  }
  const bi = brk > 0 ? brk : data.length - 1;
  const ex = x(bi);
  const ey = s.threshold !== undefined ? y(s.threshold) : y(data[bi] ?? 0);
  return (
    <AbsoluteFill>
      <Backdrop tint={accent} />
      <svg width={W} height={H} style={{position: 'absolute', inset: 0}}>
        <defs>
          <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={accent} stopOpacity={0.45} />
            <stop offset="100%" stopColor={accent} stopOpacity={0} />
          </linearGradient>
        </defs>
        {data.length > 1 ? <polygon points={`${x(0)},${H} ${pts} ${x(data.length - 1)},${H}`} fill="url(#fill)" /> : null}
        {data.length > 1 ? <polyline points={pts} fill="none" stroke={accent} strokeWidth={12} strokeLinejoin="round" strokeLinecap="round" style={{filter: `drop-shadow(0 0 18px ${accent})`}} /> : null}
        {s.threshold !== undefined ? (
          <>
            <line x1={0} x2={W} y1={ey} y2={ey} stroke="#fff" strokeWidth={6} strokeDasharray="26 18" opacity={0.9} />
            {/* kırılma patlaması */}
            {Array.from({length: 14}).map((_, i) => {
              const a = (i / 14) * Math.PI * 2;
              return <line key={i} x1={ex + Math.cos(a) * 30} y1={ey + Math.sin(a) * 30} x2={ex + Math.cos(a) * (70 + (i % 3) * 30)} y2={ey + Math.sin(a) * (70 + (i % 3) * 30)}
                stroke="#fff" strokeWidth={6} strokeLinecap="round" />;
            })}
            <circle cx={ex} cy={ey} r={22} fill="#fff" />
          </>
        ) : null}
      </svg>
      {s.thresholdLabel ? (
        <div style={{position: 'absolute', left: ex > W * 0.6 ? ex - 420 : ex + 70, top: dir === 'down' ? ey - 140 : ey + 30, width: 360, textAlign: ex > W * 0.6 ? 'right' : 'left',
          fontFamily: anton, fontSize: 96, color: '#fff', textShadow: OUT}}>{s.thresholdLabel}</div>
      ) : null}
      <div style={{position: 'absolute', left: 50, top: 120, width: 900}}>
        <BigText text={s.text ?? ''} color={col(s.textColor, accent)} size={140} width={780} />
      </div>
      {s.number ? <div style={{position: 'absolute', right: 60, top: 60}}><NumberTag n={s.number} color={accent} size={110} rot={4} /></div> : null}
    </AbsoluteFill>
  );
};

// ---------- face ----------
const FaceThumb: React.FC<{s: ProSpec}> = ({s}) => {
  const dir = s.dir ?? 'down';
  const accent = col(s.numberColor, dir === 'down' ? COL.red : COL.green);
  return (
    <AbsoluteFill>
      <Backdrop tint={accent} />
      <div style={{position: 'absolute', right: 0, top: 0, width: 700, height: 720, background: `radial-gradient(circle at 60% 45%, ${accent}66 0%, transparent 60%)`}} />
      <Img src={staticFile(s.image ?? 'auto/host_cut.png')} style={{position: 'absolute', right: -20, bottom: 0, height: 720, width: 680, objectFit: 'cover', objectPosition: '50% 10%',
        filter: 'contrast(1.12) saturate(1.15) drop-shadow(-20px 0 40px rgba(0,0,0,0.7))'}} />
      <div style={{position: 'absolute', left: 50, top: 150, width: 640}}>
        <BigText text={s.text ?? ''} color={col(s.textColor, accent)} size={160} width={600} />
      </div>
      {s.number ? <div style={{position: 'absolute', left: 60, bottom: 60}}><NumberTag n={s.number} color={accent} size={140} /></div> : null}
    </AbsoluteFill>
  );
};

export const ThumbPro: React.FC<{spec: ProSpec}> = ({spec}) => (
  <AbsoluteFill style={{background: '#04060b', overflow: 'hidden'}}>
    {spec.bg && spec.style !== 'chart' && spec.layout && spec.layout !== 'classic' ? <LayoutThumb s={spec} /> : spec.bg && spec.style !== 'chart' ? <PhotoThumb s={spec} /> : spec.style === 'object' ? <ObjectThumb s={spec} /> : spec.style === 'chart' ? <ChartThumb s={spec} /> : <FaceThumb s={spec} />}
    {/* 1 Eki: başka kanal kurgusunda (spec.noBrand) Finans Kanalı logosu basılmaz */}
    {(spec as {noBrand?: boolean}).noBrand ? null : <div style={{position: 'absolute', left: 48, top: 36}}><BrandMark h={62} /></div>}
  </AbsoluteFill>
);
