# Zephyr / Site Scout for FACEIT

A personal Chrome/Edge extension that automatically opens a pre-match briefing in a FACEIT CS2 matchroom. It is designed to work alongside GRIND.

Independent personal project by [Avilove Nilay](https://github.com/aviloveN). The public project website lives in `docs/index.html` and is published using GitHub Pages.

## Start on your gaming PC

1. Extract this entire folder. Keep the `server` and `extension` folders together.
2. Install Python 3.12 from https://www.python.org/downloads/ if needed. On Windows, enable **Add Python to PATH**. Python 3.10 to 3.13 is recommended; the core service also works with Python 3.9.
3. Run **Install-demo-support.cmd** on Windows, or **Install-demo-support.command** on Mac. This creates a project-local environment and downloads the replay parser. It does not change CS2 or FACEIT Anti-Cheat.
4. Run **Start-Windows.cmd** or **Start-Mac.command**. Keep that console open. A paired setup page opens in your browser.
5. In that page, enter your exact FACEIT nickname and a **server-side Data API key** from https://developers.faceit.com/. Create a developer application to generate the key. Save the connection. Your API key stays in the local helper; do not send it in chat.
6. Open `chrome://extensions` or `edge://extensions`. Enable **Developer mode**, click **Load unpacked**, and choose this project's **extension** folder.
7. In the helper setup page, click **Copy code for extension**. Click the extension's toolbar icon, paste that pairing code and click **Connect**.
8. Open your next FACEIT CS2 matchroom. Site Scout appears automatically. It chooses your team from your saved nickname; otherwise it asks which team is yours. Map detection uses the published API pick. If FACEIT has not published it yet, select the confirmed map in the panel.

Run the helper on the **same computer** as the FACEIT browser. Running it on your Mac will not connect a browser on your Windows gaming PC. If Mac blocks opening a `.command` file, run `zsh Start-Mac.command` or `zsh Install-demo-support.command` from Terminal in this folder.

## What this version does

- Automatically detects FACEIT matchroom URLs, including navigation without a page reload.
- Reads the two rosters and selected map using the official authenticated FACEIT Data API.
- Displays available position evidence immediately after the roster is fetched; each player's recent API statistics arrive independently.
- Shows likely early CT positions, named areas, sample rounds, sample matches and evidence age.
- Identifies frequent early CT AWP use from sampled demo weapon data. It does not turn generic sniper statistics into AWP claims.
- Compares site outcomes for the exact five-player lineup when enough shared evidence exists.
- For unfamiliar lineups, can show explicitly tentative projections from prior lineups involving the likely site defenders. These observations depend on past teammates and opposition.
- Produces a short team briefing you can copy manually.
- Attempts bounded background retrieval of accessible completed FACEIT demos for the selected map. Demos are parsed in a separate, low-priority process and deleted after extraction.
- Accepts manually downloaded completed demos when the official API does not provide an accessible download URL.
- Keeps a rolling local evidence cache. Preview examples never enter it.

## What is still required for a real match

This is a working personal first version, not a populated global scouting service. You need your own FACEIT developer key and historical demo coverage. The archive contains **no real player database**. With a cold cache, the first briefing may show recent statistics and missing position evidence until demos become available. A reliable 15 to 30 second site briefing for arbitrary opponents has **not** been demonstrated.

**Current live-use gap:** arbitrary opponents' precomputed position profiles are not connected. Local demo imports support development and accuracy checks, but they do not meet the requirement for automatic site analysis during veto and warmup. Match-triggered demo retrieval is off by default. The next data milestone is a verified source or populated service of already-processed profiles.

Completed-match tests exclude the target match and any evidence finished after its start. API statistics with missing timestamps are also excluded from those historical tests, so the result cannot silently use later games.

The automatic downloader uses only completed matches and official API demo links. If those links are absent, expired, restricted or on a host outside the supported FACEIT/CDN allowlist, the app records the problem and leaves the evidence unavailable. It does not read FACEIT login cookies or use private endpoints. Importing demos is the supported fallback.

Map support is strongest for **Mirage, Dust2, Inferno and Ancient**, with conservative named-area mappings. On the other selectable maps, explicit `BombsiteA`/`BombsiteB` labels work; unrecognised support areas remain unknown. Spawn-based position prediction, detailed rotation timings, utility scoring and opponent-skill-adjusted site models are not implemented in v0.1.

## Import a completed demo

1. Download **Watch Demo** from a finished FACEIT matchroom.
2. In Site Scout's helper dashboard, paste that completed matchroom link, choose its `.dem`, `.gz`, `.bz2` or `.zst` file, and click **Import completed demo**.
3. The helper verifies the match is finished using FACEIT metadata, extracts evidence, and refreshes the local cache. It accepts files up to 512 MB and observations from the last 30 days.

The file is sent only to the local helper. Import several recent matches on your usual maps to evaluate the analysis. The preview's invented players are deliberately separate from live matches.

## How to interpret the briefing

- **Position evidence:** modal named area in sampled early CT positions, before the first observed player damage. This is a tendency, not today's confirmed assignment.
- **Moderate position coverage:** at least 20 classified full-buy CT rounds across at least three distinct matches, with at least 65% in one sector. These are explicit v0.1 coverage thresholds, not a validated probability of being correct.
- **Full buy:** both teams have five players and at least 20,000 combined equipment value at freeze end. This is a conservative heuristic, not FACEIT's official economy label.
- **Site contact:** damage where both participants are inside the same explicitly named bombsite core, or a plant at that site. Rounds with qualifying observations at both sites are excluded. Failed attacks without core contact are not captured; this metric is not every attempted execute.
- **Contacts without a plant:** the share of those qualifying attacks that did not result in a plant. This is not the same as round win rate or individual anchor ability.
- **Retake:** a post-plant damage engagement near the planted site is used as an attempt proxy. Saving rounds with no such engagement do not enter that denominator.
- **Exact-lineup comparison:** the CT roster matches all five current opponents. A directional site finding requires at least 20 eligible observations per site over at least three matches and non-overlapping 95% Wilson intervals for plant-concession rates. The intervals are an initial safeguard; rounds within one match are correlated and the model is not calibrated.
- **Prior-lineup projection:** only players with repeatable site tendencies contribute. Their previous lineups' contact outcomes are pooled and labelled as a limited projection. Teammates, attacking skill and execute difficulty remain confounders. It is a suggestion to test, never a guarantee that A or B is weak.

## Timing and resource budget

Cached evidence is assembled first. The extension polls a progressive job for up to 90 seconds. The map is rechecked while its pick is pending. One missing player does not block the other profiles. Background demo work uses one low-priority parser process, a 30-second download budget and a 45-second parse limit per demo. It attempts at most one new suitable demo per opponent per cache pass and inspects at most six recent match records to find it. The next pass is suppressed for ten minutes.

The first-briefing timer includes roster/API retrieval and cache assembly. It excludes later demo completion and does not claim all site evidence was ready at that time. Real-match timing must be measured after you connect your key.

## Privacy and operation

The helper binds only to `127.0.0.1:8765`. A random pairing code is required for private API operations. The FACEIT key and pairing token are stored in `data/config.json`; the extension stores only the pairing code. Treat that folder as private. It is excluded from the distributed archive and Git ignore rules. There are no analytics, external AI providers, automatic messages, live game memory reads or fullscreen CS2 overlay.

To stop, close the helper console. To uninstall, remove the browser extension and this project folder. If you change the helper's port, update the extension URLs and host permission as well.

## Developer checks

Core Python tests:

```sh
python3 -m unittest discover -s tests -v
```

The socket tests need permission to bind localhost. Browser regression checks use Node 22+ and disposable Chrome with remote debugging. They cover preview rendering, escaped player names, narrow screens and, with the explicit fixture server, the real MV3 extension's matchroom injection and SPA cleanup. No automated test uses your personal FACEIT account.

See `docs/VALIDATION.md` for what was actually verified and `docs/ARCHITECTURE.md` for the main components.

Independent personal project. Not affiliated with FACEIT, Valve, Repeek or GRIND.
