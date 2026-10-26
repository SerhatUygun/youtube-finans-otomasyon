// Fed Showreel — tek tema kaynağı. Bileşenlerde renk/easing/spring INLINE YAZILMAZ.
import {Easing} from 'remotion';
import {loadFont as loadInterTight} from '@remotion/google-fonts/InterTight';
import {loadFont as loadMono} from '@remotion/google-fonts/JetBrainsMono';
import {loadFont as loadSerif} from '@remotion/google-fonts/InstrumentSerif';

const display = loadInterTight('normal', {weights: ['400', '500', '600', '700', '800', '900'], subsets: ['latin', 'latin-ext']});
const mono = loadMono('normal', {weights: ['400', '500', '700', '800'], subsets: ['latin', 'latin-ext']});
const serif = loadSerif('italic', {weights: ['400'], subsets: ['latin', 'latin-ext']});

export const T = {
  c: {
    bg: '#06080E',
    bg2: '#0B1020',
    panel: 'rgba(255,255,255,0.035)',
    line: 'rgba(255,255,255,0.09)',
    text: '#F3F1EA',
    dim: '#8C93A6',
    faint: '#3A4154',
    // Marka hero rengi: Finans Kanalı altını — kare başına EN FAZLA bir öğede.
    hero: '#F2B84B',
    heroGlow: 'rgba(242,184,75,0.45)',
    accent: '#5CC8FF',
    up: '#3DDC97',
    down: '#FF5A5F',
    gold: '#F2B84B',
    silver: '#C9D3E3',
    btc: '#F7931A',
    oil: '#8B7CFF',
    hawk: '#FF5A5F',
  },
  f: {
    display: display.fontFamily,
    mono: mono.fontFamily,
    serif: serif.fontFamily,
  },
  ease: {
    out: Easing.bezier(0.16, 1, 0.3, 1),
    inOut: Easing.bezier(0.83, 0, 0.17, 1),
    in: Easing.bezier(0.7, 0, 0.84, 0),
    soft: Easing.bezier(0.45, 0, 0.2, 1),
  },
  spring: {
    snappy: {damping: 14, stiffness: 160, mass: 0.6},
    smooth: {damping: 20, stiffness: 90, mass: 1},
    bouncy: {damping: 11, stiffness: 170, mass: 0.7},
    heavy: {damping: 26, stiffness: 120, mass: 1.4},
    count: {damping: 30, stiffness: 55, mass: 1},
  },
  // Sahne güvenli alanı: üst HUD 0-120, alt altyazı+ticker 860-1080.
  safe: {top: 130, bottom: 850, side: 120},
} as const;

// 1 Eki: İngilizce kanal kurguları (plan.lang='en') için sayı biçimi değiştirilebilir; AutoVideo render başında ayarlar.
let LOCALE = 'tr-TR';
export const setLocale = (lang?: string) => {
  LOCALE = lang === 'en' ? 'en-US' : 'tr-TR';
};
export const fmtTR = (v: number, dec = 0) =>
  v.toLocaleString(LOCALE, {minimumFractionDigits: dec, maximumFractionDigits: dec});

// 15 Eki: TEMA PAKETLERİ — her gün farklı palet (kullanıcı: hep aynı görünüm). Yalnız yüzey/vurgu renkleri değişir;
// yükselen/düşen (yeşil/kırmızı) ve varlık renkleri (altın/gümüş/btc/petrol) anlamsal olduğu için KORUNUR.
// Koyu zemin korunur (okunabilirlik). `plan.theme` yoksa ya da 'navy' ise hiçbir şey değişmez.
export const THEMES: Record<string, Partial<Record<'bg' | 'bg2' | 'text' | 'dim' | 'faint' | 'hero' | 'heroGlow' | 'accent', string>>> = {
  navy: {},
  carbon: {bg: '#080808', bg2: '#121212', text: '#F5F5F0', dim: '#8E8E8E', faint: '#3A3A3A', hero: '#FFD21F', heroGlow: 'rgba(255,210,31,0.45)', accent: '#38E1FF'},
  emerald: {bg: '#04301A', bg2: '#075A30', text: '#F1FFF6', dim: '#8FC9A6', faint: '#1E6B42', hero: '#F4D35E', heroGlow: 'rgba(244,211,94,0.5)', accent: '#42FFA8'},
  crimson: {bg: '#14060A', bg2: '#210B12', text: '#FBF1EE', dim: '#A78A8F', faint: '#472A31', hero: '#FF9A3D', heroGlow: 'rgba(255,154,61,0.45)', accent: '#FF5C7A'},
  violet: {bg: '#0B0716', bg2: '#150D29', text: '#F4F0FB', dim: '#9488B0', faint: '#3A2F57', hero: '#F7C948', heroGlow: 'rgba(247,201,72,0.45)', accent: '#B592FF'},
  steel: {bg: '#090D13', bg2: '#111823', text: '#F1F3F6', dim: '#8A94A5', faint: '#333D4D', hero: '#FF7A3C', heroGlow: 'rgba(255,122,60,0.45)', accent: '#6FB4FF'},
  terminal: {bg: '#021F0C', bg2: '#04381A', text: '#D6FFE0', dim: '#74BC88', faint: '#17572B', hero: '#9BFF7A', heroGlow: 'rgba(155,255,122,0.5)', accent: '#4DE1FF'},
  sunset: {bg: '#100810', bg2: '#1C0F1F', text: '#FFF3EC', dim: '#B39AA6', faint: '#47303F', hero: '#FFB347', heroGlow: 'rgba(255,179,71,0.45)', accent: '#FF6FB1'},
};
export const THEME_NAMES = Object.keys(THEMES);
const BASE_C = {...T.c};
// Her render başında çağrılır (setLocale gibi): önce taban palete döner, sonra seçilen temayı uygular.
export const applyTheme = (name?: string) => {
  Object.assign(T.c as Record<string, string>, BASE_C, THEMES[name ?? 'navy'] ?? {});
};
