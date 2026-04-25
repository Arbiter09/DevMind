"""Unit tests for the self-evaluation rubric."""
import pytest
from agent.rubric import (
    DIMENSIONS,
    MAX_ITERATIONS,
    PASS_THRESHOLD,
    DimensionScore,
    build_eval_prompt,
    build_refinement_prompt,
)


class TestDimensions:
    def test_has_twelve_dimensions(self):
        assert len(DIMENSIONS) == 12

    def test_all_dimensions_have_name_and_description(self):
        for name, desc in DIMENSIONS:
            assert name, "Dimension name should not be empty"
            assert desc, f"Dimension '{name}' missing description"
            assert len(desc) > 10, f"Dimension '{name}' description too short"

    def test_dimension_names_are_unique(self):
        names = [name for name, _ in DIMENSIONS]
        assert len(names) == len(set(names)), "Dimension names must be unique"

    def test_expected_dimensions_present(self):
        names = {name for name, _ in DIMENSIONS}
        required = {
            "correctness", "security", "performance", "readability",
            "error_handling", "test_coverage", "api_consistency",
            "documentation", "dependency_hygiene", "breaking_changes",
            "code_duplication", "edge_cases",
        }
        assert required == names


class TestConstants:
    def test_pass_threshold_in_range(self):
        assert 1.0 <= PASS_THRESHOLD <= 5.0

    def test_max_iterations_positive(self):
        assert MAX_ITERATIONS >= 1

    def test_reasonable_threshold(self):
        # Threshold should not be too low (allows junk) or too high (never passes)
        assert 3.0 <= PASS_THRESHOLD <= 4.5


class TestBuildEvalPrompt:
    def test_contains_all_dimension_names(self):
        prompt = build_eval_prompt(
            review_draft="Some review text.",
            diff="+ added line",
        )
        for name, _ in DIMENSIONS:
            assert name in prompt, f"Dimension '{name}' missing from eval prompt"

    def test_contains_review_draft(self):
        prompt = build_eval_prompt(
            review_draft="My detailed review.",
            diff="+ change",
        )
        assert "My detailed review." in prompt

    def test_contains_diff(self):
        prompt = build_eval_prompt(
            review_draft="Review.",
            diff="+ unique_diff_content",
        )
        assert "unique_diff_content" in prompt

    def test_truncates_long_diff(self):
        long_diff = "+" + "x" * 20000
        prompt = build_eval_prompt(review_draft="Review.", diff=long_diff)
        assert len(prompt) < 20000


class TestBuildRefinementPrompt:
    def _make_scores(self, pairs: list[tuple[str, float]]) -> list[DimensionScore]:
        return [DimensionScore(name=n, score=s, notes=f"notes for {n}") for n, s in pairs]

    def test_contains_weak_dimensions(self):
        weak = self._make_scores([("security", 1.5), ("performance", 2.0)])
        prompt = build_refinement_prompt(
            review_draft="Draft review.",
            diff="+ change",
            weak_dimensions=weak,
        )
        assert "security" in prompt
        assert "performance" in prompt

    def test_contains_original_draft(self):
        weak = self._make_scores([("correctness", 2.0)])
        prompt = build_refinement_prompt(
            review_draft="Original review text.",
            diff="+ change",
            weak_dimensions=weak,
        )
        assert "Original review text." in prompt

    def test_shows_scores_in_prompt(self):
        weak = self._make_scores([("security", 1.5)])
        prompt = build_refinement_prompt(
            review_draft="Review.",
            diff="",
            weak_dimensions=weak,
        )
        assert "1.5" in prompt
