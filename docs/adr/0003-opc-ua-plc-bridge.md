# 3. OPC UA between the PLC and the Python services

- **Status:** Accepted
- **Date:** 2026-11-23

## Context

The CODESYS soft-PLC must exchange setpoints, feedback, sensor signals, part records and AI
decisions with the Python services (twin, vision, decision layer).

## Decision

Use the CODESYS OPC UA server (symbol configuration exposing only `GVL_Bridge` and `GVL_Hmi`)
and an `asyncua` client in the Python bridge, cycling at 20 ms. Tag names have a single source
of truth in `config/opcua_tags.yaml`. A heartbeat watchdog (500 ms) aborts the cell if the
bridge is lost.

Rejected: Modbus TCP (flat registers, no structured types), raw UDP or shared memory
(non-standard, fragile).

## Consequences

- Industry-standard, typed, structured data exchange.
- 20 ms latency is far too slow for a servo loop, so servo control stays in the twin (ADR 0002)
  and the PLC does trajectory generation and supervision.
