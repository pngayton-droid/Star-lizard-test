"""Shared, side-effect-free decimal-odds comparison arithmetic."""
from math import sqrt

def wilson_interval(hits, n, z=1.959963984540054):
    if not isinstance(n,int) or n<=0 or not isinstance(hits,int) or hits<0 or hits>n:
        raise ValueError("Expected 0 <= hits <= n with n > 0")
    p=hits/n
    denominator=1+z*z/n
    centre=(p+z*z/(2*n))/denominator
    half=z*sqrt(p*(1-p)/n+z*z/(4*n*n))/denominator
    return max(0,centre-half),min(1,centre+half)

def quote_comparison(hits,n,decimal_odds,commission_percent=0):
    if not 1<decimal_odds<=1000:
        raise ValueError("Decimal odds must be greater than 1 and at most 1000")
    if not 0<=commission_percent<=30:
        raise ValueError("Commission must be between 0 and 30 percent")
    lower,upper=wilson_interval(hits,n)
    observed=hits/n
    win_profit=(decimal_odds-1)*(1-commission_percent/100)
    threshold=1/(1+win_profit)
    def estimated_return(probability):
        return probability*win_profit-(1-probability)
    return {"observed_rate":observed,"lower_rate":lower,"upper_rate":upper,
            "break_even_rate":threshold,"historical_return":estimated_return(observed),
            "lower_bound_return":estimated_return(lower),
            "upper_bound_return":estimated_return(upper)}
