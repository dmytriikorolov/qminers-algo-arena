"""Charts and written findings for analyze_round3.py. Plotly works offline.

PNG export is optional: install matplotlib separately and add it to PYTHONPATH.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from analyze_round3 import block_interval

COLORS = ["#176b76", "#bd6a24", "#6954bc", "#c34652", "#47956b"]
LABELS = {"round1": "Round 1", "round2_public": "Round 2", "round3_public": "Round 3"}
SIGNALS = {"imbalance": "L1 imbalance > 0.6", "imbalance5": "5-tick imbalance > 0.4", "flow1": "1 s flow > 0.6",
           "momentum30": "30 s momentum > 5 ticks", "momentum120": "120 s momentum > 10 ticks"}
STRATEGIES = {"full_two_sided": "Two-sided baseline", "capacity_inventory_cycler": "Inventory cycler",
              "adaptive_ml_regime": "Adaptive reference"}


def style(fig, height=440):
    fig.update_layout(template="plotly_white", height=height, paper_bgcolor="white", plot_bgcolor="white",
                      font=dict(family="Arial, sans-serif", size=13, color="#253440"),
                      colorway=COLORS, margin=dict(l=64, r=30, t=54, b=50), hovermode="x unified",
                      legend=dict(orientation="h", y=1.04, x=0),
                      modebar=dict(bgcolor="white", color="#71818d", activecolor=COLORS[0]))
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="#e9edf0", zerolinecolor="#cdd5da")
    return fig


def chart(fig, identifier, first=False):
    return fig.to_html(full_html=False, include_plotlyjs=True if first else False, div_id=identifier,
                       config={"responsive": True, "displaylogo": False, "scrollZoom": False,
                               "toImageButtonOptions": {"format": "svg", "filename": identifier}})


def table(frame, formats=None):
    labels = {"strategy": "Strategy", "pnl": "Net PnL", "first_half_pnl": "First half PnL", "second_half_pnl": "Second half PnL",
              "breach_penalty": "Penalty", "max_pnl_drawdown": "Max PnL drawdown", "traded_volume": "Executed lots",
              "condition": "Observed condition", "seconds": "Seconds", "coverage": "Time coverage", "jump_probability": "P(jump in next 10 s)",
              "ci_low": "95% low", "ci_high": "95% high", "lift": "Risk / baseline", "feature": "Signal", "n": "Observations",
              "signed_mid_move": "Signed move (ticks)", "after_spread": "After spread (ticks)", "minutes": "Minutes",
              "start_mid": "First mid", "end_mid": "Last mid", "low": "Low", "high": "High", "rms_1s": "1 s RMS",
              "mean_spread": "Mean spread", "mean_l1_min": "Mean thinner L1", "executed_lots": "Executed lots"}
    return frame.rename(columns=labels).to_html(index=False, border=0, classes="data-table", escape=True,
                                              formatters={labels.get(k, k): v for k, v in (formats or {}).items()}, na_rep="—")


def risk_diagnostics(seconds, output):
    future = pd.concat([seconds.return1.shift(-h) for h in range(1, 11)], axis=1)
    next_jump = future.abs().max(axis=1, skipna=False) >= 10
    valid = (seconds.time >= 3000) & future.notna().all(axis=1)
    train = seconds.time.between(120, 2999)
    depth_threshold = float(seconds.loc[train, "min_depth"].quantile(0.1))
    rate_threshold = float(seconds.loc[train, "events"].quantile(0.9))
    conditions = {
        "All held-out seconds": pd.Series(True, index=seconds.index),
        "Last-second mean spread >= 2": seconds.spread_mean >= 2,
        "Current spread >= 4": seconds.spread >= 4,
        f"Current thinner L1 <= {depth_threshold:.0f} lots": seconds.min_depth <= depth_threshold,
        "Trailing 30 s RMS > 2.2 ticks": seconds.rv30 > 2.2,
        f"Last-second events >= {rate_threshold:.0f}": seconds.events >= rate_threshold,
    }
    baseline = float(next_jump[valid].mean())
    rows = []
    for label, condition in conditions.items():
        chosen = valid & condition
        rate = float(next_jump[chosen].mean())
        lo, hi = block_interval(np.where(chosen[valid], next_jump[valid].astype(float), np.nan), block=60)
        rows.append({"condition": label, "seconds": int(chosen.sum()), "coverage": float(chosen.sum() / valid.sum()),
                     "jump_probability": rate, "ci_low": lo, "ci_high": hi, "lift": rate / baseline})
    result = pd.DataFrame(rows)
    result.to_csv(output / "risk_diagnostics.csv", index=False)
    return result


def shock_study(seconds, output):
    selected, last = [], -1000
    for i, row in seconds.iterrows():
        if abs(row.return1) >= 10 and row.time - last >= 60 and i + 60 < len(seconds):
            selected.append(i)
            last = row.time
    rows = []
    for period, indices in [("first_half", [i for i in selected if seconds.time.iloc[i] + 60 < 3000]),
                            ("second_half", [i for i in selected if seconds.time.iloc[i] >= 3000])]:
        if not indices:
            continue
        signs = np.sign(seconds.return1.iloc[indices].to_numpy())
        for horizon in [0, 1, 2, 5, 10, 20, 30, 60]:
            delta = signs * (seconds.mid.iloc[np.array(indices) + horizon].to_numpy() - seconds.mid.iloc[indices].to_numpy())
            delta = delta[np.isfinite(delta)]
            rows.append({"period": period, "horizon_s": horizon, "n": len(delta), "signed_move": float(np.mean(delta)),
                         "median_signed_move": float(np.median(delta))})
    result = pd.DataFrame(rows)
    result.to_csv(output / "shock_event_study.csv", index=False)
    return result


def benchmark_data(output):
    rows, curves = [], {}
    for directory in sorted((output / "benchmarks").glob("*")):
        if not (directory / "result.json").exists():
            continue
        result = json.loads((directory / "result.json").read_text())
        curve = pd.read_csv(directory / "pnl.csv")
        delta = curve.pnl.diff().fillna(0)
        lo, hi = block_interval(delta.to_numpy(), block=60)
        rows.append({"strategy": STRATEGIES.get(directory.name, directory.name), **result,
                     "max_pnl_drawdown": float((curve.pnl.cummax() - curve.pnl).max()),
                     "first_half_pnl": float(np.interp(3000, curve.elapsed_s, curve.pnl)),
                     "second_half_pnl": result["pnl"] - float(np.interp(3000, curve.elapsed_s, curve.pnl)),
                     "block_pnl_ci_low": lo * 6000, "block_pnl_ci_high": hi * 6000})
        curves[directory.name] = curve
    result = pd.DataFrame(rows)
    if len(result):
        result.to_csv(output / "strategy_comparison.csv", index=False)
    return result, curves


def build_report(output, frames, summaries):
    s = frames["round3_public"][1]
    summary = summaries[-1]
    signal = pd.read_csv(output / "signal_validation.csv")
    markout = pd.read_csv(output / "maker_markouts.csv")
    risk = risk_diagnostics(s, output)
    shock = shock_study(s, output)
    benchmarks, curves = benchmark_data(output)
    segments = s.groupby(((s.time - 1) // 300).astype(int)).agg(
        start_mid=("mid", "first"), end_mid=("mid", "last"), low=("mid", "min"), high=("mid", "max"),
        rms_1s=("return1", lambda x: np.sqrt(x.pow(2).mean())),
        mean_spread=("spread_mean", "mean"), mean_l1_min=("min_depth", "mean"), executed_lots=("trade_qty", "sum"))
    segments.insert(0, "minutes", [f"{i*5}–{(i+1)*5}" for i in segments.index])
    segments.to_csv(output / "five_minute_segments.csv", index=False)

    # 1. Linked market panels, with the holdout boundary on every panel.
    overview = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.065,
                             row_heights=[0.43, 0.2, 0.17, 0.2],
                             subplot_titles=["Midprice", "Trailing 30 s volatility", "Time-weighted spread / second", "Quantity at the touch"])
    for row, column, label, color in [(1, "mid", "Midprice", COLORS[0]), (2, "rv30", "RMS 1 s return", COLORS[1]),
                                       (3, "spread_mean", "Mean spread", COLORS[2]), (4, "bid_qty", "Bid L1", COLORS[0]),
                                       (4, "ask_qty", "Ask L1", COLORS[3])]:
        overview.add_trace(go.Scatter(x=s.time / 60, y=s[column], name=label, line=dict(color=color, width=1.3)), row=row, col=1)
    overview.add_hline(y=2.2, line_dash="dot", line_color=COLORS[3], row=2, col=1)
    overview.update_yaxes(type="log", row=4, col=1, title_text="Lots (log)")
    for row in [1, 2, 3]:
        overview.update_yaxes(title_text="Ticks", row=row, col=1)
    overview.add_vline(x=50, line_color="#7c8a94", line_dash="dash")
    overview.update_xaxes(title_text="Elapsed minutes", row=4, col=1)
    style(overview, 900)

    comparison = make_subplots(rows=1, cols=3, subplot_titles=list(LABELS.values()), shared_yaxes=True)
    for i, (name, (_, sec)) in enumerate(frames.items()):
        comparison.add_trace(go.Scatter(x=sec.time / 60, y=sec.mid - summaries[i]["mid_start"],
                                        line=dict(color=COLORS[i], width=1.5), name=LABELS[name]), row=1, col=i+1)
        comparison.update_xaxes(title_text="Elapsed minutes", row=1, col=i+1)
    comparison.update_yaxes(title_text="Move from initial mid (ticks)", row=1, col=1)
    style(comparison, 370).update_layout(showlegend=False)
    comp_rows = []
    for r in summaries:
        comp_rows.append({"Round": LABELS[Path(r["source"]).stem], "Minutes": round(r["duration_s"] / 60),
                          "Events / s": r["events"] / r["duration_s"], "Executed lots / s": r["executed_qty"] / r["duration_s"],
                          "1 s RMS (ticks)": r["rms_return1"], "Mean spread": r["mean_spread_time_weighted"],
                          "Median thinner L1": r["l1_min_median"], "|1 s move| >= 10": r["jump_ge10_count"],
                          "Top 1% variance": 100 * r["top1pct_variance_share"]})
    comparison_table = pd.DataFrame(comp_rows)
    comparison_table.to_csv(output / "comparison_display.csv", index=False)

    # 2. Tail risk and warnings available before the next ten seconds.
    tails = make_subplots(rows=1, cols=2, subplot_titles=["Large moves are much more frequent", "Tail moves dominate realized variance"])
    for i, (name, (_, sec)) in enumerate(frames.items()):
        thresholds = np.arange(1, 31)
        probabilities = [(sec.return1.dropna().abs() >= k).mean() for k in thresholds]
        tails.add_trace(go.Scatter(x=thresholds, y=probabilities, name=LABELS[name],
                                  mode="lines+markers", marker_size=4, line_color=COLORS[i]), row=1, col=1)
    tails.add_trace(go.Bar(x=list(LABELS.values()), y=[r["top1pct_variance_share"] * 100 for r in summaries],
                          marker_color=COLORS[:3], name="Top 1% variance share", showlegend=False), row=1, col=2)
    tails.update_yaxes(type="log", title_text="Fraction of 1 s returns (log)", row=1, col=1)
    tails.update_yaxes(title_text="Variance share (%)", range=[0, 100], row=1, col=2)
    tails.update_xaxes(title_text="Absolute return threshold (ticks)", row=1, col=1)
    style(tails, 400)

    # 3. Time split signal tests, with raw direction and spread-cost diagnostics.
    signal_plot = make_subplots(rows=1, cols=2, subplot_titles=["First half: exploratory reference", "Second half: chronological validation"])
    for column, period in [(1, "first_half"), (2, "second_half")]:
        heat = signal[signal.period == period].pivot(index="feature", columns="horizon_s", values="signed_mid_move").reindex(SIGNALS)
        signal_plot.add_trace(go.Heatmap(x=[str(h) for h in heat.columns], y=list(SIGNALS.values()), z=heat.values,
                                         colorscale="RdBu", zmid=0, zmin=-4, zmax=4, showscale=column == 2,
                                         colorbar=dict(title="Ticks", len=0.8),
                                         text=np.round(heat.values, 2), texttemplate="%{text}",
                                         hovertemplate="%{y}<br>Horizon %{x}s<br>Signed mid move %{z:.3f} ticks<extra></extra>"), row=1, col=column)
    signal_plot.update_xaxes(title_text="Forward horizon (seconds)", type="category")
    style(signal_plot, 430).update_layout(margin=dict(l=205, r=85, t=60, b=55), hovermode="closest")
    short = signal[(signal.period == "second_half") & (signal.horizon_s == 1)].copy()
    short["feature"] = short.feature.map(SIGNALS)
    short = short[["feature", "n", "coverage", "signed_mid_move", "ci_low", "ci_high", "after_spread"]]

    # 4. Actual historical maker fills, not hypothetical new orders.
    markout_plot = make_subplots(rows=1, cols=2, subplot_titles=["All historical market-maker fills", "Round 3, conditioned on spread before the fill"])
    for i, name in enumerate(frames):
        subset = markout[(markout["round"] == name) & (markout.group == "all") & (markout.horizon_s > 0)]
        markout_plot.add_trace(go.Scatter(x=subset.horizon_s, y=subset.maker_edge_ticks_per_lot,
                                          mode="lines+markers", name=LABELS[name], line_color=COLORS[i]), row=1, col=1)
    for i, group in enumerate(["spread=1", "spread=2-3", "spread>=4"]):
        subset = markout[(markout["round"] == "round3_public") & (markout.group == group) & (markout.horizon_s > 0)]
        markout_plot.add_trace(go.Scatter(x=subset.horizon_s, y=subset.maker_edge_ticks_per_lot, mode="lines+markers",
                                          name=group, line_color=COLORS[i], line_dash="dot"), row=1, col=2)
    markout_plot.update_xaxes(type="log", title_text="Seconds after fill (log)")
    markout_plot.update_yaxes(title_text="Maker markout (ticks / lot)")
    markout_plot.add_hline(y=0, line_color="#7c8a94", line_dash="dash")
    style(markout_plot, 440)

    # 5. Unmodified executable strategies and fixed ablations.
    pnl = go.Figure()
    for i, (name, curve) in enumerate(curves.items()):
        pnl.add_trace(go.Scatter(x=curve.elapsed_s / 60, y=curve.pnl, name=STRATEGIES.get(name, name), line=dict(color=COLORS[i], width=1.8)))
    pnl.update_xaxes(title_text="Elapsed minutes")
    pnl.update_yaxes(title_text="PnL (tick × lots)")
    pnl.add_vline(x=50, line_color="#7c8a94", line_dash="dash")
    style(pnl, 440)
    ablations = []
    variant_names = {"adaptive_trace": "Adaptive reference (trace check)", "no_inventory_bias": "No crash/recovery or fade bias",
                     "no_fade": "No 300 s fade bias", "no_crash_bias": "No crash/recovery bias; keep fade",
                     "no_risk_or_inventory_bias": "Full size, no inventory bias"}
    for name, label in variant_names.items():
        path = output / "ablations" / name / "result.json"
        if path.exists():
            result = json.loads(path.read_text())
            curve = pd.read_csv(path.parent / "pnl.csv")
            first_half = float(np.interp(3000, curve.elapsed_s, curve.pnl))
            ablations.append({"Variant": label, "PnL": result["pnl"], "First half": first_half,
                              "Second half": result["pnl"] - first_half,
                              "Max drawdown": float((curve.pnl.cummax() - curve.pnl).max()),
                              "Penalty": result["breach_penalty"], "Volume": result["traded_volume"]})
    ablation_table = pd.DataFrame(ablations, columns=["Variant", "PnL", "First half", "Second half", "Max drawdown", "Penalty", "Volume"])
    ablation_table.to_csv(output / "ablation_comparison.csv", index=False)

    controls_path = output / "ablations/adaptive_trace/controls.csv"
    control_text = ""
    control_plot = None
    if controls_path.exists():
        controls = pd.read_csv(controls_path)
        neutral = (controls.effective_limit == 0).mean()
        control_text = (f"The adaptive model sets its volatility-based quoting radius to zero for {neutral:.1%} of sampled seconds. "
                        "A zero radius still permits unwinding and trading toward a nonzero inventory center; it does not mean flat inventory.")
        control_plot = make_subplots(rows=2, cols=1, shared_xaxes=True, subplot_titles=["Adaptive controls at the first callback each second", "Inventory and target center"], vertical_spacing=0.17)
        control_plot.add_trace(go.Scatter(x=controls.time / 60, y=controls.effective_limit, name="Effective radius", line_color=COLORS[2]), row=1, col=1)
        control_plot.add_trace(go.Scatter(x=controls.time / 60, y=controls.inventory, name="Inventory", line=dict(color=COLORS[0], width=1)), row=2, col=1)
        control_plot.add_trace(go.Scatter(x=controls.time / 60, y=controls.center, name="Target center", line=dict(color=COLORS[1], width=2)), row=2, col=1)
        control_plot.update_yaxes(title_text="Lots")
        control_plot.update_xaxes(title_text="Elapsed minutes", row=2, col=1)
        style(control_plot, 530)

    # Save chart data as JSON too, allowing a compact structural verification.
    figures = {"overview": overview, "comparison": comparison, "tail-risk": tails, "signal-tests": signal_plot,
               "maker-markouts": markout_plot, "strategy-pnl": pnl}
    if control_plot is not None:
        figures["adaptive-controls"] = control_plot
    for name, fig in figures.items():
        fig.write_json(output / f"{name}.plotly.json")

    fade = signal[(signal.feature == "momentum30") & (signal.horizon_s == 10)]
    fade_test = fade[fade.period == "second_half"].iloc[0]
    adaptive = benchmarks[benchmarks.strategy == "Adaptive reference"].iloc[0] if len(benchmarks) else None
    maker1 = markout[(markout["round"] == "round3_public") & (markout.group == "all") & (markout.horizon_s == 1)].iloc[0]
    conclusions = [
        f"Round 3 is more volatile and thinner than round 2: 1 s RMS returns are {summary['rms_return1']:.2f} vs {summaries[1]['rms_return1']:.2f} ticks; median thinner-side L1 is {summary['l1_min_median']:.0f} vs {summaries[1]['l1_min_median']:.0f} lots.",
        f"Tail risk matters more than the net move: the mid ends {summary['net_move_ticks']:+.0f} ticks from its initial value, but the worst peak-to-trough decline is {summary['max_drawdown_ticks']:.1f} ticks. The largest 1% of one-second returns contribute {summary['top1pct_variance_share']:.1%} of squared returns.",
        f"Spread capture deteriorates quickly after a fill. Historical maker fills mark out at {maker1.maker_edge_ticks_per_lot:+.3f} ticks per lot after one second. Their fill selection and queue position differ from a newly submitted strategy order.",
        "Order-book imbalance and recent aggressive flow have short-lived directional information. The one-second moves do not cover the estimated round-trip spread; they are more plausible quote-skew or inventory inputs than standalone crossing signals.",
        f"A 30 s move exceeding 5 ticks tends to reverse over the next 10 s in both halves. Held-out fade gross edge is {-fade_test.signed_mid_move:.2f} ticks and spread-adjusted diagnostic edge is {fade_test.fade_after_spread:.2f} ticks (95% block interval {fade_test.fade_net_ci_low:.2f} to {fade_test.fade_net_ci_high:.2f}). This is exploratory: overlapping decisions, multiple tested horizons, no queue, depth, inventory, or 5 ms execution simulation.",
    ]
    if adaptive is not None:
        conclusions.append(f"The unchanged adaptive reference earns {adaptive.pnl:,.0f}, including {adaptive.breach_penalty:,.0f} in penalties; first half {adaptive.first_half_pnl:,.0f}, second half {adaptive.second_half_pnl:,.0f}. This is public-tape evidence, not a private-round score.")
    warning = risk[risk.condition == "Last-second mean spread >= 2"].iloc[0]
    conclusions.append(f"Spread widening is a useful risk warning: after a last-second average spread of at least 2 ticks, the held-out chance of a >=10-tick one-second move in the next ten seconds is {warning.jump_probability:.1%}, versus {risk.iloc[0].jump_probability:.1%} overall. The warning covers only {warning.coverage:.1%} of eligible held-out seconds, so it misses many jumps.")
    ablation_results = {row["Variant"]: row for row in ablations}
    if "Full size, no inventory bias" in ablation_results and "No crash/recovery or fade bias" in ablation_results:
        gated = ablation_results["No crash/recovery or fade bias"]
        full = ablation_results["Full size, no inventory bias"]
        conclusions.append(f"Risk sizing drives the adaptive strategy's protection. With inventory biases disabled in both runs, adaptive sizing earns {gated['PnL']:,.0f}, while forcing full size loses {abs(full['PnL']):,.0f}. Removing crash/recovery bias while keeping the original fade earns {ablation_results['No crash/recovery bias; keep fade']['PnL']:,.0f}; treat this as an ablation result, not a newly validated strategy choice.")

    method = [
        "Sources: local round1.csv (200 minutes), round2_public.csv and round3_public.csv (100 minutes each). SHA-256 fingerprints are stored in summary.json. All price units are integer ticks; PnL is ticks multiplied by lots, with no currency assumption.",
        "The repository's matching engine replays every insert/cancel in original order. F means immediate-or-cancel; G can match immediately and rests any remainder. Cancels of already-filled IDs are legitimate no-ops, not missing-data errors. No strategy is attached to the market-only reconstruction.",
        "Quantity conservation is checked on every full tape: inserted quantity = twice executed quantity + canceled resting quantity + unfilled IOC quantity + final resting quantity. All three residuals are zero. Two executed legs are counted because both the maker and taker lose that quantity.",
        "Quotes and depths are sampled every 100 ms from events strictly before the grid time. No interpolation or backfill from future events. Depth is visible quantity at the best price; 5-tick depth includes empty ticks. Mean spread is integrated over time, excluding intervals with an empty book side. Charts use one-second samples for readability; extrema and drawdown use all quote changes.",
        "Signals use causal inputs and fixed symmetric thresholds. First half is 0–3000 s; second half is 3000–6000 s. Warmup is 120 s, and targets crossing the split or tape end are excluded. Second-half features may use earlier observed history. These are exploratory time-split checks, not an untouched external validation set.",
        "Signal intervals use 800 moving-block bootstrap resamples, 60 s blocks for horizons up to 30 s and 120 s blocks for the 60 s horizon. Overlapping 100 ms observations are not treated as independent trades. Intervals are pointwise and unadjusted for multiple comparisons. They do not establish repeated-session profitability.",
        "Crossing-cost diagnostic subtracts half the current spread plus half the future spread. This assumes touch execution and omits size impact, 5 ms latency and inventory constraints. Maker markouts instead use actual market-market executions, quantity weighting, and exact as-of future quotes. Empty-side observations and horizons past the tape end are excluded.",
        "Strategy results use the unchanged official engine: 5 ms acceptance delay, ±100 penalty-free inventory, ±1000 potential exposure, and 10,000 per second breach penalty. PnL includes terminal depth liquidation. Ablations use fixed constructor controls; the full-size diagnostic overrides the effective limit after forecasting, retaining the history update. Effects interact and cannot be added as separate profit contributions. The traced original reproduces every result field of the unmodified original.",
    ]
    notes = "# Round 3 public-tape analysis\n\n" + "\n\n".join(f"{i+1}. {text}" for i, text in enumerate(conclusions))
    notes += "\n\n## Unchanged strategy results\n\n" + benchmarks[["strategy", "pnl", "first_half_pnl", "second_half_pnl", "breach_penalty", "max_pnl_drawdown"]].to_csv(index=False)
    notes += "\n\n## Fixed ablations\n\n" + ablation_table.to_csv(index=False)
    notes += "\n\n## Method and limitations\n\n" + "\n\n".join(method)
    notes += "\n\n## Reproduce\n\nRun `.venv/bin/python scripts/analyze_round3.py` from the repository root. Market reconstruction caches require matching tape and engine fingerprints. Missing main strategy benchmarks run automatically; `--refresh` reruns reconstruction and those benchmarks. Fixed ablations are optional: run `.venv/bin/python scripts/round3_diagnostics.py --variant NAME` for adaptive_trace, no_inventory_bias, no_fade, no_crash_bias, and no_risk_or_inventory_bias, then rerun the analyzer. Existing strategies and datasets are unchanged.\n\nThe standalone PNG/SVG overview additionally requires matplotlib; it was generated using a temporary installation, with no dependency changes in this repository.\n"
    (output / "findings.md").write_text(notes)

    def section(number, title, body):
        return f'<section id="section-{number}"><div class="eyebrow">0{number} / ANALYSIS</div><h2>{title}</h2>{body}</section>'

    fmt = {column: lambda x: f"{x:,.2f}" for column in comparison_table.select_dtypes("float").columns}
    bench_columns = ["strategy", "pnl", "first_half_pnl", "second_half_pnl", "breach_penalty", "max_pnl_drawdown", "traded_volume"]
    body = section(1, "The shape of the session", '<p>Hover for exact values, drag to zoom, and double-click to reset. The dashed line marks the 50-minute validation split. The 2.2-tick volatility line is a reference from the retained strategy; its actual forecast uses more inputs.</p>' + chart(overview, "overview", True))
    body += section(2, "How round 3 differs", chart(comparison, "comparison") + table(comparison_table, fmt) + '<p>Round 1 is twice as long, so compare rates and distributions rather than event totals. All series retain their actual elapsed time.</p>')
    body += section(3, "Risk is concentrated in bursts", chart(tails, "tail-risk") + '<h3>Warnings before the next ten seconds</h3><p>Held-out probability of at least one ≥10-tick one-second move in the next 10 seconds. Depth and event-rate thresholds come from the first half. These conditions overlap.</p>' + table(risk, {"coverage": "{:.1%}".format, "jump_probability": "{:.1%}".format, "ci_low": "{:.1%}".format, "ci_high": "{:.1%}".format, "lift": "{:.2f}×".format}))
    body += section(4, "What predicts the next move?", '<p>Positive values mean continuation in the signal direction; negative values mean reversal. Absolute thresholds apply on both sides. Each cell is a mean signed midprice move in ticks, before trading costs.</p>' + chart(signal_plot, "signal-tests") + '<h3>One-second held-out diagnostics</h3>' + table(short, {"coverage": "{:.1%}".format, **{c: "{:+.3f}".format for c in ["signed_mid_move", "ci_low", "ci_high", "after_spread"]}}) + '<p>The interval columns are pointwise 95% moving-block intervals. A small midprice forecast can be useful for passive quoting even when immediate crossing is unattractive.</p>')
    body += section(5, "The spread is compensation for adverse selection", '<p>Positive markout favors the maker; negative markout means the price moved against the maker after execution. These are actual historical market fills, weighted by executed quantity. They do not assume a new strategy can obtain the same fills.</p>' + chart(markout_plot, "maker-markouts") + '<p>Wide spreads are a stress marker. The ≥4-tick group is small (roughly 25,000 eligible lots), and its extreme averages should not be generalized.</p>')
    body += section(6, "Can the existing strategies trade this?", chart(pnl, "strategy-pnl") + table(benchmarks[bench_columns], {c: "{:,.0f}".format for c in bench_columns if c != "strategy"}) + '<h3>Fixed ablations of the adaptive reference</h3>' + table(ablation_table, {c: "{:,.0f}".format for c in ablation_table.columns if c != "Variant"}) + f'<p>{control_text}</p>' + (chart(control_plot, "adaptive-controls") if control_plot is not None else ""))
    body += section(7, "Conclusions and next experiments", '<ol>' + ''.join(f'<li>{html.escape(text)}</li>' for text in conclusions) + '</ol><p>Prioritize risk gating and controlled inventory. Validate a short-horizon fade with an actual latency-aware, inventory-limited strategy before trusting its spread-adjusted diagnostic. Preserve a fresh tape for final strategy selection.</p>')
    body += section(8, "Five-minute session map", '<p>Descriptive intervals, computed after the tape. They are not labels a live strategy could know in advance. First/last midprices are the one-second samples within each interval.</p>' + table(segments.reset_index(drop=True), {c: "{:,.2f}".format for c in segments.columns if c != "minutes"}))
    body += '<details><summary>Sources, reconstruction, and statistical limitations</summary>' + ''.join(f'<p>{html.escape(text)}</p>' for text in method) + '</details>'
    css = """
    *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f3f5f5;color:#253440;font:15px/1.65 Arial,sans-serif}
    .wrap{max-width:1380px;margin:auto;padding:42px 38px 80px}.hero{padding:35px 0 20px}.eyebrow{font-size:11px;letter-spacing:2px;font-weight:700;color:#637883}
    h1{font-size:clamp(32px,4vw,56px);line-height:1.1;letter-spacing:-2px;margin:20px 0;max-width:1000px}h2{font-size:28px;letter-spacing:-.6px;margin:7px 0 18px}h3{font-size:19px;margin:25px 0 10px}
    .sub{font-size:18px;max-width:900px;color:#5e6f78}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:30px 0}.card{padding:22px;background:white;border:1px solid #e1e7e8;border-radius:10px}
    .value{font-size:32px;font-weight:700;letter-spacing:-1px;color:#176b76}.label{font-size:12px;color:#647984;margin-top:6px}.card small{font-size:12px;color:#687c85}
    nav{display:flex;gap:20px;flex-wrap:wrap;padding:15px 0 25px}a{color:#176b76;text-decoration:none}a:hover{text-decoration:underline}
    section,details{background:white;border:1px solid #e1e7e8;border-radius:12px;padding:30px;margin:22px 0;overflow:hidden}p{max-width:1150px;color:#526772}li{margin:12px 0;padding-left:7px}
    .data-table{width:100%;border-collapse:collapse;font-size:12px;display:block;overflow-x:auto;white-space:nowrap;margin:20px 0}
    th{text-align:left!important;background:#edf3f3;color:#324f5b;border-bottom:2px solid #d8e3e5;padding:12px 13px}td{text-align:right;padding:11px 13px;border-bottom:1px solid #edf0f2}td:first-child{text-align:left}tr:hover td{background:#f6f9f9}
    details summary{cursor:pointer;font-weight:bold}.footer{font-size:12px;color:#7b8a91}.js-plotly-plot{max-width:100%}
    @media(max-width:800px){.wrap{padding:18px 12px}.cards{grid-template-columns:repeat(2,1fr)}section{padding:18px 10px}h1{letter-spacing:-1px}.value{font-size:26px}}
    """
    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Round 3 — Market Anatomy</title><style>{css}</style></head><body><main class="wrap">
    <div class="hero"><div class="eyebrow">QMINERS ALGO ARENA / ROUND 03 / PUBLIC TAPE</div><h1>Thinner liquidity.<br>A higher cost of being wrong.</h1><p class="sub">A market reconstruction, a comparison with earlier rounds, and a test of which patterns survive chronology and execution costs.</p></div>
    <div class="cards"><div class="card"><div class="value">2.41M</div><div class="label">ORDER EVENTS · 100 MINUTES</div><small>7.16M lots executed</small></div><div class="card"><div class="value">{summary['rms_return1']:.2f}</div><div class="label">ONE-SECOND RMS · TICKS</div><small>{(summary['rms_return1']/summaries[1]['rms_return1']-1):+.0%} versus round 2</small></div><div class="card"><div class="value">{summary['l1_min_median']:.0f}</div><div class="label">MEDIAN THINNER L1 · LOTS</div><small>{(summary['l1_min_median']/summaries[1]['l1_min_median']-1):+.0%} versus round 2</small></div><div class="card"><div class="value">{summary['top1pct_variance_share']:.0%}</div><div class="label">VARIANCE FROM TOP 1% OF MOVES</div><small>{summary['jump_ge10_count']} one-second moves ≥10 ticks</small></div></div>
    <nav>{''.join(f'<a href="#section-{i}">{label}</a>' for i,label in enumerate(['Session','Round comparison','Risk','Signals','Maker fills','Strategies','Conclusions','Session map'],1))}</nav>
    {body}<p class="footer">Local, self-contained report · No data leaves this machine · Price in ticks; PnL in tick × lots · Public tape only</p></main></body></html>'''
    (output / "round3_report.html").write_text(document)
    try:
        export_overview(output, frames, summaries, curves)
    except ImportError:
        print("Optional PNG skipped: matplotlib is not installed. Interactive HTML is complete.")
    print(f"Report: {output / 'round3_report.html'}", flush=True)


def export_overview(output, frames, summaries, curves):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#d1dbdf", "axes.labelcolor": "#526772", "xtick.color": "#647984", "ytick.color": "#647984",
                         "text.color": "#253440", "figure.facecolor": "#f3f5f5", "axes.facecolor": "white", "grid.color": "#e8edef"})
    fig = plt.figure(figsize=(16, 11), layout="constrained")
    axes = fig.subplot_mosaic([["price", "price"], ["risk", "depth"], ["pnl", "pnl"]], height_ratios=[1.35, 1, 1.15])
    s = frames["round3_public"][1]
    axes["price"].plot(s.time / 60, s.mid, color=COLORS[0], linewidth=1.1)
    axes["price"].set(title="Round 3 midprice — every one-second close", ylabel="Price (ticks)", xlim=(0, 100))
    axes["price"].axvline(50, color="#9eacb4", linestyle="--", linewidth=1)
    axes["price"].text(51, 10120, "Second half →", color="#6d7f89", fontsize=10)
    axes["risk"].plot(s.time / 60, s.rv30, color=COLORS[1], linewidth=1)
    axes["risk"].set(title="Volatility arrives in bursts", ylabel="30 s RMS of 1 s returns (ticks)", xlabel="Elapsed minutes", xlim=(0, 100))
    axes["risk"].axhline(2.2, color=COLORS[3], linestyle=":", linewidth=1)
    axes["depth"].bar(list(LABELS.values()), [r["l1_min_median"] for r in summaries], color=COLORS[:3], width=.55)
    axes["depth"].set(title="Less depth at the touch", ylabel="Median thinner-side L1 (lots)", ylim=(0, 470))
    for i, r in enumerate(summaries):
        axes["depth"].text(i, r["l1_min_median"] + 13, f"{r['l1_min_median']:.0f}", ha="center", fontsize=12, fontweight="bold")
    for i, (name, curve) in enumerate(curves.items()):
        axes["pnl"].plot(curve.elapsed_s / 60, curve.pnl, label=f"{STRATEGIES.get(name,name)}  {curve.pnl.iloc[-1]:+,.0f}", color=COLORS[i], linewidth=1.6)
    axes["pnl"].set(title="Unchanged strategies on the full round 3 public tape", xlabel="Elapsed minutes", ylabel="PnL (tick × lots)", xlim=(0, 100))
    axes["pnl"].yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x/1000:,.0f}k"))
    axes["pnl"].axhline(0, color="#b8c3c9", linewidth=.8)
    axes["pnl"].legend(loc="lower left", frameon=False, ncols=3, fontsize=10)
    for ax in axes.values():
        ax.grid(axis="y", linewidth=.7)
        ax.set_axisbelow(True)
        ax.set_title(ax.get_title(), fontweight="bold", pad=12)
    last = summaries[-1]
    fig.suptitle(f"ROUND 03  /  MARKET ANATOMY\n{last['rms_return1']:.2f}-tick one-second RMS  ·  {last['l1_min_median']:.0f}-lot median thinner L1  ·  {last['top1pct_variance_share']:.0%} of variance from the largest 1% of moves",
                 fontsize=19, fontweight="bold", ha="left", x=.025)
    fig.savefig(output / "round3_overview.png", dpi=160, facecolor=fig.get_facecolor())
    fig.savefig(output / "round3_overview.svg", facecolor=fig.get_facecolor())
    plt.close(fig)
