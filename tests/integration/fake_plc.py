"""An in-process OPC UA server shaped like the CODESYS application (GVL_Bridge only)."""

import socket
from dataclasses import dataclass, field
from typing import Any

from asyncua import ua
from asyncua.common.callback import CallbackType
from asyncua.server.server import Server

from airc.bridge.tags import TagMap

ARRAY_LENGTH = {
    "GVL_Bridge.aJointPosSp": 6,
    "GVL_Bridge.aJointPosFb": 6,
    "GVL_Bridge.aJointTorqueFb": 6,
    "GVL_Bridge.axBinFull": 6,
}
DEFAULTS: dict[str, Any] = {
    "Boolean": False,
    "Double": 0.0,
    "UInt32": 0,
    "Int32": 0,
    "Byte": 0,
    "Float": 0.0,
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@dataclass
class FakePlc:
    """The server, its nodes by tag name, and the order in which the client wrote them."""

    port: int
    tags: TagMap
    server: Server = field(default_factory=Server)
    nodes: dict[str, Any] = field(default_factory=dict)
    write_log: list[str] = field(default_factory=list)

    @property
    def endpoint(self) -> str:
        return f"opc.tcp://127.0.0.1:{self.port}"

    async def start(self) -> None:
        await self.server.init()
        self.server.set_endpoint(self.endpoint)
        self.server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        idx = 0
        while idx < 4:  # CODESYS publishes the application in namespace 4
            idx = await self.server.register_namespace(f"urn:fake-plc:{idx}")
        objects = self.server.nodes.objects
        by_node: dict[str, str] = {}
        for name, tag in self.tags.tags.items():
            ident = self.tags.node_id(name).split(";s=", 1)[1]
            node_id = ua.NodeId(ident, 4)  # pyright: ignore[reportArgumentType]
            default = DEFAULTS[tag.variant]
            length = ARRAY_LENGTH.get(tag.path)
            value = [default] * length if length else default
            variant = ua.Variant(value, getattr(ua.VariantType, tag.variant))
            node = await objects.add_variable(node_id, tag.path, variant)
            await node.set_writable()
            self.nodes[name] = node
            by_node[node_id.to_string()] = name
        await self.server.start()

        def _on_write(event: Any, _dispatcher: Any) -> None:
            for req in event.request_params.NodesToWrite:
                self.write_log.append(by_node.get(req.NodeId.to_string(), "?"))

        self.server.iserver.subscribe_server_callback(
            CallbackType.PostWrite,  # pyright: ignore[reportArgumentType]
            _on_write,
        )

    async def stop(self) -> None:
        await self.server.stop()

    async def get(self, name: str) -> Any:
        return await self.nodes[name].read_value()

    async def set(self, name: str, value: Any) -> None:
        tag = self.tags.tags[name]
        await self.nodes[name].write_value(ua.Variant(value, getattr(ua.VariantType, tag.variant)))
