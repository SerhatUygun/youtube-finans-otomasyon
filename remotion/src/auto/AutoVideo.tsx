// Veri güdümlü kompozisyon: plan (props) -> sahne dizisi + HUD + altyazı + ses. Yatay (16:9)
// uzun video ve dikey (9:16) Reels aynı bileşeni `layout` ile kullanır.
import React from 'react';
import {AbsoluteFill, Audio, OffthreadVideo, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {T, applyTheme, fmtTR, setLocale} from '../core/theme';
import {Grade, Grain, Vignette, clamp, ease} from '../core/kit';
import {SceneExit, SceneProvider, Timeline, cueAbs} from '../core/timing';
import {DataProvider, P, Series} from './data';
import {BrandMark} from '../core/brand';
import * as A from './templatesA';
import * as B from './templatesB';
import * as C from './templatesC';
import * as D from './templatesD';
import * as E from './templatesE';
import {Presenter3D} from './Presenter3D';
import {Expr, GestureCue, Presenter} from './Presenter';

export type Plan = Timeline & {
  layout?: 'h' | 'v';
  hud?: {date?: string; chapters?: {name: string; cue?: string; from?: number}[]; label?: string};
  ticker?: {n: string; v: string; ch?: number | null}[];
  series?: Record<string, Series>;
  scenes: {t: string; cue?: string; from?: number; p?: P; layout?: FootLayout; tr?: Trans}[];
  // Kamera çekimi (kendi çekimin ya da dijital ikiz): taban katman; sahneler `layout` ile üstüne yerleşir.
  footage?: {src: string; volume?: number; faceX?: number}; // faceX: yüzün yatay konumu 0..1 (edit_footage ölçer)
  lang?: 'tr' | 'en'; // 1 Eki: başka kanal (ör. İngilizce) kurgusu -> sayı biçimi + HUD metinleri
  brand?: {name: string; sub?: string}; // verilirse Finans Kanalı logosu yerine bu kanal adı yazılır
  progressTotal?: number; // açılış varyantı: üst ilerleme çubuğu birleşik videonun toplam süresine göre
  hits?: {cue: string; sfx: string; vol?: number}[];
  beat?: number; // 9 Eki: müzik vuruşu (kare); sahne başlangıçları ±5 kare içindeki vuruşa oturur
  emph?: number[];
  presenter?: {mouth: number[]; vis: string}; // 9 Eki: 2D çizim sunucu (build.py _presenter_track)
  captionStyle?: 'box' | 'hormozi' | 'minimal' | 'pill' | 'yellow' | 'karaoke'; // 15 Eki: altyazı stili (internette en çok kullanılanlar); yoksa 'box'
  theme?: string; // 15 Eki: tema paketi (core/theme.ts THEMES); yoksa varsayılan lacivert
  transSeed?: number; // 15 Eki: >0 ise geçiş sırası genişletilmiş set + günlük kaydırma ile çeşitlenir
  presenter3d?: boolean;
  presenterVariant?: string; // 19 Eki: Presenter3D VARIANTS anahtarı // 18 Eki: takım elbiseli 3D çizgi sunucu (Presenter3D)
  presenterPip?: boolean; // 13 Eki: referans düzeni — sunucu sol altta sabit yuvarlak kutuda, sahneler tam ekran
  hookBig?: string; // 9 Eki: Shorts 0. kare damgası (build.py _hook_big)
  hookSub?: string; // 9 Eki: seste vurgulu kelimelerin karesi (build.py _emphasis) -> Punch yakınlaşması
  audio?: {voice?: string; music?: string; musicFrom?: number; noFadeOut?: boolean};
  captions?: boolean;
  endCard?: {text: string; sub?: string};
};

export const TEMPLATES: Record<string, React.FC<{p: P}>> = {
  Intro: A.Intro, KineticTitle: A.KineticTitle, Stamp: A.Stamp, StatCards: A.StatCards, Gauge: A.GaugeScene,
  Dots: A.DotScene, ReasonCards: A.ReasonCards, Quote: A.Quote,
  Chart: B.ChartScene, Normalized: B.Normalized, Compare: B.Compare, Ladder: B.Ladder, Scenario: B.Scenario,
  RangeBar: B.RangeBar, Vote: B.Vote, Bars: B.Bars, Volatility: B.Volatility, Timeline: B.Timeline, CoinFlip: B.CoinFlip,
  Tug: B.Tug, AssetCards: B.AssetCards, Chapter: B.Chapter, Disclaimer: B.Disclaimer, Poll: B.Poll, Outro: B.Outro,
  DateQuestion: B.DateQuestion,
  Candles: C.Candles, Heatmap: C.Heatmap, WorldMap: C.WorldMap, YieldCurve: C.YieldCurve, Breaking: C.Breaking,
  Countdown: C.Countdown, Headline: C.Headline, Metal3D: D.Metal3D, Globe3D: D.Globe3D, Bars3D: E.Bars3D, Stack3D: E.Stack3D, Object3D: E.Object3D, Scale3D: E.Scale3D, HostStage: E.HostStage, PumpBoard: C.PumpBoard, Waterfall: C.Waterfall, DominoChain: C.DominoChain,
};

// ---------------- Çekim (footage) katmanı ----------------
// full: grafik tam ekran (kişi arkada, ses sürer) · split: grafik solda, kişi sağda · corner: kişi tam ekran, grafik köşe kartında
// cam: yalnız kişi (grafik yok)
// 1 Eki: left/right: kişi tam ekran ama karşı tarafa kayar, grafik yan panelde (kişinin solunda/sağında) belirir
//        pip: grafik tam ekran, kişi sağ üstte küçük yuvarlak köşeli pencerede konuşmaya devam eder
export type FootLayout = 'full' | 'split' | 'corner' | 'cam' | 'left' | 'right' | 'pip';
const PIP: Rect = {x: 1920 - 56 - 432, y: 128, w: 432, h: 243};
const SPLIT_X = 1100;
type Rect = {x: number; y: number; w: number; h: number};
const camRect = (l: FootLayout): Rect => (l === 'split' ? {x: SPLIT_X, y: 0, w: 1920 - SPLIT_X, h: 1080} : l === 'pip' ? PIP : {x: 0, y: 0, w: 1920, h: 1080});
// yan panelde kişiyi panelin karşı tarafına kaydır (yüz panelin altında kalmasın); faceX yüzün çekimdeki yeri
const camShift = (l: FootLayout, faceX = 0.5): number => {
  if (l === 'left') return Math.max(0, 0.66 - faceX) * 1920; // panel solda -> yüz ekranın ~%66'sına
  if (l === 'right') return -Math.max(0, faceX - 0.34) * 1920;
  return 0;
};
const lerpRect = (a: Rect, b: Rect, t: number): Rect => ({x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, w: a.w + (b.w - a.w) * t, h: a.h + (b.h - a.h) * t});

const FootageLayer: React.FC<{plan: Plan; scenes: ReturnType<typeof timedScenes>}> = ({plan, scenes}) => {
  const f = useCurrentFrame();
  const idx = scenes.reduce((a, s, i) => (f >= s.start ? i : a), 0);
  const cur = scenes[idx];
  const prev = scenes[idx - 1];
  const lay = cur?.layout ?? 'cam';
  const t = prev ? ease(f, cur.start, cur.start + 14, 0, 1, T.ease.inOut) : 1;
  const r = lerpRect(camRect(prev?.layout ?? lay), camRect(lay), t);
  // kesme hissi: her sahnede dönüşümlü hafif yakınlaştırma (punch-in), sahne boyunca çok yavaş itme
  const faceX = plan.footage!.faceX ?? 0.5;
  const sh = camShift(prev?.layout ?? lay, faceX) + (camShift(lay, faceX) - camShift(prev?.layout ?? lay, faceX)) * t;
  // kaydırınca kenarda boşluk görünmesin: kayma oranında büyüt
  const zoom = 1 + (2 * Math.abs(sh)) / 1920;
  const punch = ((idx % 2 ? 1.07 : 1.0) + 0.02 * Math.min((f - (cur?.start ?? 0)) / Math.max(cur?.len ?? 1, 1), 1)) * zoom;
  const isPip = lay === 'pip' && t > 0.5;
  return (
    <div style={{position: 'absolute', left: r.x, top: r.y, width: r.w, height: r.h, overflow: 'hidden', background: '#000',
      borderRadius: isPip ? 18 : 0, border: isPip ? `2px solid ${T.c.line}` : undefined, boxShadow: isPip ? '0 18px 50px rgba(0,0,0,0.6)' : undefined,
      zIndex: lay === 'pip' ? 5 : undefined}}>
      <OffthreadVideo src={staticFile(plan.footage!.src)} volume={plan.footage!.volume ?? 1}
        style={{width: '100%', height: '100%', objectFit: 'cover', transform: `translateX(${sh}px) scale(${punch})`}} />
      {/* açık arka planlı çekimde HUD/altyazı okunaklı kalsın */}
      <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(rgba(6,8,14,0.7) 0px, rgba(6,8,14,0) 170px, rgba(6,8,14,0) 800px, rgba(6,8,14,0.65) 1080px)'}} />
      {lay === 'split' ? <div style={{position: 'absolute', left: 0, top: 0, bottom: 0, width: 6, background: `linear-gradient(${T.c.accent}, ${T.c.hero})`}} /> : null}
    </div>
  );
};

// Sahneyi layout'a göre yerleştir: split'te sol panele ölçekli, corner'da köşe kartı.
const Placed: React.FC<{layout: FootLayout | undefined; footage: boolean; children: React.ReactNode}> = ({layout, footage, children}) => {
  if (!footage || !layout || layout === 'full') return <AbsoluteFill style={{background: footage ? T.c.bg : undefined}}>{children}</AbsoluteFill>;
  if (layout === 'cam') return null;
  if (layout === 'pip') return <AbsoluteFill style={{background: T.c.bg}}>{children}</AbsoluteFill>;
  if (layout === 'left' || layout === 'right') {
    // yan panel: cam gibi buzlu kart, şablon 0,47 ölçekte; kişi karşı tarafta
    const k = 0.47;
    const w = 1920 * k, h = 1080 * k;
    return (
      <div style={{position: 'absolute', [layout]: 48, top: (1080 - h) / 2 - 20, width: w, height: h, borderRadius: 24, overflow: 'hidden',
        background: 'rgba(8,11,18,0.82)', backdropFilter: 'blur(14px)', border: `2px solid ${T.c.line}`, boxShadow: '0 30px 80px rgba(0,0,0,0.6)'}}>
        <div style={{position: 'absolute', [layout === 'left' ? 'right' : 'left']: 0, top: 0, bottom: 0, width: 5, background: `linear-gradient(${T.c.accent}, ${T.c.hero})`, zIndex: 2}} />
        <div style={{width: 1920, height: 1080, transform: `scale(${k})`, transformOrigin: '0 0', position: 'relative'}}>{children}</div>
      </div>
    );
  }
  if (layout === 'split') {
    // 30 Eyl: 0,57 ölçekte küçük yazılar okunmuyordu -> 0,66 + yatay ortadan kırpma (şablonların yan güvenli payı ~120 px)
    const k = 0.66;
    const offX = (1920 * k - SPLIT_X) / 2;
    return (
      <div style={{position: 'absolute', left: 0, top: 0, width: SPLIT_X, height: 1080, background: T.c.bg, overflow: 'hidden'}}>
        <div style={{position: 'absolute', left: -offX, top: (1080 - 1080 * k) / 2, width: 1920, height: 1080, transform: `scale(${k})`, transformOrigin: '0 0'}}>{children}</div>
      </div>
    );
  }
  const k = 0.42; // köşe kartı: daha büyük olursa ortadaki konuşmacının yüzüne biniyor (720p/1080p çekimlerde yüz ~x 850-1100)
  return (
    <div style={{position: 'absolute', left: 56, top: 120, width: 1920 * k, height: 1080 * k, borderRadius: 22, overflow: 'hidden', background: T.c.bg,
      border: `2px solid ${T.c.line}`, boxShadow: '0 24px 60px rgba(0,0,0,0.55)'}}>
      <div style={{width: 1920, height: 1080, transform: `scale(${k})`, transformOrigin: '0 0', position: 'relative'}}>{children}</div>
    </div>
  );
};

// ---------------- 2D sunucu (9 Eki) ----------------
// HOST: konuşma ağırlıklı sahneler -> grafik solda (split), karakter sağda büyük. CORNER: bölüm kartı -> karakter sağ altta.
// Diğerleri (yoğun grafik): tam ekran, karakter yok (okunabilirlik).
const HOST = ['KineticTitle', 'Quote', 'Headline', 'Breaking', 'Stamp', 'ReasonCards', 'Countdown', 'DateQuestion', 'Poll', 'Vote', 'CoinFlip', 'Tug', 'Gauge'];
const CORNER = ['Chapter'];
const HOST_GESTURE: Record<string, GestureCue['kind']> = {
  KineticTitle: 'explain', Quote: 'think', Headline: 'point', Breaking: 'point', Stamp: 'point', ReasonCards: 'explain',
  Countdown: 'point', DateQuestion: 'think', Poll: 'think', Vote: 'shrug', CoinFlip: 'shrug', Tug: 'explain', Gauge: 'point', Chapter: 'up',
};
export const presenterPlan = (plan: Plan, scenes: ReturnType<typeof timedScenes>) => {
  const gestures: GestureCue[] = [];
  const expr: {at: number; e: Expr}[] = [];
  scenes.forEach((s, i) => {
    if (i === 0) return;
    const d = sceneDir(s.p ?? {});
    expr.push({at: s.start, e: s.t === 'Breaking' ? 'surprised' : d > 0 ? 'happy' : d < 0 ? 'worried' : 'neutral'});
    if (HOST.includes(s.t) || CORNER.includes(s.t)) {
      gestures.push({at: s.start + 8, kind: HOST_GESTURE[s.t] ?? 'explain', len: Math.min(80, Math.max(s.len - 10, 30))});
      // uzun sahnede vurgulu kelimelerde ek jest (en az 3 sn arayla)
      let last = s.start + 8;
      for (const e of plan.emph ?? []) {
        if (e > last + 90 && e < s.start + s.len - 40) {
          gestures.push({at: e - 4, kind: gestures.length % 2 ? 'point' : 'explain', len: 60});
          last = e;
        }
      }
    }
    // soru cümlesi: düşünme
  });
  return {gestures, expr};
};

const PresenterLayer: React.FC<{plan: Plan; scenes: ReturnType<typeof timedScenes>; V: boolean}> = ({plan, scenes, V}) => {
  const f = useCurrentFrame();
  const pr = plan.presenter!;
  const {gestures, expr} = React.useMemo(() => presenterPlan(plan, scenes), [plan, scenes]);
  const idx = scenes.reduce((a, s, i) => (f >= s.start ? i : a), 0);
  if (plan.presenterPip && !V) {
    // sol altta sabit kutu: ilk sahneden (açılış) sonra girer, kapanışta çıkar; jestler vurgulu kelimelerde
    // 19 Eki: sunucu sahnenin içindeyken (3D sahne içi sunucu) köşe kutusu gizlenir
    const inScene = plan.presenter3d && ['Bars3D', 'Stack3D', 'Object3D', 'Scale3D', 'HostStage'].includes(scenes[idx]?.t);
    const on = idx > 0 && f < plan.outroStart && !inScene ? 1 : 0;
    const inT = ease(f, scenes[1]?.start ?? 0, (scenes[1]?.start ?? 0) + 14, 0, 1, T.ease.inOut);
    const outT = ease(f, plan.outroStart - 12, plan.outroStart, 1, 0, T.ease.inOut);
    const a = on ? inT : f >= plan.outroStart ? 0 : 0;
    const vis2 = Math.min(a, f >= plan.outroStart - 12 ? outT : 1);
    if (vis2 < 0.01) return null;
    const BOX = 330;
    const pg: GestureCue[] = [];
    (plan.emph ?? []).forEach((e, i) => { if (!pg.length || e > pg[pg.length - 1].at + 100) pg.push({at: e - 4, kind: (['explain', 'point', 'explain', 'think', 'shrug'] as const)[i % 5], len: 60}); });
    return (
      <AbsoluteFill style={{pointerEvents: 'none'}}>
        <div style={{position: 'absolute', left: 40, bottom: 52 + 26, width: BOX, height: BOX, borderRadius: 30, overflow: 'hidden', opacity: vis2,
          transform: `translateY(${(1 - vis2) * 60}px)`, border: '3px solid rgba(255,255,255,0.9)', boxShadow: '0 12px 40px rgba(0,0,0,0.55)',
          background: 'radial-gradient(ellipse 80% 70% at 50% 40%, #2a3a66, #121a30)'}}>
          <div style={{position: 'absolute', left: '50%', top: 4, transform: 'translateX(-50%)'}}>
            {plan.presenter3d ? <Presenter3D variant={plan.presenterVariant} mouth={pr.mouth} vis={pr.vis} gestures={pg} expr={expr} width={BOX} height={BOX} zoom={1.3} lift={0.55} /> : <Presenter mouth={pr.mouth} vis={pr.vis} gestures={pg} expr={expr} size={BOX * 0.96} mirror={false} crop={0.42} />}
          </div>
        </div>
      </AbsoluteFill>
    );
  }
  const kind = (i: number) => (i <= 0 || f >= plan.outroStart ? 'none' : HOST.includes(scenes[i]?.t) ? 'host' : CORNER.includes(scenes[i]?.t) ? 'corner' : 'none');
  const cur = kind(idx);
  const prev = kind(idx - 1);
  const t = ease(f, scenes[idx].start, scenes[idx].start + 12, 0, 1, T.ease.inOut);
  // görünürlük ve konum: önceki sahneden şimdikine yumuşak geçiş
  const vis = (k: string) => (k === 'none' ? 0 : 1);
  const show = vis(prev) + (vis(cur) - vis(prev)) * t;
  if (show < 0.01) return null;
  const pos = (k: string) => (V ? {x: 10, y: 1000, s: 410} : k === 'corner' ? {x: 1920 - 470, y: 1080 - 52 - 470, s: 470} : {x: 1180, y: 150, s: 930});
  const a = pos(prev === 'none' ? cur : prev);
  const b = pos(cur === 'none' ? prev : cur);
  const x = a.x + (b.x - a.x) * t, y = a.y + (b.y - a.y) * t, s = a.s + (b.s - a.s) * t;
  const slide = (1 - show) * (V ? -260 : 320);
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {!V && cur === 'host' ? (
        // sağ sahne: yumuşak spot ışığı + zemin
        <div style={{position: 'absolute', left: 1100, top: 0, width: 820, height: 1080, opacity: show * (prev === 'host' ? 1 : t),
          background: `radial-gradient(ellipse 60% 55% at 55% 62%, #22305a, ${T.c.bg} 75%)`}}>
          <div style={{position: 'absolute', left: 0, top: 0, bottom: 0, width: 6, background: `linear-gradient(${T.c.accent}, ${T.c.hero})`}} />
        </div>
      ) : null}
      <div style={{position: 'absolute', left: x + (V ? slide : 0), top: y + (V ? 0 : slide * 0.4), opacity: Math.min(1, show * 1.5),
        transform: V || cur !== 'host' ? undefined : undefined}}>
        <Presenter mouth={pr.mouth} vis={pr.vis} gestures={gestures} expr={expr} size={s} mirror={!V} crop={V ? 0.35 : cur === 'corner' ? 0.25 : 0} />
      </div>
    </AbsoluteFill>
  );
};

// ---------------- Ses tasarımı (30 Eyl) ----------------
// Her şablon kendi karakterinde ses çalar; kategoride varyantlar dönüşümlü (aynı ses art arda gelmez).
// Yoğunluk: iki otomatik efekt arası en az MIN_GAP kare (öncelikli olaylar hariç); sesler kısık — finans izleyicisi abartı sevmez.
type Cue2 = {at: number; sfx: string; vol: number; len: number; prio?: boolean};
const MIN_GAP = 75;
// 9 Eki: sahnenin "yönü" — props içindeki up/down renk/işaretlerinin çoğunluğu (+1 yükseliş, -1 düşüş, 0 belirsiz)
const sceneDir = (p: P): number => {
  const s = JSON.stringify(p);
  const up = (s.match(/"(?:color|tone|dir)":"(?:up|bull|green)"/g) ?? []).length;
  const dn = (s.match(/"(?:color|tone|dir)":"(?:down|bear|red)"/g) ?? []).length;
  return up > dn ? 1 : dn > up ? -1 : 0;
};
const pick = (arr: string[], i: number) => arr[i % arr.length];
export const sceneSfx = (plan: Plan, scenes: ReturnType<typeof timedScenes>): Cue2[] => {
  const out: Cue2[] = [];
  scenes.forEach((s, i) => {
    if (i === 0) return;
    const p: P = s.p ?? {};
    const c = (dt: number, sfx: string, vol: number, len = 60, prio = false) => out.push({at: s.start + dt, sfx, vol, len, prio});
    switch (s.t) {
      case 'Chapter': c(-30, 'reverse_swell', 0.32, 50, true); c(8, pick(['impact_deep_1', 'impact_deep_2'], i), 0.42, 60, true); break;
      case 'Breaking': c(2, 'alert_breaking', 0.3, 45, true); break;
      case 'Stamp': out.push({at: cueAbs(plan, p.bigCue ?? s.cue ?? '0', 0) + 2, sfx: 'impact_tight', vol: 0.32, len: 40, prio: true}); break;
      case 'Chart': case 'Candles': case 'Normalized': case 'YieldCurve': {
        const d = sceneDir(p);
        c(8, d > 0 ? 'lift_whoosh' : d < 0 ? 'drop_whoosh' : pick(['data_sweep_1', 'data_sweep_2'], i), d ? 0.2 : 0.16, 45);
        break;
      }
      case 'StatCards': case 'AssetCards': case 'Counter': {
        const d = sceneDir(p);
        c(6, pick(['counter_ticks_short', 'counter_ticks'], i), 0.12, 40);
        if (d) c(34, d > 0 ? 'rise_steps' : 'fall_steps', 0.18, 45, true); else c(34, 'number_lock', 0.2, 30, true);
        break;
      }
      case 'PumpBoard': c(40, 'counter_ticks', 0.14, 45); break;
      case 'Heatmap': case 'Dots': case 'Bars': case 'Waterfall': c(10, pick(['blips', 'blips_low'], i), 0.14, 40); break;
      case 'Metal3D': {
        const sh = D.shapeFor(String(p.symbol ?? ''), p.shape as string | undefined);
        c(10, sh === 'barrel' ? 'impact_deep_2' : sh === 'bills' ? 'cash_register' : sh === 'btc' || /XAG|silver/i.test(String(p.symbol ?? p.metal ?? '')) ? 'metal_ring_silver' : 'metal_ring_gold',
          sh === 'bills' ? 0.18 : 0.26, 70, true);
        break;
      }
      case 'Bars3D': c(10, pick(['blips', 'blips_low'], i), 0.14, 40); break;
      case 'Stack3D': c(8, 'coin_drop', 0.2, 40); break;
      case 'Scale3D': case 'HostStage': case 'Object3D': c(4, pick(['whoosh_air_1', 'whoosh_air_2'], i), 0.2, 40); break;
      case 'Globe3D': case 'WorldMap': c(0, pick(['whoosh_air_1', 'whoosh_air_2'], i), 0.22, 40); break;
      case 'Quote': out.push({at: cueAbs(plan, p.cue ?? s.cue ?? '0', 0), sfx: 'typewriter', vol: 0.1, len: 45}); break;
      case 'Headline': c(0, 'paper_flip', 0.28, 30); break;
      case 'Countdown': c(14, 'heartbeat', 0.28, 40); break;
      case 'DominoChain': c(14, 'impact_tight', 0.16, 30); break;
      case 'Scenario': case 'Tug': case 'CoinFlip': c(-4, pick(['swipe_1', 'swipe_2'], i), 0.2, 20); break;
      case 'Outro': c(20, 'chime_up', 0.26, 60, true); break;
      case 'Disclaimer': break;
      default: break;
    }
    // 8 Eki: her geçişin kendi sesi (hareketle eşleşir); şablon sesi yakınsa MIN_GAP eler, öncelikliler kalır
    const tk = pickTrans(i, s.t, s.tr);
    const tsfx: Partial<Record<Trans, [string[], number]>> = {
      fade: [['whoosh_subtle', 'whoosh_soft_1'], 0.1], push: [['swipe_1', 'swipe_2'], 0.16], rise: [['whoosh_soft_2', 'whoosh_air_1'], 0.14],
      wipe: [['paper_slide', 'swipe_2'], 0.16], zoom: [['whoosh_fast', 'whoosh_air_2'], 0.18], iris: [['reverse_swell'], 0.14], whip: [['whoosh_fast', 'swipe_1'], 0.2],
      clock: [['reverse_swell'], 0.14], flip: [['paper_flip', 'swipe_2'], 0.18], diag: [['whoosh_fast', 'swipe_1'], 0.16], split: [['whoosh_soft_2'], 0.14],
      glitch: [['glitch'], 0.16], blinds: [['data_sweep_1', 'data_sweep_2'], 0.14],
    };
    if (!['Chapter', 'Outro', 'Disclaimer'].includes(s.t)) { const ts = tsfx[tk] ?? TSFX_DEFAULT[tk] ?? [['whoosh_soft_1', 'swipe_1'], 0.14]; c(-6, pick(ts[0], i), ts[1], 30); }
  });
  out.sort((a, b) => a.at - b.at);
  const kept: Cue2[] = [];
  let last = -1e9;
  for (const x of out) {
    if (x.prio || x.at - last >= MIN_GAP) {
      kept.push(x);
      last = x.at;
    }
  }
  return kept;
};

const LEAD = 8;
const hookify = (p: P): P => {
  const out: P = Array.isArray(p) ? [] : {};
  for (const [k, v] of Object.entries(p)) {
    if ((k === 'cue' || k.endsWith('Cue')) && (typeof v === 'string' || typeof v === 'number')) out[k] = '0';
    else if (v && typeof v === 'object') out[k] = hookify(v as P);
    else out[k] = v;
  }
  return out;
};
const OVERLAP = 10;

export const timedScenes = (plan: Plan) => {
  const bf = plan.beat ?? 0;
  const mOff = -(plan.audio?.musicFrom ?? 0); // açılış varyantında müzik kaydırılmış başlar
  const snap = (x: number) => {
    if (bf < 8) return x;
    const b = mOff + Math.round((x - mOff) / bf) * bf;
    return b - x >= -6 && b - x <= 5 ? Math.round(b) : x; // konuşmanın önüne en fazla 6, arkasına 5 kare
  };
  const starts = plan.scenes.map((s, i) => (s.from !== undefined ? s.from : i === 0 && !s.cue ? 0 : snap(cueAbs(plan, s.cue ?? '0', LEAD))));
  return plan.scenes.map((s, i) => {
    const start = Math.max(0, starts[i]);
    const next = i < plan.scenes.length - 1 ? starts[i + 1] : plan.total;
    return {...s, start, len: Math.max(next - start, 12)};
  });
};

// ---------------- HUD (yatay) ----------------
const MiniSpark: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <div style={{width: 34, height: 34, position: 'relative', transform: `rotate(${f * 0.4}deg)`}}>
      {Array.from({length: 8}).map((_, i) => (
        <div key={i} style={{position: 'absolute', left: '50%', top: '50%', width: 4, height: i % 2 ? 11 : 16, background: T.c.hero, borderRadius: 4,
          transformOrigin: '50% 0%', transform: `translateX(-50%) rotate(${i * 45}deg) translateY(2px)`}} />
      ))}
    </div>
  );
};

const HUD: React.FC<{plan: Plan; showFrom: number}> = ({plan, showFrom}) => {
  const f = useCurrentFrame();
  const show = ease(f, showFrom - 20, showFrom, 0, 1) * ease(f, plan.outroStart - 10, plan.outroStart + 6, 1, 0, T.ease.in);
  if (show <= 0.001) return null;
  const chapters = (plan.hud?.chapters ?? []).map((c) => ({name: c.name, s: c.from ?? cueAbs(plan, c.cue ?? '0', 0)}));
  const cur = chapters.reduce((a, c, i) => (f >= c.s ? i : a), 0);
  return (
    <AbsoluteFill style={{opacity: show, pointerEvents: 'none'}}>
      <div style={{position: 'absolute', top: 0, left: 0, height: 4, width: 1920 * (f / (plan.progressTotal ?? plan.total)), background: `linear-gradient(90deg, ${T.c.accent}, ${T.c.hero})`}} />
      <div style={{position: 'absolute', top: 38, left: 56, display: 'flex', alignItems: 'center', gap: 16}}>
        {plan.brand ? <TextBrand b={plan.brand} h={52} /> : <BrandMark h={52} />}
      </div>
      {chapters.length ? (
        <div style={{position: 'absolute', top: 40, left: '50%', transform: 'translateX(-50%)', display: 'flex', gap: 8}}>
          {chapters.map((c, i) => (
            <div key={i} style={{padding: '7px 18px', borderRadius: 999, fontFamily: T.f.mono, fontSize: 17, letterSpacing: '0.12em', textTransform: 'uppercase',
              color: i === cur ? T.c.bg : T.c.dim, background: i === cur ? T.c.text : 'rgba(255,255,255,0.04)', border: `1px solid ${i === cur ? T.c.text : T.c.line}`}}>{c.name}</div>
          ))}
        </div>
      ) : null}
      {plan.hud?.date ? (
        <div style={{position: 'absolute', top: 40, right: 56, display: 'flex', alignItems: 'center', gap: 12, fontFamily: T.f.mono, fontSize: 20, color: T.c.dim, letterSpacing: '0.08em'}}>
          <div style={{width: 10, height: 10, borderRadius: '50%', background: T.c.down, opacity: 0.4 + 0.6 * Math.abs(Math.sin(f / 12))}} />
          {plan.hud.date}
        </div>
      ) : null}
      {plan.ticker?.length ? <Ticker items={plan.ticker} label={plan.hud?.label ?? (plan.lang === 'en' ? 'LAST CLOSE' : 'SON KAPANIŞ')} /> : null}
    </AbsoluteFill>
  );
};

// başka kanal kurgusu: logo yerine sade kanal adı rozeti
const TextBrand: React.FC<{b: NonNullable<Plan['brand']>; h: number}> = ({b, h}) => (
  <div style={{display: 'flex', alignItems: 'center', gap: 12, height: h}}>
    <div style={{width: 6, height: h * 0.8, borderRadius: 3, background: `linear-gradient(${T.c.accent}, ${T.c.hero})`}} />
    <div style={{display: 'flex', flexDirection: 'column', lineHeight: 1.05}}>
      <span style={{fontFamily: T.f.display, fontWeight: 900, fontSize: h * 0.42, color: T.c.text, letterSpacing: '0.06em', textTransform: 'uppercase'}}>{b.name}</span>
      {b.sub ? <span style={{fontFamily: T.f.mono, fontSize: h * 0.26, color: T.c.dim, letterSpacing: '0.12em', textTransform: 'uppercase'}}>{b.sub}</span> : null}
    </div>
  </div>
);

const Ticker: React.FC<{items: NonNullable<Plan['ticker']>; label: string}> = ({items, label}) => {
  const f = useCurrentFrame();
  const rowW = Math.max(items.length * 420, 2000);
  const x = -((f * 1.6) % rowW);
  const row = (k: string) => (
    <div style={{display: 'flex', width: rowW}}>
      {items.map((t, i) => (
        <div key={k + i} style={{display: 'flex', alignItems: 'center', gap: 14, paddingRight: 56, whiteSpace: 'nowrap'}}>
          <span style={{fontFamily: T.f.mono, fontSize: 19, color: T.c.dim, letterSpacing: '0.1em'}}>{t.n}</span>
          <span style={{fontFamily: T.f.mono, fontSize: 21, fontWeight: 700, color: T.c.text}}>{t.v}</span>
          {t.ch !== null && t.ch !== undefined ? (
            <span style={{fontFamily: T.f.mono, fontSize: 19, fontWeight: 700, color: t.ch >= 0 ? T.c.up : T.c.down}}>{t.ch >= 0 ? '▲' : '▼'}{fmtTR(Math.abs(t.ch), 1)}%</span>
          ) : null}
          <span style={{color: T.c.faint, marginLeft: 20}}>•</span>
        </div>
      ))}
    </div>
  );
  return (
    <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 52, background: 'rgba(6,8,14,0.85)', borderTop: `1px solid ${T.c.line}`, overflow: 'hidden', display: 'flex', alignItems: 'center'}}>
      <div style={{position: 'absolute', left: 0, top: 0, bottom: 0, zIndex: 2, display: 'flex', alignItems: 'center', padding: '0 22px', background: T.c.text,
        fontFamily: T.f.mono, fontWeight: 800, fontSize: 18, color: T.c.bg, letterSpacing: '0.12em'}}>{label}</div>
      <div style={{display: 'flex', transform: `translateX(${x}px)`, paddingLeft: 260}}>{row('a')}{row('b')}</div>
    </div>
  );
};

// ---------------- Karaoke altyazı ----------------
type Page = {s: number; e: number; words: {w: string; s: number}[]};
const buildPages = (plan: Plan, maxWords: number, maxChars: number): Page[] => {
  const pages: Page[] = [];
  plan.segments.forEach((seg) => {
    let cur: {w: string; s: number}[] = [];
    let chars = 0;
    const flush = () => {
      if (cur.length) pages.push({s: cur[0].s, e: 0, words: cur});
      cur = [];
      chars = 0;
    };
    seg.words.forEach((w, i) => {
      if (cur.length >= maxWords || chars + w.w.length > maxChars) flush();
      cur.push({w: w.w, s: w.s});
      chars += w.w.length + 1;
      if (/[,:;]$/.test(w.w) && cur.length >= 3 && i < seg.words.length - 2) flush();
    });
    flush();
    if (pages.length) pages[pages.length - 1].e = seg.e + 6;
  });
  for (let i = 0; i < pages.length; i++) {
    if (!pages[i].e) pages[i].e = pages[i + 1] ? pages[i + 1].s : pages[i].s + 60;
    if (pages[i + 1] && pages[i].e > pages[i + 1].s) pages[i].e = pages[i + 1].s;
  }
  return pages;
};

const Captions: React.FC<{plan: Plan; pages: Page[]; V: boolean; hostAt?: (fr: number) => boolean}> = ({plan, pages, V, hostAt}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (f >= plan.outroStart) return null;
  const p = pages.find((pg) => f >= pg.s - 2 && f < pg.e);
  if (!p) return null;
  const inP = spring({frame: f - p.s + 2, fps, config: T.spring.snappy});
  const cs = plan.captionStyle ?? 'box';
  if (cs !== 'box') {
    // 15 Eki: kutusuz/animasyonlu stiller. hormozi = BÜYÜK HARF kalın + aktif kelime renkli ve büyük; minimal = kutusuz beyaz, aktif tam parlak;
    // pill = aktif kelime renkli hap; yellow = klasik sarı aktif + siyah kontur; karaoke = söylenen kelimeler soldan dolar (renk geçişi)
    const base = V ? 76 : 58;
    return (
      <div style={{position: 'absolute', left: plan.presenterPip && !V ? 400 : 0, right: hostAt?.(f) ? 820 : 0, ...(V ? {top: 1380} : {bottom: 96}), display: 'flex', justifyContent: 'center', pointerEvents: 'none', padding: V ? '0 50px' : 0}}>
        <div style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', columnGap: V ? 28 : 26, rowGap: 2, transform: `translateY(${interpolate(inP, [0, 1], [10, 0])}px)`, opacity: interpolate(inP, [0, 0.4], [0, 1], clamp)}}>
          {p.words.map((w, i) => {
            const active = f >= w.s - 1 && (i === p.words.length - 1 || f < p.words[i + 1].s - 1);
            const past = f >= w.s - 1;
            const num = /\d|%|\$|₺/.test(w.w);
            const pop = active ? spring({frame: f - w.s + 1, fps, config: T.spring.bouncy}) : 1;
            const up = cs === 'hormozi' || cs === 'yellow';
            const txt = up ? w.w.toLocaleUpperCase('tr-TR') : w.w;
            const hi = num ? T.c.hero : cs === 'yellow' ? '#FFE600' : cs === 'hormozi' ? T.c.hero : T.c.accent;
            const stroke = cs === 'minimal' || cs === 'pill' ? undefined : '8px #000';
            let color: string = past ? T.c.text : 'rgba(243,241,234,0.4)';
            let bg: string | undefined;
            if (cs === 'hormozi' || cs === 'yellow') color = active || num ? hi : T.c.text;
            if (cs === 'minimal') color = active ? '#fff' : past ? 'rgba(255,255,255,0.78)' : 'rgba(255,255,255,0.35)';
            if (cs === 'pill') { color = active ? '#06080E' : T.c.text; bg = active ? hi : undefined; }
            if (cs === 'karaoke') color = past ? hi : T.c.text;
            const sc = active ? interpolate(pop, [0, 1], [cs === 'hormozi' ? 1.12 : 1.08, 1]) : 1;
            return (
              <span key={i} style={{fontFamily: T.f.display, fontWeight: 900, fontSize: cs === 'minimal' ? base * 0.86 : base, lineHeight: 1.12, letterSpacing: up ? '0.01em' : '-0.01em', color,
                background: bg, padding: bg ? '0 16px' : undefined, borderRadius: bg ? 14 : undefined, display: 'inline-block', transform: `scale(${sc})`, transformOrigin: '50% 70%',
                WebkitTextStroke: stroke, paintOrder: 'stroke fill', textShadow: cs === 'minimal' ? '0 4px 24px rgba(0,0,0,0.85)' : cs === 'pill' ? 'none' : '0 6px 0 rgba(0,0,0,0.55)'} as React.CSSProperties}>{txt}</span>
            );
          })}
        </div>
      </div>
    );
  }
  return (
    <div style={{position: 'absolute', left: plan.presenterPip && !V ? 400 : 0, right: hostAt?.(f) ? 820 : 0, ...(V ? {top: 1420} : {bottom: 86}), display: 'flex', justifyContent: 'center', pointerEvents: 'none', padding: V ? '0 60px' : 0}}>
      <div style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', columnGap: V ? 16 : 12, rowGap: 4, padding: V ? '16px 26px' : '12px 26px', borderRadius: 16,
        background: 'rgba(6,8,14,0.72)', border: `1px solid ${T.c.line}`, transform: `translateY(${interpolate(inP, [0, 1], [14, 0])}px)`, opacity: interpolate(inP, [0, 0.5], [0, 1], clamp)}}>
        {p.words.map((w, i) => {
          const active = f >= w.s - 1 && (i === p.words.length - 1 || f < p.words[i + 1].s - 1);
          const past = f >= w.s - 1;
          // 8 Eki: rakam/yüzde/para içeren kelime = anahtar bilgi -> altın renk + söylendiği an küçük sıçrama
          const num = /\d|%|\$|₺/.test(w.w);
          const pop = num && past ? spring({frame: f - w.s + 1, fps, config: T.spring.snappy}) : 1;
          // 9 Eki: inline-block ile ölçek gerçekten uygulanınca büyüyen kelime boşluğu yiyordu ("işlemlerdekimlik") -> kalıcı ölçek yok,
          // rakam sıçraması kısa ve merkezden
          const sc = num ? interpolate(pop, [0, 1], [1.12, 1]) : 1;
          return (
            <span key={i} style={{fontFamily: T.f.display, fontWeight: V || num ? 800 : 700, fontSize: V ? 58 : 38,
              color: past ? (num ? T.c.hero : V && active ? T.c.hero : T.c.text) : 'rgba(243,241,234,0.45)', display: 'inline-block',
              borderBottom: V ? undefined : `3px solid ${active ? T.c.accent : 'transparent'}`, paddingBottom: 2, transformOrigin: '50% 60%', transform: sc !== 1 ? `scale(${sc})` : undefined}}>{w.w}</span>
          );
        })}
      </div>
    </div>
  );
};

const CutFlash: React.FC<{i: number}> = ({i}) => {
  const f = useCurrentFrame();
  const x = ease(f, 0, 16, -40, 140, T.ease.inOut);
  const o = ease(f, 0, 6, 0, 1) * ease(f, 10, 16, 1, 0);
  return (
    <AbsoluteFill style={{pointerEvents: 'none', overflow: 'hidden', opacity: o * 0.5}}>
      <div style={{position: 'absolute', top: -200, bottom: -200, width: 260, left: `${x}%`, transform: `skewX(${i % 2 ? -18 : 18}deg)`,
        background: `linear-gradient(90deg, transparent, ${i % 2 ? T.c.accent : T.c.text}44, transparent)`}} />
    </AbsoluteFill>
  );
};

// Geçiş çeşitliliği (hep aynı fade "şablon video" hissi veriyordu). Hareket sırasında yön bulanıklığı = ucuz motion blur.
export type Trans = 'fade' | 'push' | 'wipe' | 'zoom' | 'iris' | 'rise' | 'whip' | 'clock' | 'flip' | 'diag' | 'split' | 'glitch' | 'blinds' | 'drop' | 'pushL' | 'wipeL' | 'wipeU' | 'wipeD' | 'splitV' | 'diagR' | 'diamond' | 'cross' | 'cornerTL' | 'cornerBR' | 'rect' | 'flipX' | 'flipR' | 'spin' | 'zoomOut' | 'zoomBlur' | 'shake' | 'rgb' | 'blurIn' | 'blindsH' | 'dots' | 'stripes' | 'curtain' | 'shutter' | 'swing' | 'bounce';
const TRANS_CYCLE: Trans[] = ['fade', 'push', 'rise', 'whip', 'wipe', 'fade', 'zoom', 'push', 'iris', 'whip'];
// 15 Eki: genişletilmiş set (transSeed>0): 13 geçiş, (i*3+seed) ile gezilir -> ardışık aynı geçiş çıkmaz, her gün farklı sıra
const TRANS_ALL: Trans[] = ['fade', 'push', 'rise', 'whip', 'wipe', 'zoom', 'iris', 'clock', 'flip', 'diag', 'split', 'glitch', 'blinds', 'drop', 'pushL', 'wipeL', 'wipeU', 'wipeD', 'splitV', 'diagR', 'diamond', 'cross', 'cornerTL', 'cornerBR', 'rect', 'flipX', 'flipR', 'spin', 'zoomOut', 'zoomBlur', 'shake', 'rgb', 'blurIn', 'blindsH', 'dots', 'stripes', 'curtain', 'shutter', 'swing', 'bounce'];
const TSFX_DEFAULT: Partial<Record<Trans, [string[], number]>> = {
  drop: [['drop_whoosh'], 0.18], bounce: [['drop_whoosh', 'impact_soft'], 0.16], shutter: [['impact_tight'], 0.12], shake: [['impact_soft', 'whoosh_fast'], 0.14],
  rgb: [['glitch'], 0.14], blurIn: [['reverse_swell', 'whoosh_air_1'], 0.12], zoomBlur: [['whoosh_fast', 'whoosh_air_2'], 0.18], zoomOut: [['whoosh_air_1', 'lift_whoosh'], 0.14],
  spin: [['whoosh_fast', 'swipe_2'], 0.16], swing: [['swipe_1', 'whoosh_soft_2'], 0.16], flipX: [['paper_flip'], 0.18], flipR: [['paper_flip', 'swipe_2'], 0.18],
  dots: [['data_sweep_1', 'blips'], 0.12], stripes: [['data_sweep_2', 'swipe_2'], 0.14], blindsH: [['data_sweep_1', 'data_sweep_2'], 0.14], curtain: [['paper_slide', 'whoosh_soft_1'], 0.16],
  cross: [['pop_clean', 'whoosh_soft_2'], 0.14], diamond: [['reverse_swell', 'pop_clean'], 0.14], rect: [['pop_clean', 'whoosh_subtle'], 0.12],
  cornerTL: [['reverse_swell', 'whoosh_air_1'], 0.14], cornerBR: [['reverse_swell', 'whoosh_air_2'], 0.14],
  pushL: [['swipe_1', 'swipe_2'], 0.16], wipeL: [['paper_slide'], 0.16], wipeU: [['lift_whoosh', 'paper_slide'], 0.16], wipeD: [['drop_whoosh', 'paper_slide'], 0.16],
  splitV: [['whoosh_soft_2'], 0.14], diagR: [['whoosh_fast', 'swipe_1'], 0.16],
};
let TSEED = 0;
const TSTEP = [7, 5, 11].find((k) => TRANS_ALL.length % k !== 0) ?? 1; // uzunlukla aralarında asal adım -> tüm geçişler gezilir
export const setTransSeed = (n?: number) => {
  TSEED = n && n > 0 ? Math.floor(n) : 0;
};

// 8 Eki: darbe anlarında (Stamp/Chapter çarpması) kısa, sönümlü kamera sarsıntısı — yalnız öncelikli impact sesleriyle eşli
export const impactFrames = (plan: Plan, scenes: ReturnType<typeof timedScenes>) =>
  sceneSfx(plan, scenes).filter((c) => /^impact_(tight|deep)/.test(c.sfx) && c.prio).map((c) => c.at);
const Shake: React.FC<{hits: number[]; children: React.ReactNode}> = ({hits, children}) => {
  const f = useCurrentFrame();
  let x = 0, y = 0, s = 1;
  for (const h of hits) {
    const d = f - h;
    if (d < 0 || d > 14) continue;
    const a = Math.exp(-d / 4);
    x += Math.sin(d * 2.7) * 9 * a;
    y += Math.cos(d * 3.1) * 6 * a;
    s += 0.018 * a;
  }
  return <AbsoluteFill style={x || y ? {transform: `translate(${x}px, ${y}px) scale(${s})`} : undefined}>{children}</AbsoluteFill>;
};

// 9 Eki: Shorts kancası — 0. karede ekran DOLU olsun (kaydırma kararı ilk ~0,5 sn'de veriliyor). Damga çarpar, ~1,2 sn sonra
// sahneye yer açarak yukarı süzülüp söner.
const ReelHook: React.FC<{text: string; sub?: string}> = ({text, sub}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const inS = spring({frame: f + 2, fps, config: {damping: 11, stiffness: 260, mass: 0.6}}); // f=0'da zaten büyük ölçüde görünür
  const out = ease(f, 24, 34, 0, 1, T.ease.in);
  if (out >= 0.999) return null;
  const lines = text.length > 11 && text.includes(' ') ? [text.slice(0, text.lastIndexOf(' ', Math.ceil(text.length / 2) + 2)), text.slice(text.lastIndexOf(' ', Math.ceil(text.length / 2) + 2) + 1)] : [text];
  const size = Math.min(210, 980 / Math.max(...lines.map((l) => l.length)) * 1.6);
  const flash = ease(f, 0, 4, 0.22, 0);
  return (
    <AbsoluteFill style={{pointerEvents: 'none', justifyContent: 'center', alignItems: 'center', opacity: 1 - out, transform: `translateY(${-140 * out}px)`}}>
      <AbsoluteFill style={{background: `radial-gradient(ellipse 95% 55% at 50% 46%, ${T.c.bg} 55%, ${T.c.bg}c0 80%, transparent)`}} />
      <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18, transform: `scale(${interpolate(inS, [0, 1], [1.45, 1])}) rotate(${interpolate(inS, [0, 1], [-4, -2])}deg)`}}>
        {sub ? <div style={{fontFamily: T.f.mono, fontSize: 34, letterSpacing: '0.16em', color: T.c.bg, background: T.c.text, padding: '8px 22px', borderRadius: 8}}>{sub}</div> : null}
        {lines.map((l, i) => (
          <div key={i} style={{fontFamily: T.f.display, fontWeight: 900, fontSize: size, lineHeight: 0.95, color: i === lines.length - 1 ? T.c.hero : T.c.text,
            textShadow: '0 10px 40px rgba(0,0,0,0.65)', letterSpacing: '-0.02em', whiteSpace: 'nowrap'}}>{l}</div>
        ))}
      </div>
      <AbsoluteFill style={{background: '#fff', opacity: flash, mixBlendMode: 'overlay'}} />
    </AbsoluteFill>
  );
};

// 9 Eki: vurgulu kelimede kameranın yumuşakça yaklaşıp geri çekilmesi (konuşan sunucu kurgusundaki "punch-in" hissi)
const Punch: React.FC<{at: number[]; children: React.ReactNode}> = ({at, children}) => {
  const f = useCurrentFrame();
  let k = 0;
  for (const h of at) {
    const d = f - h + 4; // kelimeden biraz önce başlasın
    if (d < 0 || d > 60) continue;
    k = Math.max(k, d < 8 ? T.ease.out(d / 8) : 1 - T.ease.inOut(Math.min((d - 22) / 38, 1) * (d > 22 ? 1 : 0)));
  }
  return <AbsoluteFill style={k > 0.001 ? {transform: `scale(${1 + 0.04 * k})`} : undefined}>{children}</AbsoluteFill>;
};

// 8 Eki: bölüm geçişinde sıcak ışık sızıntısı (film hissi), sahneyi kapatmadan üstten süzülür
const LightLeak: React.FC<{i: number}> = ({i}) => {
  const f = useCurrentFrame();
  const o = ease(f, 0, 10, 0, 1, T.ease.out) * ease(f, 18, 40, 1, 0, T.ease.in);
  const x = ease(f, 0, 40, i % 2 ? 80 : 10, i % 2 ? 30 : 60, T.ease.inOut);
  return (
    <AbsoluteFill style={{pointerEvents: 'none', mixBlendMode: 'screen', opacity: o * 0.55,
      background: `radial-gradient(ellipse 55% 75% at ${x}% 40%, ${T.c.hero}cc, ${T.c.accent}44 45%, transparent 75%)`}} />
  );
};
export const pickTrans = (i: number, t: string, tr?: Trans): Trans => tr ?? (t === 'Chapter' ? 'zoom' : t === 'Outro' || t === 'Disclaimer' ? 'fade' : TSEED > 0 ? TRANS_ALL[(i * TSTEP + TSEED) % TRANS_ALL.length] : TRANS_CYCLE[i % TRANS_CYCLE.length]);

// Kamera nefesi (30 Eyl): durağan grafik sahnelerine çok yavaş itme/çekme + hafif yatay kayma (sahne başına yön değişir).
const Drift: React.FC<{children: React.ReactNode; i: number; dur: number}> = ({children, i, dur}) => {
  const f = useCurrentFrame();
  const q = interpolate(f, [0, Math.max(dur, 1)], [0, 1], clamp);
  const push = i % 2 === 0;
  const s = push ? 1.012 + 0.028 * q : 1.04 - 0.028 * q; // ≥1,012: yatay kaymada kenar boşluğu görünmesin
  const x = (i % 3 === 0 ? 1 : i % 3 === 1 ? -1 : 0) * 14 * (q - 0.5);
  return <AbsoluteFill style={{transform: `translateX(${x}px) scale(${s})`}}>{children}</AbsoluteFill>;
};

const SceneIn: React.FC<{children: React.ReactNode; first: boolean; kind?: Trans}> = ({children, first, kind = 'fade'}) => {
  const f = useCurrentFrame();
  if (first) return <>{children}</>;
  const D = OVERLAP + 6;
  const p = ease(f, 0, D, 0, 1, T.ease.out);
  const o = ease(f, 0, OVERLAP, 0, 1, T.ease.soft);
  const blur = (1 - p) * 14;
  let style: React.CSSProperties;
  switch (kind) {
    case 'push':
      style = {opacity: o, transform: `translateX(${(1 - p) * 220}px)`, filter: blur > 0.3 ? `blur(${blur * 0.6}px)` : undefined};
      break;
    case 'rise':
      style = {opacity: o, transform: `translateY(${(1 - p) * 140}px)`, filter: blur > 0.3 ? `blur(${blur * 0.5}px)` : undefined};
      break;
    case 'wipe':
      style = {clipPath: `inset(0 ${(1 - p) * 100}% 0 0)`};
      break;
    case 'zoom':
      style = {opacity: o, transform: `scale(${1.18 - 0.18 * p})`, filter: blur > 0.3 ? `blur(${blur}px)` : undefined};
      break;
    case 'iris':
      style = {clipPath: `circle(${p * 75}% at 50% 50%)`};
      break;
    case 'whip': {
      // hızlı yatay savurma: kısa sürede büyük yol + güçlü yön bulanıklığı
      const q = ease(f, 0, OVERLAP, 0, 1, T.ease.out);
      style = {opacity: ease(f, 0, 4, 0, 1), transform: `translateX(${(1 - q) * -520}px) skewX(${(1 - q) * 8}deg)`, filter: q < 0.97 ? `blur(${(1 - q) * 26}px)` : undefined};
      break;
    }
    case 'clock': {
      const m = `conic-gradient(from 0deg at 50% 50%, #000 ${p * 360}deg, transparent ${p * 360}deg)`;
      style = {WebkitMaskImage: m, maskImage: m};
      break;
    }
    case 'flip':
      style = {opacity: o, transformOrigin: '0% 50%', transform: `perspective(1800px) rotateY(${(1 - p) * -72}deg)`};
      break;
    case 'diag': {
      const x = p * 135;
      style = {clipPath: `polygon(0 0, ${x}% 0, ${x - 35}% 100%, 0 100%)`};
      break;
    }
    case 'split':
      style = {clipPath: `inset(0 ${(1 - p) * 50}% 0 ${(1 - p) * 50}%)`};
      break;
    case 'glitch':
      style = {opacity: f < 2 ? 0 : 1, transform: p < 0.92 ? `translateX(${Math.sin(f * 7.3) * (1 - p) * 46}px) skewX(${Math.cos(f * 5.1) * (1 - p) * 6}deg)` : undefined,
        filter: p < 0.92 ? `hue-rotate(${(1 - p) * 110}deg) saturate(${1 + (1 - p) * 1.2})` : undefined};
      break;
    case 'blinds': {
      const m = `repeating-linear-gradient(90deg, #000 0px, #000 ${Math.max(p * 128, 0.01)}px, transparent ${Math.max(p * 128, 0.01)}px, transparent 128px)`;
      style = p >= 0.995 ? {} : {WebkitMaskImage: m, maskImage: m};
      break;
    }
    case 'drop':
      style = {opacity: o, transform: `translateY(${(1 - p) * -700}px)`, filter: blur > 0.3 ? `blur(${blur * 0.4}px)` : undefined};
      break;
    case 'pushL':
      style = {opacity: o, transform: `translateX(${(1 - p) * -220}px)`, filter: blur > 0.3 ? `blur(${blur * 0.6}px)` : undefined};
      break;
    case 'wipeL':
      style = {clipPath: `inset(0 0 0 ${(1 - p) * 100}%)`};
      break;
    case 'wipeU':
      style = {clipPath: `inset(${(1 - p) * 100}% 0 0 0)`};
      break;
    case 'wipeD':
      style = {clipPath: `inset(0 0 ${(1 - p) * 100}% 0)`};
      break;
    case 'splitV':
      style = {clipPath: `inset(${(1 - p) * 50}% 0 ${(1 - p) * 50}% 0)`};
      break;
    case 'diagR': {
      const x = p * 135;
      style = {clipPath: `polygon(${100 - x}% 0, 100% 0, 100% 100%, ${100 - x + 35}% 100%)`};
      break;
    }
    case 'diamond': {
      const r = p * 78;
      style = {clipPath: `polygon(50% ${50 - r}%, ${50 + r}% 50%, 50% ${50 + r}%, ${50 - r}% 50%)`};
      break;
    }
    case 'cross': {
      const w = p * 60;
      style = {clipPath: `polygon(${50 - w}% 0, ${50 + w}% 0, ${50 + w}% ${50 - w}%, 100% ${50 - w}%, 100% ${50 + w}%, ${50 + w}% ${50 + w}%, ${50 + w}% 100%, ${50 - w}% 100%, ${50 - w}% ${50 + w}%, 0 ${50 + w}%, 0 ${50 - w}%, ${50 - w}% ${50 - w}%)`};
      break;
    }
    case 'cornerTL':
      style = {clipPath: `circle(${p * 150}% at 0% 0%)`};
      break;
    case 'cornerBR':
      style = {clipPath: `circle(${p * 150}% at 100% 100%)`};
      break;
    case 'rect':
      style = {clipPath: `inset(${(1 - p) * 49}% ${(1 - p) * 49}% ${(1 - p) * 49}% ${(1 - p) * 49}%)`};
      break;
    case 'flipX':
      style = {opacity: o, transformOrigin: '50% 0%', transform: `perspective(1800px) rotateX(${(1 - p) * 70}deg)`};
      break;
    case 'flipR':
      style = {opacity: o, transformOrigin: '100% 50%', transform: `perspective(1800px) rotateY(${(1 - p) * 72}deg)`};
      break;
    case 'spin':
      style = {opacity: o, transform: `rotate(${(1 - p) * -14}deg) scale(${0.8 + 0.2 * p})`};
      break;
    case 'zoomOut':
      style = {opacity: o, transform: `scale(${0.78 + 0.22 * p})`, filter: blur > 0.3 ? `blur(${blur * 0.5}px)` : undefined};
      break;
    case 'zoomBlur':
      style = {opacity: o, transform: `scale(${1.55 - 0.55 * p})`, filter: p < 0.97 ? `blur(${(1 - p) * 30}px)` : undefined};
      break;
    case 'shake':
      style = {opacity: o, transform: p < 0.95 ? `translate(${Math.sin(f * 4.1) * (1 - p) * 34}px, ${Math.cos(f * 5.3) * (1 - p) * 22}px)` : undefined};
      break;
    case 'rgb':
      style = {opacity: o, filter: p < 0.95 ? `drop-shadow(${(1 - p) * 18}px 0 0 rgba(255,0,80,0.7)) drop-shadow(${(1 - p) * -18}px 0 0 rgba(0,200,255,0.7))` : undefined};
      break;
    case 'blurIn':
      style = {opacity: o, filter: p < 0.97 ? `blur(${(1 - p) * 38}px) brightness(${1 + (1 - p) * 0.6})` : undefined};
      break;
    case 'blindsH': {
      const m = `repeating-linear-gradient(0deg, #000 0px, #000 ${Math.max(p * 90, 0.01)}px, transparent ${Math.max(p * 90, 0.01)}px, transparent 90px)`;
      style = p >= 0.995 ? {} : {WebkitMaskImage: m, maskImage: m};
      break;
    }
    case 'dots': {
      const m = `radial-gradient(circle at 50% 50%, #000 ${p * 62}px, transparent ${p * 62 + 1}px)`;
      style = p >= 0.995 ? {} : {WebkitMaskImage: m, maskImage: m, WebkitMaskSize: '110px 110px', maskSize: '110px 110px'};
      break;
    }
    case 'stripes': {
      const m = `repeating-linear-gradient(45deg, #000 0px, #000 ${Math.max(p * 110, 0.01)}px, transparent ${Math.max(p * 110, 0.01)}px, transparent 110px)`;
      style = p >= 0.995 ? {} : {WebkitMaskImage: m, maskImage: m};
      break;
    }
    case 'curtain': {
      const m = `linear-gradient(90deg, #000 ${p * 50}%, transparent ${p * 50}%, transparent ${100 - p * 50}%, #000 ${100 - p * 50}%)`;
      style = p >= 0.995 ? {} : {WebkitMaskImage: m, maskImage: m};
      break;
    }
    case 'shutter':
      style = {opacity: o, transform: `scaleY(${0.04 + 0.96 * p})`};
      break;
    case 'swing':
      style = {opacity: o, transformOrigin: '0% 100%', transform: `rotate(${(1 - p) * -22}deg)`};
      break;
    case 'bounce': {
      const q = ease(f, 0, D + 6, 0, 1, T.ease.out);
      style = {opacity: o, transform: `translateY(${(1 - q) * 520}px) scale(${1 + Math.sin(Math.min(q, 1) * Math.PI) * 0.03})`};
      break;
    }
    default:
      style = {opacity: o, transform: `scale(${ease(f, 0, D, 0.965, 1, T.ease.out)})`};
  }
  return <AbsoluteFill style={style}>{children}</AbsoluteFill>;
};

// Dikey: üstte marka + başlık şeridi, sonda "tam analiz kanalda" kartı
const ReelChrome: React.FC<{plan: Plan}> = ({plan}) => {
  const f = useCurrentFrame();
  const o = ease(f, 0, 12, 0, 1);
  return (
    <AbsoluteFill style={{pointerEvents: 'none', opacity: o}}>
      <div style={{position: 'absolute', top: 120, left: 0, right: 0, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 14}}>
        {plan.brand ? <TextBrand b={plan.brand} h={62} /> : <BrandMark h={62} />}
        {plan.hud?.date ? <span style={{fontFamily: T.f.mono, fontSize: 22, color: T.c.dim, marginLeft: 10}}>{plan.hud.date}</span> : null}
      </div>
      <div style={{position: 'absolute', top: 0, left: 0, height: 8, width: 1080 * (f / plan.total), background: `linear-gradient(90deg, ${T.c.accent}, ${T.c.hero})`}} />
    </AbsoluteFill>
  );
};

export const AutoVideo: React.FC<{plan: Plan}> = ({plan}) => {
  const V = plan.layout === 'v';
  setLocale(plan.lang);
  applyTheme(plan.theme);
  setTransSeed(plan.transSeed);
  const scenes = timedScenes(plan);
  const csm = plan.captionStyle && plan.captionStyle !== 'box' && plan.captionStyle !== 'minimal';
  const pages = buildPages(plan, V ? (csm ? 3 : 4) : csm ? 4 : 7, V ? (csm ? 20 : 26) : csm ? 28 : 44);
  const speaking = (fr: number) => plan.segments.some((s) => fr >= s.s - 6 && fr <= s.e + 6);
  const hudFrom = scenes[1]?.start ?? 0;
  const pm = !!plan.presenter && !plan.footage && !V && !plan.presenterPip; // 9 Eki: 2D sunucu modu (yatay)
  const hostAt = (fr: number) => pm && fr < plan.outroStart && HOST.includes(scenes.reduce((a, s) => (fr >= s.start ? s : a), scenes[0]).t);
  return (
    <DataProvider series={plan.series ?? {}}>
      <AbsoluteFill style={{background: T.c.bg}}>
        {plan.footage ? <FootageLayer plan={plan} scenes={scenes} /> : null}
        <Shake hits={plan.footage ? [] : impactFrames(plan, scenes)}><Punch at={plan.footage ? [] : plan.emph ?? []}>
        {scenes.map((s0, i) => {
          let s = s0;
          const C = TEMPLATES[s.t] ?? A.KineticTitle;
          // Dikey (Shorts): ilk sahne ilk yarım saniyede tamamen dolu olmalı — içindeki tetikleri başa çek.
          if (V && i === 0 && s.p) s = {...s, p: hookify(s.p)};
          const dur = s.len + (i < scenes.length - 1 ? OVERLAP : 0);
          return (
            <Sequence key={i} from={s.start} durationInFrames={dur} name={`${i}-${s.t}`}>
              <SceneProvider tl={plan} start={s.start} dur={dur} layout={V ? 'v' : 'h'}>
                <SceneIn first={i === 0} kind={pickTrans(i, s.t, s.tr)}>
                  <Placed layout={pm && HOST.includes(s.t) ? 'split' : s.layout} footage={!!plan.footage || (pm && HOST.includes(s.t))}><SceneExit>
                    {/* 3D sahneler kendi kamerasıyla, bölüm kartı ve açılış kendi animasyonuyla oynar -> kamera nefesi yok */}
                    {['Metal3D', 'Globe3D', 'Bars3D', 'Stack3D', 'Object3D', 'Scale3D', 'HostStage', 'Chapter', 'Intro', 'Outro'].includes(s.t) ? <C p={s.p ?? {}} /> : <Drift i={i} dur={dur}><C p={s.p ?? {}} /></Drift>}
                  </SceneExit></Placed>
                </SceneIn>
              </SceneProvider>
            </Sequence>
          );
        })}
        {scenes.slice(1).map((s, i) => (
          <Sequence key={`fx${i}`} from={Math.max(s.start - 4, 0)} durationInFrames={18}><CutFlash i={i} /></Sequence>
        ))}
        </Punch></Shake>
        {plan.presenter && !plan.footage ? <PresenterLayer plan={plan} scenes={scenes} V={V} /> : null}
        {scenes.map((s, i) => (s.t === 'Chapter' && i > 0 ? (
          <Sequence key={`lk${i}`} from={Math.max(s.start - 6, 0)} durationInFrames={42}><LightLeak i={i} /></Sequence>
        ) : null))}
        <Grade />
        {V ? <ReelChrome plan={plan} /> : <HUD plan={plan} showFrom={hudFrom} />}
        {V && plan.hookBig ? <ReelHook text={plan.hookBig} sub={plan.hookSub || undefined} /> : null}
        {plan.captions !== false ? <Captions plan={plan} pages={pages} V={V} hostAt={hostAt} /> : null}
        <Grain />
        <Vignette />
        {plan.audio?.voice && !plan.footage ? <Audio src={staticFile(plan.audio.voice)} /> : null}
        {plan.audio?.music ? (
          // musicFrom: açılış varyantında müzik, ana videoya eklendiği noktada kesintisiz devam etsin diye kaydırılır
          <Sequence from={Math.max(-(plan.audio.musicFrom ?? 0), 0)} layout="none">
            <Audio src={staticFile(plan.audio.music)} trimBefore={Math.max(plan.audio.musicFrom ?? 0, 0) || undefined}
              volume={(fr) => (speaking(fr) ? 0.07 : 0.16) * interpolate(fr, [0, 30], [0, 1], clamp) * (plan.audio?.noFadeOut ? 1 : interpolate(fr, [plan.total - 90, plan.total - 5], [1, 0], clamp))} />
          </Sequence>
        ) : null}
        {/* 30 Eyl ses tasarımı: sahneye duyarlı, varyantlı, yoğunluk sınırlı (bkz. sceneSfx) */}
        {sceneSfx(plan, scenes).map((c, i) => (
          <Sequence key={`sx${i}`} from={Math.max(c.at, 0)} durationInFrames={c.len}><Audio src={staticFile(`sfx/${c.sfx}.wav`)} volume={c.vol} /></Sequence>
        ))}
        {(plan.hits ?? []).map((h, i) => (
          <Sequence key={`h${i}`} from={Math.max(cueAbs(plan, h.cue, 2), 0)} durationInFrames={60}><Audio src={staticFile(`sfx/${h.sfx}.wav`)} volume={h.vol ?? 0.4} /></Sequence>
        ))}
        <Sequence from={V && plan.hookBig ? 0 : 2} durationInFrames={80}><Audio src={staticFile('sfx/impact_deep_1.wav')} volume={V ? 0.35 : 0.45} /></Sequence>
        {V && plan.hookBig ? <Sequence from={0} durationInFrames={60}><Audio src={staticFile('sfx/sub_boom.wav')} volume={0.3} /></Sequence> : null}
      </AbsoluteFill>
    </DataProvider>
  );
};
