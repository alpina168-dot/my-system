#!/usr/bin/env python3
"""Generate reservation CSV for auction sniping based on target margin.

Input CSV columns:
- listing_id
- title
- url
- format            ("auction" or "buy_now")
- end_at            (ISO-8601, e.g. 2026-04-16T12:34:56+09:00)
- expected_sell_price_jpy
- current_price_jpy

Output CSV columns:
- listing_id
- title
- url
- snipe_at
- max_bid_jpy
- target_margin_rate
- expected_sell_price_jpy
- reason
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Input candidates CSV path")
    parser.add_argument("--output", required=True, help="Output reservation CSV path")
    parser.add_argument("--target-margin", type=float, default=0.30, help="Target margin rate (default: 0.30)")
    parser.add_argument("--sell-fee-rate", type=float, default=0.10, help="Selling fee rate (default: 0.10)")
    parser.add_argument("--purchase-shipping", type=float, default=1200, help="Purchase shipping JPY (default: 1200)")
    parser.add_argument("--sale-shipping", type=float, default=750, help="Sale shipping JPY (default: 750)")
    parser.add_argument("--snipe-seconds", type=int, default=6, help="Seconds before end for snipe (default: 6)")
    parser.add_argument("--reserve-minutes", type=int, default=6, help="Minutes-before-end label for manual reservation (default: 6)")
    parser.add_argument("--bid-unit", type=int, default=100, help="Bid increment unit JPY (default: 100)")
    parser.add_argument(
        "--output-profile",
        choices=["internal", "jp_basic", "aucfan_manual"],
        default="internal",
        help="Output columns profile (default: internal)",
    )
    parser.add_argument(
        "--header-map",
        default="",
        help="Optional JSON file that maps internal keys to custom output headers",
    )
    return parser.parse_args()


def safe_float(value: str) -> float:
    return float(str(value).strip())


def parse_end_at(value: str) -> dt.datetime:
    value = value.strip()
    # Accept both "...Z" and explicit offsets
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return dt.datetime.fromisoformat(value)


def compute_max_bid(
    expected_sell: float,
    target_margin: float,
    sell_fee_rate: float,
    purchase_shipping: float,
    sale_shipping: float,
    bid_unit: int = 100,
) -> int:
    # profit_rate = (sell - sell_fee - sale_shipping - purchase - purchase_shipping) / sell
    # require profit_rate >= target_margin
    # => purchase <= sell*(1 - sell_fee_rate - target_margin) - sale_shipping - purchase_shipping
    raw = expected_sell * (1 - sell_fee_rate - target_margin) - sale_shipping - purchase_shipping
    floored = max(0, math.floor(raw))
    unit = max(1, int(bid_unit))
    return (floored // unit) * unit


def build_row(row: dict[str, str], args: argparse.Namespace) -> dict[str, str] | None:
    listing_format = row.get("format", "").strip().lower()
    if listing_format != "auction":
        return None

    expected_sell = safe_float(row["expected_sell_price_jpy"])
    current_price = safe_float(row["current_price_jpy"])

    max_bid = compute_max_bid(
        expected_sell=expected_sell,
        target_margin=args.target_margin,
        sell_fee_rate=args.sell_fee_rate,
        purchase_shipping=args.purchase_shipping,
        sale_shipping=args.sale_shipping,
        bid_unit=args.bid_unit,
    )

    if max_bid <= 0:
        reason = "max_bid<=0"
    elif current_price > max_bid:
        reason = "current_price_over_max_bid"
    else:
        reason = "ok"

    end_at = parse_end_at(row["end_at"])
    snipe_at = end_at - dt.timedelta(seconds=args.snipe_seconds)

    return {
        "listing_id": row.get("listing_id", ""),
        "title": row.get("title", ""),
        "url": row.get("url", ""),
        "snipe_at": snipe_at.isoformat(),
        "max_bid_jpy": str(max_bid),
        "end_at": end_at.isoformat(),
        "target_margin_rate": str(args.target_margin),
        "expected_sell_price_jpy": str(int(expected_sell)),
        "reason": reason,
        "reserve_minutes": str(args.reserve_minutes),
        "current_price_jpy": str(int(current_price)),
    }



def get_output_profile(profile: str) -> list[tuple[str, str]]:
    if profile == "aucfan_manual":
        return [
            ("url", "商品URL"),
            ("max_bid_jpy", "入札金額(円)"),
            ("reserve_minutes", "入札タイミング(分前)"),
            ("current_price_jpy", "現在価格(円)"),
            ("reason", "判定"),
            ("title", "商品名"),
        ]
    if profile == "jp_basic":
        return [
            ("listing_id", "商品ID"),
            ("title", "商品名"),
            ("url", "URL"),
            ("snipe_at", "予約入札時刻"),
            ("max_bid_jpy", "上限入札額"),
            ("end_at", "終了時刻"),
            ("target_margin_rate", "目標利益率"),
            ("expected_sell_price_jpy", "想定売価"),
            ("reason", "判定理由"),
        ]
    return [
        ("listing_id", "listing_id"),
        ("title", "title"),
        ("url", "url"),
        ("snipe_at", "snipe_at"),
        ("max_bid_jpy", "max_bid_jpy"),
        ("end_at", "end_at"),
        ("target_margin_rate", "target_margin_rate"),
        ("expected_sell_price_jpy", "expected_sell_price_jpy"),
        ("reason", "reason"),
    ]


def load_header_map(path: str) -> dict[str, str]:
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {str(k): str(v) for k, v in data.items()}


def remap_output_row(row: dict[str, str], pairs: list[tuple[str, str]], custom_map: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for source_key, default_header in pairs:
        header = custom_map.get(source_key, default_header)
        out[header] = row.get(source_key, "")
    return out

def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader]

    out_rows = []
    for row in rows:
        out = build_row(row, args)
        if out is not None:
            out_rows.append(out)

    profile_pairs = get_output_profile(args.output_profile)
    custom_map = load_header_map(args.header_map)
    mapped_rows = [remap_output_row(r, profile_pairs, custom_map) for r in out_rows]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        fieldnames = [custom_map.get(src, header) for src, header in profile_pairs]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(mapped_rows)

    print(f"wrote {len(out_rows)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
