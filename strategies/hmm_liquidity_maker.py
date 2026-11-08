"""Two-state causal HMM liquidity filter; no pretrained historical weights.

Hand-set Gaussian emission priors on log spread and log event rate are
updated online. Only completed seconds feed the filter.
"""
import math
import strategies.full_two_sided as base


class HMMLiquidityMaker(base.FullTwoSidedStrategy):
    def __init__(self, power=2, cutoff=None):
        super().__init__()
        self.power = power
        self.cutoff = cutoff
        self.probability = .1
        self.means = [[math.log(1.08), math.log(380)], [math.log(1.8), math.log(500)]]
        self.variances = [[.04, .025], [.16, .04]]
        self.second = None
        self.events = 0
        self.spread_sum = 0

    def on_order_book_change(self, snapshot, trades):
        bid, _ = base.market_best(snapshot.bids)
        ask, _ = base.market_best(snapshot.asks)
        if bid is None or ask is None:
            return
        second = snapshot.timestamp_us // 1000000
        if self.second is not None and second > self.second and self.events:
            x = [math.log(self.spread_sum/self.events), math.log(self.events/max(1,second-self.second))]
            prior = .02 + .96*self.probability
            likelihoods = []
            for mean, variance in zip(self.means,self.variances):
                likelihoods.append(sum(-.5*(math.log(v)+(a-m)**2/v) for a,m,v in zip(x,mean,variance)))
            odds = math.log(prior/(1-prior))+likelihoods[1]-likelihoods[0]
            self.probability = 1/(1+math.exp(-max(-40,min(40,odds))))
            for state, weight in enumerate([1-self.probability,self.probability]):
                rate = .005*weight
                for j in range(2):
                    error = x[j]-self.means[state][j]
                    self.means[state][j] += rate*error
                    self.variances[state][j] = max(.01,(1-rate)*self.variances[state][j]+rate*error*error)
            new_limit = int(100*(1-self.probability)**self.power)
            if self.cutoff is not None:
                new_limit = 100 if self.probability < self.cutoff else 0
            if new_limit < self._limit:
                for oid, order in self._orders.items():
                    if not order[3]:
                        self.cancel_order(oid)
                        order[3] = True
            self._limit = new_limit
            self.events = self.spread_sum = 0
        self.second = second
        self.events += 1
        self.spread_sum += ask-bid
        super().on_order_book_change(snapshot,trades)
