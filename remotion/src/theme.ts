// Ortak palet + sayi bicimleme -- pipeline/market_data.py render_chart() ile gorsel
// sureklilik icin (tum Remotion sablonlari ayni koyu/broadcast temasini paylasir).
export const BG = '#0d1117';
export const INK = '#e6edf3';
export const MUTED = '#8b949e';
export const GRID = '#21262d';
export const UP = '#3fb950';
export const DOWN = '#f85149';
export const NEUTRAL = '#58a6ff';

export function fmtNum(v: number, decimals = 0): string {
  if (Math.abs(v) >= 1000) {
    return v.toLocaleString('tr-TR', {maximumFractionDigits: 0});
  }
  if (decimals > 0) {
    return v.toLocaleString('tr-TR', {minimumFractionDigits: decimals, maximumFractionDigits: decimals});
  }
  if (Math.abs(v) >= 1) {
    return v.toLocaleString('tr-TR', {maximumFractionDigits: 2});
  }
  return v.toFixed(4).replace('.', ',');
}

// LLM'in doldurduğu 'unit' alanı hem sembol ("$", "%") hem kelime ("bin", "milyon") olabilir.
// Sembol bitişik ÖNE ("$4.900"), kelime bosluklu SONA ("162 bin") eklenir.
export function formatWithUnit(value: number, unit: string | undefined, decimals = 0): string {
  const trimmed = (unit || '').trim();
  const num = fmtNum(value, decimals);
  if (!trimmed) return num;
  const isWordUnit = /[a-zA-ZçğıöşüÇĞİÖŞÜ]/.test(trimmed);
  return isWordUnit ? `${num} ${trimmed}` : `${trimmed}${num}`;
}

export function accentFor(trend: 'up' | 'down' | 'neutral' | undefined): string {
  if (trend === 'up') return UP;
  if (trend === 'down') return DOWN;
  return NEUTRAL;
}
