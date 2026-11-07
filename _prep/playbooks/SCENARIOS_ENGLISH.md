# My Hackathon Decision Book (plain English)

These are **possibilities**, not leaked tasks. The task may have all four themes in one problem.

## First 15 minutes
I read the actual rules, the scoring formula, the input/output contract and the sample submission. I ask: what exactly am I controlling? What is measured? How often can I act? Which data are legal to use? How do we reproduce one official evaluation? I assign one teammate to run the untouched baseline immediately.

## If I receive an order book / simulated exchange
I parse the best bid and ask, calculate the spread and see how inventory changes after fills. I run a no-trade baseline and a very simple market maker. Then I test whether buying after large bid-side imbalance and selling after large ask-side imbalance works **after fees and slippage**. I do not assume a quote gets filled just because the price touches it. I avoid accumulating a huge directional position.

## If I receive a trading game with multiple assets
I check which assets move together. If one asset has a formula from other assets, I compute its implied fair price and compare it with the price I can actually trade. I include fees and limits. I test a simple strategy before attempting neural networks or reinforcement learning.

## If I receive a labelled table (ML)
I inspect the target and the split. I start with a constant prediction, then logistic regression or a simple tree model. I use a time-based validation split when the future must be predicted. I care about the actual scoring metric: accuracy, log loss, PnL, or another rule. I test leakage before trusting high scores.

## If I receive an allocation game / budget game
I write the payoff function with a tiny concrete example. If there are few choices, I enumerate every legal allocation and use the result to test my faster solver. For bigger choices I try dynamic programming or integer programming, depending on constraints. If other teams affect my payoff, I simulate multiple opponent styles and prefer a strategy that is robust to them.

## If I receive an auction
I determine whether we pay our bid or another price, whether bids are sealed or repeated, and what we know about competitors. I estimate the value of winning. I simulate opponent bids and evaluate **profit if we win times the chance of winning**. I verify the rules before using any textbook bidding formula.

## If I receive a shared-reward game
I model that choosing a popular option could split the prize among many players. I simulate opponents who chase the largest reward and opponents who spread their bets. I compare expected payoff and worst-case performance. I never optimize only the prize amount while ignoring the split.

## If I receive a sequential or repeated game
I check what the opponent can observe from our past moves. I keep state explicitly and test fixed, reactive and randomized policies. I look for simple exploitable behavior, then guard against being predictable ourselves.

## If I receive a pure coding problem
I start from a brute-force oracle for small inputs. Then I identify if the task is graph search, shortest path, dynamic programming, sorting, scheduling, linear programming, or a simulation. I implement one correct solution before optimizing. I test edge cases, memory limits, complexity, and the exact submission interface.

## When a strategy wins in local tests
I rerun on new seeds, new time windows and different opponent or execution assumptions. I inspect the losses and compare against the baseline. I never announce an edge based on one favorable synthetic test.

## Last 90 minutes of the competition
I freeze feature work, run official-contract tests, check paths/libraries/CPU/memory/timeouts, preserve the last known good build and submit deliberately. No late untested refactors.
