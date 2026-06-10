"""Operational monitor for country-level internet disruptions via Cloudflare Radar.

Runs the same detector as the notebook but headless, compares its findings
against a JSON state file, and prints only what has changed since last run —
suitable for cron + email/Slack alerting. Works for any country: pass the
ISO alpha-2 code with --location (e.g. US, BR, IR, KE, IN, RU, EG).

Usage:
    export CLOUDFLARE_API_TOKEN=...        # or set on Windows: $env:CLOUDFLARE_API_TOKEN
    python monitor.py --location IR                       # 28d window
    python monitor.py --location BR --range 90d           # custom window
    python monitor.py --location IN --state ./in_state.json --quiet

Exit codes:
    0  ran successfully, no new disruption windows since last run
    2  ran successfully, NEW disruption windows detected (alert-worthy)
    1  unexpected error (network, auth, missing token, etc.)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

BASE_URL = "https://api.cloudflare.com/client/v4/radar"

WINDOW = 24        # 1-day rolling baseline at 1h resolution (annotation filter cleans false positives)
DROP_RATIO = 0.50
Z_THRESHOLD = 3.5


def radar_get(token: str, path: str, params: dict | None = None) -> dict:
    resp = requests.get(
        f"{BASE_URL}/{path.lstrip('/')}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code} for {path}: {resp.text[:300]}")
    payload = resp.json()
    if not payload.get("success", False):
        raise RuntimeError(f"API error for {path}: {payload.get('errors')}")
    return payload["result"]


def fetch_http(token: str, location: str, date_range: str) -> pd.DataFrame:
    res = radar_get(token, "http/timeseries", {
        "location": location,
        "dateRange": date_range,
        "aggInterval": "1h",
    })
    serie = res.get("serie_0") or next(
        (v for k, v in res.items() if k.startswith("serie")), None)
    if not serie:
        raise RuntimeError("No HTTP timeseries in response.")
    return pd.DataFrame(
        {"http_requests": pd.to_numeric(serie["values"], errors="coerce")},
        index=pd.to_datetime(serie["timestamps"], utc=True),
    ).sort_index()


def fetch_outages(token: str, location: str) -> list[dict]:
    res = radar_get(token, "annotations/outages", {
        "location": location,
        "dateRange": "52w",
        "limit": 50,
    })
    return res.get("annotations", [])


def detect(df: pd.DataFrame) -> pd.DataFrame:
    s = df["http_requests"].astype(float)
    baseline = s.rolling(WINDOW, min_periods=WINDOW // 2, center=True).median()
    mad = (s - baseline).abs().rolling(
        WINDOW, min_periods=WINDOW // 2, center=True).median()
    robust_z = 0.6745 * (s - baseline) / mad.replace(0, pd.NA)
    out = pd.DataFrame({
        "http_requests": s,
        "baseline": baseline,
        "robust_z": robust_z,
        "pct_of_baseline": s / baseline,
    })
    out["disruption"] = (out["pct_of_baseline"] < DROP_RATIO) & (out["robust_z"] < -Z_THRESHOLD)
    return out


def known_intervals(annotations: Iterable[dict]) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    now = pd.Timestamp.utcnow().tz_localize(None).tz_localize("UTC")
    out = []
    for a in annotations:
        start = pd.to_datetime(a["startDate"], utc=True)
        end = pd.to_datetime(a["endDate"], utc=True) if a.get("endDate") else now
        out.append((start, end))
    return out


def group_windows(flagged: pd.DataFrame,
                  known: list[tuple[pd.Timestamp, pd.Timestamp]]) -> list[dict]:
    hits = flagged[flagged["disruption"]]
    if hits.empty:
        return []
    gap = pd.Timedelta("2h")
    new_event = hits.index.to_series().diff() > gap
    groups = new_event.cumsum()
    rows = []
    for _, idx in hits.groupby(groups).groups.items():
        sub = hits.loc[idx]
        start, end = sub.index.min(), sub.index.max()
        inside = any(s <= end and start <= e for s, e in known)
        if inside:
            continue
        rows.append({
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration_h": round((end - start).total_seconds() / 3600 + 1, 1),
            "min_pct_of_baseline": round(float(sub["pct_of_baseline"].min()) * 100, 1),
        })
    return rows


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"seen_windows": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def diff_new(current: list[dict], state: dict) -> list[dict]:
    seen = {(w["start"], w["end"]) for w in state.get("seen_windows", [])}
    return [w for w in current if (w["start"], w["end"]) not in seen]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--location", required=True,
                   help="ISO alpha-2 country code (e.g. US, BR, IR, KE, IN)")
    p.add_argument("--range", dest="date_range", default="28d",
                   help="Cloudflare Radar look-back window (default 28d)")
    p.add_argument("--state", default=None,
                   help="Path to JSON state file (default: monitor_state_<LOCATION>.json)")
    p.add_argument("--quiet", action="store_true", help="suppress non-alert output")
    args = p.parse_args(argv)

    args.location = args.location.strip().upper()
    if len(args.location) != 2 or not args.location.isalpha():
        print(f"ERROR: --location must be a 2-letter ISO code, got {args.location!r}",
              file=sys.stderr)
        return 1
    if args.state is None:
        args.state = str(Path(__file__).with_name(
            f"monitor_state_{args.location}.json"))

    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        print("ERROR: CLOUDFLARE_API_TOKEN not set", file=sys.stderr)
        return 1

    try:
        http_df = fetch_http(token, args.location, args.date_range)
        annotations = fetch_outages(token, args.location)
    except Exception as e:
        print(f"ERROR: fetch failed: {e}", file=sys.stderr)
        return 1

    flagged = detect(http_df)
    windows = group_windows(flagged, known_intervals(annotations))

    state_path = Path(args.state)
    state = load_state(state_path)
    new_windows = diff_new(windows, state)

    state["seen_windows"] = windows
    state["last_run"] = pd.Timestamp.utcnow().isoformat()
    state["location"] = args.location
    state["range"] = args.date_range
    save_state(state_path, state)

    if not args.quiet:
        print(f"[{args.location}] window {http_df.index.min():%Y-%m-%d} -> "
              f"{http_df.index.max():%Y-%m-%d} | {len(windows)} window(s) total | "
              f"{len(new_windows)} NEW since last run")

    if new_windows:
        print("ALERT: new disruption windows detected:")
        for w in new_windows:
            print(f"  - {w['start']} -> {w['end']} "
                  f"({w['duration_h']}h, low {w['min_pct_of_baseline']}% of baseline)")
        # Hook your alerting here:
        #   requests.post(SLACK_WEBHOOK, json={'text': format_alert(new_windows)})
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
