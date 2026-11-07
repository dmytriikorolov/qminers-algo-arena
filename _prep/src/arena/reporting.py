"""On-demand reports generated strictly from saved experiment results."""
from html import escape
import json
from pathlib import Path

from .common import ROOT, project_path
from .experiments import load_run, numeric_metrics


def report(run_id, root=ROOT, pdf=False):
    record = load_run(run_id, root)
    result = record["result"]
    metrics = numeric_metrics(result.get("metrics", {}))
    synthetic = record["dataset"]["kind"] == "synthetic"
    label = "SYNTHETIC / EXAMPLE DATA" if synthetic else "USER-SUPPLIED DATA (meaning not independently verified)"
    directory = project_path(Path(root) / "reports" / run_id, root)
    directory.mkdir(parents=True, exist_ok=True)
    warnings = result.get("warnings", []) + result.get("assumptions", [])
    html_path = project_path(directory / "report.html", root)
    markdown_path = project_path(directory / "report.md", root)
    pdf_path = project_path(directory / "report.pdf", root)
    rows = "".join(f"<tr><td>{escape(key)}</td><td>{value:.8g}</td></tr>" for key, value in metrics.items())
    html = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<title>Arena experiment {escape(run_id)}</title>
<style>body{{font:16px system-ui;max-width:1000px;margin:40px auto;padding:16px}}
td,th{{padding:6px 12px;border-bottom:1px solid #ddd;text-align:left}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
.label{{color:#963a00;font-weight:bold}}</style>
<h1>Offline experiment: {escape(record['config']['family'])}</h1>
<p class="label">{label}</p><p>Run: {escape(run_id)} | Seed: {record['seed']} | {escape(record['timestamp'])}</p>
<p>Question: how do the implemented baselines perform on this configured example?</p>
<h2>Observed metrics</h2><table><tr><th>Metric (units in name/result)</th><th>Value</th></tr>{rows}</table>
<h2>Interpretation and limitations</h2><p>These values describe this run only. A better synthetic score is not evidence of a competitive or profitable strategy.
No official submission contract has been tested. Inspect assumptions, losses, sample size, and independent seeds before selecting a method.</p>
<ul>{''.join('<li>' + escape(str(item)) + '</li>' for item in warnings)}</ul>
<p>Next action: reproduce the official evaluator, then compare these methods on its metric and legal data.</p>
<h2>Source result and provenance</h2><p>Source: experiments/{escape(run_id)}/result.json</p>
<pre>{escape(json.dumps(record, indent=2, sort_keys=True))}</pre></html>"""
    html_path.write_text(html)
    markdown = [f"# Arena experiment {run_id}", "", label, "",
                f"Family: {record['config']['family']}; seed: {record['seed']}", "",
                "| Observed metric | Value |", "|---|---:|"]
    markdown.extend(f"| {key} | {value:.8g} |" for key, value in metrics.items())
    markdown.extend(["", f"Source: experiments/{run_id}/result.json",
                     f"Dataset SHA-256: {record['dataset']['sha256']}",
                     f"Source SHA-256: {record['source_sha256']}", "",
                     "This run is preparation evidence, not official evaluation or demonstrated trading edge.",
                     "Next: test on the official metric, legal data, independent seeds and pessimistic fill assumptions."])
    markdown.extend(["", "## Assumptions and warnings", ""] + ["- " + str(item) for item in warnings])
    markdown_path.write_text("\n".join(markdown) + "\n")
    outputs = {"html": str(html_path), "markdown": str(markdown_path)}
    if pdf:
        _pdf(record, metrics, label, pdf_path)
        outputs["pdf"] = str(pdf_path)
    return outputs


def _pdf(record, metrics, label, output):
    try:
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    except ImportError as exc:
        raise ValueError("PDF dependency unavailable; install .[reports] in a venv; HTML/Markdown were generated") from exc
    styles = getSampleStyleSheet()
    items = [Paragraph("Arena Quick Insight", styles["Title"]),
             Paragraph(escape(label), styles["Heading2"]),
             Paragraph(f"Run: {escape(record['id'])}<br/>Family: {escape(record['config']['family'])} | Seed: {record['seed']}", styles["Normal"]),
             Spacer(1, 12)]
    table_data = [["Observed metric", "Value"]] + [[key, f"{value:.8g}"] for key, value in metrics.items()]
    table = Table(table_data, colWidths=[350, 130], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2edf5")),
                               ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                               ("FONTSIZE", (0, 0), (-1, -1), 8),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey)]))
    items.extend([table, Spacer(1, 12)])
    chart = _chart(record)
    if chart is not None:
        items.extend([chart, Spacer(1, 12)])
    assumptions = record["result"].get("warnings", []) + record["result"].get("assumptions", [])
    for assumption in assumptions:
        items.append(Paragraph(escape(str(assumption)), styles["Normal"]))
    items.extend([
                  Paragraph("What this means", styles["Heading2"]),
                  Paragraph("The table contains observed values from this saved run, with no invented performance estimates. "
                            "Values from different metrics have different units and must not be ranked together. "
                            "Synthetic comparisons demonstrate implementation and sensitivity; they do not demonstrate trading edge.", styles["Normal"]),
                  Paragraph("Limitations and next test", styles["Heading2"]),
                  Paragraph("Official runtime, API, scoring and dependencies must still be checked. "
                            "Use the official evaluator and legal data, compare paired seeds, and inspect worst cases. "
                            "A mock fill model can materially change the ranking of strategies.", styles["Normal"]),
                  Spacer(1, 12), Paragraph("Provenance", styles["Heading2"]),
                  Paragraph(f"Source: experiments/{escape(record['id'])}/result.json<br/>"
                            f"Timestamp: {escape(record['timestamp'])}<br/>"
                            f"Dataset SHA-256: {record['dataset']['sha256']}<br/>"
                            f"Source SHA-256: {record['source_sha256']}<br/>"
                            f"Git: {escape(record['git']['revision'])}; dirty={record['git']['dirty']}", styles["Normal"])])
    if record["config"]["family"] == "games":
        from .game_reporting import puzzle_cards
        items.extend([PageBreak(), *puzzle_cards(record, styles)])
    SimpleDocTemplate(str(output), title=f"Arena {record['id']}", author="Quant Arena Lab",
                      leftMargin=48, rightMargin=48, topMargin=36, bottomMargin=36).build(items)


def _chart(record):
    """Plot comparable quantities only, with data taken from this result."""
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors
    result = record["result"]
    family = record["config"]["family"]
    comparison = result.get("comparison", [])
    drawing = Drawing(480, 235)
    if family == "market" and comparison:
        plot = LinePlot()
        plot.data = [[(row["time"], row["pnl"]) for row in method["equity"]] for method in comparison]
        plot.x, plot.y, plot.width, plot.height = 55, 70, 390, 140
        palette = [colors.black, colors.blue, colors.red, colors.green, colors.purple,
                   colors.orange, colors.brown, colors.grey]
        for index, method in enumerate(comparison):
            plot.lines[index].strokeColor = palette[index % len(palette)]
            drawing.add(String(15 + (index % 4) * 118, 30 - (index // 4) * 14,
                               method["strategy"], fontSize=8, fillColor=palette[index % len(palette)]))
        drawing.add(plot)
        drawing.add(String(12, 222, "Mock equity: cash + position x mid (price units)", fontSize=10))
        drawing.add(String(205, 43, "Synthetic event step", fontSize=8))
        return drawing
    if family == "ml" and comparison:
        metric = result["selection"]["primary_metric"]
        chart = VerticalBarChart()
        chart.x, chart.y, chart.width, chart.height = 55, 45, 380, 150
        chart.data = [[row[metric] for row in comparison]]
        chart.categoryAxis.categoryNames = [row["strategy"] for row in comparison]
        chart.valueAxis.valueMin = 0
        drawing.add(chart)
        drawing.add(String(15, 215, f"Held-out {metric} (lower is better), n={result['split']['test_rows']}", fontSize=10))
        return drawing
    return None


def quick_cards(output):
    """Six printable offline cards, independent of any experiment metrics."""
    try:
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak
    except ImportError as exc:
        raise ValueError("quick cards require the optional reports extra") from exc
    cards = [
        ("First 15 minutes", "Read rules, objective, input/output and official example. Confirm Python version, AI/prewritten-code eligibility, data rights, dependencies and resource limits. Run the untouched official baseline. Do not substitute past contest assumptions."),
        ("Market and execution", "Spread = ask - bid. Midpoint is a mark, not an executable fill. Track cash + inventory * mark, fees and pending-order exposure. A cancel request does not free risk until acknowledged. Test duplicate and partial fills. Compare no-op, fixed and inventory-aware quotes. Synthetic fills prove no edge."),
        ("Tabular ML", "Configure target, features and time explicitly. Sort in time; keep train/validation/test separate. Fit imputation and scaling only on train. Purge overlapping labels and embargo gaps. Compare constant with ridge/logistic. Select settings on validation; leave test untouched. Predictive accuracy is not net trading profit."),
        ("Allocation and games", "Write legal choices and the exact payoff first. Use enumeration as a tiny-case oracle, then knapsack DP for integer costs. Shared rewards depend on rival counts. Auctions need explicit payment and tie rules. Zero-sum games need maximin bounds; general-sum games require different analysis."),
        ("Coding and packaging", "Start with an exact small oracle. Dijkstra requires nonnegative edges; Bellman-Ford detects reachable negative cycles. Confirm filename, function/class signature and import restrictions. Static AST checks do not prove runtime or sandbox safety. Run official samples and edge cases under the real limits."),
        ("Experiment and handoff", "Change one idea at a time. Save config, seed, input hash, source hash and metric. Compare identical cases, then new cases and pessimistic assumptions. Preserve last-known-good submission. Before stopping: run arena validate, save results, generate handoff, list three next actions. External AI memory remains disabled."),
    ]
    styles = getSampleStyleSheet()
    items = []
    for index, (title, text) in enumerate(cards):
        if index:
            items.append(PageBreak())
        items.extend([Paragraph(title, styles["Title"]), Paragraph(text, styles["BodyText"])])
    SimpleDocTemplate(str(output), title="Arena offline quick cards").build(items)
