"""The pull request title and Summary land as the squash commit, so they read as release notes."""

from __future__ import annotations

import re
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILL = SKILL_ROOT / "SKILL.md"
AUTHORING = SKILL_ROOT / "references" / "authoring.md"

CONVENTIONAL_TITLE = re.compile(
    r"^(feat|fix|docs|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9-]+\))?!?: \S"
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _section(path: Path, heading: str) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index(f"\n{heading}\n")
    level = heading.split(" ", 1)[0]
    ends = [
        text.find(f"\n{marker} ", start + len(heading) + 2)
        for marker in ("#" * n for n in range(2, len(level) + 1))
    ]
    ends = [end for end in ends if end != -1]
    return text[start : min(ends) if ends else len(text)]


def test_title_is_a_conventional_commits_subject() -> None:
    title = _flat(_section(AUTHORING, "## Title"))
    assert "Conventional Commits" in title
    assert "`type(scope): description`" in title
    for kind in (
        "feat", "fix", "docs", "refactor", "perf", "test", "build", "ci", "chore", "revert",
    ):
        assert f"`{kind}`" in title, kind
    assert "`!`" in title and "breaking" in title
    assert "at most 120 characters" in title
    assert "names the observable result" in title
    assert "squash commit subject" in title


def test_title_examples_follow_the_rule() -> None:
    title = _section(AUTHORING, "## Title")
    good = re.findall(r"`([^`]+)` beats", title)
    assert good, "the Title section shows a good example"
    for example in good:
        assert CONVENTIONAL_TITLE.match(example), example
        assert len(example) <= 120


def test_summary_is_release_note_prose_only() -> None:
    summary = _flat(_section(AUTHORING, "## Summary"))
    assert "only one to three sentences of release-note prose" in summary
    assert "user-visible change and why it matters" in summary
    assert "someone reading release notes" in summary
    for excluded in ("no diagram", "no file list", "no internal process"):
        assert excluded in summary, excluded
    assert "squash commit body" in summary


def test_the_pr_skill_visual_moves_to_change_shape_after_summary() -> None:
    shape = _flat(_section(AUTHORING, "## Change shape"))
    assert "`## Change shape`" in shape
    assert "directly after `## Summary`" in shape
    assert "diagram, diff-sketch or tree" in shape
    assert "does not land in the commit" in shape


def test_closing_reference_stays_outside_the_summary() -> None:
    summary = _flat(_section(AUTHORING, "## Summary"))
    assert "`Closes #<n>`" in summary
    assert "Work order reference" in summary
    assert "ccore adds closing references" in summary


def test_skill_names_the_landing_consequence_and_keeps_one_list() -> None:
    skill = _flat(SKILL.read_text(encoding="utf-8"))
    assert "Conventional Commits title" in skill
    assert "`## Summary`" in skill and "`## Change shape`" in skill
    assert "`ccore pr merge`" in skill
    assert "That reference is the only place this list is held" in skill


def test_verification_names_the_full_40_character_head_sha() -> None:
    verification = _flat(_section(AUTHORING, "### Verification"))
    assert "the full 40-character SHA of the head `ccore pr merge` starts from" in (
        verification
    )
    assert "`pr_land_verification_stale`" in verification
    assert "an abbreviated SHA does not count" in verification


def test_verification_head_covers_the_squashed_retry_head() -> None:
    verification = _flat(_section(AUTHORING, "### Verification"))
    assert (
        "after a stopped `ccore pr merge` run, the squashed head that `executive-pack` "
        "records under the same verdict" in verification
    )
    assert "A commit the delivery adds to the branch invalidates the verdict" in (
        verification
    )
    assert "A new commit on the branch invalidates the verdict" not in verification


def test_cognovis_sections_are_level_2_headings_in_the_body() -> None:
    added = _flat(_section(AUTHORING, "## Sections Cognovis adds"))
    lead = added[: added.index("### Work order reference")]
    assert "level-2 heading" in lead
    assert "`## Verification`" in lead and "`## Risk statement`" in lead
    assert "`ccore pr merge` reads only level-2 headings" in lead
    assert "The `###` headings below are this document's structure" in lead


def test_the_waiver_line_is_written_only_for_an_agents_md_waiver() -> None:
    merge = _flat(_section(AUTHORING, "### Merge assessment"))
    assert "Only when `executive-pack` passes a repository `AGENTS.md` waiver" in merge
    assert "plain prose line `pr-agent review not required: <reason>`" in merge
    assert "whose reason cites that `AGENTS.md` waiver" in merge
    assert "outside any fenced code block" in merge
    assert "Without such a waiver, never write the line" in merge
    skill = _flat(SKILL.read_text(encoding="utf-8"))
    assert "the repository's `AGENTS.md` waiver of pr-agent evidence" in skill
