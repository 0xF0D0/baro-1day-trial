# Poll log of the trial run (2026-11-10, run `jW1nciLHcwFh84Z1C`)

Each line is one `GET https://api.apify.com/v2/actor-runs/jW1nciLHcwFh84Z1C?waitForFinish=20`, copied from the console output of the trial.

| Poll | `status` | `chargedEventCounts` (non-zero) | `usageTotalUsd` | `statusMessage` |
|---|---|---|---|---|
| 1 | RUNNING | `apify-actor-start: 1` | 0.00005 | Nothing extracted yet |
| 2 | RUNNING | `apify-actor-start: 1` | 0.00005 | Nothing extracted yet |
| 3 | RUNNING | `apify-actor-start: 1` | 0.00005 | Processed 1 queries on 1 pages. Extracted: 6 organicResults, 16 relatedQueries, 1 aiOverviews, 1 itemsPushed |
| 4 | SUCCEEDED | `search-page-scraped: 2`, `ads-scraped: 2`, `apify-actor-start: 1` | 0.02205 | Finished! Total 3 requests: 3 succeeded, 0 failed. |
| later read (`GET .../actor-runs/jW1nciLHcwFh84Z1C`, after the dataset download) | SUCCEEDED | `search-page-scraped: 3`, `ads-scraped: 3`, `apify-actor-start: 1` | 0.03305 | Finished! Total 3 requests: 3 succeeded, 0 failed. |

The first read that showed `SUCCEEDED` still counted 2 of the 3 pages. The charges for the third page appeared in a later read. The final values are in `trial_run_summary.json`.

Start request (before poll 1): `POST https://api.apify.com/v2/acts/apify~google-search-scraper/runs?maxTotalChargeUsd=0.5&timeout=300` returned HTTP 201 with `data.id` `jW1nciLHcwFh84Z1C`, `data.status` `READY`, `data.defaultDatasetId` `h0dSGPMou7N31ewbT`, `data.defaultKeyValueStoreId` `35b63vdvacHjMLHFK` and `data.options` `{"build": "latest", "timeoutSecs": 300, "memoryMbytes": 1024, "maxTotalChargeUsd": 0.5, "isMaxTotalChargeUsdSetByUser": true, "diskMbytes": 2048}`.
