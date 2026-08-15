"""One test per documented test case for the deal-scoring core.

Every test here is named `test_<SheetName>__UTCID<nn>` and drives exactly the case that
row of the Unit Test document describes. That name is the point: the document's
Passed/Untested column is then read straight out of the JUnit report rather than
inferred from coverage, so "Passed" means *this row ran and asserted*, not "the suite
entered this function at some point".

These seven functions are the ones the deal score is built from, so they are the ones
worth pinning row by row.
"""

from src.ai.lead_qualifier.scoring import (
    COLD_THRESHOLD,
    HOT_THRESHOLD,
    READINESS_CRITERIA,
    RUBRIC_LEVELS,
    build_gap_summary,
    compute_readiness,
    compute_win_likelihood,
    explain_gap,
    level_from_score,
    normalize_price_range,
    snap_to_level,
)

MAXED = {key: points for key, points in READINESS_CRITERIA.items()}
ZEROED = {key: 0 for key in READINESS_CRITERIA}


# --------------------------------------------------------------------- SnapToLevel
def test_SnapToLevel__UTCID01():
    """30 is exactly a level, so it survives untouched."""
    assert snap_to_level("scope", 30) == 30


def test_SnapToLevel__UTCID02():
    """22 rounds DOWN to 20, not to the nearest level - a generous score is worse."""
    assert snap_to_level("scope", 22) == 20


def test_SnapToLevel__UTCID03():
    assert snap_to_level("scope", 19) == 12


def test_SnapToLevel__UTCID04():
    assert snap_to_level("scope", 0) == RUBRIC_LEVELS["scope"][-1].points


def test_SnapToLevel__UTCID05():
    """Above the top level clamps to the top level."""
    assert snap_to_level("scope", 999) == RUBRIC_LEVELS["scope"][0].points


def test_SnapToLevel__UTCID06():
    """An unknown criterion is passed through rather than crashing the whole score."""
    assert snap_to_level("not_a_criterion", 17) == 17


# ----------------------------------------------------------------------- ExplainGap
def test_ExplainGap__UTCID01():
    """At the maximum there is nothing missing, so there is no gap to explain."""
    assert explain_gap("scope", RUBRIC_LEVELS["scope"][0].points) is None


def test_ExplainGap__UTCID02():
    gap = explain_gap("scope", 20)
    assert gap is not None
    assert gap["lost_points"] == 10
    assert len(gap["steps"]) == 1


def test_ExplainGap__UTCID03():
    """From the bottom every level above is listed, cheapest first."""
    gap = explain_gap("scope", 0)
    assert gap is not None
    assert gap["lost_points"] == 30
    assert len(gap["steps"]) == 3
    gains = [step["gain"] for step in gap["steps"]]
    assert gains == sorted(gains)


def test_ExplainGap__UTCID04():
    assert explain_gap("not_a_criterion", 0) is None


# ------------------------------------------------------------------ ComputeReadiness
def test_ComputeReadiness__UTCID01():
    score, breakdown = compute_readiness(MAXED)
    assert score == 100
    assert len(breakdown) == 5


def test_ComputeReadiness__UTCID02():
    score, breakdown = compute_readiness(ZEROED)
    assert score == 0
    assert len(breakdown) == 5


def test_ComputeReadiness__UTCID03():
    """The total is the sum of the SNAPPED levels, not of the raw model numbers."""
    raw = {"scope": 22, "budget": 24, "timeline": 7, "detail": 15, "context": 3}
    score, breakdown = compute_readiness(raw)
    assert score == sum(item["points"] for item in breakdown)
    for item in breakdown:
        assert item["points"] == snap_to_level(item["key"], item["points"])


def test_ComputeReadiness__UTCID04():
    """A criterion the model omitted scores 0 and still gets a breakdown row."""
    partial = {key: value for key, value in MAXED.items() if key != "budget"}
    score, breakdown = compute_readiness(partial)
    assert len(breakdown) == 5
    budget = next(item for item in breakdown if item["key"] == "budget")
    assert budget["points"] == 0
    assert score == 100 - READINESS_CRITERIA["budget"]


# ------------------------------------------------------------------- BuildGapSummary
def test_BuildGapSummary__UTCID01():
    score, breakdown = compute_readiness(MAXED)
    summary = build_gap_summary(score, breakdown)
    assert summary["gaps"] == []
    assert summary["points_to_hot"] == 0


def test_BuildGapSummary__UTCID02():
    raw = dict(MAXED, budget=0, timeline=0)
    score, breakdown = compute_readiness(raw)
    summary = build_gap_summary(score, breakdown)
    assert {gap["key"] for gap in summary["gaps"]} == {"budget", "timeline"}
    # most points lost first - the question worth asking is at the top
    lost = [gap["lost_points"] for gap in summary["gaps"]]
    assert lost == sorted(lost, reverse=True)


def test_BuildGapSummary__UTCID03():
    score, breakdown = compute_readiness(ZEROED)
    summary = build_gap_summary(score, breakdown)
    assert len(summary["gaps"]) == 5
    assert summary["points_to_hot"] == HOT_THRESHOLD


# -------------------------------------------------------------------- LevelFromScore
def test_LevelFromScore__UTCID01():
    assert level_from_score(100) == "HOT"


def test_LevelFromScore__UTCID02():
    """Exactly HOT_THRESHOLD is HOT - the boundary is inclusive."""
    assert level_from_score(HOT_THRESHOLD) == "HOT"


def test_LevelFromScore__UTCID03():
    assert level_from_score(HOT_THRESHOLD - 1) == "WARM"


def test_LevelFromScore__UTCID04():
    """Exactly COLD_THRESHOLD is still WARM - COLD is strictly below."""
    assert level_from_score(COLD_THRESHOLD) == "WARM"


def test_LevelFromScore__UTCID05():
    assert level_from_score(COLD_THRESHOLD - 1) == "COLD"


def test_LevelFromScore__UTCID06():
    assert level_from_score(0) == "COLD"


# -------------------------------------------------------------- ComputeWinLikelihood
def _factor_named(result, key):
    return next(f for f in result["factors"] if f["key"] == key)


def test_ComputeWinLikelihood__UTCID01():
    """Everything at its best: a high likelihood, and the strengths are named."""
    result = compute_win_likelihood(
        budget_points=READINESS_CRITERIA["budget"],
        timeline_points=READINESS_CRITERIA["timeline"],
        detail_points=READINESS_CRITERIA["detail"],
        estimated_value=20_000_000,
        price_range_min=10_000_000,
        source="referral",
    )
    assert result["level"] == "high"
    assert result["score"] >= 70
    assert _factor_named(result, "budget")["impact"] == "positive"


def test_ComputeWinLikelihood__UTCID02():
    """No budget from the client: low likelihood, and budget scores nothing."""
    result = compute_win_likelihood(
        budget_points=0,
        timeline_points=0,
        detail_points=0,
        estimated_value=None,
        price_range_min=None,
        source=None,
    )
    assert result["level"] == "low"
    assert _factor_named(result, "budget")["points"] == 0


def test_ComputeWinLikelihood__UTCID03():
    result = compute_win_likelihood(
        budget_points=READINESS_CRITERIA["budget"],
        timeline_points=0,
        detail_points=READINESS_CRITERIA["detail"],
        estimated_value=20_000_000,
        price_range_min=10_000_000,
        source="referral",
    )
    timeline = _factor_named(result, "timeline")
    assert timeline["points"] == 0
    assert timeline["impact"] == "negative"


def test_ComputeWinLikelihood__UTCID04():
    result = compute_win_likelihood(
        budget_points=READINESS_CRITERIA["budget"],
        timeline_points=READINESS_CRITERIA["timeline"],
        detail_points=0,
        estimated_value=20_000_000,
        price_range_min=10_000_000,
        source="referral",
    )
    detail = _factor_named(result, "detail")
    assert detail["points"] == 0
    assert detail["impact"] == "negative"


def test_ComputeWinLikelihood__UTCID05():
    """No estimated value: the budget factor degrades to neutral, nothing raises."""
    result = compute_win_likelihood(
        budget_points=READINESS_CRITERIA["budget"],
        timeline_points=READINESS_CRITERIA["timeline"],
        detail_points=READINESS_CRITERIA["detail"],
        estimated_value=None,
        price_range_min=10_000_000,
        source="referral",
    )
    assert _factor_named(result, "budget")["impact"] == "neutral"
    assert 0 <= result["score"] <= 100


def test_ComputeWinLikelihood__UTCID06():
    """An unknown source is handled, not treated as a missing argument."""
    result = compute_win_likelihood(
        budget_points=READINESS_CRITERIA["budget"],
        timeline_points=READINESS_CRITERIA["timeline"],
        detail_points=READINESS_CRITERIA["detail"],
        estimated_value=20_000_000,
        price_range_min=10_000_000,
        source=None,
    )
    assert _factor_named(result, "source")["points"] >= 0
    assert 0 <= result["score"] <= 100


# -------------------------------------------------------------- NormalizePriceRange
def test_NormalizePriceRange__UTCID01():
    """30 means "30 million" - the model dropped the unit, so scale it up."""
    assert normalize_price_range(30, 50) == (30_000_000, 50_000_000)


def test_NormalizePriceRange__UTCID02():
    """999 is still under the shorthand threshold, so it scales."""
    low, _ = normalize_price_range(999, 999)
    assert low == 999_000_000


def test_NormalizePriceRange__UTCID03():
    """At the threshold itself the intent is unreadable - show nothing, not a wrong price."""
    low, _ = normalize_price_range(1_000, 1_000)
    assert low == 0


def test_NormalizePriceRange__UTCID04():
    low, _ = normalize_price_range(499_999, 499_999)
    assert low == 0


def test_NormalizePriceRange__UTCID05():
    """A realistic price is kept exactly as given."""
    low, _ = normalize_price_range(500_000, 500_000)
    assert low == 500_000


def test_NormalizePriceRange__UTCID06():
    assert normalize_price_range(0, 0) == (0, 0)


def test_NormalizePriceRange__UTCID07():
    assert normalize_price_range(-5, -5) == (0, 0)


def test_NormalizePriceRange__UTCID08():
    """A non-numeric value is swallowed rather than crashing the qualifier."""
    assert normalize_price_range("abc", "abc") == (0, 0)
