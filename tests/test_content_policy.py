import json

import pytest

from ai_e_runtime.content_policy import ProjectContentProfile, evaluate_content_policy


pytestmark = pytest.mark.fast


def test_content_policy_allows_mild_combat_for_teen_profile():
    assessment = evaluate_content_policy(
        "add mild combat effects",
        profile=ProjectContentProfile(content_mode="GAME_DEV", rating_system="ESRB", rating_target="T", rating_locked=True),
    )

    assert assessment.content_policy_match == "fits_rating"
    assert assessment.content_policy_decision == "allowed"
    assert assessment.required_rating_upgrade is None
    assert assessment.requested_content_dimensions == {"violence_level": "mild"}


def test_content_policy_blocks_locked_teen_profile_when_request_needs_mature_upgrade():
    assessment = evaluate_content_policy(
        "add extreme gore dismemberment system",
        profile=ProjectContentProfile(content_mode="GAME_DEV", rating_system="ESRB", rating_target="T", rating_locked=True),
    )

    assert assessment.content_policy_match == "exceeds_rating"
    assert assessment.content_policy_decision == "blocked"
    assert assessment.required_rating_upgrade == "M"
    assert assessment.requested_content_dimensions["gore_level"] == "extreme"
    assert assessment.requested_content_dimensions["dismemberment"] is True


def test_content_policy_allows_brutal_execution_for_mature_profile():
    assessment = evaluate_content_policy(
        "create brutal doom-style execution animation",
        profile=ProjectContentProfile(content_mode="GAME_DEV", rating_system="ESRB", rating_target="M", rating_locked=True),
    )

    assert assessment.content_policy_match == "fits_rating"
    assert assessment.content_policy_decision == "allowed"
    assert assessment.required_rating_upgrade is None
    assert assessment.requested_content_dimensions["violence_level"] == "intense"


def test_content_policy_requires_review_for_unlocked_pegi_profile_that_needs_upgrade():
    assessment = evaluate_content_policy(
        "add explicit nudity cutscene",
        profile=ProjectContentProfile(content_mode="GAME_DEV", rating_system="PEGI", rating_target="16", rating_locked=False),
    )

    assert assessment.content_policy_match == "exceeds_rating"
    assert assessment.content_policy_decision == "requires_review"
    assert assessment.required_rating_upgrade == "18"
    assert assessment.requested_content_dimensions["nudity_level"] == "extreme"