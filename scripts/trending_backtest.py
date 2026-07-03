"""Phase-0 backtest that VALIDATED the trending engine (ingestion/trending.py). Design doc:
docs/specs/trending-engine.md.

Question: does ranking stocks by an anomaly composite (each stock vs its OWN normal) surface names
that are genuinely 'worth watching' over the next week — better than the current top-gainers strip?

Label (chosen): a stock-day is 'notable' if over the NEXT 5 trading days it shows abnormal forward
turnover (it stays in play) AND/OR an abnormal absolute price move vs its own volatility.

Strict no-lookahead: every feature/baseline at day t uses only data <= t; labels use only data > t.

FINDINGS (2y daily_bars, walk-forward, OOS = last ~40%):
  - Only self-normalized volume + turnover surge carry edge (rank-IC ~0.40 each).
  - Composite precision@10 ~54% vs 33.5% for the top-gainers strip vs 16.3% base rate.
  - Range / breakout / abnormal-move add little; persistence ~zero. Lean (vol+turnover) wins.
  => engine = vol_z + turnover_z, liquidity-gated. Move/breakout are display chips, not rank drivers.

RUN (on the server, where daily_bars lives):
  docker compose -f infra/docker-compose.yml exec -T postgres psql -U bulls -d bulls -p 5432 \\
    -c "COPY (select code,date,open,high,low,close,volume from daily_bars where market='DSE' \\
        order by code,date) TO STDOUT WITH CSV HEADER" > /tmp/dse_bars.csv
  uv run --with pandas --with numpy --with scipy python scripts/trending_backtest.py
"""

import numpy as np
import pandas as pd

W_VOL = 60  # baseline window for volume/turnover/range z-scores
W_RET = 20  # window for return volatility
K = 5  # forward horizon (days) for the label
MIN_HIST = 120  # need this much history before a stock is scored
NS = [5, 10, 20]  # top-N cutoffs to report precision at

df = pd.read_csv("/tmp/dse_bars.csv", parse_dates=["date"])
df = df.sort_values(["code", "date"]).reset_index(drop=True)
g = df.groupby("code", group_keys=False)

# --- base series ---
df["ret"] = g["close"].pct_change()
df["turnover"] = df["close"] * df["volume"]  # value-traded proxy
df["log_vol"] = np.log1p(df["volume"])
df["log_to"] = np.log1p(df["turnover"])
df["range"] = (df["high"] - df["low"]) / df["close"].replace(0, np.nan)


def z_trailing(col, w):
    """z-score of today vs the trailing window ending YESTERDAY (baseline excludes today)."""
    grp = df.groupby("code")[col]
    mean = grp.transform(lambda s: s.shift(1).rolling(w, min_periods=w // 2).mean())
    std = grp.transform(lambda s: s.shift(1).rolling(w, min_periods=w // 2).std())
    return (df[col] - mean) / std.replace(0, np.nan)


# --- features (all known at close of day t) ---
df["vol_z"] = z_trailing("log_vol", W_VOL)
df["to_z"] = z_trailing("log_to", W_VOL)
df["range_z"] = z_trailing("range", W_VOL)
ret_vol = df.groupby("code")["ret"].transform(
    lambda s: s.shift(1).rolling(W_RET, min_periods=10).std()
)
df["ret_vol"] = ret_vol
df["abs_ret_z"] = (df["ret"].abs()) / ret_vol
roll_max = df.groupby("code")["close"].transform(
    lambda s: s.shift(1).rolling(252, min_periods=60).max()
)
roll_min = df.groupby("code")["close"].transform(
    lambda s: s.shift(1).rolling(252, min_periods=60).min()
)
df["breakout"] = ((df["close"] >= roll_max) | (df["close"] <= roll_min)).astype(float)
sign = np.sign(df["ret"]).fillna(0)
df["persist"] = (
    df.groupby("code")["ret"].transform(lambda s: np.sign(s).rolling(5, min_periods=3).sum().abs())
    / 5.0
)
# liquidity: trailing-20 median turnover (known at t)
df["liq"] = df.groupby("code")["turnover"].transform(
    lambda s: s.shift(1).rolling(20, min_periods=10).median()
)

# --- forward label (uses only data > t) ---
fwd_to = pd.concat(
    [df.groupby("code")["turnover"].shift(-i) for i in range(1, K + 1)], axis=1
).mean(axis=1)
mean_logto = df.groupby("code")["log_to"].transform(
    lambda s: s.shift(1).rolling(W_VOL, min_periods=W_VOL // 2).mean()
)
std_logto = df.groupby("code")["log_to"].transform(
    lambda s: s.shift(1).rolling(W_VOL, min_periods=W_VOL // 2).std()
)
df["fwd_to_z"] = (np.log1p(fwd_to) - mean_logto) / std_logto.replace(0, np.nan)
fwd_cum = [df.groupby("code")["close"].shift(-i) / df["close"] - 1 for i in range(1, K + 1)]
df["fwd_abs_move"] = pd.concat([c.abs() for c in fwd_cum], axis=1).max(axis=1)
# scale daily vol to the K-day horizon (√K) so 'abnormal' means beyond normal random drift
df["fwd_abs_z"] = df["fwd_abs_move"] / (df["ret_vol"] * np.sqrt(K))
df["notable"] = ((df["fwd_to_z"] >= 1.8) | (df["fwd_abs_z"] >= 1.8)).astype(float)
# a continuous notability score for rank-IC
df["notable_score"] = df[["fwd_to_z", "fwd_abs_z"]].clip(lower=0).fillna(0).sum(axis=1)

# --- scoring universe: enough history, valid features, liquidity gate (top 60% by trailing turnover, per day) ---
df["bar_n"] = df.groupby("code").cumcount()
feat_cols = ["vol_z", "to_z", "range_z", "abs_ret_z", "breakout", "persist"]
elig = df[
    (df["bar_n"] >= MIN_HIST)
    & df[feat_cols].notna().all(axis=1)
    & df["notable"].notna()
    & df["liq"].notna()
].copy()
# per-day liquidity gate
elig["liq_pct"] = elig.groupby("date")["liq"].rank(pct=True)
elig = elig[elig["liq_pct"] >= 0.40].copy()
for c in feat_cols:  # clip extreme z's
    elig[c] = elig[c].clip(-6, 6)

dates = np.sort(elig["date"].unique())
split = dates[int(len(dates) * 0.6)]
print(
    f"scored rows={len(elig):,}  days={len(dates)}  base notable rate={elig['notable'].mean():.1%}"
)
print(f"in-sample <= {pd.Timestamp(split).date()}  | OOS after\n")

WEIGHTS = {
    "equal": dict(vol_z=1, to_z=1, range_z=1, abs_ret_z=1, breakout=1, persist=1),
    "spec": dict(vol_z=0.35, to_z=0.25, abs_ret_z=0.20, persist=0.10, range_z=0.05, breakout=0.05),
    "volume_heavy": dict(
        vol_z=0.45, to_z=0.35, abs_ret_z=0.10, range_z=0.05, breakout=0.05, persist=0.0
    ),
    "activity_only": dict(vol_z=0.5, to_z=0.5, range_z=0, abs_ret_z=0, breakout=0, persist=0),
}


def composite(frame, w):
    s = sum(frame[c] * wt for c, wt in w.items())
    return s


def eval_precision(frame, score_col, n):
    """avg precision@n across days in frame."""

    def per_day(d):
        top = d.nlargest(n, score_col)
        return top["notable"].mean()

    return frame.groupby("date").apply(per_day).mean()


def rank_ic(frame, score_col):
    return (
        frame.groupby("date")
        .apply(lambda d: d[score_col].corr(d["notable_score"], method="spearman"))
        .mean()
    )


oos = elig[elig["date"] > split]
ins = elig[elig["date"] <= split]
base_rate = oos["notable"].mean()

# baselines to beat
oos = oos.copy()
oos["gainers"] = oos["ret"]  # current strip: today's % change (top gainers)
oos["absmove_today"] = oos["ret"].abs()

print("=== univariate precision@10 (OOS) — which single signal carries edge? ===")
for c in feat_cols:
    print(f"  {c:11}: {eval_precision(oos, c, 10):.1%}   IC={rank_ic(oos, c):+.3f}")
print(f"  {'gainers':11}: {eval_precision(oos, 'gainers', 10):.1%}   (current strip baseline)")
print(f"  {'base rate':11}: {base_rate:.1%}\n")

print("=== composite weight sets (precision@N OOS, lift vs base, rank-IC) ===")
for name, w in WEIGHTS.items():
    elig["_c"] = composite(elig, w)
    o = elig[elig["date"] > split]
    line = f"  {name:13}"
    for n in NS:
        p = eval_precision(o, "_c", n)
        line += f"  @{n}={p:.1%}(x{p / base_rate:.2f})"
    line += f"  IC={rank_ic(o, '_c'):+.3f}"
    print(line)

print(f"\n  baseline strip @10 lift = {eval_precision(oos, 'gainers', 10) / base_rate:.2f}x base")
print(
    f"  abs-move-today @10 lift = {eval_precision(oos, 'absmove_today', 10) / base_rate:.2f}x base"
)
