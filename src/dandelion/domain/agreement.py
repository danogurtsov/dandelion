"""
Inter-rater agreement — pure core (no I/O).

Used to calibrate the membership judge against a human gold set: we trust the judge's precision
numbers only as far as it agrees with humans. Cohen's kappa corrects raw agreement for chance.
"""
from __future__ import annotations


def simple_agreement(a: list[bool], b: list[bool]) -> float:
    """Fraction of labels that match (0..1)."""
    if not a:
        return 1.0
    return round(sum(1 for x, y in zip(a, b, strict=False) if x == y) / len(a), 3)


def cohen_kappa(a: list[bool], b: list[bool]) -> float:
    """
    Cohen's kappa for two binary raters over the same items. 1=perfect, 0=chance, <0=worse.
    Returns 1.0 for empty input, and 1.0 when both raters are constant and identical.
    """
    n = len(a)
    if n == 0:
        return 1.0
    po = sum(1 for x, y in zip(a, b, strict=False) if x == y) / n
    pa1 = sum(1 for x in a if x) / n
    pb1 = sum(1 for y in b if y) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)   # chance agreement
    if pe >= 1.0:                            # both raters constant and identical
        return 1.0 if po >= 1.0 else 0.0
    return round((po - pe) / (1 - pe), 3)
