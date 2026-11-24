"""Editing the soft-PLC's user-level CODESYSControl.cfg (airc.plc.runtime)."""

from pathlib import Path

import pytest

from airc.plc.runtime import (
    RuntimeSettings,
    apply_runtime_settings,
    inbound_allowed_from_rules,
    load_runtime_settings,
)

CFG = """\
[ComponentManager]
Component.1=CmpTargetVisuStub

[CmpWebServer]
;LocalAddress=127.0.0.1

[CmpOPCUAServer]
;NetworkPort=4841 ;comment kept

[CmpUserMgr]
;SECURITY.UserMgmtEnforce=NO
SECURITY.UserLogin_AuthenticationType=ONLY_ASYMMETRIC
"""


def _settings(**sections: dict[str, str]) -> RuntimeSettings:
    return RuntimeSettings.model_validate(
        {
            "executable": "C:/runtime/CODESYSControlService.exe",
            "data_dir": "C:/data",
            "settings": sections,
        }
    )


@pytest.fixture
def cfg(tmp_path: Path) -> Path:
    path = tmp_path / "CODESYSControl.cfg"
    path.write_text(CFG, encoding="utf-8", newline="")
    return path


def test_apply_runtime_settings_is_idempotent(cfg: Path) -> None:
    settings = _settings(
        CmpUserMgr={"SECURITY.UserMgmtAllowAnonymous": "YES"},
        CmpWebServer={"LocalAddress": "127.0.0.1"},
        CmpBlkDrvTcp={"itf.0.IpAddress": "127.0.0.1"},
    )
    assert apply_runtime_settings(cfg, settings) is True
    first = cfg.read_text(encoding="utf-8")
    assert apply_runtime_settings(cfg, settings) is False
    assert cfg.read_text(encoding="utf-8") == first

    lines = first.splitlines()
    assert lines.count("SECURITY.UserMgmtAllowAnonymous=YES") == 1
    assert "LocalAddress=127.0.0.1" in lines
    assert ";LocalAddress=127.0.0.1" in lines  # comment lines are kept
    assert ";NetworkPort=4841 ;comment kept" in lines
    assert "SECURITY.UserLogin_AuthenticationType=ONLY_ASYMMETRIC" in lines
    # a missing section is appended with its keys
    assert lines.index("[CmpBlkDrvTcp]") < lines.index("itf.0.IpAddress=127.0.0.1")
    # the key lands inside its own section
    section = lines.index("[CmpUserMgr]")
    assert lines.index("SECURITY.UserMgmtAllowAnonymous=YES") > section


def test_existing_key_value_is_replaced(cfg: Path) -> None:
    settings = _settings(CmpUserMgr={"SECURITY.UserLogin_AuthenticationType": "ALL"})
    assert apply_runtime_settings(cfg, settings) is True
    lines = cfg.read_text(encoding="utf-8").splitlines()
    assert "SECURITY.UserLogin_AuthenticationType=ALL" in lines
    assert "SECURITY.UserLogin_AuthenticationType=ONLY_ASYMMETRIC" not in lines


def test_backup_written_once(cfg: Path) -> None:
    backup = cfg.with_name(cfg.name + ".orig")
    apply_runtime_settings(cfg, _settings(CmpWebServer={"LocalAddress": "127.0.0.1"}))
    assert backup.read_text(encoding="utf-8") == CFG
    apply_runtime_settings(cfg, _settings(CmpWebServer={"LocalAddress": "127.0.0.2"}))
    assert backup.read_text(encoding="utf-8") == CFG


def test_load_runtime_settings_from_repo_config() -> None:
    settings = load_runtime_settings()
    assert settings.executable.name == "CODESYSControlService.exe"
    assert settings.settings["CmpUserMgr"]["SECURITY.UserMgmtAllowAnonymous"] == "YES"
    assert settings.opcua_port == 4840


def test_enabled_allow_rule_is_reported() -> None:
    assert inbound_allowed_from_rules("True|Allow|Inbound\nFalse|Allow|Inbound\n") is True
    assert inbound_allowed_from_rules("False|Allow|Inbound\nFalse|Allow|Inbound\n") is False
    assert inbound_allowed_from_rules("True|Block|Inbound\n") is False
    assert inbound_allowed_from_rules("") is False
