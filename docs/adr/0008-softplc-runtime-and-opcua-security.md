# 8. Soft-PLC runtime, headless deploy and OPC UA security

- **Status:** Accepted
- **Date:** 2026-11-24

## Context

From Phase 2 the PLC application must run on a real CODESYS runtime, because CODESYS's own
simulation (used for the Phase 1 tests) has no OPC UA server. The laptop has CODESYS Control Win
V3 x64 3.5.22.40 installed as a Windows service, which needs administrator rights to start. The
project must be operable without manual IDE steps, and it runs on a laptop that joins public
Wi-Fi networks.

Findings (spike, 2026-11-23/24):

- `CODESYSControlService.exe -d` runs the runtime as a console process of the current user; its
  data and `CODESYSControl.cfg` live in `%APPDATA%\CODESYS\CODESYSControlWinV3x64\<id>\`.
- The CODESYS IDE can deploy headlessly (`--noUI --runscript`): local gateway, device address
  `127.0.0.1`, initial user (`set_credentials_for_initial_user`), login/download, start, boot
  application. A symbol configuration with OPC UA support publishes variables marked
  `{attribute 'symbol' := ...}`.
- Out of the box the OPC UA server offers no usable login: without a server certificate there is
  no secure endpoint, and the plaintext endpoint offers no identity token. Creating the server
  certificate is only possible in the IDE's security dialog.
- `[CmpUserMgr] SECURITY.UserMgmtAllowAnonymous=YES` makes the plaintext endpoint offer an
  anonymous token. `[CmpOPCUAServer] NetworkAdapter=Loopback Pseudo-Interface 1` binds OPC UA to
  `127.0.0.1` only (verified).
- The programming port 11740 (`CmpBlkDrvTcp`) cannot be bound to the loopback adapter
  (`ListenPort=0` only moves it to a random port on all adapters). The CODESYS installer adds an
  inbound firewall rule that allows the runtime on the *Public* profile.

## Decision

- `airc plc start|stop|status|deploy` manage the runtime as a console process; `config/runtime.yaml`
  holds the settings that `start` writes into the user-level `CODESYSControl.cfg` (idempotent, the
  original is kept as `.orig`).
- **Security option A** (owner decision, 2026-11-23): anonymous, plaintext OPC UA on loopback only;
  web server on loopback only. The installer's inbound firewall rules for
  `CODESYSControlService.exe` are **disabled** (owner, 2026-11-24, admin PowerShell:
  `Disable-NetFirewallRule -DisplayName "CODESYS Control Service"`), so nothing of the runtime is
  reachable from the network; loopback traffic is never filtered by the Windows firewall.
- `SECURITY.UserMgmtAllowAnonymous` is a runtime-wide setting, so we assume that it also admits
  anonymous *programming* logins on 11740 (worst case; not separately verified). The firewall is
  therefore the only barrier for 11740, and `airc plc start` **refuses to start** the runtime while
  an enabled inbound allow rule exists for it (rule paths with environment variables are expanded;
  `--allow-network` overrides, for a deliberate lab network). The deploy logs in with the initial
  user, whose credentials are test values in `.env` (never committed, template `.env.example`).

Rejected: option B, signed and encrypted OPC UA with a user (closer to industrial practice, but
needs a manual certificate step in the IDE per machine and does not change the exposure of the
programming port); the Windows service (needs administrator rights at every start).

## Consequences

- Fully scripted start and deploy; a deploy takes about 3 minutes, mostly CODESYS start-up.
- The demo licence stops the runtime after about 2 hours; `airc plc start` and `deploy` restart it.
- The OPC UA link is unauthenticated and unencrypted. That is acceptable for a single-host lab cell
  and is stated as such in the paper; a plant would use option B with certificates.
- If a CODESYS update or reinstall re-enables the installer's firewall rule, the programming port
  would be reachable from the network with anonymous login; `airc plc start` checks the rules
  before it launches the runtime and stops with the command that disables them.
