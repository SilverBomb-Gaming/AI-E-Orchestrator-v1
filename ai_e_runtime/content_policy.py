from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping

from orchestrator.config import OrchestratorConfig
from orchestrator.utils import ensure_dir, read_json, write_json


CONTENT_MODE_GAME_DEV = "GAME_DEV"
DEFAULT_PROFILE_PAYLOAD = {
    "content_mode": CONTENT_MODE_GAME_DEV,
    "rating_system": "ESRB",
    "rating_target": "M",
    "rating_locked": True,
}
CONTENT_DIMENSION_KEYS = (
    "violence_level",
    "blood_level",
    "gore_level",
    "horror_intensity",
    "language_level",
    "sexual_content_level",
    "nudity_level",
    "substance_reference_level",
    "gambling_reference_level",
)
LEVEL_VALUES = ("none", "mild", "moderate", "intense", "extreme")
LEVEL_RANK = {level: index for index, level in enumerate(LEVEL_VALUES)}
INTERNAL_TIERS = ("ALL_AGES", "YOUTH", "TEEN", "MATURE", "ADULT_ONLY")
INTERNAL_TIER_RANK = {tier: index for index, tier in enumerate(INTERNAL_TIERS)}
RATING_SYSTEMS: Dict[str, Dict[str, str]] = {
    "ESRB": {
        "RP": "ALL_AGES",
        "E": "ALL_AGES",
        "E10+": "YOUTH",
        "T": "TEEN",
        "M": "MATURE",
        "AO": "ADULT_ONLY",
    },
    "PEGI": {
        "3": "ALL_AGES",
        "7": "YOUTH",
        "12": "TEEN",
        "16": "MATURE",
        "18": "ADULT_ONLY",
    },
    "USK": {
        "0": "ALL_AGES",
        "6": "YOUTH",
        "12": "TEEN",
        "16": "MATURE",
        "18": "ADULT_ONLY",
    },
    "CERO": {
        "A": "ALL_AGES",
        "B": "YOUTH",
        "C": "TEEN",
        "D": "MATURE",
        "Z": "ADULT_ONLY",
    },
}
DEFAULT_RATING_BY_TIER = {
    "ESRB": {
        "ALL_AGES": "E",
        "YOUTH": "E10+",
        "TEEN": "T",
        "MATURE": "M",
        "ADULT_ONLY": "AO",
    },
    "PEGI": {
        "ALL_AGES": "3",
        "YOUTH": "7",
        "TEEN": "12",
        "MATURE": "16",
        "ADULT_ONLY": "18",
    },
    "USK": {
        "ALL_AGES": "0",
        "YOUTH": "6",
        "TEEN": "12",
        "MATURE": "16",
        "ADULT_ONLY": "18",
    },
    "CERO": {
        "ALL_AGES": "A",
        "YOUTH": "B",
        "TEEN": "C",
        "MATURE": "D",
        "ADULT_ONLY": "Z",
    },
}
DIMENSION_TIER_REQUIREMENTS = {
    "violence_level": {"none": "ALL_AGES", "mild": "YOUTH", "moderate": "TEEN", "intense": "MATURE", "extreme": "MATURE"},
    "blood_level": {"none": "ALL_AGES", "mild": "YOUTH", "moderate": "TEEN", "intense": "MATURE", "extreme": "MATURE"},
    "gore_level": {"none": "ALL_AGES", "mild": "TEEN", "moderate": "MATURE", "intense": "MATURE", "extreme": "MATURE"},
    "horror_intensity": {"none": "ALL_AGES", "mild": "YOUTH", "moderate": "TEEN", "intense": "MATURE", "extreme": "MATURE"},
    "language_level": {"none": "ALL_AGES", "mild": "YOUTH", "moderate": "TEEN", "intense": "MATURE", "extreme": "MATURE"},
    "sexual_content_level": {"none": "ALL_AGES", "mild": "TEEN", "moderate": "MATURE", "intense": "ADULT_ONLY", "extreme": "ADULT_ONLY"},
    "nudity_level": {"none": "ALL_AGES", "mild": "TEEN", "moderate": "MATURE", "intense": "ADULT_ONLY", "extreme": "ADULT_ONLY"},
    "substance_reference_level": {"none": "ALL_AGES", "mild": "TEEN", "moderate": "MATURE", "intense": "MATURE", "extreme": "MATURE"},
    "gambling_reference_level": {"none": "ALL_AGES", "mild": "TEEN", "moderate": "MATURE", "intense": "MATURE", "extreme": "MATURE"},
}
BOOLEAN_TIER_REQUIREMENTS = {"dismemberment": "MATURE"}


@dataclass(frozen=True)
class ProjectContentProfile:
    content_mode: str
    rating_system: str
    rating_target: str
    rating_locked: bool

    def to_payload(self) -> Dict[str, Any]:
        return {
            "content_mode": self.content_mode,
            "rating_system": self.rating_system,
            "rating_target": self.rating_target,
            "rating_locked": self.rating_locked,
        }

    @property
    def internal_rating_tier(self) -> str | None:
        system = RATING_SYSTEMS.get(self.rating_system)
        if system is None:
            return None
        return system.get(self.rating_target)

    @staticmethod
    def from_payload(payload: Mapping[str, Any]) -> "ProjectContentProfile":
        content_mode = str(payload.get("content_mode") or CONTENT_MODE_GAME_DEV).upper()
        rating_system = str(payload.get("rating_system") or "ESRB").upper()
        raw_target = payload.get("rating_target") or DEFAULT_PROFILE_PAYLOAD["rating_target"]
        rating_target = str(raw_target).upper() if rating_system in {"ESRB", "CERO"} else str(raw_target)
        return ProjectContentProfile(
            content_mode=content_mode,
            rating_system=rating_system,
            rating_target=rating_target,
            rating_locked=bool(payload.get("rating_locked", True)),
        )


@dataclass(frozen=True)
class ContentPolicyAssessment:
    rating_system: str
    rating_target: str
    rating_locked: bool
    content_policy_match: str
    content_policy_decision: str
    required_rating_upgrade: str | None
    requested_content_dimensions: Dict[str, Any]
    summary: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "rating_system": self.rating_system,
            "rating_target": self.rating_target,
            "rating_locked": self.rating_locked,
            "content_policy_match": self.content_policy_match,
            "content_policy_decision": self.content_policy_decision,
            "required_rating_upgrade": self.required_rating_upgrade,
            "requested_content_dimensions": dict(self.requested_content_dimensions),
            "summary": self.summary,
        }


def project_content_profile_path(config: OrchestratorConfig) -> Path:
    return config.contracts_dir / "content_policy" / "project_content_profile.json"


def load_project_content_profile(config: OrchestratorConfig) -> ProjectContentProfile:
    payload = read_json(project_content_profile_path(config), default=DEFAULT_PROFILE_PAYLOAD)
    return ProjectContentProfile.from_payload(payload)


def load_profile(config: OrchestratorConfig) -> ProjectContentProfile:
    return load_project_content_profile(config)


def ensure_project_content_profile(config: OrchestratorConfig) -> Path:
    path = project_content_profile_path(config)
    ensure_dir(path.parent)
    if not path.exists():
        save_profile(config, ProjectContentProfile.from_payload(DEFAULT_PROFILE_PAYLOAD))
    return path


def save_profile(config: OrchestratorConfig, profile: ProjectContentProfile) -> Path:
    _validate_profile(profile)
    path = project_content_profile_path(config)
    ensure_dir(path.parent)
    _write_atomic_json(path, profile.to_payload())
    return path


def update_rating_target(config: OrchestratorConfig, rating_target: str) -> ProjectContentProfile:
    profile = load_profile(config)
    normalized = _normalize_rating_target(profile.rating_system, rating_target)
    if normalized not in RATING_SYSTEMS.get(profile.rating_system, {}):
        allowed = ", ".join(RATING_SYSTEMS.get(profile.rating_system, {}).keys())
        raise ValueError(f"Rating target '{rating_target}' is not valid for {profile.rating_system}. Allowed values: {allowed}.")
    updated = ProjectContentProfile(
        content_mode=profile.content_mode,
        rating_system=profile.rating_system,
        rating_target=normalized,
        rating_locked=profile.rating_locked,
    )
    save_profile(config, updated)
    return updated


def update_rating_lock(config: OrchestratorConfig, locked: bool) -> ProjectContentProfile:
    profile = load_profile(config)
    updated = ProjectContentProfile(
        content_mode=profile.content_mode,
        rating_system=profile.rating_system,
        rating_target=profile.rating_target,
        rating_locked=bool(locked),
    )
    save_profile(config, updated)
    return updated


def evaluate_content_policy(
    prompt: str,
    *,
    profile: ProjectContentProfile,
    capability_tags: Mapping[str, Any] | None = None,
) -> ContentPolicyAssessment:
    if profile.content_mode != CONTENT_MODE_GAME_DEV:
        return ContentPolicyAssessment(
            rating_system=profile.rating_system,
            rating_target=profile.rating_target,
            rating_locked=profile.rating_locked,
            content_policy_match="out_of_scope",
            content_policy_decision="blocked",
            required_rating_upgrade=None,
            requested_content_dimensions={},
            summary="Content Policy Layer v1 only evaluates GAME_DEV workflows.",
        )

    target_tier = profile.internal_rating_tier
    if target_tier is None:
        return ContentPolicyAssessment(
            rating_system=profile.rating_system,
            rating_target=profile.rating_target,
            rating_locked=profile.rating_locked,
            content_policy_match="requires_review",
            content_policy_decision="requires_review",
            required_rating_upgrade=None,
            requested_content_dimensions={},
            summary="Project content profile uses an unmapped rating target and requires operator review.",
        )

    requested_dimensions = _merge_content_dimensions(
        _infer_prompt_content_dimensions(prompt),
        _normalize_content_dimensions(capability_tags),
    )
    compact_dimensions = _compact_content_dimensions(requested_dimensions)
    required_tier = _required_internal_tier(requested_dimensions)

    if INTERNAL_TIER_RANK[required_tier] <= INTERNAL_TIER_RANK[target_tier]:
        return ContentPolicyAssessment(
            rating_system=profile.rating_system,
            rating_target=profile.rating_target,
            rating_locked=profile.rating_locked,
            content_policy_match="fits_rating",
            content_policy_decision="allowed",
            required_rating_upgrade=None,
            requested_content_dimensions=compact_dimensions,
            summary=f"Requested content fits the {profile.rating_system} {profile.rating_target} project target.",
        )

    required_upgrade = DEFAULT_RATING_BY_TIER.get(profile.rating_system, {}).get(required_tier)
    if profile.rating_locked:
        return ContentPolicyAssessment(
            rating_system=profile.rating_system,
            rating_target=profile.rating_target,
            rating_locked=profile.rating_locked,
            content_policy_match="exceeds_rating",
            content_policy_decision="blocked",
            required_rating_upgrade=required_upgrade,
            requested_content_dimensions=compact_dimensions,
            summary=(
                f"Requested content exceeds the locked {profile.rating_system} {profile.rating_target} target"
                + (f" and requires upgrade to {required_upgrade}." if required_upgrade else ".")
            ),
        )
    return ContentPolicyAssessment(
        rating_system=profile.rating_system,
        rating_target=profile.rating_target,
        rating_locked=profile.rating_locked,
        content_policy_match="exceeds_rating",
        content_policy_decision="requires_review",
        required_rating_upgrade=required_upgrade,
        requested_content_dimensions=compact_dimensions,
        summary=(
            f"Requested content exceeds the current {profile.rating_system} {profile.rating_target} target"
            + (f" and would require upgrade to {required_upgrade}." if required_upgrade else ".")
        ),
    )


def _required_internal_tier(content_dimensions: Mapping[str, Any]) -> str:
    required = "ALL_AGES"
    for key in CONTENT_DIMENSION_KEYS:
        tier = DIMENSION_TIER_REQUIREMENTS[key][_normalize_level(content_dimensions.get(key))]
        if INTERNAL_TIER_RANK[tier] > INTERNAL_TIER_RANK[required]:
            required = tier
    for key, tier in BOOLEAN_TIER_REQUIREMENTS.items():
        if bool(content_dimensions.get(key, False)) and INTERNAL_TIER_RANK[tier] > INTERNAL_TIER_RANK[required]:
            required = tier
    return required


def _normalize_content_dimensions(payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {key: "none" for key in CONTENT_DIMENSION_KEYS}
    normalized["dismemberment"] = False
    if payload is None:
        return normalized
    for key in CONTENT_DIMENSION_KEYS:
        if key in payload:
            normalized[key] = _normalize_level(payload.get(key))
    if "dismemberment" in payload:
        normalized["dismemberment"] = bool(payload.get("dismemberment", False))
    return normalized


def _compact_content_dimensions(payload: Mapping[str, Any]) -> Dict[str, Any]:
    compact: Dict[str, Any] = {}
    for key in CONTENT_DIMENSION_KEYS:
        value = _normalize_level(payload.get(key))
        if value != "none":
            compact[key] = value
    if bool(payload.get("dismemberment", False)):
        compact["dismemberment"] = True
    return compact


def _merge_content_dimensions(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> Dict[str, Any]:
    merged = _normalize_content_dimensions(base)
    other = _normalize_content_dimensions(overlay)
    for key in CONTENT_DIMENSION_KEYS:
        if LEVEL_RANK[other[key]] > LEVEL_RANK[merged[key]]:
            merged[key] = other[key]
    merged["dismemberment"] = bool(merged.get("dismemberment", False) or other.get("dismemberment", False))
    return merged


def _normalize_level(value: Any) -> str:
    normalized = str(value or "none").strip().lower()
    return normalized if normalized in LEVEL_RANK else "none"


def _infer_prompt_content_dimensions(prompt: str) -> Dict[str, Any]:
    normalized = " ".join(str(prompt or "").strip().lower().split())
    dimensions = _normalize_content_dimensions(None)

    if _contains_any(normalized, ("combat", "fight", "attack", "weapon", "shoot", "violence", "execution")):
        _set_level(dimensions, "violence_level", _detect_intensity(normalized, default="mild"))
    if _contains_any(normalized, ("blood", "bloody", "bleed")):
        _set_level(dimensions, "blood_level", _detect_intensity(normalized, default="moderate"))
    if _contains_any(normalized, ("gore", "gory", "guts", "viscera", "gruesome")):
        _set_level(dimensions, "gore_level", _detect_intensity(normalized, default="intense"))
    if _contains_any(normalized, ("horror", "terror", "terrifying", "jump scare", "nightmare")):
        _set_level(dimensions, "horror_intensity", _detect_intensity(normalized, default="moderate"))
    if _contains_any(normalized, ("profanity", "swearing", "foul language", "cursing", "strong language")):
        _set_level(dimensions, "language_level", _detect_intensity(normalized, default="moderate"))
    if _contains_any(normalized, ("sexual", "sex scene", "adult scene", "erotic", "explicit intimacy")):
        _set_level(dimensions, "sexual_content_level", _detect_intensity(normalized, default="moderate"))
    if _contains_any(normalized, ("nudity", "nude", "topless", "explicit nudity")):
        _set_level(dimensions, "nudity_level", _detect_intensity(normalized, default="moderate"))
    if _contains_any(normalized, ("alcohol", "drinking", "drugs", "drug use", "smoking", "intoxication")):
        _set_level(dimensions, "substance_reference_level", _detect_intensity(normalized, default="mild"))
    if _contains_any(normalized, ("gambling", "casino", "poker", "slots", "betting")):
        _set_level(dimensions, "gambling_reference_level", _detect_intensity(normalized, default="mild"))
    if _contains_any(normalized, ("dismember", "decapitat", "limb sever", "severed limb")):
        dimensions["dismemberment"] = True
        _set_level(dimensions, "violence_level", _detect_intensity(normalized, default="intense"))
        _set_level(dimensions, "gore_level", _detect_intensity(normalized, default="intense"))
    return dimensions


def _detect_intensity(prompt: str, *, default: str) -> str:
    if _contains_any(prompt, ("extreme", "graphic", "explicit", "adult only")):
        return "extreme"
    if _contains_any(prompt, ("intense", "brutal", "doom-style", "gruesome", "execution")):
        return "intense"
    if _contains_any(prompt, ("moderate", "strong")):
        return "moderate"
    if _contains_any(prompt, ("mild", "light", "cartoon")):
        return "mild"
    return default


def _set_level(dimensions: Dict[str, Any], key: str, level: str) -> None:
    normalized = _normalize_level(level)
    if LEVEL_RANK[normalized] > LEVEL_RANK[dimensions[key]]:
        dimensions[key] = normalized


def _contains_any(prompt: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in prompt for phrase in phrases)


def _normalize_rating_target(rating_system: str, rating_target: str) -> str:
    raw = str(rating_target or "").strip()
    return raw.upper() if rating_system in {"ESRB", "CERO"} else raw


def _validate_profile(profile: ProjectContentProfile) -> None:
    if profile.content_mode != CONTENT_MODE_GAME_DEV:
        raise ValueError("Content Policy Layer v1 only supports GAME_DEV content_mode.")
    if profile.rating_system not in RATING_SYSTEMS:
        raise ValueError(f"Unsupported rating system '{profile.rating_system}'.")
    if profile.rating_target not in RATING_SYSTEMS[profile.rating_system]:
        allowed = ", ".join(RATING_SYSTEMS[profile.rating_system].keys())
        raise ValueError(f"Rating target '{profile.rating_target}' is not valid for {profile.rating_system}. Allowed values: {allowed}.")


def _write_atomic_json(path: Path, payload: Dict[str, Any]) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


__all__ = [
    "CONTENT_MODE_GAME_DEV",
    "ContentPolicyAssessment",
    "ProjectContentProfile",
    "ensure_project_content_profile",
    "evaluate_content_policy",
    "load_profile",
    "load_project_content_profile",
    "project_content_profile_path",
    "save_profile",
    "update_rating_lock",
    "update_rating_target",
]