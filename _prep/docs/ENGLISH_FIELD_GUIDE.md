# Field guide and learning priorities

The complete supplied guide, including numeric examples and twenty questions/answers, is preserved in [Markdown](../preparation/ENGLISH_FIELD_GUIDE.md) and [10-page PDF](../preparation/ENGLISH_FIELD_GUIDE.pdf). Tonight's six generated cards are `QUICK_CARDS.pdf`.

The guide's original statement that official rules were inaccessible is historical. We have now read the published rules; use [COMPETITION_RULES.md](COMPETITION_RULES.md) for current verified details and unresolved Technical Rules.

Before the event, understand these by running the examples:

1. **An order is not a fill.** A limit buy at 100 limits the price; it does not guarantee an execution. Pending and cancelling orders still carry risk.
2. **A position is a risk, not booked profit.** Buying two at 100 reduces cash by 200; marking them at 101 gives marked PnL 2 before fees. Liquidation may pay the bid, below the mark.
3. **Chronology is necessary, not sufficient.** Training on earlier rows does not fix a feature copied from a future result. Check when each field became available.
4. **The objective changes the strategy.** Expected final score and probability of finishing first can favour different risk levels. Run the six game examples.
5. **An exact tiny solution is valuable.** Enumerated knapsack/graph results test a faster algorithm independently. A fast wrong answer has no value.
6. **A mock score is conditional.** In our market simulation passive fills assume front-of-queue priority. A ranking can change under the real exchange.

Start with `arena baseline configs/market.json`, then `configs/ml.json`, then `arena optimize configs/games.json`. Read the relevant source alongside the actual output. Use `arena report ID --pdf` to turn one saved run into a readable study sheet.
