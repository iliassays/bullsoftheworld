export interface SearchTargetSymbol {
  code: string;
}

export interface SearchTargetDesk {
  handle: string;
  name: string;
}

export type SearchTarget<S extends SearchTargetSymbol, D extends SearchTargetDesk> =
  | { kind: "symbol"; value: S }
  | { kind: "desk"; value: D };

const normalized = (value: string) =>
  value.trim().replace(/^[$@]/, "").toLocaleLowerCase("en-US");

export function chooseSearchTarget<S extends SearchTargetSymbol, D extends SearchTargetDesk>(
  query: string,
  symbols: S[],
  desks: D[],
): SearchTarget<S, D> | null {
  const needle = normalized(query);
  const exactSymbol = symbols.find((symbol) => normalized(symbol.code) === needle);
  if (exactSymbol) return { kind: "symbol", value: exactSymbol };

  const exactDesk = desks.find(
    (desk) => normalized(desk.handle) === needle || normalized(desk.name) === needle,
  );
  if (exactDesk) return { kind: "desk", value: exactDesk };
  if (symbols[0]) return { kind: "symbol", value: symbols[0] };
  if (desks[0]) return { kind: "desk", value: desks[0] };
  return null;
}
