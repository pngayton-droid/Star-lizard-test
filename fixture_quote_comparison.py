"""Transparent bookmaker quote comparison for full-win and Asian settlement markets.

No claim of a validated model edge. Inputs must be user-supplied observed odds.
"""
from math import isfinite

def compare_quote(decimal_odds, win_stake, lose_stake, push_stake=0.0, commission=0.0):
    """Expected net profit per unit staked under provided research probabilities.

    A full win earns odds-1; an Asian half win is encoded in win_stake as
    its winning stake fraction. Push fraction earns zero. Commission applies
    to positive net winnings only (simplified exchange convention).
    """
    odds=float(decimal_odds)
    win=float(win_stake)
    loss=float(lose_stake)
    push=float(push_stake)
    fee=float(commission)
    if not all(isfinite(v) for v in (odds,win,loss,push,fee)):
        raise ValueError("All inputs must be finite")
    if odds<=1 or not 0<=fee<1:
        raise ValueError("Decimal odds must exceed 1; commission must be in [0,1)")
    if min(win,loss,push)<0 or win+loss+push>1.0000001:
        raise ValueError("Settlement fractions must be nonnegative and sum to at most one")
    if win+loss+push<0.999:
        raise ValueError("Settlement fractions do not cover enough probability mass")
    net=(odds-1)*(1-fee)*win-loss
    breakeven=1+loss/((1-fee)*win) if win>0 else None
    return {"quoted_decimal":odds,"break_even_decimal":breakeven,
            "expected_roi":net,"expected_profit_per_unit":net,
            "commission":fee,"unmodelled_mass":max(0.0,1-win-loss-push)}
