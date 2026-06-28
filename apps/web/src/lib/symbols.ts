import { api, type SymbolOut } from "./api";

// The DSE symbol universe is small (~hundreds), so we fetch it once and module-cache it for
// instant client-side typeahead (header search + composer ticker autocomplete share this).
let cache: SymbolOut[] | null = null;
let inflight: Promise<SymbolOut[]> | null = null;

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
