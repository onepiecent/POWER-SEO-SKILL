#!/usr/bin/env python3
"""US/UK holiday calendar and the publish/refresh dates to aim for with seasonal posts. Standard library only.

Holiday dates are COMPUTED by rule (not typed by hand and not taken from search results) because US and UK dates differ:
  * US Mother's Day: second Sunday of May.  UK Mothering Sunday: three weeks before Easter (a Sunday).
  * Father's Day (US and UK): third Sunday of June.
  * Thanksgiving: fourth Thursday of November; Black Friday = the next day; Cyber Monday = the Monday after Thanksgiving.
  * Easter: Gregorian algorithm (Meeus/Jones/Butcher).
Remembrance and bank holidays are not included: bank holiday dates depend on "substitute day" rules; take them from https://www.gov.uk/bank-holidays.

Usage:
    occasion_calendar.py --year 2027 --market both --out outputs
    occasion_calendar.py --year 2027 --topic-map outputs/topic-map.csv --out outputs   (adds seasonal-plan.csv)

The default lead times (12 weeks for new posts, 6 weeks for refreshing old ones) are an industry CONVENTION, not
Google guidance (Google does not publish indexing or ranking times). Calibrate them with the site's own seasonality
(Google Search Console, Google Trends).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys

MON, THU, SUN = 0, 3, 6


def nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    first = dt.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + dt.timedelta(days=offset + 7 * (n - 1))


def easter(year: int) -> dt.date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


# key, label, markets, rule, note
OCCASIONS = [
    ("new-year", "New Year's Eve", ("us", "uk"), ("fixed", 12, 31), ""),
    ("valentines-day", "Valentine's Day", ("us", "uk"), ("fixed", 2, 14), "Confirm the order deadline with operations before writing 'order by'."),
    ("st-patricks-day", "St. Patrick's Day", ("us", "uk"), ("fixed", 3, 17), ""),
    ("easter", "Easter Sunday", ("us", "uk"), ("easter", 0), ""),
    ("mothers-day", "Mother's Day (US)", ("us",), ("nth", 5, SUN, 2), "Confirm the order deadline with operations before writing 'order by'."),
    ("mothers-day", "Mothering Sunday (UK)", ("uk",), ("easter", -21), "British readers use both 'Mother's Day' and 'Mothering Sunday'; check the volume of each cluster."),
    ("fathers-day", "Father's Day", ("us", "uk"), ("nth", 6, SUN, 3), "Confirm the order deadline with operations before writing 'order by'."),
    ("independence-day", "Fourth of July", ("us",), ("fixed", 7, 4), "US only."),
    ("halloween", "Halloween", ("us", "uk"), ("fixed", 10, 31), ""),
    ("bonfire-night", "Bonfire Night", ("uk",), ("fixed", 11, 5), "UK only."),
    ("thanksgiving", "Thanksgiving", ("us",), ("nth", 11, THU, 4), "US only."),
    ("black-friday", "Black Friday", ("us", "uk"), ("after", "thanksgiving", 1), "Prices and offers must be confirmed by the commercial team; never invent them."),
    ("cyber-monday", "Cyber Monday", ("us", "uk"), ("after", "thanksgiving", 4), "Prices and offers must be confirmed by the commercial team; never invent them."),
    ("christmas", "Christmas Day", ("us", "uk"), ("fixed", 12, 25), "Confirm the order deadline with operations before writing 'order by'."),
    ("graduation", "Graduation season (window, approximate)", ("us", "uk"), ("window", 5, 1), "APPROXIMATE: check with Google Trends/GSC."),
    ("back-to-school", "Back to school (window, approximate)", ("us", "uk"), ("window", 8, 1), "APPROXIMATE: the US usually starts earlier than the UK; check with Google Trends/GSC."),
]
ALIAS = {"black-friday-cyber": "black-friday"}


def occurrence(rule: tuple, year: int) -> dt.date:
    kind = rule[0]
    if kind == "fixed":
        return dt.date(year, rule[1], rule[2])
    if kind == "nth":
        return nth_weekday(year, rule[1], rule[2], rule[3])
    if kind == "easter":
        return easter(year) + dt.timedelta(days=rule[1])
    if kind == "window":
        return dt.date(year, rule[1], rule[2])
    if kind == "after":
        return nth_weekday(year, 11, THU, 4) + dt.timedelta(days=rule[2])
    raise ValueError(rule)


def status(deadline: dt.date, today: dt.date) -> str:
    days = (deadline - today).days
    if days < 0:
        return "overdue"
    return "due_soon" if days <= 14 else "upcoming"


def calendar_rows(years: list[int], markets: list[str], lead_new: int, lead_refresh: int, today: dt.date) -> list[dict]:
    rows = []
    for y in years:
        for key, label, mks, rule, note in OCCASIONS:
            for mk in mks:
                if mk not in markets:
                    continue
                d = occurrence(rule, y)
                new_by = d - dt.timedelta(weeks=lead_new)
                ref_by = d - dt.timedelta(weeks=lead_refresh)
                rows.append({"year": y, "market": mk, "occasion_key": key, "occasion": label, "date": d.isoformat(),
                             "weekday": d.strftime("%A"), "publish_new_by": new_by.isoformat(),
                             "refresh_existing_by": ref_by.isoformat(), "new_status": status(new_by, today),
                             "refresh_status": status(ref_by, today),
                             "date_type": "window_start" if rule[0] == "window" else "event", "notes": note})
    return sorted(rows, key=lambda r: (r["date"], r["market"]))


def seasonal_plan(topic_rows: list[dict], cal: list[dict], today: dt.date, lead_new: int, lead_refresh: int) -> list[dict]:
    by_key: dict[tuple, list[dict]] = {}
    for r in cal:
        by_key.setdefault((r["market"], r["occasion_key"]), []).append(r)
    plan = []
    for t in topic_rows:
        season = ALIAS.get(t.get("season", ""), t.get("season", ""))
        if not season or t.get("role") in ("skip", "merged", "backlog") or not t.get("planned_slug"):
            continue  # merged clusters are covered by the post they were merged into
        mk = t.get("market", "us")
        mk = "us" if mk in ("all", "") else mk
        occ = sorted(by_key.get((mk, season), []), key=lambda r: r["date"])
        upcoming = next((o for o in occ if dt.date.fromisoformat(o["date"]) >= today), None) or (occ[-1] if occ else None)
        base = {"planned_slug": t["planned_slug"], "post_type": t["post_type"], "role": t["role"], "season": season, "market": mk}
        if upcoming is None:
            plan.append({**base, "event_date": "", "publish_new_by": "", "refresh_existing_by": "", "days_to_publish_by": "",
                         "status": "no_calendar_rule",
                         "note": f"No calendar rule for '{season}' in market {mk}: set a date by hand or add it to OCCASIONS."})
            continue
        d = dt.date.fromisoformat(upcoming["date"])
        new_by, ref_by = d - dt.timedelta(weeks=lead_new), d - dt.timedelta(weeks=lead_refresh)
        plan.append({**base, "event_date": upcoming["date"], "publish_new_by": new_by.isoformat(),
                     "refresh_existing_by": ref_by.isoformat(), "days_to_publish_by": (new_by - today).days,
                     "status": status(new_by, today), "note": upcoming["notes"]})
    plan.sort(key=lambda r: (r["event_date"] or "9999", r["planned_slug"]))
    return plan


def write_csv(path: str, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        if rows:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, action="append", help="year to compute (repeat to add more); default: this year and next")
    ap.add_argument("--market", choices=["us", "uk", "both"], default="both")
    ap.add_argument("--lead-new", type=int, default=12, help="weeks before the event to publish a NEW post (convention, default 12)")
    ap.add_argument("--lead-refresh", type=int, default=6, help="weeks before the event to REFRESH an existing post (convention, default 6)")
    ap.add_argument("--today", help="current date YYYY-MM-DD (default: today), used to compute overdue/due_soon")
    ap.add_argument("--topic-map", help="topic-map.csv: also write seasonal-plan.csv for the posts that have a season")
    ap.add_argument("--out", default="outputs")
    args = ap.parse_args(argv)

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    years = args.year or [today.year, today.year + 1]
    markets = ["us", "uk"] if args.market == "both" else [args.market]
    cal = calendar_rows(years, markets, args.lead_new, args.lead_refresh, today)
    os.makedirs(args.out, exist_ok=True)
    write_csv(os.path.join(args.out, "occasion-calendar.csv"), cal)
    lines = ["# US/UK holiday calendar", "", f"Computed on: {today.isoformat()}. Lead time: new posts {args.lead_new} weeks, "
             f"refreshes {args.lead_refresh} weeks (convention; calibrate with GSC/Trends).", "",
             "| Year | Market | Occasion | Date | Weekday | Publish new post by | Refresh old post by | Status | Notes |", "|---|---|---|---|---|---|---|---|---|"]
    for r in cal:
        lines.append(f"| {r['year']} | {r['market']} | {r['occasion']} | {r['date']} | {r['weekday']} | {r['publish_new_by']} | "
                     f"{r['refresh_existing_by']} | {r['new_status']} / {r['refresh_status']} | {r['notes']} |")
    with open(os.path.join(args.out, "occasion-calendar.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    msg = f"{len(cal)} calendar rows ({', '.join(map(str, years))}; {args.market})"
    if args.topic_map:
        with open(args.topic_map, encoding="utf-8-sig", newline="") as fh:
            topic_rows = list(csv.DictReader(fh))
        plan = seasonal_plan(topic_rows, cal, today, args.lead_new, args.lead_refresh)
        write_csv(os.path.join(args.out, "seasonal-plan.csv"), plan)
        counts: dict[str, int] = {}
        for p in plan:
            counts[p["status"]] = counts.get(p["status"], 0) + 1
        msg += f" | {len(plan)} seasonal posts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(msg)
    print(f"Written to: {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
