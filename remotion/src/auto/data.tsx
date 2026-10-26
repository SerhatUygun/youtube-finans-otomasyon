// Plan verisi: seriler (piyasa verisi) + yardımcılar. Şablonlar veriyi bu bağlamdan okur.
import React, {createContext, useContext} from 'react';
import {T} from '../core/theme';

export type Series = {d: string[]; c: number[]; o?: number[]; h?: number[]; l?: number[]};
export type P = Record<string, any>;

const DataCtx = createContext<{series: Record<string, Series>}>({series: {}});
export const DataProvider: React.FC<{series: Record<string, Series>; children: React.ReactNode}> = ({series, children}) => (
  <DataCtx.Provider value={{series}}>{children}</DataCtx.Provider>
);

export const useSeries = (symbol?: string, opts: {since?: string; last?: number} = {}): Series | null => {
  const {series} = useContext(DataCtx);
  if (!symbol || !series[symbol]) return null;
  const src = series[symbol];
  let a = 0;
  let b = src.d.length;
  if (opts.since) a = Math.max(src.d.findIndex((x) => x >= opts.since!), 0);
  if (opts.last && opts.last < b - a) a = b - opts.last;
  const cut = (x?: number[]) => (x && x.length === src.d.length ? x.slice(a, b) : undefined);
  const out: Series = {d: src.d.slice(a, b), c: src.c.slice(a, b), o: cut(src.o), h: cut(src.h), l: cut(src.l)};
  return out.c.length >= 2 ? out : null;
};

// Renk anahtar kelimeleri: plan JSON'u hex yerine anlamsal ad kullanır (tema dışı renk yok).
const NAMED: Record<string, string> = {
  hero: T.c.hero, gold: T.c.gold, silver: T.c.silver, btc: T.c.btc, oil: T.c.oil, accent: T.c.accent,
  up: T.c.up, down: T.c.down, hawk: T.c.hawk, text: T.c.text, dim: T.c.dim,
};
export const col = (name?: string, fallback: string = T.c.accent) => (name && NAMED[name]) || fallback;

export const shortDate = (s: string) => {
  const [, m, d] = s.split('-');
  const ay = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'][Number(m) - 1];
  return `${Number(d)} ${ay}`;
};
