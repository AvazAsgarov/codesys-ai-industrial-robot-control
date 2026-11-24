"""OPC UA tag map: logical bridge names -> CODESYS node ids (``config/opcua_tags.yaml``)."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from airc.common.config import default_config_path


class Tag(BaseModel):
    """One PLC variable as the bridge sees it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    variant: str


class TagMap(BaseModel):
    """All bridge tags and the node-id prefix of the CODESYS application."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    namespace_prefix: str
    tags: dict[str, Tag]

    @classmethod
    def load(cls, path: Path | None = None) -> "TagMap":
        """Load the tag map (default: ``config/opcua_tags.yaml`` of the repository)."""
        file = path if path is not None else default_config_path().parent / "opcua_tags.yaml"
        raw: Any = yaml.safe_load(file.read_text(encoding="utf-8"))
        return cls.model_validate(raw)

    def node_id(self, name: str) -> str:
        """Return the OPC UA node id of a tag.

        Raises:
            KeyError: If the tag is not in the map.
        """
        if name not in self.tags:
            msg = f"unknown OPC UA tag: {name}"
            raise KeyError(msg)
        return self.namespace_prefix + self.tags[name].path
