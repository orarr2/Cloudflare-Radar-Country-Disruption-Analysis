# Iran — Cloudflare Radar Connectivity Analysis of Internet Disruptions

A Jupyter notebook that uses the [Cloudflare Radar API](https://developers.cloudflare.com/radar/)
to monitor internet traffic and connectivity in **Iran** and surface **sudden drops
or outages**. Abrupt, country-wide collapses in traffic — outside the normal daily
rhythm — are a known signature of government-imposed internet shutdowns during
periods of civil unrest.

## What the notebook does

1. Pulls Iran's **HTTP request** and **NetFlows** traffic time series.
2. Plots them so daily cycles and anomalies are visible.
3. Runs a **rolling-median anomaly detector** that flags abnormal traffic *drops*
   and groups them into disruption windows.
4. Fetches Cloudflare's curated **outage annotations** for Iran.
5. Pulls the **Internet Quality Index** (latency) as a throttling signal.
6. Prints a short summary report.

## Setup

```bash
pip install requests pandas matplotlib jupyter

# Cloudflare token with the Radar read permission:
#   https://dash.cloudflare.com/profile/api-tokens
export CLOUDFLARE_API_TOKEN="your_token_here"

jupyter notebook iran_internet_disruption_analysis.ipynb
```

The notebook reads the token from `CLOUDFLARE_API_TOKEN` (or prompts securely).
**Never commit your token** — it is git-ignored via `.gitignore`.

## Scope & ethics

This is an observational, read-only analysis of publicly reported aggregate network
data. A traffic drop is *evidence* of disruption, not proof of intent. Corroborate
against multiple sources — [NetBlocks](https://netblocks.org/),
[OONI](https://explorer.ooni.org/), [IODA](https://ioda.inetintel.cc.gatech.edu/),
and news reporting — before drawing conclusions.
