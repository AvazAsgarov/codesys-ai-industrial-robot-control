# CODESYS IronPython 2.7 script (runs inside CODESYS, not in the uv environment).
#
# Downloads the PLC application to the local soft-PLC (CODESYS Control Win V3 x64 started by
# `airc plc start`) and starts it. Called by `airc plc deploy`, which passes:
#   AIRC_DEPLOY_PROJECT  temporary copy of plc/RobotCell.project (modified freely here)
#   AIRC_DEPLOY_LOG      log file; the last line is "DEPLOY OK" on success
#   AIRC_PLC_USER / AIRC_PLC_PASSWORD  the runtime's initial user (from .env, never committed)
#   AIRC_GATEWAY_PORT    port of the local CODESYS gateway (default 1217)
#
# Steps: symbol configuration with OPC UA support (created on the copy if missing; the variables
# to publish carry {attribute 'symbol' := ...} in the sources) -> gateway "Gateway-1" on
# localhost -> device address 127.0.0.1 -> initial user -> build -> login (download, deleting
# other applications) -> start -> boot application.
from __future__ import print_function

import os
import time
import traceback

LOG = open(os.environ["AIRC_DEPLOY_LOG"], "w")


def log(*parts):
    LOG.write(" ".join(str(p) for p in parts) + "\n")
    LOG.flush()


def ensure_symbol_config(app):
    from System import Guid
    if not [c for c in app.get_children() if c.is_symbol_config]:
        app.create_symbol_config(False, True, Guid.Empty)
        log("symbol configuration created (OPC UA support)")


def local_gateway():
    port = int(os.environ.get("AIRC_GATEWAY_PORT", "1217"))
    for gw in online.gateways:  # noqa: F821
        if gw.name == "Gateway-1":
            return gw
    return online.gateways.add_new_gateway(  # noqa: F821
        "Gateway-1", {"IP-Address": "localhost", "Port": port})


def main():
    proj = projects.open(os.environ["AIRC_DEPLOY_PROJECT"])  # noqa: F821
    app = proj.active_application
    log("project", proj.path)
    ensure_symbol_config(app)
    dev = proj.find("Device", False)[0]
    dev.set_gateway_and_ip_address(local_gateway(), "127.0.0.1")
    log("device address", dev.get_address())
    user = os.environ["AIRC_PLC_USER"]
    password = os.environ["AIRC_PLC_PASSWORD"]
    online.set_default_credentials(user, password)  # noqa: F821
    odev = online.create_online_device(dev)  # noqa: F821
    odev.set_credentials_for_initial_user(user, password)
    odev.connect()
    log("connected as", odev.current_logged_on_username)
    app.build()
    oapp = online.create_online_application(app)  # noqa: F821
    oapp.login(OnlineChangeOption.Never, True)  # noqa: F821
    oapp.start()
    time.sleep(2)
    log("application state", oapp.application_state)
    log("GVL_Bridge.eState", oapp.read_value("GVL_Bridge.eState"))
    oapp.create_boot_application()
    oapp.logout()
    proj.close()
    log("DEPLOY OK")


try:
    main()
except Exception:
    log(traceback.format_exc())
finally:
    LOG.close()
