#!/usr/bin/env python3
"""Keyword difficulty against the site's reach: how much of a keyword's volume the blog can realistically win.
Standard library only.

A high-volume keyword the site cannot rank on page one for brings nothing, so the plan ranks keywords by their
winnable volume, not their raw volume:

    winnable = (volume + variant volume) x fit(KD)
    fit(KD)  = 1                                  when KD <= reach     ('easy' for this site)
             = 1 - (KD - reach) / SPAN, >= FLOOR  above the reach      ('stretch' up to reach + 15, then 'hard')
             = UNKNOWN_FIT                        when the tool gave no KD (usually too little data: a long tail)

The reach is the KD the site can win with a good post and its internal links, in this order:
  1. --site-kd N (the SEO's own judgement of the domain);
  2. measured: the 75th percentile KD of the keywords the export says the site already ranks top 10 for (a Semrush or
     Ahrefs organic-positions export of the site: Position + Keyword Difficulty columns), when there are >= 20 of them;
  3. DEFAULT_REACH = 30: the start of Semrush's 'possible' band (KD 0-14 very easy, 15-29 easy, 30-49 possible,
     50-69 difficult, 70-84 very difficult, 85-100 extremely difficult [Tool documentation: Semrush KB]).
Semrush's Personal Keyword Difficulty (PKD) already measures the difficulty for the site's own domain, so a PKD is
compared with PKD_REACH = 49 (the end of the 'possible' band) instead. The curve, the span and the defaults are
internal heuristics [Convention]; Ahrefs KD uses another scale, so pass --site-kd with Ahrefs data.
"""
from __future__ import annotations

DEFAULT_REACH = 30.0
PKD_REACH = 49.0
SPAN = 30.0          # KD points above the reach at which a keyword is practically out of reach
FLOOR = 0.05         # ... it still keeps a little: a strong post can surprise
UNKNOWN_FIT = 0.8    # no KD in the export: a long tail is usually easy, but nothing proves it
STRETCH = 15.0       # 'stretch' up to reach + 15: a good post plus internal links can get there
MIN_MEASURED = 20


def is_personal(kd_src: str) -> bool:
    return (kd_src or "").endswith(":pkd")


class KdModel:
    def __init__(self, reach: float = DEFAULT_REACH, source: str = "default"):
        self.reach, self.source = float(reach), source

    def reach_for(self, kd_src: str = "") -> float:
        return PKD_REACH if is_personal(kd_src) else self.reach

    def fit(self, kd, kd_src: str = "") -> float:
        if kd is None or kd == "":
            return UNKNOWN_FIT
        gap = float(kd) - self.reach_for(kd_src)
        return 1.0 if gap <= 0 else max(FLOOR, 1.0 - gap / SPAN)

    def label(self, kd, kd_src: str = "") -> str:
        if kd is None or kd == "":
            return "unknown"
        gap = float(kd) - self.reach_for(kd_src)
        return "easy" if gap <= 0 else "stretch" if gap <= STRETCH else "hard"

    def winnable(self, volume: float, kd, kd_src: str = "") -> float:
        return float(volume or 0) * self.fit(kd, kd_src)

    def describe(self) -> str:
        return (f"site reach KD {self.reach:g} ({self.source}); a Personal KD (PKD) is compared with {PKD_REACH:g}; "
                f"fit falls to {FLOOR:g} at reach + {SPAN:g}; no KD counts {UNKNOWN_FIT:g}")


def measure_reach(points: list[tuple[float, float]]) -> tuple[float, int] | None:
    """(75th percentile KD, n) of the (position, KD) pairs ranked top 10, or None with fewer than MIN_MEASURED."""
    kds = sorted(kd for pos, kd in points if pos is not None and kd is not None and 0 < pos <= 10)
    if len(kds) < MIN_MEASURED:
        return None
    return kds[min(len(kds) - 1, int(0.75 * len(kds)))], len(kds)


def build_model(site_kd: float | None, points: list[tuple[float, float]]) -> KdModel:
    if site_kd is not None:
        return KdModel(site_kd, "--site-kd")
    measured = measure_reach(points)
    if measured:
        return KdModel(measured[0], f"measured: 75th percentile KD of {measured[1]} keywords the site ranks top 10 for")
    return KdModel(DEFAULT_REACH, "default: no --site-kd and no ranking positions in the export")
