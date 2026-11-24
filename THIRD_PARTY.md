# Third-party components

| Component | Licence | Use | Source |
|---|---|---|---|
| Ultralytics YOLO | AGPL-3.0 | Object detection (from Phase 3) | https://github.com/ultralytics/ultralytics |
| MuJoCo | Apache-2.0 | Digital twin physics and rendering | https://github.com/google-deepmind/mujoco |
| OpenVINO | Apache-2.0 | Detector inference (from Phase 3) | https://github.com/openvinotoolkit/openvino |

## Scanned objects (Google Scanned Objects, CC BY 4.0)

The parts in `assets/objects/` are 3D scans from *Google Scanned Objects* by Google Research
(Downs et al., ICRA 2022), licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), obtained from
[Gazebo Fuel](https://app.gazebosim.org/GoogleResearch). They were changed: placed in a resting
pose, uniformly scaled where `config/parts.yaml` says so, re-centred, and their textures resized
to at most 1024 px (`tools/fetch_objects.py`). Each part folder has a `LICENSE.txt` naming its
source. Candidates in `config/parts.yaml`:

| Slug | Scanned object |
|---|---|
| cup | Ecoforms_Cup_B4_SAN |
| ramekin | BIA_Porcelain_Ramekin_With_Glazed_Rim_35_45_oz_cup |
| ink_cartridge | Office_Depot_HP_71_Remanufactured_Ink_Cartridge_Black |
| android_figure | Android_Figure_Orange |
| triceratops | Great_Dinos_Triceratops_Toy |
| bull | Schleich_Hereford_Bull |
| rhino | Schleich_African_Black_Rhino |
| fire_truck | FIRE_TRUCK |
