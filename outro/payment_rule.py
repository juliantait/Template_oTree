import random
from typing import Iterable, List, Sequence, Tuple


RoundPayoff = Tuple[int, float]


def select_random_payouts(round_payoffs: Sequence[RoundPayoff], payment_num_rewarded: int) -> List[RoundPayoff]:
    """
    Payment rule: pick up to ``payment_num_rewarded`` random (round, payoff) pairs to pay out.
    Expects an ordered list of tuples and returns the sampled subset.

    Example incoming vector (round_payoffs):
        # e.g. [(1, 24.5), (2, 75.0), (3, 16.0), (4, 97.2), (5, 53.5)]

    Example output (if payment_num_rewarded = 2):
        # e.g. [(3, 16.0), (5, 53.5)]
    """
    if not round_payoffs or payment_num_rewarded <= 0:
        return []

    count = min(len(round_payoffs), payment_num_rewarded)
    chosen_indices = random.sample(range(len(round_payoffs)), count)
    return [round_payoffs[idx] for idx in chosen_indices]
