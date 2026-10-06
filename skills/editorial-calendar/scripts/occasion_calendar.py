#!/usr/bin/env python3
"""Lịch dịp lễ US/UK và ngày xuất bản/cập nhật nên có cho bài theo mùa. Chỉ dùng thư viện chuẩn.

Ngày lễ được TÍNH bằng quy tắc (không gõ tay, không lấy từ kết quả tìm kiếm) vì ngày của US và UK khác nhau:
  * Mother's Day US: Chủ nhật thứ hai của tháng 5.  Mothering Sunday UK: 3 tuần trước Easter (Chủ nhật).
  * Father's Day (cả US và UK): Chủ nhật thứ ba của tháng 6.
  * Thanksgiving: thứ Năm thứ tư của tháng 11; Black Friday = hôm sau; Cyber Monday = thứ Hai sau Thanksgiving.
  * Easter: thuật toán Gregorian (Meeus/Jones/Butcher).
Không có Remembrance, bank holiday: ngày bank holiday phụ thuộc quy tắc "ngày bù"; lấy từ https://www.gov.uk/bank-holidays.

Chạy:
    occasion_calendar.py --year 2027 --market both --out outputs
    occasion_calendar.py --year 2027 --topic-map outputs/topic-map.csv --out outputs   (thêm seasonal-plan.csv)

Số tuần "lead time" mặc định (12 tuần cho bài mới, 6 tuần cho bài cập nhật) là QUY ƯỚC ngành, không phải
hướng dẫn của Google (Google không công bố thời gian index/xếp hạng). Hãy hiệu chỉnh bằng seasonality
của chính site (Google Search Console, Google Trends).
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


# key, nhãn, thị trường, quy tắc, ghi chú
OCCASIONS = [
    ("new-year", "New Year's Eve", ("us", "uk"), ("fixed", 12, 31), ""),
    ("valentines-day", "Valentine's Day", ("us", "uk"), ("fixed", 2, 14), "Cần chốt hạn đặt hàng với vận hành trước khi viết 'order by'."),
    ("st-patricks-day", "St. Patrick's Day", ("us", "uk"), ("fixed", 3, 17), ""),
    ("easter", "Easter Sunday", ("us", "uk"), ("easter", 0), ""),
    ("mothers-day", "Mother's Day (US)", ("us",), ("nth", 5, SUN, 2), "Cần chốt hạn đặt hàng với vận hành trước khi viết 'order by'."),
    ("mothers-day", "Mothering Sunday (UK)", ("uk",), ("easter", -21), "Người Anh dùng cả 'Mother's Day' lẫn 'Mothering Sunday'; kiểm tra volume từng cụm."),
    ("fathers-day", "Father's Day", ("us", "uk"), ("nth", 6, SUN, 3), "Cần chốt hạn đặt hàng với vận hành trước khi viết 'order by'."),
    ("independence-day", "Fourth of July", ("us",), ("fixed", 7, 4), "Chỉ US."),
    ("halloween", "Halloween", ("us", "uk"), ("fixed", 10, 31), ""),
    ("bonfire-night", "Bonfire Night", ("uk",), ("fixed", 11, 5), "Chỉ UK."),
    ("thanksgiving", "Thanksgiving", ("us",), ("nth", 11, THU, 4), "Chỉ US."),
    ("black-friday", "Black Friday", ("us", "uk"), ("after", "thanksgiving", 1), "Giá/ưu đãi phải do team thương mại xác nhận; không tự bịa."),
    ("cyber-monday", "Cyber Monday", ("us", "uk"), ("after", "thanksgiving", 4), "Giá/ưu đãi phải do team thương mại xác nhận; không tự bịa."),
    ("christmas", "Christmas Day", ("us", "uk"), ("fixed", 12, 25), "Cần chốt hạn đặt hàng với vận hành trước khi viết 'order by'."),
    ("graduation", "Graduation season (cửa sổ, xấp xỉ)", ("us", "uk"), ("window", 5, 1), "XẤP XỈ: kiểm tra bằng Google Trends/GSC."),
    ("back-to-school", "Back to school (cửa sổ, xấp xỉ)", ("us", "uk"), ("window", 8, 1), "XẤP XỈ: US thường sớm hơn UK; kiểm tra bằng Google Trends/GSC."),
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
        if not season or t.get("role") == "skip":
            continue
        mk = t.get("market", "us")
        mk = "us" if mk in ("all", "") else mk
        occ = sorted(by_key.get((mk, season), []), key=lambda r: r["date"])
        upcoming = next((o for o in occ if dt.date.fromisoformat(o["date"]) >= today), None) or (occ[-1] if occ else None)
        base = {"planned_slug": t["planned_slug"], "post_type": t["post_type"], "role": t["role"], "season": season, "market": mk}
        if upcoming is None:
            plan.append({**base, "event_date": "", "publish_new_by": "", "refresh_existing_by": "", "days_to_publish_by": "",
                         "status": "no_calendar_rule",
                         "note": f"Chưa có quy tắc lịch cho '{season}' ở thị trường {mk}: tự đặt ngày hoặc thêm vào OCCASIONS."})
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
    ap.add_argument("--year", type=int, action="append", help="năm cần tính (lặp lại để thêm); mặc định năm nay và năm sau")
    ap.add_argument("--market", choices=["us", "uk", "both"], default="both")
    ap.add_argument("--lead-new", type=int, default=12, help="số tuần trước sự kiện để xuất bản bài MỚI (quy ước, mặc định 12)")
    ap.add_argument("--lead-refresh", type=int, default=6, help="số tuần trước sự kiện để CẬP NHẬT bài cũ (quy ước, mặc định 6)")
    ap.add_argument("--today", help="ngày hiện tại YYYY-MM-DD (mặc định: hôm nay), dùng để tính overdue/due_soon")
    ap.add_argument("--topic-map", help="topic-map.csv: thêm seasonal-plan.csv cho các bài có season")
    ap.add_argument("--out", default="outputs")
    args = ap.parse_args(argv)

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    years = args.year or [today.year, today.year + 1]
    markets = ["us", "uk"] if args.market == "both" else [args.market]
    cal = calendar_rows(years, markets, args.lead_new, args.lead_refresh, today)
    os.makedirs(args.out, exist_ok=True)
    write_csv(os.path.join(args.out, "occasion-calendar.csv"), cal)
    lines = ["# Lịch dịp lễ US/UK", "", f"Tính ngày: {today.isoformat()}. Lead time: bài mới {args.lead_new} tuần, "
             f"cập nhật {args.lead_refresh} tuần (quy ước, hãy hiệu chỉnh bằng GSC/Trends).", "",
             "| Năm | TT | Dịp | Ngày | Thứ | Xuất bản bài mới trước | Cập nhật bài cũ trước | Trạng thái | Ghi chú |", "|---|---|---|---|---|---|---|---|---|"]
    for r in cal:
        lines.append(f"| {r['year']} | {r['market']} | {r['occasion']} | {r['date']} | {r['weekday']} | {r['publish_new_by']} | "
                     f"{r['refresh_existing_by']} | {r['new_status']} / {r['refresh_status']} | {r['notes']} |")
    with open(os.path.join(args.out, "occasion-calendar.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    msg = f"{len(cal)} dòng lịch ({', '.join(map(str, years))}; {args.market})"
    if args.topic_map:
        with open(args.topic_map, encoding="utf-8-sig", newline="") as fh:
            topic_rows = list(csv.DictReader(fh))
        plan = seasonal_plan(topic_rows, cal, today, args.lead_new, args.lead_refresh)
        write_csv(os.path.join(args.out, "seasonal-plan.csv"), plan)
        counts: dict[str, int] = {}
        for p in plan:
            counts[p["status"]] = counts.get(p["status"], 0) + 1
        msg += f" | {len(plan)} bài theo mùa: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(msg)
    print(f"Đã ghi vào: {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
