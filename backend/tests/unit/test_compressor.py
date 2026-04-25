"""Unit tests for the prompt compressor."""
import pytest
from agent.compressor import (
    build_analysis_prompt,
    deduplicate_file_contexts,
    extract_changed_context,
)


class TestExtractChangedContext:
    def test_returns_full_content_when_no_patch(self):
        content = "line1\nline2\nline3"
        result = extract_changed_context(content, patch="")
        assert result == content

    def test_returns_full_content_when_no_hunks(self):
        content = "line1\nline2\nline3"
        result = extract_changed_context(content, patch="no hunks here")
        assert result == content

    def test_extracts_window_around_hunk(self):
        lines = [f"line {i}" for i in range(1, 51)]  # 50 lines
        content = "\n".join(lines)
        # Patch says change is at line 25
        patch = "@@ -24,3 +24,3 @@ def foo():"
        result = extract_changed_context(content, patch=patch, context_lines=3)
        # Should include lines around 24, not the full 50 lines
        assert len(result.splitlines()) < 50
        assert "line 24" in result

    def test_merges_overlapping_ranges(self):
        lines = [f"line {i}" for i in range(1, 101)]
        content = "\n".join(lines)
        # Two close hunks that should be merged
        patch = "@@ -10,2 +10,2 @@\n@@ -15,2 +15,2 @@"
        result = extract_changed_context(content, patch=patch, context_lines=3)
        # Should be a single contiguous block (no "..." separator)
        assert result.count("...") == 0

    def test_empty_content_returns_empty(self):
        result = extract_changed_context("", "@@ -1,1 +1,1 @@")
        assert result == ""

    def test_line_number_annotations_present(self):
        lines = [f"def func_{i}():" for i in range(1, 20)]
        content = "\n".join(lines)
        patch = "@@ -5,3 +5,3 @@"
        result = extract_changed_context(content, patch=patch, context_lines=2)
        # Annotations look like "   5 | line content"
        assert "|" in result


class TestDeduplicateFileContexts:
    def test_removes_exact_duplicates(self):
        contexts = {
            "utils.py": "def helper(): pass",
            "helpers.py": "def helper(): pass",  # same content
            "main.py": "import utils",
        }
        result = deduplicate_file_contexts(contexts)
        assert len(result) == 2
        assert "main.py" in result
        # One of utils.py or helpers.py remains (first wins)
        assert "utils.py" in result
        assert "helpers.py" not in result

    def test_keeps_unique_files(self):
        contexts = {
            "a.py": "content_a",
            "b.py": "content_b",
            "c.py": "content_c",
        }
        result = deduplicate_file_contexts(contexts)
        assert result == contexts

    def test_empty_dict(self):
        assert deduplicate_file_contexts({}) == {}

    def test_whitespace_normalised(self):
        contexts = {
            "a.py": "  content  ",
            "b.py": "content",  # same after strip
        }
        result = deduplicate_file_contexts(contexts)
        assert len(result) == 1


class TestBuildAnalysisPrompt:
    def _metadata(self, **kwargs):
        base = {
            "number": 42,
            "title": "Add feature X",
            "author": "alice",
            "base_branch": "main",
            "additions": 10,
            "deletions": 2,
            "changed_files": 1,
            "body": "",
        }
        base.update(kwargs)
        return base

    def test_contains_pr_number(self):
        prompt = build_analysis_prompt(self._metadata(), diff="+ added line", file_contexts={})
        assert "42" in prompt

    def test_contains_diff(self):
        prompt = build_analysis_prompt(self._metadata(), diff="+ added line", file_contexts={})
        assert "added line" in prompt

    def test_contains_file_context(self):
        prompt = build_analysis_prompt(
            self._metadata(),
            diff="",
            file_contexts={"utils.py": "def helper(): pass"},
        )
        assert "utils.py" in prompt
        assert "def helper" in prompt

    def test_deduplicates_file_contexts(self):
        # The same content under two different paths should appear only once
        prompt = build_analysis_prompt(
            self._metadata(),
            diff="",
            file_contexts={
                "a.py": "shared content",
                "b.py": "shared content",
            },
        )
        assert prompt.count("shared content") == 1

    def test_truncates_long_diff(self):
        long_diff = "+" + "x" * 20000
        prompt = build_analysis_prompt(self._metadata(), diff=long_diff, file_contexts={})
        # Prompt should be truncated, not contain full 20k char diff
        assert len(prompt) < 20000

    def test_description_included_when_present(self):
        meta = self._metadata(body="This PR fixes a critical bug.")
        prompt = build_analysis_prompt(meta, diff="", file_contexts={})
        assert "critical bug" in prompt
