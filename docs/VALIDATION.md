# Validation record

Built on 10 November 2026.

## Verified

- All 44 Python analysis, job, persistence and HTTP protocol regression checks passed, including target-match exclusion and historical timestamp filtering.
- JavaScript syntax checks on every extension script.
- The unpacked Manifest V3 extension loads in a disposable Chrome instance.
- Browser renders five-player example reports on desktop and a 390-pixel viewport without horizontal overflow.
- A nickname containing HTML renders literally and does not execute.
- Actual extension content injection on an intercepted FACEIT-shaped matchroom URL, with an explicitly synthetic server fixture.
- Extension service-worker calls to the paired local helper, report rendering and panel cleanup after SPA navigation.
- Native `demoparser2` 0.42.0 successfully parsed the upstream project's real `src/parser/test_demo.dem` replay (60,601,900 bytes). It yielded nine complete five-versus-five Mirage rounds with named early positions, equipment classifications and site observations.
- A zstd-compressed copy of that replay completed the full import, subprocess extraction, validation and temporary database write in 1.27 seconds on the build Mac. This is a local-file benchmark, not a real-match download or briefing latency claim.
- The real replay was used only in temporary QA files. No invented current date or fixture player data was inserted into a user's live evidence cache.

## Live integration findings

- Authenticated FACEIT match and player-statistic retrieval was verified locally after the user saved their key. No key is committed to this repository.
- Real API history returns lowercase `finished`; the demo filter now accepts it.
- Public API demo URLs encountered during the live test did not resolve. The logged-in website provided an authenticated replay download; that manual path is only suitable for validation. A data source for precomputed, arbitrary-player position profiles remains unverified.

## Still not verified
- Automatic official demo downloads from their matchmaking history.
- Real-match warmup latency and the percentage of opponents with enough position coverage.
- Prediction accuracy against manually reviewed FACEIT matches.
- Windows launcher execution on the user's gaming PC. The archive includes Windows launch and dependency-install scripts; Python tests were run on macOS.

The synthetic browser fixture demonstrates the extension plumbing and renderer, not real scouting accuracy or internet/API latency. This archive contains no API key, pairing token, parsed real-player cache, replay, browser profile or QA screenshot.
