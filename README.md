# codesys-ai-industrial-robot-control

Vision-guided 6-axis robot cell: CODESYS SoftMotion PLC, YOLO26 perception, THX-02 decision layer, MuJoCo digital twin, ISA-101 HMI.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)

> **Work in progress.** Phase 3 (vision) is complete: the CODESYS soft-PLC drives a MuJoCo model
> of the cell over OPC UA and sorts three scanned products from the moving belt; a camera in the
> twin and YOLOE with visual prompts (no training, mAP@0.5 0.997) tell the PLC what and where each
> part is. Design: [`docs/specs/2026-11-23-system-design.md`](docs/specs/2026-11-23-system-design.md);
> architecture: [PLC](docs/architecture/plc.md), [twin and bridge](docs/architecture/twin-bridge.md),
> [vision](docs/architecture/vision.md).

## Quick start (Windows, CODESYS V3.5 SP22 Patch 4 installed)

```powershell
copy .env.example .env                    # test credentials for the local soft-PLC
python tools/uv_run.py airc plc start     # CODESYS Control Win as a console process
python tools/uv_run.py airc plc deploy    # headless download of the PLC project (~3 min)
python tools/uv_run.py airc run --viewer  # digital twin + OPC UA bridge (ground-truth vision)
python tools/uv_run.py --group vision airc vision export --prompts visual   # once
python tools/uv_run.py --group vision airc run --vision yoloe --viewer      # camera + YOLOE
```

Production is started with Reset and Start (HMI in Phase 5; meanwhile the end-to-end test does it:
`python tools/uv_run.py pytest -m codesys -s`). The installer's inbound firewall rule for the
runtime should be disabled so the soft-PLC is not reachable from the network (see
[ADR 0008](docs/adr/0008-softplc-runtime-and-opcua-security.md)).

Copyright (C) 2026 Avaz Asgarov. Licensed under the GNU Affero General Public License v3.0.
