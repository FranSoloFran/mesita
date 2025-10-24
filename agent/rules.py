def signal_ars_to_usd(implied, mep_ref_a2u, operable_ars, min_notional, thresh):
    if mep_ref_a2u is None or operable_ars < min_notional: return False
    return implied <= mep_ref_a2u * (1 - thresh)

def signal_usd_to_ars(implied_rev, mep_ref_u2a, operable_ars, min_notional, thresh):
    if mep_ref_u2a is None or operable_ars < min_notional: return False
    return implied_rev >= mep_ref_u2a * (1 + thresh)
