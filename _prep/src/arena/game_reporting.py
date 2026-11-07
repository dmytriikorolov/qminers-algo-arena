"""Six compact printable puzzle answers drawn only from a saved games run.

ReportLab is imported on demand. Importing the solver package stays offline
and dependency-free. The caller inserts a page break before these flowables.
"""

from html import escape
import math


PUZZLES = ("knapsack", "shared_reward", "sealed_bid_auction", "matrix_game",
           "conversion_graph", "tournament_risk")


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("puzzle report requires observed finite numeric values")
    return f"{value:.8g}"


def _bar(labels, values, title, probability=False):
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors
    if not labels or len(labels) != len(values):
        raise ValueError("puzzle chart needs matching nonempty labels and values")
    for value in values:
        _number(value)
    drawing = Drawing(470, 205)
    chart = VerticalBarChart()
    chart.x, chart.y, chart.width, chart.height = 60, 43, 380, 135
    chart.data = [list(values)]
    chart.categoryAxis.categoryNames = [str(label)[:18] for label in labels]
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.valueMin = min(0, min(values))
    chart.valueAxis.valueMax = 1 if probability else max(0, max(values))
    if chart.valueAxis.valueMax == chart.valueAxis.valueMin:
        chart.valueAxis.valueMax += 1
    chart.bars[0].fillColor = colors.HexColor("#286d96")
    chart.barLabels.fontSize = 8
    chart.barLabelFormat = "%.3g"
    drawing.add(chart)
    drawing.add(String(10, 192, title, fontName="Helvetica-Bold", fontSize=10))
    return drawing


def _auction_chart(solution):
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.shapes import Drawing, String
    bids, utilities = solution["bids"], solution["expected_utilities"]
    if not bids or len(bids) != len(utilities):
        raise ValueError("auction plot needs the observed bid grid and utilities")
    for value in list(bids) + list(utilities):
        _number(value)
    drawing = Drawing(470, 215)
    plot = LinePlot()
    plot.x, plot.y, plot.width, plot.height = 60, 50, 380, 130
    plot.data = [list(zip(bids, utilities))]
    plot.xValueAxis.labels.fontSize = plot.yValueAxis.labels.fontSize = 8
    plot.lines[0].strokeWidth = 1.3
    drawing.add(plot)
    drawing.add(String(10, 198, "Empirical expected utility (reward units)", fontName="Helvetica-Bold", fontSize=10))
    drawing.add(String(205, 20, "Our bid (price units)", fontSize=9))
    return drawing


def puzzle_cards(record, styles):
    """Return six one-page cards, with actual outcomes, assumptions and charts.

    Required input is a saved games experiment with exactly the six named
    puzzles produced by games.demo. Missing evidence raises a clear error.
    No solver is rerun while reporting and no metric is reconstructed by guess.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, PageBreak
    except ImportError as exc:
        raise ValueError("puzzle cards require the optional reports extra") from exc
    if record.get("config", {}).get("family") != "games" or not record.get("id"):
        raise ValueError("puzzle cards require a saved games run with an ID")
    result = record.get("result", {})
    puzzles = result.get("puzzles", [])
    if (len(puzzles) != len(PUZZLES) or
            sorted(item.get("name", "") for item in puzzles) != sorted(PUZZLES)):
        raise ValueError("puzzle cards require all six distinct named puzzle results")
    by_name = {item["name"]: item for item in puzzles}
    small = ParagraphStyle("PuzzleSmall", parent=styles["BodyText"], fontSize=8, leading=11, spaceAfter=5)
    body = ParagraphStyle("PuzzleBody", parent=styles["BodyText"], fontSize=10, leading=14, spaceAfter=6)
    title = ParagraphStyle("PuzzleTitle", parent=styles["Title"], fontSize=20, leading=24, spaceAfter=10)

    def paragraph(text, style=body):
        return Paragraph(escape(str(text)), style)

    def table(rows, widths):
        data = [[paragraph(value, small) for value in row] for row in rows]
        grid = Table(data, colWidths=widths, hAlign="LEFT")
        grid.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2edf5")),
                                  ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                                  ("TOPPADDING", (0, 0), (-1, -1), 3),
                                  ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey)]))
        return grid

    flowables = []
    for index, name in enumerate(PUZZLES):
        if index:
            flowables.append(PageBreak())
        puzzle = by_name[name]
        solution = puzzle["solution"]
        flowables += [Paragraph(name.replace("_", " ").title(), title),
                      paragraph("SYNTHETIC / EXAMPLE PUZZLE | " + name, small),
                      paragraph("Run: " + str(record["id"]) + " | Seed: " + str(record.get("seed", result.get("seed"))), small),
                      paragraph(puzzle["statement"])]
        if name == "knapsack":
            inputs = puzzle["input"]
            costs, rewards = inputs["costs"], inputs["rewards"]
            chosen = set(solution["indices"])
            rows = [["Item", "Cost", "Reward", "Selected?"]]
            rows += [[str(i), _number(costs[i]), _number(rewards[i]), "yes" if i in chosen else "no"]
                     for i in range(min(8, len(costs))) ]
            flowables += [paragraph("Budget: " + _number(inputs["budget"]) + "; chosen item indices: " + str(solution["indices"])),
                          table(rows, [70, 110, 110, 160]),
                          paragraph("Reward: " + _number(solution["reward"]) + "; oracle reward: " +
                                    _number(puzzle["oracle"]["reward"]) + "; unused budget: " + _number(solution["unused_budget"])),
                          _bar([str(i) for i in range(min(12, len(rewards)))], rewards[:12], "Item rewards (first 12 at most; reward units)") if rewards else paragraph("No items: empty allocation."),
                          paragraph("Why: DP compares taking or skipping each item. Enumeration independently checks the tiny instance. Costs and rewards must be additive; indivisible items may be chosen once. Table shows at most eight items.", small)]
        elif name == "shared_reward":
            values = solution["expected_payoffs"]
            labels = ["Option " + str(i) for i in range(len(values))]
            flowables += [_bar(labels, values, "Expected reward per choice (reward units)"),
                          paragraph("Best option index: " + str(solution["best_choice"])),
                          table([["Option index", "Expected payoff"]] +
                                [[str(i), _number(value)] for i, value in enumerate(values)], [180, 270]),
                          paragraph("Why: a less crowded option can pay more despite a smaller prize. Compute the expectation of reward divided by crowd size, not reward divided by expected crowd size. Independence and rival choice probabilities are assumptions.", small)]
        elif name == "sealed_bid_auction":
            flowables += [paragraph("Payment rule: " + solution["kind"] + "; tie win probability: " + _number(solution["tie_probability"])),
                          _auction_chart(solution),
                          table([["Selected bid", "Expected utility under sampled rivals"],
                                 [_number(solution["best_bid"]), _number(solution["best_utility"])]], [180, 270]),
                          paragraph("Why: compare utility over the whole bid grid. A higher bid wins more often but can leave less profit. Monte Carlo sampling and the assumed rival distribution can move the selected bid. Confirm reserve prices, tie rules and payment rules from the real statement.", small)]
        elif name == "matrix_game":
            matrix = puzzle["input"]
            rows = [["Payoff matrix", "Column payoffs (first six columns)"]]
            rows += [["Row " + str(i), ", ".join(_number(value) for value in row[:6])]
                     for i, row in enumerate(matrix[:6])]
            flowables += [table(rows, [120, 330]),
                          _bar(["Row " + str(i) for i in range(min(10, len(solution["row_strategy"])))],
                               solution["row_strategy"][:10], "Row-player mixed strategy (probabilities; first 10)", probability=True),
                          paragraph("Method: " + solution["method"], small),
                          paragraph("Value: " + _number(solution["value"]) + "; lower bound: " +
                                    _number(solution["lower_bound"]) + "; upper bound: " +
                                    _number(solution["upper_bound"]) + "; best-response gap: " + _number(solution["exploitability_gap"])),
                          paragraph("Why: mixing makes the row player harder to exploit. The lower bound is what its mixture guarantees; the upper bound comes from the column mixture. A small gap supports an approximate equilibrium. This applies to two-player zero-sum games. Matrix table shows at most six rows/columns.", small)]
        elif name == "conversion_graph":
            flowables += [paragraph("Best path: " + " -> ".join(map(str, solution["path"]))),
                          _bar(["Initial", "Final"], [solution["initial_amount"], solution["final_amount"]],
                               "Holdings in starting currency (units)"),
                          table([["Initial amount", "Final amount", "Fee per conversion", "Maximum steps"],
                                 [_number(solution["initial_amount"]), _number(solution["final_amount"]),
                                  _number(solution["fee_per_conversion"]), str(solution["max_steps"])]], [110, 110, 130, 100]),
                          paragraph("Why: bounded dynamic programming compares all reachable currencies after each conversion. Keeping the starting holding allows doing nothing if every cycle loses money. Depth, changing prices and slippage are absent from this toy model.", small)]
        else:
            comparison = solution["comparison"]
            flowables += [_bar([row["strategy"] for row in comparison], [row["probability_first"] for row in comparison],
                               "Probability of first place under assumed returns", probability=True),
                          table([["Risk choice", "Expected final score", "Probability first", "Sampling SE"]] +
                                [[row["strategy"], _number(row["expected_final_score"]), _number(row["probability_first"]),
                                  _number(row["probability_first_standard_error"])] for row in comparison], [110, 120, 110, 110]),
                          paragraph("Best expected score: " + solution["best_for_expected_score"] +
                                    "; best probability of first: " + solution["best_for_probability_first"] +
                                    "; trials: " + str(solution["trials"])),
                          paragraph("Why: maximizing average score can choose a different risk level from maximizing the chance of winning. Common random draws compare policies fairly. Sampling SE measures Monte Carlo uncertainty under the assumed distributions; it does not validate those distributions.", small)]
        flowables += [Spacer(1, 8),
                      paragraph("Source: experiments/" + str(record["id"]) + "/result.json | result.puzzles[" + str(puzzles.index(puzzle)) + "]", small),
                      paragraph("Next: verify the actual objective and legal actions, then rerun with official inputs and alternative opponent assumptions.", small)]
    return flowables
