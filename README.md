# Country Internet Connectivity — Disruption Analysis (Cloudflare Radar)

A Jupyter notebook and a daily-runnable monitor that use the
[Cloudflare Radar API](https://developers.cloudflare.com/radar/) to surface
**sudden internet traffic drops or outages** in **any country**. Works for any
of the 200+ ISO alpha-2 country codes Cloudflare Radar supports
(`US`, `BR`, `IR`, `KE`, `IN`, `RU`, `EG`, etc.).

Abrupt, country-wide collapses in traffic — outside the normal daily rhythm —
are a known signature of government-imposed internet shutdowns during periods of
civil unrest.

## What's in here

| File | Purpose |
|---|---|
| `internet_disruption_analysis.ipynb` | Interactive analysis: time series, plots, anomaly detector, summary report. |
| `monitor.py` | Headless daily-runnable script that diffs new disruption windows against a JSON state file (suitable for cron + alerting). |
| `.env.example` | Template for your Cloudflare API token + optional defaults. Copy to `.env` and fill in your own credentials. |

## What the notebook does

1. Pulls the selected country's **HTTP request** and **NetFlows** traffic time series.
2. Plots them so daily cycles and anomalies are visible.
3. Runs a **rolling-median anomaly detector** that flags abnormal traffic *drops*
   and groups them into disruption windows.
4. Fetches Cloudflare's curated **outage annotations** for the country and
   **suppresses** any flagged window that already overlaps a known outage —
   so the report shows only *new* candidate events.
5. Pulls the **Internet Quality Index** (latency) as a throttling signal.
6. Prints a short summary report.

## Setup

Requires Python 3.9+.

```bash
pip install requests pandas matplotlib jupyter python-dotenv
```

**Bring your own Cloudflare API token.** Create one (with the **Radar Read**
permission only) at <https://dash.cloudflare.com/profile/api-tokens>.

The repo ships with a `.env.example` template. Copy it and fill in your token:

```bash
# macOS / Linux
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

Open `.env` in an editor and set:

```dotenv
CLOUDFLARE_API_TOKEN=your_token_here
CFR_LOCATION=                 # optional — leave blank to be prompted
CFR_DATE_RANGE=               # optional — leave blank for 28d
```

The notebook and `monitor.py` both auto-load `.env` via `python-dotenv`. The
`.env` file itself is git-ignored, so your token never gets committed.

Alternatively, export the variables yourself instead of using `.env`:

```bash
export CLOUDFLARE_API_TOKEN="your_token_here"        # macOS / Linux
$env:CLOUDFLARE_API_TOKEN = "your_token_here"        # Windows PowerShell
```

**Never commit your token.** If you ever do by accident, rotate it immediately at
the Cloudflare token page above.

## Run the notebook

```bash
jupyter notebook internet_disruption_analysis.ipynb
```

The configuration cell will prompt for:

- **Country code** — any ISO alpha-2 code (e.g. `US`, `BR`, `IR`)
- **Date range** — Cloudflare Radar window (`7d`, `14d`, `28d`, `90d`, `52w`)

You can skip the prompts by setting `CFR_LOCATION` and `CFR_DATE_RANGE`:

```bash
export CFR_LOCATION=IR
export CFR_DATE_RANGE=28d
```

## Run the monitor (cron / scheduled task)

`monitor.py` runs the same detector headless. The first run seeds a per-country
state file; subsequent runs print *only* new disruption windows since the last
run — perfect for daily cron + email/Slack alerting.

```bash
python monitor.py --location IR                        # default 28d window
python monitor.py --location BR --range 90d            # custom window
python monitor.py --location IN --state ./in.json      # custom state path
python monitor.py --location US --quiet                # only print alerts
```

Exit codes (useful for cron routing):

- `0` — ran cleanly, no new windows since last run
- `2` — **new disruption windows detected** (alert-worthy)
- `1` — error (missing token, network, etc.)

Wire your alerting at the marked `# Hook your alerting here:` comment in
`monitor.py` (Slack webhook, email, PagerDuty, etc.).

### Cron example (Linux)

```cron
# Check Iran every hour; email any new disruption windows
0 * * * * CLOUDFLARE_API_TOKEN=xxx /usr/bin/python /opt/radar/monitor.py --location IR --quiet | mail -s "Radar alert" you@example.com
```

### Windows Task Scheduler

Create a daily task that runs:

```powershell
python.exe C:\path\to\monitor.py --location IR --quiet
```

with `CLOUDFLARE_API_TOKEN` set as a user environment variable.

## How the anomaly detector works

For each hourly data point, compute:

- **Baseline**: 1-day rolling median (robust to spikes)
- **MAD**: 1-day rolling median absolute deviation around the baseline
- **Robust z-score**: `0.6745 * (value − baseline) / MAD`

Flag a point as a disruption when **both**:

- `value < 50% of baseline` (relative drop)
- `robust_z < −3.5` (statistically large negative deviation)

Consecutive flagged hours (gap ≤ 2h) are merged into one **window**.

To keep the output meaningful, windows that overlap a Cloudflare-curated outage
annotation are **suppressed** automatically — so the report shows only *new*
candidate disruptions.

Tune the thresholds in the notebook config cell or in `monitor.py`:

| Constant | Default | Effect |
|---|---|---|
| `WINDOW` | 24 (1 day @ 1h) | Rolling baseline window. |
| `DROP_RATIO` | 0.50 | Max ratio to baseline to flag (smaller = stricter). |
| `Z_THRESHOLD` | 3.5 | Min |z| to flag (larger = stricter). |

## Scope & ethics

This is an observational, read-only analysis of publicly reported aggregate
network data. A traffic drop is *evidence* of disruption, not proof of intent.
Corroborate against multiple sources before drawing conclusions:

- [Cloudflare Radar](https://radar.cloudflare.com/)
- [NetBlocks](https://netblocks.org/)
- [OONI Explorer](https://explorer.ooni.org/)
- [IODA](https://ioda.inetintel.cc.gatech.edu/)

## License

MIT.
