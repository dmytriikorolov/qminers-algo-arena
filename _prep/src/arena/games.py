"""Small independently implemented allocation and strategic-game examples.

Each solver states its model. None of these toy game rules are Qminers rules.
"""

import itertools
import hashlib
import json
import math
import random


def _integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(name + " must be an integer >= " + str(minimum))


def _items(costs, rewards, budget):
    _integer(budget, "budget")
    if len(costs) != len(rewards):
        raise ValueError("costs and rewards must have equal lengths")
    for cost in costs:
        _integer(cost, "cost")
    if any(not math.isfinite(value) for value in rewards):
        raise ValueError("rewards must be finite")


def _allocation(indices, costs, rewards, budget):
    spent = sum(costs[index] for index in indices)
    return {"indices": list(indices), "cost": spent,
            "reward": sum(rewards[index] for index in indices), "unused_budget": budget - spent}


def knapsack(costs, rewards, budget):
    """0/1 integer-cost DP, including zero-cost and negative-reward items."""
    _items(costs, rewards, budget)
    if budget > 100000 or (budget + 1) * len(costs) > 2000000:
        raise ValueError("DP exceeds the small-solver budget; use a sparse/optimization solver")
    best = [(0.0, ()) for _ in range(budget + 1)]
    for index, (cost, reward) in enumerate(zip(costs, rewards)):
        for remaining in range(budget, cost - 1, -1):
            previous_reward, previous_indices = best[remaining - cost]
            candidate = previous_reward + reward
            if candidate > best[remaining][0]:
                best[remaining] = (candidate, previous_indices + (index,))
    return _allocation(best[budget][1], costs, rewards, budget)


def knapsack_oracle(costs, rewards, budget):
    _items(costs, rewards, budget)
    if len(costs) > 22:
        raise ValueError("enumeration is limited to 22 items")
    best = _allocation((), costs, rewards, budget)
    for mask in range(1 << len(costs)):
        indices = tuple(index for index in range(len(costs)) if mask & (1 << index))
        candidate = _allocation(indices, costs, rewards, budget)
        if candidate["cost"] <= budget and candidate["reward"] > best["reward"]:
            best = candidate
    return best


def shared_rewards(rewards, probabilities, opponents):
    """Expected reward R/(1+K), K~Binomial(opponents,p), for each option.

    Each opponent independently chooses one option with the supplied probability.
    This computes E[1/(1+K)], rather than replacing K with its expectation.
    """
    _integer(opponents, "opponents")
    if not rewards or len(rewards) != len(probabilities):
        raise ValueError("supply matching nonempty rewards and probabilities")
    if any(not math.isfinite(value) or value < 0 for value in rewards):
        raise ValueError("rewards must be nonnegative finite values")
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in probabilities):
        raise ValueError("probabilities must lie in [0,1]")
    if not math.isclose(sum(probabilities), 1.0, abs_tol=1e-10):
        raise ValueError("opponent choice probabilities must sum to one")
    scores = []
    for reward, probability in zip(rewards, probabilities):
        if probability == 0:
            share = 1.0
        elif probability == 1:
            share = 1.0 / (opponents + 1)
        else:
            share = -math.expm1((opponents + 1) * math.log1p(-probability)) / ((opponents + 1) * probability)
        scores.append(reward * share)
    return {"expected_payoffs": scores, "best_choice": max(range(len(scores)), key=scores.__getitem__)}


def auction(value, bids, rival_max_bids, kind="first_price", tie_probability=0.5):
    """Empirical expected utility for one item and sampled highest competing bid.

    No reserve price. A tied highest bid is won with tie_probability. In all-pay
    auctions our bid is paid even when we lose; second-price pays the rival max.
    """
    if kind not in ("first_price", "second_price", "all_pay"):
        raise ValueError("unknown auction kind")
    if not bids or not rival_max_bids:
        raise ValueError("provide candidate bids and observed/simulated rival maxima")
    if not math.isfinite(value) or value < 0 or not 0 <= tie_probability <= 1:
        raise ValueError("invalid valuation or tie probability")
    if any(not math.isfinite(bid) or bid < 0 for bid in list(bids) + list(rival_max_bids)):
        raise ValueError("bids must be nonnegative and finite")
    utilities = []
    for bid in bids:
        total = 0.0
        for rival in rival_max_bids:
            win = 1.0 if bid > rival else tie_probability if bid == rival else 0.0
            if kind == "all_pay":
                total += win * value - bid
            else:
                payment = rival if kind == "second_price" else bid
                total += win * (value - payment)
        utilities.append(total / len(rival_max_bids))
    best = max(range(len(bids)), key=utilities.__getitem__)
    return {"kind": kind, "bids": list(bids), "expected_utilities": utilities,
            "best_bid": bids[best], "best_utility": utilities[best], "tie_probability": tie_probability}


def zero_sum(payoffs, iterations=10000):
    """Approximate two-player zero-sum equilibrium by fictitious play.

    Row player maximizes payoff; column player minimizes. Returns independent
    lower/upper best-response bounds and their gap, not an unqualified claim of
    an exact equilibrium. Works offline without LP packages.
    """
    _integer(iterations, "iterations", 1)
    if iterations > 1000000:
        raise ValueError("iterations exceed the bounded offline solver limit")
    if not payoffs or not payoffs[0] or any(len(row) != len(payoffs[0]) for row in payoffs):
        raise ValueError("payoff matrix must be nonempty and rectangular")
    if any(not math.isfinite(value) for row in payoffs for value in row):
        raise ValueError("payoffs must be finite")
    row_count, column_count = len(payoffs), len(payoffs[0])
    row_counts, column_counts = [1] * row_count, [1] * column_count
    row_scores = [sum(row) for row in payoffs]
    column_scores = [sum(payoffs[i][j] for i in range(row_count)) for j in range(column_count)]
    for _ in range(iterations):
        # Simultaneous best responses to the history before this iteration.
        row = max(range(row_count), key=row_scores.__getitem__)
        column = min(range(column_count), key=column_scores.__getitem__)
        row_counts[row] += 1
        column_counts[column] += 1
        for i in range(row_count):
            row_scores[i] += payoffs[i][column]
        for j in range(column_count):
            column_scores[j] += payoffs[row][j]
    row_mix = [count / sum(row_counts) for count in row_counts]
    column_mix = [count / sum(column_counts) for count in column_counts]
    lower = min(sum(row_mix[i] * payoffs[i][j] for i in range(row_count)) for j in range(column_count))
    upper = max(sum(column_mix[j] * payoffs[i][j] for j in range(column_count)) for i in range(row_count))
    value = sum(row_mix[i] * column_mix[j] * payoffs[i][j]
                for i in range(row_count) for j in range(column_count))
    return {"row_strategy": row_mix, "column_strategy": column_mix, "value": value,
            "lower_bound": lower, "upper_bound": upper, "exploitability_gap": max(0.0, upper - lower),
            "iterations": iterations, "method": "fictitious_play_approximation"}


def zero_sum_lp(payoffs):
    """Optional SciPy LP solution, with both primal and dual independently solved.

    Importing this module does not require SciPy. Calling this function does.
    Use the explicit `equilibrium_method: lp` demo parameter to select it.
    """
    if not payoffs or not payoffs[0] or any(len(row) != len(payoffs[0]) for row in payoffs):
        raise ValueError("payoff matrix must be nonempty and rectangular")
    if any(not math.isfinite(value) for row in payoffs for value in row):
        raise ValueError("payoffs must be finite")
    try:
        from scipy.optimize import linprog
    except ImportError as exc:
        raise RuntimeError("zero_sum_lp requires optional scipy; use zero_sum for the offline approximation") from exc
    rows, columns = len(payoffs), len(payoffs[0])
    primal = linprog([0.0] * rows + [-1.0],
                     A_ub=[[-payoffs[i][j] for i in range(rows)] + [1.0] for j in range(columns)],
                     b_ub=[0.0] * columns, A_eq=[[1.0] * rows + [0.0]], b_eq=[1.0],
                     bounds=[(0.0, 1.0)] * rows + [(None, None)], method="highs")
    dual = linprog([0.0] * columns + [1.0],
                   A_ub=[list(row) + [-1.0] for row in payoffs],
                   b_ub=[0.0] * rows, A_eq=[[1.0] * columns + [0.0]], b_eq=[1.0],
                   bounds=[(0.0, 1.0)] * columns + [(None, None)], method="highs")
    if not primal.success or not dual.success:
        raise RuntimeError("equilibrium LP failed: " + primal.message + "; " + dual.message)
    row_mix, column_mix = list(map(float, primal.x[:-1])), list(map(float, dual.x[:-1]))
    lower = min(sum(row_mix[i] * payoffs[i][j] for i in range(rows)) for j in range(columns))
    upper = max(sum(column_mix[j] * payoffs[i][j] for j in range(columns)) for i in range(rows))
    gap = upper - lower
    if gap > 1e-7 * max(1.0, max(abs(value) for row in payoffs for value in row)):
        raise RuntimeError("LP returned inconsistent best-response bounds")
    return {"row_strategy": row_mix, "column_strategy": column_mix,
            "value": sum(row_mix[i] * column_mix[j] * payoffs[i][j]
                         for i in range(rows) for j in range(columns)),
            "lower_bound": lower, "upper_bound": upper, "exploitability_gap": max(0.0, gap),
            "method": "scipy_primal_dual_linear_program"}


def convert(rates, start, steps, amount=1.0, fee=0.0):
    """Best conversion path using at most steps edges; repeated currencies legal.

    rates maps a currency to (destination, units_received_per_unit_spent) pairs.
    Each conversion multiplies proceeds by (1-fee). This is a bounded path model,
    with no depth, slippage, or changing rates.
    """
    _integer(steps, "steps")
    if steps > 10000 or not math.isfinite(amount) or amount < 0 or not 0 <= fee < 1:
        raise ValueError("invalid steps, amount, or fee")
    for edges in rates.values():
        if any(not math.isfinite(rate) or rate <= 0 for _, rate in edges):
            raise ValueError("conversion rates must be positive and finite")
    current = {start: (amount, (start,))}
    best_return = current[start]
    for _ in range(steps):
        following = {}
        for source, (units, path) in current.items():
            for destination, rate in rates.get(source, []):
                candidate = units * rate * (1 - fee)
                if not math.isfinite(candidate):
                    raise ValueError("conversion amount overflow")
                if candidate > following.get(destination, (-1, ()))[0]:
                    following[destination] = (candidate, path + (destination,))
        current = following
        if start in current and current[start][0] > best_return[0]:
            best_return = current[start]
    return {"start": start, "initial_amount": amount, "final_amount": best_return[0],
            "path": list(best_return[1]), "max_steps": steps, "fee_per_conversion": fee}


def _tournament_inputs(seed, trials, our_score, rival_score):
    _integer(trials, "trials", 1)
    if trials > 1000000:
        raise ValueError("trials exceed the bounded simulation limit")
    rng = random.Random(seed)
    return {"our_score": our_score, "rival_score": rival_score,
            "rival_return_mean": 5.0, "rival_return_deviation": 5.0,
            "policies": [("safe", 6.0, 1.0), ("moderate", 5.0, 7.0), ("aggressive", 3.0, 20.0)],
            "draws": [(rng.gauss(0, 1), rng.gauss(0, 1)) for _ in range(trials)]}


def _evaluate_tournament(inputs, seed):
    draws = inputs["draws"]
    trials, our_score = len(draws), inputs["our_score"]
    results = []
    for name, mean, deviation in inputs["policies"]:
        scores = [our_score + mean + deviation * z for z, _ in draws]
        wins = sum(score > inputs["rival_score"] + inputs["rival_return_mean"] +
                   inputs["rival_return_deviation"] * rival for score, (_, rival) in zip(scores, draws))
        probability = wins / trials
        results.append({"strategy": name, "expected_final_score": our_score + mean,
                        "sample_mean_final_score": sum(scores) / trials,
                        "probability_first": probability,
                        "probability_first_standard_error": math.sqrt(probability * (1 - probability) / trials),
                        "probability_negative_score": sum(score < 0 for score in scores) / trials})
    return {"comparison": results, "trials": trials, "seed": seed,
            "best_for_expected_score": max(results, key=lambda item: item["expected_final_score"])["strategy"],
            "best_for_probability_first": max(results, key=lambda item: item["probability_first"])["strategy"]}


def tournament_risk(seed=7, trials=5000, our_score=90.0, rival_score=100.0):
    """One-round example: fixed normal return models, common random numbers.

    Objective is probability of finishing ahead, rather than expected score.
    These assumed normal distributions are sensitivity scenarios, not estimates.
    The draws are generated once, then shared across all candidate risk levels.
    """
    return _evaluate_tournament(_tournament_inputs(seed, trials, our_score, rival_score), seed)


def demo(seed=7, **config):
    unknown = set(config) - {"costs", "rewards", "budget", "payoffs", "iterations", "trials", "equilibrium_method"}
    if unknown:
        raise ValueError("unknown games demo parameters: " + ", ".join(sorted(unknown)))
    costs = config.get("costs", [6, 4, 5])
    rewards = config.get("rewards", [11, 8, 9])
    budget = config.get("budget", 10)
    if len(costs) > 22:
        raise ValueError("games demo enumeration is limited to 22 items; use knapsack directly for larger inputs")
    allocation = knapsack(costs, rewards, budget)
    oracle = knapsack_oracle(costs, rewards, budget)
    matrix = config.get("payoffs", [[1, -1], [-1, 1]])
    method = config.get("equilibrium_method", "fictitious_play")
    if method not in ("fictitious_play", "lp"):
        raise ValueError("equilibrium_method must be fictitious_play or lp")
    equilibrium = (zero_sum_lp(matrix) if method == "lp" else
                   zero_sum(matrix, iterations=config.get("iterations", 10000)))
    rng = random.Random(seed)
    rival_bids = [rng.uniform(0, 10) for _ in range(2000)]
    source_inputs = {
        "knapsack": {"costs": costs, "rewards": rewards, "budget": budget},
        "shared_reward": {"rewards": [100, 80], "probabilities": [0.9, 0.1], "opponents": 10},
        "auction": {"value": 10, "bids": [index / 10 for index in range(101)],
                    "rival_max_bids": rival_bids, "kind": "first_price", "tie_probability": 0.5},
        "matrix": matrix,
        "conversion": {"rates": {"A": [("B", 2.0)], "B": [("C", 3.0)], "C": [("A", 0.2)]},
                       "start": "A", "steps": 3, "amount": 1.0, "fee": 0.01},
        "tournament": _tournament_inputs(seed, config.get("trials", 5000), 90.0, 100.0),
    }
    bidding = auction(**source_inputs["auction"])
    shared = shared_rewards(**source_inputs["shared_reward"])
    conversion = convert(**source_inputs["conversion"])
    tournament = _evaluate_tournament(source_inputs["tournament"], seed)
    puzzles = [
        {"name": "knapsack", "statement": "Choose each item at most once; maximize reward within integer budget.",
         "input": {"costs": costs, "rewards": rewards, "budget": budget},
         "solution": allocation, "oracle": oracle},
        {"name": "shared_reward", "statement": "10 independent rivals choose A/B with probabilities 0.9/0.1; rewards 100/80 split equally.",
         "solution": shared},
        {"name": "sealed_bid_auction", "statement": "First-price auction, value 10, highest rival bid uniform on [0,10]; empirical grid search.",
         "solution": bidding},
        {"name": "matrix_game", "statement": "Row maximizes, column minimizes the supplied zero-sum payoff matrix.",
         "input": matrix, "solution": equilibrium},
        {"name": "conversion_graph", "statement": "At most 3 conversions A->B->C->A, one percent fee each; maximize final A.",
         "solution": conversion},
        {"name": "tournament_risk", "statement": "Choose a risk level for one final round while trailing by 10; assumed normal returns.",
         "solution": tournament},
    ]
    return {"family": "games", "synthetic": True, "seed": seed,
            "source": "six stated toy puzzles, not actual Qminers tasks",
            "dataset_fingerprint": hashlib.sha256(json.dumps(
                source_inputs, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest(),
            "dataset_fingerprint_format": "SHA-256 of six-puzzle source data as UTF-8 canonical JSON, including actual rival bid samples and normal draw pairs; optimizer settings excluded",
            "stochastic_data_recipe": "Separate random.Random(seed) streams: 2000 uniform(0,10) rival maxima; trials sequential pairs (gauss(0,1), gauss(0,1)) shared by tournament policies. The fingerprint hashes actual draws, not this recipe.",
            "metrics": {"knapsack_reward": allocation["reward"], "oracle_reward": oracle["reward"],
                        "oracle_agrees": allocation["reward"] == oracle["reward"],
                        "exploitability_gap": equilibrium["exploitability_gap"],
                        "conversion_return": conversion["final_amount"] - conversion["initial_amount"]},
            "puzzles": puzzles,
            "warnings": ["Opponent distributions and utility rules are assumptions; rerun sensitivity scenarios.",
                         "Inspect the equilibrium solver's best-response gap before using its mix."]}
