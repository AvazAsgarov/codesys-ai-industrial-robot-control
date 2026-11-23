---
name: isa101-hmi
description: Use when designing, building or reviewing operator screens in CODESYS Visualization for this cell. Applies ISA-101 high-performance HMI and ISA-18.2 alarm rules, the project's screen list, grid and palette.
---

# ISA-101 HMI (this project)

Design: spec §9.

## Principles

- Neutral grey backgrounds; colour is reserved for abnormal states and alarms.
- Analog values are always shown with context (range, target, limits), never as bare numbers.
- Alarm colours follow ISA-18.2 priority (critical, high, medium, low) and are used for nothing else.
- Running/stopped equipment is shown by shape, text or fill level, not by red/green.
- One typeface, a fixed text-size scale, an 8 px spacing grid, a 1920×1080 canvas, also served as WebVisu.
- Consistent top bar (PackML state and mode, alarm banner, user) and navigation.

## Screens

1 Overview · 2 Robot · 3 Vision & AI · 4 Alarms · 5 Trends · 6 Recipes · 7 Production · 8 System.
Roles: Operator / Maintenance / Engineer (VisuUserMgmt).

## Workflow

1. Mock up with the CODESYS MCP tool (`hmi_template`, `hmi_save_screen`, `hmi_screenshot`).
2. Critique with the `impeccable` skill before building.
3. Build natively (`hmi_export_codesys`), then check it live in simulation.

Extended in phase P5 (exact palette values, symbol set, component specs).
