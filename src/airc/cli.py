"""Command-line interface: ``airc``."""

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml

from airc import __version__
from airc.bridge.client import BridgeClient
from airc.bridge.tags import TagMap
from airc.common.config import ConfigError, load_config
from airc.plc import runtime
from airc.plc.runtime import RuntimeSettings, load_runtime_settings
from airc.runner import Runner, raise_priority, run_precise
from airc.twin.config import TwinConfig
from airc.twin.scenario import Scenario
from airc.twin.twin import Twin
from airc.vision.service import VisionWorker

app = typer.Typer(
    name="airc",
    help="AI Industrial Robot Control: services for the robotic sorting cell.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
config_app = typer.Typer(help="Inspect the cell configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")
plc_app = typer.Typer(
    help="Run and deploy the soft-PLC (CODESYS Control Win).", no_args_is_help=True
)
app.add_typer(plc_app, name="plc")

EXIT_CONFIG_ERROR = 2
EXIT_PLC_ERROR = 3


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"airc {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """AI Industrial Robot Control."""


@config_app.command("show")
def config_show(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to a cell.yaml (default: config/cell.yaml)."),
    ] = None,
) -> None:
    """Validate the configuration and print it as YAML."""
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR) from None
    # The types-PyYAML stubs leave one safe_dump parameter partially unknown.
    dumped: str = yaml.safe_dump(  # pyright: ignore[reportUnknownMemberType]
        cfg.model_dump(mode="json"), sort_keys=False
    )
    typer.echo(dumped.rstrip())


def _runtime_settings() -> RuntimeSettings:
    try:
        return load_runtime_settings()
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR) from None


@plc_app.command("start")
def plc_start(
    allow_network: Annotated[
        bool,
        typer.Option(
            "--allow-network", help="Start even if a firewall rule exposes the runtime (unsafe)."
        ),
    ] = False,
) -> None:
    """Start the soft-PLC as a console process (applies config/runtime.yaml first)."""
    settings = _runtime_settings()
    try:
        pid = runtime.start(settings, allow_network=allow_network)
    except RuntimeError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_PLC_ERROR) from None
    typer.echo(f"soft-PLC running (pid {pid})")


@plc_app.command("unthrottle-ide")
def plc_unthrottle_ide() -> None:
    """Exempt the CODESYS IDE (and its simulation) from Windows timer throttling."""
    pids = runtime.unthrottle_ide()
    typer.echo(f"exempted: {', '.join(map(str, pids))}" if pids else "no CODESYS IDE running")


@plc_app.command("stop")
def plc_stop() -> None:
    """Stop the soft-PLC started by `airc plc start`."""
    typer.echo("soft-PLC stopped" if runtime.stop() else "soft-PLC was not running")


@plc_app.command("status")
def plc_status() -> None:
    """Show whether the soft-PLC process and its ports are up."""
    st = runtime.status(_runtime_settings())
    typer.echo(f"pid: {st.pid}  alive: {st.process_alive}")
    typer.echo(f"programming port open: {st.programming_port_open}")
    typer.echo(f"OPC UA port open: {st.opcua_port_open}")
    typer.echo(f"PackML state (GVL_Bridge.eState): {st.packml_state}")
    if st.main_task_period_ms is not None:
        typer.echo(f"MainTask period: {st.main_task_period_ms:.2f} ms (configured 4 ms)")


@plc_app.command("deploy")
def plc_deploy(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to a cell.yaml (default: config/cell.yaml)."),
    ] = None,
) -> None:
    """Download the PLC application to the running soft-PLC and start it (takes minutes)."""
    try:
        cfg = load_config(config)
        log = runtime.deploy(_runtime_settings(), cfg.plc.project_file)
    except (ConfigError, RuntimeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_PLC_ERROR) from None
    typer.echo(log.rstrip())


@app.command("run")
def run_cell(  # noqa: PLR0913, PLR0917 - one parameter per command-line option
    scenario: Annotated[
        Path, typer.Option("--scenario", "-s", help="Scenario YAML (config/scenarios/...).")
    ] = Path("config/scenarios/p2_demo.yaml"),
    duration: Annotated[
        float | None, typer.Option("--duration", "-d", help="Seconds (default: the scenario's).")
    ] = None,
    viewer: Annotated[bool, typer.Option("--viewer", help="Open the MuJoCo viewer.")] = False,
    vision: Annotated[
        str,
        typer.Option(
            "--vision",
            help="Who answers captures: 'yoloe' (camera + YOLOE visual prompts, needs "
            "`airc vision export`) or 'oracle' (simulator ground truth).",
        ),
    ] = "oracle",
    record: Annotated[
        Path | None,
        typer.Option(
            "--record", help="Record a video of the run to this .mp4 file (rendered off-cycle)."
        ),
    ] = None,
    record_fps: Annotated[
        float, typer.Option("--record-fps", help="Frames per second of the video.")
    ] = 10.0,
    record_camera: Annotated[
        str, typer.Option("--record-camera", help="Scene camera to record.")
    ] = "cam_showcase",
) -> None:
    """Run the digital twin against the soft-PLC through the OPC UA bridge."""
    try:
        cfg = load_config()
        scen = Scenario.load(scenario)
    except (ConfigError, OSError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR) from None
    if vision not in ("oracle", "yoloe"):
        typer.echo("error: --vision oracle|yoloe", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)
    twin = Twin(cfg=TwinConfig.load(parts=scen.parts), bin_capacity=scen.bin_capacity)
    client = BridgeClient(
        cfg.plc.opcua_endpoint, TagMap.load(), timeout_s=twin.cfg.bridge_timeout_s
    )
    recorder = None
    if record is not None:
        from airc.video import VideoRecorder  # noqa: PLC0415 - OpenCV only when recording

        try:
            recorder = VideoRecorder(twin, record, fps=record_fps, camera=record_camera)
        except (ValueError, OSError, RuntimeError) as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(EXIT_CONFIG_ERROR) from None
    worker = _vision_worker(twin) if vision == "yoloe" else None
    runner = Runner(client, twin, scen, vision=worker, recorder=recorder)
    handle = None
    if viewer:
        import mujoco.viewer  # noqa: PLC0415 - GUI libraries only when asked for

        handle = mujoco.viewer.launch_passive(twin.model, twin.data)
        runner.after_cycle = handle.sync
    raise_priority()
    try:
        report = run_precise(runner.run(duration_s=duration or scen.duration_s))
    except KeyboardInterrupt:
        typer.echo("interrupted")
        raise typer.Exit(1) from None
    finally:
        if handle is not None:
            handle.close()
        if worker is not None:
            worker.close()
        if recorder is not None:  # closed by the runner already, unless it never started
            recorder.close()
            typer.echo(f"video: {recorder.frames_written} frames -> {record}")
    typer.echo(
        f"cycles {report.cycles}, overruns {report.overruns}, reconnects {report.reconnects}, "
        f"cycle {report.cycle_ms_mean:.1f} ms mean / {report.cycle_ms_p95:.1f} ms p95, "
        f"longest gap {report.max_gap_ms:.0f} ms"
    )
    typer.echo(
        f"parts spawned {report.spawned} (skipped {report.spawn_skipped}), captures "
        f"{report.captures}, bins {report.bin_counts}, wrong bin {report.wrong_bin}, "
        f"missed {report.missed}, lost {report.lost}"
    )


def _vision_worker(twin: Twin) -> "VisionWorker":
    """Camera + YOLOE (visual prompts) on OpenVINO, in its own thread."""
    from airc.twin.catalogue import PartCatalogue  # noqa: PLC0415
    from airc.vision import models  # noqa: PLC0415
    from airc.vision.detector import LabelMap, OpenVinoDetector  # noqa: PLC0415

    labels = LabelMap.for_slugs(PartCatalogue.load())
    return VisionWorker(twin, lambda: OpenVinoDetector(models.yoloe_dir("visual"), labels))


@app.command("calibrate")
def calibrate_camera(
    poses: Annotated[int, typer.Option(help="Checkerboard views.")] = 15,
    seed: Annotated[int, typer.Option(help="Seed of the board poses.")] = 7,
    out: Annotated[Path, typer.Option(help="Calibration study (JSON).")] = Path(
        "experiments/results/calibration.json"
    ),
    model: Annotated[Path, typer.Option(help="Calibrated camera for the vision service.")] = Path(
        "config/calibration/cam_inspect.json"
    ),
) -> None:
    """Calibrate the inspection camera with a checkerboard and compare with the exact camera."""
    from airc.vision.calibration import compare, run_calibration  # noqa: PLC0415 - OpenCV
    from airc.vision.camera import CameraModel  # noqa: PLC0415

    twin = Twin()
    truth = CameraModel.from_mujoco(twin.model, twin.data, "cam_inspect")
    try:
        cal = run_calibration(twin, poses=poses, seed=seed)
    except RuntimeError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None
    report = compare(cal.camera, truth)
    study = {
        "command": f"airc calibrate --poses {poses} --seed {seed}",
        "seed": seed,
        "poses": poses,
        "views": cal.views,
        "rms_px": round(cal.rms_px, 4),
        "distortion": [round(float(d), 6) for d in cal.dist],
        "focal_error_pct": round(report.focal_error_pct, 4),
        "principal_point_error_px": round(report.principal_point_error_px, 3),
        "position_error_mm": round(report.position_error_mm, 3),
        "rotation_error_deg": round(report.rotation_error_deg, 4),
        "k_calibrated": cal.camera.k.round(3).tolist(),
        "k_true": truth.k.round(3).tolist(),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(study, indent=2) + "\n", encoding="utf-8")
    cal.camera.save(model, note=f"airc calibrate --poses {poses} --seed {seed}")
    typer.echo(
        f"{cal.views} views, RMS {cal.rms_px:.3f} px, focal error {report.focal_error_pct:+.3f} %, "
        f"position error {report.position_error_mm:.2f} mm, rotation error "
        f"{report.rotation_error_deg:.3f} deg -> {out}, {model}"
    )


vision_app = typer.Typer(help="Detectors: export to OpenVINO.", no_args_is_help=True)
app.add_typer(vision_app, name="vision")


@vision_app.command("export")
def vision_export(
    prompts: Annotated[
        str,
        typer.Option(
            help="YOLOE prompts: 'visual' (example renders, default), 'classes' (text, the 3 "
            "parts) or 'candidates' (text, all)."
        ),
    ] = "visual",
    precision: Annotated[str, typer.Option(help="fp32 or fp16.")] = "fp32",
) -> None:
    """Download the weights and export YOLOE-26 (with prompts) and YOLO26 to OpenVINO."""
    from airc.twin.catalogue import PartCatalogue  # noqa: PLC0415
    from airc.vision import models  # noqa: PLC0415

    if prompts not in ("visual", "classes", "candidates") or precision not in ("fp32", "fp16"):
        typer.echo("error: --prompts visual|classes|candidates, --precision fp32|fp16", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)
    cat = PartCatalogue.load()
    parts = cat.classes if prompts == "classes" else cat.candidates
    prec: models.Precision = "fp16" if precision == "fp16" else "fp32"
    if prompts == "visual":
        yoloe = models.export_yoloe_visual([p.slug for p in cat.classes], prec)
    else:
        yoloe = models.export_yoloe([p.prompt for p in parts], prompts, prec)
    coco = models.export_coco(prec)
    typer.echo(f"exported {yoloe} and {coco}")
