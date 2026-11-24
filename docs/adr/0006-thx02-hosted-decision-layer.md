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

## Throughput and fallback

- The free tier counts every question, so one part (quality + identification) costs two
  decisions. The client-side token bucket allows 50 decisions per minute (burst 2), i.e.
  25 parts per minute, under the 60 per minute per IP the API allows. The cell's target of
  about 25 parts per minute therefore uses the whole budget; a faster supply, a 429 or a
  `Retry-After` longer than 1 s makes parts fall back instead of queueing past their deadline.
- The bridge runner asks in a worker thread with its own event loop and polls the answers each
  20 ms cycle, so a slow or stuck API never delays the cycle. The budget per part is the PLC's
  deadline (`tDecisionDeadline`, 2.5 s) minus the time since the capture.
- Fallback decisions are never written to the PLC: `ST_DecisionMsg` has no source field and the
  PLC marks every decision it accepts as AI. A part without an AI answer is decided by the PLC's
  own rule when its deadline passes (quality unknown, class bin, low confidence to Quarantine;
  alarm `DecisionFallback`), so the fallback is visible on the HMI and in the alarm log.
- The bridge writes `xDecisionActive` TRUE every cycle while a decision service is configured
  (`airc run --decision thx02|replay:<path>`). With it FALSE (`--decision off`, or after the
  run) the PLC decides each part by its rule as soon as vision has identified it, without the
  2.5 s wait and without a `DecisionFallback` alarm.
- An AI decision is also dropped if it arrives for a part that has already reached the pick
  window (PE2) or for a part id the runner did not ask about; the run report counts these.

## Consequences

- At most 30 parts per minute within the free tier (two decisions per part); the client limit
  is 25 parts per minute (see above).
- The hosted model is not version-pinned; the paper states the API date range.
- Part images (simulation renders) are sent to an external service; no personal data is involved.
