"""cost — show cost of resources matching a tag, over the last N days.

WHAT YOU MUST BUILD
-------------------
A function that:
  1. Queries Cost Explorer (`ce.get_cost_and_usage`) for the last N days
  2. Filters by a tag (e.g. Application=HealthBot)
  3. Groups by SERVICE dimension
  4. Sums per-service costs across the date range
  5. Prints services sorted descending by cost, plus a TOTAL row

GOTCHAS
-------
- Cost data lags 8–24h. If --days 1 returns nothing, try --days 7.
- Tag filter requires that you have ACTIVATED cost allocation tags in Billing.
- Amount field is a STRING in the response — cast to float before summing.
"""
import boto3
from botocore.exceptions import ClientError
from collections import defaultdict
from datetime import date, timedelta

from commands._common import parse_kv


def run(args):
    """Entry point."""
    key, val = parse_kv(args.tag)
    end = date.today()
    start = end - timedelta(days=args.days)

    ce = boto3.client("ce")
    try:
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            Filter={"Tags": {"Key": key, "Values": [val]}},
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
    except ClientError as e:
        err = e.response.get("Error", {})
        code = err.get("Code", "Unknown")
        msg = err.get("Message", str(e))
        print(f"AWS error [{code}]: {msg}")
        return

    totals = defaultdict(float)
    for day in resp.get("ResultsByTime", []):
        for group in day.get("Groups", []):
            service = group["Keys"][0]
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            totals[service] += amount

    print(f"Cost for {key}={val} over last {args.days} days ({start} → {end}):")
    print("-" * 60)
    if not totals:
        print("  (no cost data — try increasing --days or check that the tag is activated as a cost allocation tag)")
        print("-" * 60)
        print(f"  {'TOTAL':<42} ${0.0:>7.2f}")
        return

    for service, amount in sorted(totals.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {service:<42} ${amount:>7.2f}")
    print("-" * 60)
    grand = sum(totals.values())
    print(f"  {'TOTAL':<42} ${grand:>7.2f}")
