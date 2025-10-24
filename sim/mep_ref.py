from collections import deque
import math

class MEPRef:
    def __init__(self, window=120):
        self.a = deque(maxlen=window)
        self.b = deque(maxlen=window)

    @staticmethod
    def _gmean(xs):
        xs = [x for x in xs if x and x > 0]
        if not xs: return None
        return math.exp(sum(map(math.log, xs))/len(xs))

    def update(self, ask_peso_al30, bid_usd_al30d, bid_peso_al30, ask_usd_al30d):
        if ask_peso_al30>0 and bid_usd_al30d>0: self.a.append(ask_peso_al30 / bid_usd_al30d)
        if bid_peso_al30>0 and ask_usd_al30d>0: self.b.append(bid_peso_al30 / ask_usd_al30d)

    @property
    def mep_ref_ars_to_usd(self): return self._gmean(self.a)
    @property
    def mep_ref_usd_to_ars(self): return self._gmean(self.b)
