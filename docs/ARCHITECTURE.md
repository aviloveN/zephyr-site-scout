# Architecture

## Components

| Component | Responsibility |
| --- | --- |
| `extension/content.js` | Detect matchroom route, select own team, start a job, poll progressive results, render a shadow-root panel, clean up after navigation |
| `extension/background.js` | Authenticated requests to the fixed localhost API; API tokens never enter the FACEIT page |
| `extension/ui.js` | Shared DOM renderer for the panel and setup dashboard; all external strings use text nodes |
| `server/scout.py` | Loopback-only HTTP service, setup, pairing, configuration and completed-demo uploads |
| `server/faceit.py` | Official Data API, bounded HTTP requests, rate pacing, 429 cooldown and response caching |
| `server/jobs.py` | Two briefing workers, four concurrent stat requests and immediate cached results |
| `server/warmer.py` | One background demo worker, approved delivery URLs, compressed-file limits, subprocess isolation and temporary-file cleanup |
| `server/demo_import.py` | Native replay extraction into compact round-level observations |
| `server/analysis.py` | Conservative map-area classification, sample counts, exact-roster results, tentative projections and deterministic summaries |
| `server/storage.py` | SQLite API cache and deduplicated completed-demo evidence |

## Network boundary

The extension only requests `http://127.0.0.1:8765`. The helper uses the user's server-side key with `https://open.faceit.com/data/v4`. It downloads replay bytes without forwarding that key to a CDN. It supports approved FACEIT and CloudFront delivery hosts and checks redirect destinations. Unavailable links produce a visible cache event. Manual import is supported instead of relying on private FACEIT APIs.

## Data source distinctions

Recent API match statistics do not produce site labels. Position labels require parsed completed demos. Historical results by the exact five-player lineup and projections based on individual defenders' earlier lineups have different visible labels. The synthetic preview is generated in memory; the evidence import validator rejects its source type.

## Next engineering priorities

1. Time cold and warm real FACEIT matchrooms after a user key is connected.
2. Measure official demo-link coverage and current API map-pick availability.
3. Validate named-area classifications against human-reviewed rounds on each map.
4. Benchmark projected site recommendations on held-out matches; account for opponent skill and correlated rounds.
5. Add a precomputed shared player service only if the measured coverage justifies its hosting cost.
6. Add finer route and rotation evidence once basic site classification is validated.

Reference documentation: https://docs.faceit.com/docs/data-api/ and https://github.com/LaihoE/demoparser .
