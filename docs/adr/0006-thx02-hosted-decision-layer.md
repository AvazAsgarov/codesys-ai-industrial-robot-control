# 6. THX-02 as a supervisory decision layer via its hosted API

- **Status:** Accepted
- **Date:** 2026-11-23

## Context

The cell sorts parts by type and quality. Quality disposition (ok / rework / scrap) and an
identification reliability check need judgement beyond a detector's class label. THX-02
(HAL-X AI) is a decision model that answers typed questions (`choice`, `noul`, `score`) over
text and images with calibrated probabilities. Its hosted API is free without a key at
60 decisions per minute per IP.

## Decision

Use THX-02 through its hosted API as a supervisory layer that never commands motion. One
request per part carries both questions. A per-part deadline (default 2.5 s) and a rule-based
fallback keep the PLC independent of the API. Every request and response is recorded so paper
results can be recomputed without calling the API. A local mode (`thx02[local]`) stays optional.

## Consequences

- At most about 50 parts per minute within the free tier.
- The hosted model is not version-pinned; the paper states the API date range.
- Part images (simulation renders) are sent to an external service; no personal data is involved.
