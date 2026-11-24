"""Minimal type stubs for the parts of the MuJoCo Python bindings this project uses.

MuJoCo ships without stubs; pyright runs in strict mode on ``src/airc``. Extend as needed.
"""

import numpy as np
from numpy.typing import NDArray

_F64 = NDArray[np.float64]
_I32 = NDArray[np.int32]

class _Named:
    id: int
    name: str

class MjModel:
    njnt: int
    nu: int
    nbody: int
    neq: int
    jnt_qposadr: _I32
    jnt_dofadr: _I32
    body_jntadr: _I32
    eq_data: _F64
    dof_damping: _F64
    @staticmethod
    def from_xml_string(xml: str) -> MjModel: ...
    def joint(self, key: int | str) -> _Named: ...
    def body(self, key: int | str) -> _Named: ...
    def site(self, key: int | str) -> _Named: ...
    def equality(self, key: int | str) -> _Named: ...
    def camera(self, key: int | str) -> _Named: ...

class MjData:
    time: float
    qpos: _F64
    qvel: _F64
    ctrl: _F64
    xpos: _F64
    xquat: _F64
    xmat: _F64
    site_xpos: _F64
    site_xmat: _F64
    actuator_force: _F64
    qfrc_actuator: _F64
    eq_active: NDArray[np.uint8]
    def __init__(self, model: MjModel) -> None: ...

def mj_step(m: MjModel, d: MjData, nstep: int = 1) -> None: ...
def mj_forward(m: MjModel, d: MjData) -> None: ...
def mj_ray(
    m: MjModel,
    d: MjData,
    pnt: _F64,
    vec: _F64,
    geomgroup: NDArray[np.uint8] | None,
    flg_static: int,
    bodyexclude: int,
    geomid: _I32,
) -> float: ...
def mju_negQuat(res: _F64, quat: _F64) -> None: ...  # noqa: N802 - MuJoCo's name
def mju_mulQuat(res: _F64, quat1: _F64, quat2: _F64) -> None: ...  # noqa: N802 - MuJoCo's name
