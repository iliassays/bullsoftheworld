import { api, type SymbolOut } from "./api";

// The default list is only a landing sample. Real typeahead uses the server-side query path so
// large markets such as US equities do not depend on a browser-side full-universe preload.
let cache: SymbolOut[] | null = null;
let inflight: Promise<SymbolOut[]> | null = null;
const searchCache = new Map<string, SymbolOut[]>();

export function loadSymbols(): Promise<SymbolOut[]> {
  if (cache) return Promise.resolve(cache);
  if (!inflight) {
    inflight = api
      .symbols(500)
      .then((s) => {
        cache = s;
        return s;
      })
      .catch(() => []);
  }
  return inflight;
}

export function cachedSymbols(): SymbolOut[] {
  return cache ?? [];
}

export function searchSymbols(query: string, limit = 12): Promise<SymbolOut[]> {
  const q = query.trim();
  const key = `${limit}:${q.toUpperCase()}`;
  if (searchCache.has(key)) return Promise.resolve(searchCache.get(key)!);
  const fallback = () => {
    const upper = q.toUpperCase();
    return cachedSymbols()
      .filter(
        (s) =>
          !q ||
          s.code.includes(upper) ||
          s.name_en.toUpperCase().includes(upper) ||
          (s.name_bn ?? "").includes(q),
      )
      .slice(0, limit);
  };
  return api
    .symbols(limit, q || undefined)
    .then((symbols) => {
      searchCache.set(key, symbols);
      return symbols;
    })
    .catch(fallback);
}
