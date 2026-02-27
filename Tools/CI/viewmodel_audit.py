#!/usr/bin/env python
"""Parses Unity weapon diagnostics and emits a consumable JSON audit."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SUMMARY_PATTERN = re.compile(
    r"\[WEAPON]\[(?P<context>[^\]]+)]\s*"
    r"weapon=(?P<weapon>[^,]+),\s*"
    r"prefab=(?P<prefab>[^,]+),\s*"
    r"instance=(?P<instance>[^,]+),\s*"
    r"parent=(?P<parent>[^,]+),\s*"
    r"active=(?P<active>[^,]+),\s*"
    r"layer=(?P<layer_name>[^()]+)\((?P<layer_index>-?\d+)\),\s*"
    r"holder=(?P<holder>[^,]+),\s*"
    r"renderers=(?P<renderer_count>\d+)",
)

RENDERER_PATTERN = re.compile(
    r"\[WEAPON]\[(?P<context>[^\]]+)]\s*"
    r"renderer=(?P<renderer>[^,]+),\s*"
    r"enabled=(?P<enabled>[^,]+),\s*"
    r"goActive=(?P<go_active>[^,]+),\s*"
    r"layer=(?P<layer_name>[^()]+)\((?P<layer_index>-?\d+)\),\s*"
    r"materials=(?P<materials>.+)"
)

RENDERER_DETAIL_PATTERN = re.compile(
    r"\[WEAPON]\[(?P<context>[^\]]+)]\s*"
    r"weapon=(?P<weapon>[^,]+),\s*"
    r"path=(?P<path>[^,]+),\s*"
    r"name=(?P<name>[^,]+),\s*"
    r"type=(?P<renderer_type>[^,]+),\s*"
    r"enabled=(?P<enabled>[^,]+),\s*"
    r"goActive=(?P<go_active>[^,]+),\s*"
    r"layer=(?P<layer_name>[^()]+)\((?P<layer_index>-?\d+)\),\s*"
    r"sortingLayer=(?P<sorting_layer_name>[^()]+)\((?P<sorting_layer_id>-?\d+)\),\s*"
    r"sortingOrder=(?P<sorting_order>-?\d+),\s*"
    r"shadowCasting=(?P<shadow_casting>[^,]+),\s*"
    r"receiveShadows=(?P<receive_shadows>[^,]+),\s*"
    r"boundsCenter=(?P<bounds_center>\([^)]*\)),\s*"
    r"boundsExtents=(?P<bounds_extents>\([^)]*\)),\s*"
    r"materialCount=(?P<material_count>\d+)"
)

MATERIAL_DETAIL_PATTERN = re.compile(
    r"\[WEAPON]\[(?P<context>[^\]]+)]\s*"
    r"weapon=(?P<weapon>[^,]+),\s*"
    r"renderer=(?P<renderer>[^,]+),\s*"
    r"material=(?P<material>[^,]+),\s*"
    r"shader=(?P<shader>[^,]+),\s*"
    r"renderQueue=(?P<render_queue>-?\d+),\s*"
    r"hasColor=(?P<has_color>[^,]+),\s*"
    r"colorAlpha=(?P<color_alpha>[^,]+),\s*"
    r"surface=(?P<surface>[^,]+),\s*"
    r"alphaClip=(?P<alpha_clip>[^,]+),\s*"
    r"cutoff=(?P<cutoff>[^,]+),\s*"
    r"zwrite=(?P<zwrite>.+)"
)

WARNING_PATTERN = re.compile(r"\[WEAPON]\[(?P<context>[^\]]+)]\s*(?P<message>No Renderer components.+)")

CAMERA_PATTERN = re.compile(
    r"\[WEAPON]\[(?P<context>[^\]]+)]\s*"
    r"camera=(?P<camera>[^,]+),\s*"
    r"weapon=(?P<weapon>[^,]+),\s*"
    r"active=(?P<active>[^,]+),\s*"
    r"isMain=(?P<is_main>[^,]+),\s*"
    r"isViewmodel=(?P<is_viewmodel>[^,]+),\s*"
    r"nearClip=(?P<near_clip>[^,]+),\s*"
    r"fieldOfView=(?P<field_of_view>[^,]+),\s*"
    r"orthographic=(?P<orthographic>[^,]+),\s*"
    r"cullingIncludesViewmodel=(?P<culling>[^,]+),\s*"
    r"viewmodelLayer=(?P<layer_name>[^()]+)\((?P<layer_index>-?\d+)\),\s*"
    r"cullingMask=(?P<culling_mask>[^,]+),\s*"
    r"cullingLayers=(?P<culling_layers>[^,]+),\s*"
    r"includesRendererLayers=(?P<includes_renderer_layers>[^,]+),\s*"
    r"renderPath=(?P<render_path>[^,]+),\s*"
    r"distance=(?P<distance>[^,]+),\s*"
    r"relativeZ=(?P<relative_z>[^,]+),\s*"
    r"behindCamera=(?P<behind>[^,]+),\s*"
    r"renderType=(?P<render_type>.+)"
)

CAMERA_PATTERN_LEGACY = re.compile(
    r"\[WEAPON]\[(?P<context>[^\]]+)]\s*"
    r"camera=(?P<camera>[^,]+),\s*"
    r"weapon=(?P<weapon>[^,]+),\s*"
    r"active=(?P<active>[^,]+),\s*"
    r"isMain=(?P<is_main>[^,]+),\s*"
    r"isViewmodel=(?P<is_viewmodel>[^,]+),\s*"
    r"nearClip=(?P<near_clip>[^,]+),\s*"
    r"fieldOfView=(?P<field_of_view>[^,]+),\s*"
    r"orthographic=(?P<orthographic>[^,]+),\s*"
    r"cullingIncludesViewmodel=(?P<culling>[^,]+),\s*"
    r"viewmodelLayer=(?P<layer_name>[^()]+)\((?P<layer_index>-?\d+)\),\s*"
    r"cullingMask=(?P<culling_mask>[^,]+),\s*"
    r"renderPath=(?P<render_path>[^,]+),\s*"
    r"distance=(?P<distance>[^,]+),\s*"
    r"relativeZ=(?P<relative_z>[^,]+),\s*"
    r"behindCamera=(?P<behind>.+)"
)

TRANSFORM_PATTERN = re.compile(
    r"\[WEAPON]\[(?P<context>[^\]]+)]\s*"
    r"weapon=(?P<weapon>[^,]+),\s*"
    r"active=(?P<active>[^,]+),\s*"
    r"parent=(?P<parent>[^,]+),\s*"
    r"worldPos=(?P<world>\([^)]*\)),\s*"
    r"localPos=(?P<local>\([^)]*\)),\s*"
    r"localScale=(?P<scale>\([^)]*\)),\s*"
    r"localToMain=(?P<local_main>\([^)]*\)|[^,]+),\s*"
    r"distFromMain=(?P<distance>.+)"
)

HEURISTICS_PATTERN = re.compile(
    r"\[WEAPON]\[(?P<context>[^\]]+)]\s*weapon=(?P<weapon>[^,]+),\s*flags=(?P<flags>.+)"
)

RENDERERS_SUMMARY_PATTERN = re.compile(
    r"\[WEAPON]\[(?P<context>[^\]]+)]\s*"
    r"weapon=(?P<weapon>[^,]+),\s*"
    r"count=(?P<count>\d+),\s*"
    r"uniqueLayers=(?P<layers>[^,]+),\s*"
    r"anyDisabled=(?P<any_disabled>[^,]+),\s*"
    r"anyMaterialMissing=(?P<any_material_missing>[^,]+),\s*"
    r"anyAlphaZero=(?P<any_alpha_zero>.+)"
)

LAYERS_PATTERN = re.compile(
    r"\[WEAPON]\[(?P<context>[^\]]+)]\s*"
    r"weapon=(?P<weapon>[^,]+),\s*"
    r"rootLayer=(?P<root_layer>[^()]+)\((?P<root_index>-?\d+)\),\s*"
    r"cameraIncludesRoot=(?P<camera_includes_root>[^,]+),\s*"
    r"rendererLayersIncluded=(?P<renderer_layers_included>.+)"
)

PIPELINE_PATTERN = re.compile(
    r"\[WEAPON]\[(?P<context>[^\]]+)]\s*"
    r"hasPipeline=(?P<has_pipeline>[^,]+),\s*"
    r"pipelineAsset=(?P<pipeline_asset>[^,]+),\s*"
    r"pipelineType=(?P<pipeline_type>[^,]+),\s*"
    r"rendererAsset=(?P<renderer_asset>[^,]+),\s*"
    r"rendererType=(?P<renderer_type>[^,]+),\s*"
    r"referenceCamera=(?P<reference_camera>[^,]+),\s*"
    r"cameraRenderType=(?P<camera_render_type>.+)"
)

LAYER_TOKEN_PATTERN = re.compile(r"(?P<name>[^()]+)\((?P<index>-?\d+)\)")


@dataclass
class MaterialEntry:
    line: int
    context: str
    weapon: str
    renderer: str
    name: str
    shader: Optional[str]
    render_queue: Optional[int]
    has_color: Optional[bool]
    color_alpha: Optional[float]
    surface: Optional[float]
    alpha_clip: Optional[float]
    cutoff: Optional[float]
    zwrite: Optional[float]


@dataclass
class RendererEntry:
    line: int
    context: str
    weapon: str
    name: str
    path: Optional[str]
    renderer_type: Optional[str]
    enabled: bool
    go_active: bool
    layer_name: str
    layer_index: int
    sorting_layer_name: Optional[str]
    sorting_layer_id: Optional[int]
    sorting_order: Optional[int]
    shadow_casting: Optional[str]
    receive_shadows: Optional[bool]
    bounds_center: Optional[List[float]]
    bounds_extents: Optional[List[float]]
    material_count: Optional[int]
    materials: List[MaterialEntry] = field(default_factory=list)


@dataclass
class CameraEntry:
    line: int
    context: str
    weapon: str
    name: str
    active: bool
    is_main: bool
    is_viewmodel: bool
    near_clip: float
    field_of_view: float
    orthographic: bool
    culling_includes_viewmodel: bool
    culling_includes_renderer_layers: bool
    culling_mask_raw: str
    culling_mask_value: int
    culling_layers: List[str]
    render_path: str
    layer_name: str
    layer_index: int
    render_type: Optional[str]
    distance: float
    relative_z: float
    behind_camera: bool


@dataclass
class TransformEntry:
    line: int
    context: str
    weapon: str
    active: bool
    parent: str
    world_position: List[float]
    local_position: List[float]
    local_scale: List[float]
    local_to_main: Optional[List[float]]
    dist_from_main: Optional[float]


@dataclass
class WeaponEntry:
    line: int
    context: str
    weapon: str
    prefab: str
    instance: str
    parent: str
    active: bool
    layer_name: str
    layer_index: int
    holder: str
    renderer_count: int
    renderers: List[RendererEntry] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    cameras: List[CameraEntry] = field(default_factory=list)
    transform: Optional[TransformEntry] = None
    heuristics: List[str] = field(default_factory=list)
    renderer_summary: Optional["RendererSummary"] = None
    layers_summary: Optional["LayerSummary"] = None


@dataclass
class RendererSummary:
    line: int
    context: str
    count: int
    unique_layers: List[Dict[str, object]]
    any_disabled: bool
    any_material_missing: bool
    any_alpha_zero: bool


@dataclass
class LayerSummary:
    line: int
    context: str
    root_layer_name: str
    root_layer_index: int
    camera_includes_root: bool
    renderer_layers_included: bool


@dataclass
class PipelineInfo:
    line: int
    context: str
    has_pipeline: bool
    pipeline_asset: str
    pipeline_type: str
    renderer_asset: str
    renderer_type: str
    reference_camera: str
    camera_render_type: str


TRUTHY = {"true", "1", "yes", "on"}
FALSY = {"false", "0", "no", "off"}


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in TRUTHY:
        return True
    if lowered in FALSY:
        return False
    return value.strip().lower() not in {"<null>", "none", ""}


def parse_float(value: str) -> float:
    return float(value.strip())


def parse_optional_float(value: str) -> Optional[float]:
    text = value.strip()
    if text.lower() in {"<none>", "none", "null", ""}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_vector(value: str) -> List[float]:
    cleaned = value.strip().strip("()")
    if not cleaned:
        return [0.0, 0.0, 0.0]
    parts = [part.strip() for part in cleaned.split(",")]
    return [float(part) for part in parts if part]


def parse_optional_vector(value: str) -> Optional[List[float]]:
    text = value.strip()
    if text.lower() in {"<none>", "none", "null", ""}:
        return None
    return parse_vector(text)


def find_entry_for_weapon(entries: List[WeaponEntry], weapon_name: str, fallback: Optional[WeaponEntry]) -> Optional[WeaponEntry]:
    if weapon_name:
        normalized = weapon_name.strip().lower()
        for entry in reversed(entries):
            if entry.weapon.strip().lower() == normalized:
                return entry
    return fallback


def find_renderer_entry(entries: List[WeaponEntry], weapon_name: str, renderer_name: str) -> Optional[RendererEntry]:
    if not weapon_name or not renderer_name:
        return None

    normalized_weapon = weapon_name.strip().lower()
    normalized_renderer = renderer_name.strip().lower()
    for entry in reversed(entries):
        if entry.weapon.strip().lower() != normalized_weapon:
            continue
        for renderer in reversed(entry.renderers):
            if renderer.name.strip().lower() == normalized_renderer:
                return renderer
    return None


def parse_layer_token(token: str) -> Dict[str, object]:
    text = token.strip()
    if not text:
        return {"name": "<none>", "index": None}

    match = LAYER_TOKEN_PATTERN.match(text)
    if match:
        return {
            "name": match.group("name").strip(),
            "index": int(match.group("index")),
        }

    return {"name": text, "index": None}


def parse_layer_list(value: str) -> List[Dict[str, object]]:
    text = value.strip()
    if not text or text.lower() in {"<none>", "none"}:
        return []

    tokens = [token.strip() for token in text.split("|") if token.strip()]
    return [parse_layer_token(token) for token in tokens]


def split_layer_tokens(value: str) -> List[str]:
    text = value.strip()
    if not text or text.lower() in {"<none>", "none"}:
        return []
    return [token.strip() for token in text.split("|") if token.strip()]


def parse_log(log_path: Path) -> Tuple[List[WeaponEntry], Optional[PipelineInfo]]:
    entries: List[WeaponEntry] = []
    current: Optional[WeaponEntry] = None
    pipeline_info: Optional[PipelineInfo] = None

    with log_path.open(encoding="utf-8", errors="ignore") as stream:
        for line_no, raw_line in enumerate(stream, start=1):
            line = raw_line.strip()
            if "[WEAPON]" not in line:
                continue

            summary = SUMMARY_PATTERN.search(line)
            if summary:
                current = WeaponEntry(
                    line=line_no,
                    context=summary.group("context").strip(),
                    weapon=summary.group("weapon").strip(),
                    prefab=summary.group("prefab").strip(),
                    instance=summary.group("instance").strip(),
                    parent=summary.group("parent").strip(),
                    active=parse_bool(summary.group("active")),
                    layer_name=summary.group("layer_name").strip(),
                    layer_index=int(summary.group("layer_index")),
                    holder=summary.group("holder").strip(),
                    renderer_count=int(summary.group("renderer_count")),
                )
                entries.append(current)
                continue

            renderer_detail = RENDERER_DETAIL_PATTERN.search(line)
            if renderer_detail:
                weapon_name = renderer_detail.group("weapon").strip()
                target = find_entry_for_weapon(entries, weapon_name, current)
                if target:
                    renderer_entry = RendererEntry(
                        line=line_no,
                        context=renderer_detail.group("context").strip(),
                        weapon=weapon_name,
                        name=renderer_detail.group("name").strip(),
                        path=renderer_detail.group("path").strip(),
                        renderer_type=renderer_detail.group("renderer_type").strip(),
                        enabled=parse_bool(renderer_detail.group("enabled")),
                        go_active=parse_bool(renderer_detail.group("go_active")),
                        layer_name=renderer_detail.group("layer_name").strip(),
                        layer_index=int(renderer_detail.group("layer_index")),
                        sorting_layer_name=renderer_detail.group("sorting_layer_name").strip(),
                        sorting_layer_id=int(renderer_detail.group("sorting_layer_id")),
                        sorting_order=int(renderer_detail.group("sorting_order")),
                        shadow_casting=renderer_detail.group("shadow_casting").strip(),
                        receive_shadows=parse_bool(renderer_detail.group("receive_shadows")),
                        bounds_center=parse_vector(renderer_detail.group("bounds_center")),
                        bounds_extents=parse_vector(renderer_detail.group("bounds_extents")),
                        material_count=int(renderer_detail.group("material_count")),
                    )
                    target.renderers.append(renderer_entry)
                continue

            material_detail = MATERIAL_DETAIL_PATTERN.search(line)
            if material_detail:
                weapon_name = material_detail.group("weapon").strip()
                renderer_name = material_detail.group("renderer").strip()
                renderer_entry = find_renderer_entry(entries, weapon_name, renderer_name)
                if renderer_entry:
                    renderer_entry.materials.append(
                        MaterialEntry(
                            line=line_no,
                            context=material_detail.group("context").strip(),
                            weapon=weapon_name,
                            renderer=renderer_name,
                            name=material_detail.group("material").strip(),
                            shader=material_detail.group("shader").strip(),
                            render_queue=int(material_detail.group("render_queue")),
                            has_color=parse_bool(material_detail.group("has_color")),
                            color_alpha=parse_optional_float(material_detail.group("color_alpha")),
                            surface=parse_optional_float(material_detail.group("surface")),
                            alpha_clip=parse_optional_float(material_detail.group("alpha_clip")),
                            cutoff=parse_optional_float(material_detail.group("cutoff")),
                            zwrite=parse_optional_float(material_detail.group("zwrite")),
                        )
                    )
                continue

            renderers_summary = RENDERERS_SUMMARY_PATTERN.search(line)
            if renderers_summary:
                weapon_name = renderers_summary.group("weapon").strip()
                target = find_entry_for_weapon(entries, weapon_name, current)
                if target:
                    target.renderer_summary = RendererSummary(
                        line=line_no,
                        context=renderers_summary.group("context").strip(),
                        count=int(renderers_summary.group("count")),
                        unique_layers=parse_layer_list(renderers_summary.group("layers")),
                        any_disabled=parse_bool(renderers_summary.group("any_disabled")),
                        any_material_missing=parse_bool(renderers_summary.group("any_material_missing")),
                        any_alpha_zero=parse_bool(renderers_summary.group("any_alpha_zero")),
                    )
                continue

            layers_summary = LAYERS_PATTERN.search(line)
            if layers_summary:
                weapon_name = layers_summary.group("weapon").strip()
                target = find_entry_for_weapon(entries, weapon_name, current)
                if target:
                    target.layers_summary = LayerSummary(
                        line=line_no,
                        context=layers_summary.group("context").strip(),
                        root_layer_name=layers_summary.group("root_layer").strip(),
                        root_layer_index=int(layers_summary.group("root_index")),
                        camera_includes_root=parse_bool(layers_summary.group("camera_includes_root")),
                        renderer_layers_included=parse_bool(layers_summary.group("renderer_layers_included")),
                    )
                continue

            pipeline_match = PIPELINE_PATTERN.search(line)
            if pipeline_match and pipeline_info is None:
                pipeline_info = PipelineInfo(
                    line=line_no,
                    context=pipeline_match.group("context").strip(),
                    has_pipeline=parse_bool(pipeline_match.group("has_pipeline")),
                    pipeline_asset=pipeline_match.group("pipeline_asset").strip(),
                    pipeline_type=pipeline_match.group("pipeline_type").strip(),
                    renderer_asset=pipeline_match.group("renderer_asset").strip(),
                    renderer_type=pipeline_match.group("renderer_type").strip(),
                    reference_camera=pipeline_match.group("reference_camera").strip(),
                    camera_render_type=pipeline_match.group("camera_render_type").strip(),
                )
                continue

            warning = WARNING_PATTERN.search(line)
            if warning and current is not None:
                current.notes.append(warning.group("message").strip())

            camera = CAMERA_PATTERN.search(line)
            legacy_camera = False
            if camera is None:
                camera = CAMERA_PATTERN_LEGACY.search(line)
                legacy_camera = camera is not None

            if camera:
                weapon_name = camera.group("weapon").strip()
                target = find_entry_for_weapon(entries, weapon_name, current)
                if target:
                    mask_raw = camera.group("culling_mask").strip()
                    mask_value = 0
                    mask_text = mask_raw.lower()
                    try:
                        if mask_text.startswith("0x"):
                            mask_value = int(mask_text, 16)
                        else:
                            mask_value = int(mask_raw)
                    except ValueError:
                        mask_value = 0

                    target.cameras.append(
                        CameraEntry(
                            line=line_no,
                            context=camera.group("context").strip(),
                            weapon=weapon_name,
                            name=camera.group("camera").strip(),
                            active=parse_bool(camera.group("active")),
                            is_main=parse_bool(camera.group("is_main")),
                            is_viewmodel=parse_bool(camera.group("is_viewmodel")),
                            near_clip=parse_float(camera.group("near_clip")),
                            field_of_view=parse_float(camera.group("field_of_view")),
                            orthographic=parse_bool(camera.group("orthographic")),
                            culling_includes_viewmodel=parse_bool(camera.group("culling")),
                            culling_includes_renderer_layers=parse_bool(camera.group("includes_renderer_layers")) if not legacy_camera else False,
                            culling_mask_raw=mask_raw,
                            culling_mask_value=mask_value,
                            culling_layers=split_layer_tokens(camera.group("culling_layers")) if not legacy_camera else [],
                            render_path=camera.group("render_path").strip(),
                            layer_name=camera.group("layer_name").strip(),
                            layer_index=int(camera.group("layer_index")),
                            render_type=camera.group("render_type").strip() if not legacy_camera else "pipeline_unknown",
                            distance=parse_float(camera.group("distance")),
                            relative_z=parse_float(camera.group("relative_z")),
                            behind_camera=parse_bool(camera.group("behind")),
                        )
                    )
                continue

            transform_match = TRANSFORM_PATTERN.search(line)
            if transform_match:
                target = find_entry_for_weapon(entries, transform_match.group("weapon"), current)
                if target:
                    target.transform = TransformEntry(
                        line=line_no,
                        context=transform_match.group("context"),
                        weapon=transform_match.group("weapon"),
                        active=parse_bool(transform_match.group("active")),
                        parent=transform_match.group("parent"),
                        world_position=parse_vector(transform_match.group("world")),
                        local_position=parse_vector(transform_match.group("local")),
                        local_scale=parse_vector(transform_match.group("scale")),
                        local_to_main=parse_optional_vector(transform_match.group("local_main")),
                        dist_from_main=parse_optional_float(transform_match.group("distance")),
                    )
                continue

            heuristic_match = HEURISTICS_PATTERN.search(line)
            if heuristic_match:
                target = find_entry_for_weapon(entries, heuristic_match.group("weapon"), current)
                if target:
                    raw_flags = [flag.strip() for flag in heuristic_match.group("flags").split("|")]
                    target.heuristics = [flag for flag in raw_flags if flag and flag.lower() != "<none>"]
                continue

            renderer_legacy = RENDERER_PATTERN.search(line)
            if renderer_legacy and current is not None:
                material_names = [piece.strip() for piece in renderer_legacy.group("materials").split("|")]
                entry = RendererEntry(
                    line=line_no,
                    context=renderer_legacy.group("context").strip(),
                    weapon=current.weapon,
                    name=renderer_legacy.group("renderer").strip(),
                    path=None,
                    renderer_type=None,
                    enabled=parse_bool(renderer_legacy.group("enabled")),
                    go_active=parse_bool(renderer_legacy.group("go_active")),
                    layer_name=renderer_legacy.group("layer_name").strip(),
                    layer_index=int(renderer_legacy.group("layer_index")),
                    sorting_layer_name=None,
                    sorting_layer_id=None,
                    sorting_order=None,
                    shadow_casting=None,
                    receive_shadows=None,
                    bounds_center=None,
                    bounds_extents=None,
                    material_count=None,
                )
                for material_name in material_names:
                    entry.materials.append(
                        MaterialEntry(
                            line=line_no,
                            context=renderer_legacy.group("context"),
                            weapon=current.weapon,
                            renderer=entry.name,
                            name=material_name,
                            shader=None,
                            render_queue=None,
                            has_color=None,
                            color_alpha=None,
                            surface=None,
                            alpha_clip=None,
                            cutoff=None,
                            zwrite=None,
                        )
                    )
                current.renderers.append(entry)
                continue

    return entries, pipeline_info


def analyze(entries: List[WeaponEntry]) -> Dict[str, object]:
    warnings: List[str] = []
    if not entries:
        warnings.append("No [WEAPON] diagnostics were found in the provided log.")
        return {"weapons": [], "warnings": warnings, "drift": [], "issue_counts": {}}

    issue_counter: Counter[str] = Counter()
    grouped: Dict[str, List[WeaponEntry]] = defaultdict(list)

    for entry in entries:
        key = entry.weapon.strip().lower()
        grouped[key].append(entry)
        evaluate_entry(entry, issue_counter)

    drift_reports: List[Dict[str, object]] = []
    for weapon_key, weapon_entries in grouped.items():
        weapon_entries.sort(key=lambda item: item.line)
        baseline = weapon_entries[0]
        for comparison in weapon_entries[1:]:
            deltas = []
            if comparison.layer_index != baseline.layer_index:
                deltas.append("layer_index")
            if comparison.renderer_count != baseline.renderer_count:
                deltas.append("renderer_count")
            if comparison.holder != baseline.holder:
                deltas.append("holder")
            if deltas:
                drift_reports.append(
                    {
                        "weapon": baseline.weapon,
                        "baseline_line": baseline.line,
                        "comparison_line": comparison.line,
                        "differences": deltas,
                    }
                )

    return {
        "weapons": [entry_to_dict(item) for item in entries],
        "warnings": warnings,
        "drift": drift_reports,
        "issue_counts": dict(issue_counter),
    }


def evaluate_entry(entry: WeaponEntry, counter: Counter[str]) -> None:
    prefab_missing = entry.prefab.lower() in {"<null>", "null", "none", "<none>"}
    if prefab_missing:
        entry.issues.append("prefab_missing")
        counter["prefab_missing"] += 1

    if entry.renderer_count == 0 or not entry.renderers:
        entry.issues.append("no_renderers")
        counter["no_renderers"] += 1

    disabled = [rend for rend in entry.renderers if not (rend.enabled and rend.go_active)]
    if disabled:
        entry.issues.append("renderer_disabled")
        counter["renderer_disabled"] += 1

    mismatch = [rend for rend in entry.renderers if rend.layer_index != entry.layer_index]
    if mismatch:
        entry.issues.append("layer_mismatch")
        counter["layer_mismatch"] += 1

    if entry.notes:
        entry.issues.append("log_warnings")
        counter["log_warnings"] += 1


def entry_to_dict(entry: WeaponEntry) -> Dict[str, object]:
    return {
        "line": entry.line,
        "context": entry.context,
        "weapon": entry.weapon,
        "prefab": entry.prefab,
        "instance": entry.instance,
        "parent": entry.parent,
        "active": entry.active,
        "layer": {"name": entry.layer_name, "index": entry.layer_index},
        "holder": entry.holder,
        "renderer_count": entry.renderer_count,
        "renderers": [renderer_to_dict(renderer) for renderer in entry.renderers],
        "notes": entry.notes,
        "issues": entry.issues,
        "transform": transform_to_dict(entry.transform),
        "cameras": [camera_to_dict(camera) for camera in entry.cameras],
        "heuristics": entry.heuristics,
        "renderer_summary": renderer_summary_to_dict(entry.renderer_summary),
        "layers_summary": layer_summary_to_dict(entry.layers_summary),
    }


def camera_to_dict(camera: CameraEntry) -> Dict[str, object]:
    return {
        "line": camera.line,
        "context": camera.context,
        "weapon": camera.weapon,
        "name": camera.name,
        "active": camera.active,
        "is_main": camera.is_main,
        "is_viewmodel": camera.is_viewmodel,
        "near_clip": camera.near_clip,
        "field_of_view": camera.field_of_view,
        "orthographic": camera.orthographic,
        "culling_includes_viewmodel": camera.culling_includes_viewmodel,
        "culling_includes_renderer_layers": camera.culling_includes_renderer_layers,
        "culling_mask": {
            "raw": camera.culling_mask_raw,
            "value": camera.culling_mask_value,
        },
        "culling_mask_layers": camera.culling_layers,
        "layer": {"name": camera.layer_name, "index": camera.layer_index},
        "render_path": camera.render_path,
        "render_type": camera.render_type,
        "distance": camera.distance,
        "relative_z": camera.relative_z,
        "behind_camera": camera.behind_camera,
    }


def renderer_to_dict(renderer: RendererEntry) -> Dict[str, object]:
    return {
        "line": renderer.line,
        "context": renderer.context,
        "weapon": renderer.weapon,
        "name": renderer.name,
        "path": renderer.path,
        "type": renderer.renderer_type,
        "enabled": renderer.enabled,
        "go_active": renderer.go_active,
        "layer": {"name": renderer.layer_name, "index": renderer.layer_index},
        "sorting_layer": {
            "name": renderer.sorting_layer_name,
            "id": renderer.sorting_layer_id,
        }
        if renderer.sorting_layer_name is not None or renderer.sorting_layer_id is not None
        else None,
        "sorting_order": renderer.sorting_order,
        "shadow_casting": renderer.shadow_casting,
        "receive_shadows": renderer.receive_shadows,
        "bounds": {
            "center": renderer.bounds_center,
            "extents": renderer.bounds_extents,
        }
        if renderer.bounds_center is not None or renderer.bounds_extents is not None
        else None,
        "material_count": renderer.material_count,
        "materials": [material_to_dict(material) for material in renderer.materials],
    }


def material_to_dict(material: MaterialEntry) -> Dict[str, object]:
    return {
        "line": material.line,
        "context": material.context,
        "weapon": material.weapon,
        "renderer": material.renderer,
        "name": material.name,
        "shader": material.shader,
        "render_queue": material.render_queue,
        "has_color": material.has_color,
        "color_alpha": material.color_alpha,
        "surface": material.surface,
        "alpha_clip": material.alpha_clip,
        "cutoff": material.cutoff,
        "zwrite": material.zwrite,
    }


def renderer_summary_to_dict(summary: Optional[RendererSummary]) -> Optional[Dict[str, object]]:
    if summary is None:
        return None
    return {
        "line": summary.line,
        "context": summary.context,
        "count": summary.count,
        "unique_layers": summary.unique_layers,
        "any_disabled": summary.any_disabled,
        "any_material_missing": summary.any_material_missing,
        "any_alpha_zero": summary.any_alpha_zero,
    }


def layer_summary_to_dict(summary: Optional[LayerSummary]) -> Optional[Dict[str, object]]:
    if summary is None:
        return None
    return {
        "line": summary.line,
        "context": summary.context,
        "root_layer": {"name": summary.root_layer_name, "index": summary.root_layer_index},
        "camera_includes_root": summary.camera_includes_root,
        "renderer_layers_included": summary.renderer_layers_included,
    }


def transform_to_dict(transform: Optional[TransformEntry]) -> Optional[Dict[str, object]]:
    if transform is None:
        return None
    return {
        "line": transform.line,
        "context": transform.context,
        "weapon": transform.weapon,
        "active": transform.active,
        "parent": transform.parent,
        "world_position": transform.world_position,
        "local_position": transform.local_position,
        "local_scale": transform.local_scale,
        "local_to_main": transform.local_to_main,
        "dist_from_main": transform.dist_from_main,
    }


def pipeline_to_dict(pipeline: Optional[PipelineInfo]) -> Optional[Dict[str, object]]:
    if pipeline is None:
        return None

    return {
        "line": pipeline.line,
        "context": pipeline.context,
        "has_pipeline": pipeline.has_pipeline,
        "pipeline_asset": pipeline.pipeline_asset,
        "pipeline_type": pipeline.pipeline_type,
        "renderer_asset": pipeline.renderer_asset,
        "renderer_type": pipeline.renderer_type,
        "reference_camera": pipeline.reference_camera,
        "camera_render_type": pipeline.camera_render_type,
    }


def build_output_structure(log_path: Path, entries: List[WeaponEntry], pipeline: Optional[PipelineInfo]) -> Dict[str, object]:
    analysis = analyze(entries)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stats = log_path.stat()
    return {
        "generated_at": generated_at,
        "log_path": str(log_path),
        "log_size_bytes": stats.st_size,
        "weapons": analysis["weapons"],
        "warnings": analysis["warnings"],
        "drift": analysis["drift"],
        "issue_counts": analysis["issue_counts"],
        "pipeline": pipeline_to_dict(pipeline),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a viewmodel audit from Unity Editor logs.")
    parser.add_argument(
        "--log",
        default="scripts/logs/Editor.log",
        help="Path to the Unity Editor log relative to the orchestrator root.",
    )
    parser.add_argument(
        "--output",
        default="Tools/CI/viewmodel_audit.json",
        help="Where to write the resulting JSON report (relative to root).",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    log_path = (root / args.log).resolve()
    if not log_path.exists():
        raise FileNotFoundError(f"Unity log not found: {log_path}")

    entries, pipeline = parse_log(log_path)
    payload = build_output_structure(log_path, entries, pipeline)

    output_path = (root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")

    print(f"[viewmodel-audit] Processed {len(entries)} weapon diagnostics -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
