import json
import subprocess
import sys
from pathlib import Path


STANDARD_DIR = Path(__file__).resolve().parents[1]
SCRIPT = STANDARD_DIR / "scripts" / "validate_decision_gate.py"


def valid_document() -> str:
    return """# Release Decision

## Decision Brief

### Compact Manager View

Decision required: Choose whether to proceed with the deployment.
Recommended default: BLOCK until rollback evidence exists.
Operational risk: external-side-effect.
Operational do-nothing/default outcome: Do not deploy.
Delivery consequence: Delivery slips one day.
Decision needed by: 2026-07-14T18:00:00Z.

### Evidence Appendix

Evidence appendix references: tests/release/rollback.test.ts.
Blast radius: One deployment environment.
Rollback path: Revert the deployment tag.
Alternatives considered: Wait for the next window.

## Human Decision Gate

Decision owner: Release manager.
Approval class: production-change.
Allowed outcomes: ALLOW, BLOCK, REVISE, ESCALATE.
Trigger timing: Before deployment.
Minimum evidence plan: Run rollback smoke test and deployment dry run.
Operational do-nothing/default outcome: Keep the current release in place.
Delivery consequence: Delivery waits for the next window.
Overrideability: Not overrideable by the implementation agent.
Sequencing constraints: Evidence must be gathered before the gate is presented.
"""


def run_validator(text: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "-"],
        input=text,
        capture_output=True,
        text=True,
        check=False,
    )


def test_valid_decision_brief_and_gate_pass() -> None:
    result = run_validator(valid_document())

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["data"]["decision_brief"] is True
    assert data["data"]["human_decision_gate"] is True


def test_missing_decision_gate_field_fails() -> None:
    payload = valid_document().replace(
        "Minimum evidence plan: Run rollback smoke test and deployment dry run.\n",
        "",
    )

    result = run_validator(payload)

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "error"
    assert any("Minimum evidence plan" in error for error in data["errors"])


def test_invalid_allowed_outcome_fails_without_semantic_risk_judgment() -> None:
    payload = valid_document().replace(
        "Allowed outcomes: ALLOW, BLOCK, REVISE, ESCALATE.",
        "Allowed outcomes: approve, reject.",
    )

    result = run_validator(payload)

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert any("Allowed outcomes" in error for error in data["errors"])
    assert not any("false urgency" in error.lower() for error in data["errors"])
    assert not any("residual risk" in error.lower() for error in data["errors"])


def test_mandate_field_names_are_rejected_as_gate_fields() -> None:
    payload = valid_document().replace(
        "Sequencing constraints: Evidence must be gathered before the gate is presented.\n",
        "Sequencing constraints: Evidence must be gathered before the gate is presented.\n"
        "scope: release deployment.\n",
    )

    result = run_validator(payload)

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert any("Mandate" in error and "scope" in error for error in data["errors"])


def test_gate_without_approval_class_fails() -> None:
    payload = valid_document().replace("Approval class: production-change.\n", "")

    result = run_validator(payload)

    assert result.returncode == 1
    errors = json.loads(result.stdout)["errors"]
    assert any("Approval class" in error for error in errors)


def test_gate_for_internal_work_fails() -> None:
    payload = valid_document().replace(
        "Approval class: production-change.", "Approval class: secret-creation."
    )

    result = run_validator(payload)

    assert result.returncode == 1
    errors = json.loads(result.stdout)["errors"]
    assert any("production-change, customer-message" in error for error in errors)


def test_customer_message_gate_passes() -> None:
    payload = valid_document().replace(
        "Approval class: production-change.", "Approval class: customer-message."
    )

    result = run_validator(payload)

    assert result.returncode == 0, result.stdout


def test_punctuation_only_approval_class_fails() -> None:
    for value in (".", "`", "...", " . "):
        payload = valid_document().replace(
            "Approval class: production-change.", f"Approval class: {value}"
        )
        result = run_validator(payload)
        assert result.returncode == 1, value


def test_second_gate_fails() -> None:
    second = valid_document().split("## Human Decision Gate", 1)[1].replace(
        "Approval class: production-change.", "Approval class: customer-message."
    )
    payload = valid_document() + "\n## Human Decision Gate" + second

    result = run_validator(payload)

    assert result.returncode == 1
    errors = json.loads(result.stdout)["errors"]
    assert any("one ## Human Decision Gate" in error for error in errors)


def test_second_gate_with_variant_heading_fails() -> None:
    body = valid_document().split("## Human Decision Gate", 1)[1]
    for heading in ["## Human Decision Gate 2", "## Human Decision Gate (stage 2)", "## Human Decision Gate: customer message", "## human decision gate"]:
        result = run_validator(valid_document() + "\n" + heading + body)
        assert result.returncode == 1, heading


def test_gate_heading_inside_longer_fence_is_not_counted() -> None:
    """A gate heading after a four-backtick block containing a three-backtick line."""
    payload = valid_document().replace(
        "## Human Decision Gate",
        "````markdown\n```\n## Human Decision Gate (fenced example)\n```\n````\n\n## Human Decision Gate",
    )

    result = run_validator(payload)

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "ok"


def test_gate_heading_inside_html_comment_is_not_counted() -> None:
    """A gate heading inside an HTML comment is ignored."""
    payload = valid_document().replace(
        "## Human Decision Gate",
        "<!-- ## Human Decision Gate (commented out) -->\n\n## Human Decision Gate",
    )

    result = run_validator(payload)

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "ok"


def test_multiline_html_comment_hides_gate_heading() -> None:
    """A gate heading inside a multi-line HTML comment is ignored."""
    payload = valid_document().replace(
        "## Human Decision Gate",
        "<!--\n## Human Decision Gate (draft)\n-->\n\n## Human Decision Gate",
    )

    result = run_validator(payload)

    assert result.returncode == 0, result.stdout + result.stderr


def test_hidden_exact_heading_preceding_real_gate() -> None:
    """An exact ``## Human Decision Gate`` inside a comment must not steal the section."""
    payload = valid_document().replace(
        "## Human Decision Gate",
        "<!--\n## Human Decision Gate\n-->\n\n## Human Decision Gate",
    )

    result = run_validator(payload)

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "ok"


def test_qualified_gate_heading_without_exact_section_fails() -> None:
    """A visible qualified heading that cannot be extracted is an error."""
    payload = valid_document().replace(
        "## Human Decision Gate",
        "## Human Decision Gate (production)",
    )

    result = run_validator(payload)

    assert result.returncode == 1
    errors = json.loads(result.stdout)["errors"]
    assert any("could not be extracted" in e for e in errors)


def test_gate_fields_inside_fence_are_not_valid() -> None:
    """Fields inside a fenced code block must not satisfy gate requirements."""
    # Replace the real gate with one entirely inside a code fence
    brief = valid_document().split("## Human Decision Gate")[0]
    fenced_gate = "```\n## Human Decision Gate\n"
    fenced_gate += "Decision owner: Release manager.\n"
    fenced_gate += "Approval class: production-change.\n"
    fenced_gate += "```\n"
    payload = brief + fenced_gate

    result = run_validator(payload)

    # The fenced gate is invisible; only the brief validates.
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["data"]["decision_brief"] is True
    assert data["data"]["human_decision_gate"] is False


def test_commented_decision_owner_fails() -> None:
    """A required field inside a comment must fail the field check."""
    payload = valid_document().replace(
        "Decision owner: Release manager.",
        "<!-- Decision owner: Release manager. -->",
    )

    result = run_validator(payload)

    assert result.returncode == 1
    errors = json.loads(result.stdout)["errors"]
    assert any("Decision owner" in e for e in errors)


def test_duplicate_gate_with_second_inside_comment() -> None:
    """A duplicate gate inside a comment must not count as a second gate."""
    body = valid_document().split("## Human Decision Gate", 1)[1]
    payload = valid_document() + "\n<!--\n## Human Decision Gate" + body + "\n-->\n"

    result = run_validator(payload)

    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Visible Markdown: an HTML comment hides only itself; fences hide whole lines.
# Every case runs the public CLI.
# ---------------------------------------------------------------------------

GATE_BODY = valid_document().split("## Human Decision Gate", 1)[1]
BRIEF_ONLY = valid_document().split("## Human Decision Gate", 1)[0]


def _errors(result: subprocess.CompletedProcess[str]) -> list[str]:
    return json.loads(result.stdout)["errors"]


def test_second_exact_gate_with_inline_comment_fails() -> None:
    result = run_validator(valid_document() + "\n## Human Decision Gate <!-- note -->" + GATE_BODY)

    assert result.returncode == 1, result.stdout
    assert any("one ## Human Decision Gate" in error for error in _errors(result))


def test_second_qualified_gate_with_inline_comment_fails() -> None:
    result = run_validator(valid_document() + "\n## Human Decision Gate (stage 2) <!-- note -->" + GATE_BODY)

    assert result.returncode == 1, result.stdout
    assert any("one ## Human Decision Gate" in error for error in _errors(result))


def test_single_gate_heading_with_inline_comment_passes() -> None:
    result = run_validator(
        valid_document().replace("## Human Decision Gate", "## Human Decision Gate <!-- reviewed 2026-10-08 -->")
    )

    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["data"]["human_decision_gate"] is True


def test_inline_comment_after_field_value_keeps_the_field() -> None:
    result = run_validator(
        valid_document().replace("Decision owner: Release manager.", "Decision owner: Release manager. <!-- per RACI -->")
    )

    assert result.returncode == 0, result.stdout


def test_inline_comment_hiding_a_field_label_fails() -> None:
    result = run_validator(
        valid_document().replace("Decision owner: Release manager.", "<!-- Decision owner: --> Release manager.")
    )

    assert result.returncode == 1
    assert any("Decision owner" in error for error in _errors(result))


def test_multiline_comment_opened_after_a_field_hides_following_fields() -> None:
    result = run_validator(
        valid_document().replace(
            "Decision owner: Release manager.\nApproval class: production-change.\n",
            "Decision owner: Release manager. <!-- draft\nApproval class: production-change.\n-->\n",
        )
    )

    assert result.returncode == 1
    assert any("Approval class: missing" in error for error in _errors(result))


def test_text_after_a_multiline_comment_close_stays_visible() -> None:
    result = run_validator(
        valid_document().replace(
            "Approval class: production-change.",
            "<!-- reviewer note\nspanning lines --> Approval class: production-change.",
        )
    )

    assert result.returncode == 0, result.stdout


def test_comment_opener_inside_a_fence_does_not_hide_the_gate() -> None:
    result = run_validator(
        valid_document().replace("## Human Decision Gate", "```html\n<!-- unterminated\n```\n\n## Human Decision Gate")
    )

    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["data"]["human_decision_gate"] is True


def test_tilde_fence_is_not_closed_by_backticks() -> None:
    result = run_validator(
        valid_document().replace(
            "## Human Decision Gate",
            "~~~\n```\n## Human Decision Gate (example)\n```\n~~~\n\n## Human Decision Gate",
        )
    )

    assert result.returncode == 0, result.stdout


def test_shorter_closing_fence_does_not_close_and_hides_a_later_gate() -> None:
    """An unclosed four-backtick fence runs to the end, so the gate is not visible."""
    result = run_validator(BRIEF_ONLY + "````\nexample\n```\n\n## Human Decision Gate" + GATE_BODY)

    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["data"]["human_decision_gate"] is False


def test_fence_line_with_info_string_does_not_close_the_fence() -> None:
    result = run_validator(
        valid_document().replace(
            "## Human Decision Gate",
            "```\n```python\n## Human Decision Gate (example)\n```\n\n## Human Decision Gate",
        )
    )

    assert result.returncode == 0, result.stdout


def test_hidden_invalid_field_does_not_mask_a_visible_invalid_one() -> None:
    result = run_validator(
        valid_document().replace(
            "Approval class: production-change.",
            "<!-- Approval class: production-change. --> Approval class: internal.",
        )
    )

    assert result.returncode == 1
    assert any("internal work takes no gate" in error for error in _errors(result))


# ---------------------------------------------------------------------------
# CommonMark ATX heading indentation: 0-3 spaces are headings, 4+ are not.
# ---------------------------------------------------------------------------

INDENT_GATE_BODY = valid_document().split("## Human Decision Gate", 1)[1]


def test_duplicate_gate_one_space_indent_fails() -> None:
    """A second gate heading with one leading space is a valid ATX heading and must be rejected."""
    result = run_validator(valid_document() + "\n ## Human Decision Gate" + INDENT_GATE_BODY)

    assert result.returncode == 1, f"expected exit 1 but got {result.returncode}: {result.stdout}"
    assert any("one ## Human Decision Gate" in e for e in _errors(result))


def test_duplicate_gate_two_space_indent_fails() -> None:
    """A second gate heading with two leading spaces is a valid ATX heading and must be rejected."""
    result = run_validator(valid_document() + "\n  ## Human Decision Gate" + INDENT_GATE_BODY)

    assert result.returncode == 1, f"expected exit 1 but got {result.returncode}: {result.stdout}"
    assert any("one ## Human Decision Gate" in e for e in _errors(result))


def test_duplicate_gate_three_space_indent_fails() -> None:
    """A second gate heading with three leading spaces is a valid ATX heading and must be rejected."""
    result = run_validator(valid_document() + "\n   ## Human Decision Gate" + INDENT_GATE_BODY)

    assert result.returncode == 1, f"expected exit 1 but got {result.returncode}: {result.stdout}"
    assert any("one ## Human Decision Gate" in e for e in _errors(result))


def _indent_block(text: str) -> str:
    return "".join(f"    {line}" if line.strip() else line for line in text.splitlines(keepends=True))


def test_duplicate_gate_four_space_indent_passes() -> None:
    """Four leading spaces are an indented code block, not a heading — no duplicate."""
    result = run_validator(valid_document() + "\n" + _indent_block("## Human Decision Gate" + INDENT_GATE_BODY))

    assert result.returncode == 0, f"expected exit 0 but got {result.returncode}: {result.stdout}"


def test_duplicate_gate_inside_backtick_fence_passes() -> None:
    """A duplicate gate inside a backtick fence is not a heading."""
    fenced = "\n```\n## Human Decision Gate" + INDENT_GATE_BODY + "```\n"
    result = run_validator(valid_document() + fenced)

    assert result.returncode == 0, f"expected exit 0 but got {result.returncode}: {result.stdout}"


def test_duplicate_gate_inside_tilde_fence_passes() -> None:
    """A duplicate gate inside a tilde fence is not a heading."""
    fenced = "\n~~~\n## Human Decision Gate" + INDENT_GATE_BODY + "~~~\n"
    result = run_validator(valid_document() + fenced)

    assert result.returncode == 0, f"expected exit 0 but got {result.returncode}: {result.stdout}"


def test_valid_single_gate_with_one_space_indent() -> None:
    """A single gate heading with one leading space is extracted and validated normally."""
    doc = valid_document().replace("## Human Decision Gate", " ## Human Decision Gate")
    result = run_validator(doc)

    assert result.returncode == 0, f"expected exit 0 but got {result.returncode}: {result.stdout}"
    data = json.loads(result.stdout)
    assert data["data"]["human_decision_gate"] is True


def test_valid_single_gate_with_two_space_indent() -> None:
    """A single gate heading with two leading spaces is extracted and validated normally."""
    doc = valid_document().replace("## Human Decision Gate", "  ## Human Decision Gate")
    result = run_validator(doc)

    assert result.returncode == 0, f"expected exit 0 but got {result.returncode}: {result.stdout}"
    data = json.loads(result.stdout)
    assert data["data"]["human_decision_gate"] is True


def test_valid_single_gate_with_three_space_indent() -> None:
    """A single gate heading with three leading spaces is extracted and validated normally."""
    doc = valid_document().replace("## Human Decision Gate", "   ## Human Decision Gate")
    result = run_validator(doc)

    assert result.returncode == 0, f"expected exit 0 but got {result.returncode}: {result.stdout}"
    data = json.loads(result.stdout)
    assert data["data"]["human_decision_gate"] is True


def test_indented_subheading_is_recognized() -> None:
    """A level-3 subheading with 1-3 leading spaces is recognized."""
    doc = valid_document().replace("### Compact Manager View", " ### Compact Manager View")
    doc = doc.replace("### Evidence Appendix", "  ### Evidence Appendix")
    result = run_validator(doc)

    assert result.returncode == 0, f"expected exit 0 but got {result.returncode}: {result.stdout}"


def test_section_boundary_prevents_field_leaking() -> None:
    """An indented heading boundary stops field extraction from leaking across sections."""
    # Remove Decision owner from the gate section, then add it after a new indented heading
    doc = valid_document().replace(
        "Decision owner: Release manager.\n",
        "",
    )
    doc += "\n ## Unrelated Section\nDecision owner: Release manager.\n"
    result = run_validator(doc)

    assert result.returncode == 1, f"expected exit 1 but got {result.returncode}: {result.stdout}"
    assert any("Decision owner" in e for e in _errors(result))


def test_empty_heading_boundary_prevents_field_leaking() -> None:
    """A bare ## (empty ATX heading) stops extraction; a field after it must not leak in."""
    doc = valid_document().replace("Decision owner: Release manager.\n", "")
    doc += "\n##\nDecision owner: Release manager.\n"
    result = run_validator(doc)

    assert result.returncode == 1, f"expected exit 1 but got {result.returncode}: {result.stdout}"
    assert any("Decision owner" in e for e in _errors(result))


def test_empty_heading_boundary_with_indent_one_space() -> None:
    """A bare ## with one leading space is still a section boundary."""
    doc = valid_document().replace("Decision owner: Release manager.\n", "")
    doc += "\n ##\nDecision owner: Release manager.\n"
    result = run_validator(doc)

    assert result.returncode == 1, f"expected exit 1 but got {result.returncode}: {result.stdout}"
    assert any("Decision owner" in e for e in _errors(result))


def test_empty_heading_boundary_with_indent_two_spaces() -> None:
    """A bare ## with two leading spaces is still a section boundary."""
    doc = valid_document().replace("Decision owner: Release manager.\n", "")
    doc += "\n  ##\nDecision owner: Release manager.\n"
    result = run_validator(doc)

    assert result.returncode == 1, f"expected exit 1 but got {result.returncode}: {result.stdout}"
    assert any("Decision owner" in e for e in _errors(result))


def test_empty_heading_boundary_with_indent_three_spaces() -> None:
    """A bare ## with three leading spaces is still a section boundary."""
    doc = valid_document().replace("Decision owner: Release manager.\n", "")
    doc += "\n   ##\nDecision owner: Release manager.\n"
    result = run_validator(doc)

    assert result.returncode == 1, f"expected exit 1 but got {result.returncode}: {result.stdout}"
    assert any("Decision owner" in e for e in _errors(result))


def test_gate_heading_with_closing_hashes() -> None:
    """A gate heading with optional closing hashes per CommonMark is recognized."""
    doc = valid_document().replace("## Human Decision Gate", "## Human Decision Gate ##")
    result = run_validator(doc)

    assert result.returncode == 0, f"expected exit 0 but got {result.returncode}: {result.stdout}"
    data = json.loads(result.stdout)
    assert data["data"]["human_decision_gate"] is True


# ---------------------------------------------------------------------------
# Visibility and control-field structure (cognovis/library-core#246, Fleet #111).
# ---------------------------------------------------------------------------


def test_inline_code_comment_opener_does_not_hide_a_second_gate() -> None:
    """A literal `<!--` inside a code span is code, not an HTML comment."""
    result = run_validator(
        valid_document() + "\nThe literal comment opener is `<!--`.\n\n## Human Decision Gate" + GATE_BODY
    )

    assert result.returncode == 1, result.stdout
    assert any("one ## Human Decision Gate" in error for error in _errors(result))


def test_double_backtick_code_span_with_comment_opener_does_not_hide_a_second_gate() -> None:
    result = run_validator(
        valid_document() + "\nWrite ``<!-- ` -->`` here, then `<!--` again.\n\n## Human Decision Gate" + GATE_BODY
    )

    assert result.returncode == 1, result.stdout
    assert any("one ## Human Decision Gate" in error for error in _errors(result))


def test_code_span_across_paragraph_lines_does_not_hide_a_second_gate() -> None:
    result = run_validator(
        valid_document() + "\nA span `starts here\nand <!-- continues` on the next line.\n\n## Human Decision Gate" + GATE_BODY
    )

    assert result.returncode == 1, result.stdout
    assert any("one ## Human Decision Gate" in error for error in _errors(result))


def test_unmatched_backtick_leaves_a_genuine_comment_hiding_a_second_gate() -> None:
    """A lone backtick is literal text, so the comment after it is still a comment."""
    result = run_validator(
        valid_document().replace(
            "Decision owner: Release manager.",
            "A lone ` backtick. <!-- Decision owner: Release manager. -->",
        )
    )

    assert result.returncode == 1, result.stdout
    assert any("Decision owner: missing" in error for error in _errors(result))


def test_inline_code_inside_a_genuine_comment_stays_hidden() -> None:
    result = run_validator(
        valid_document().replace(
            "Decision owner: Release manager.",
            "<!-- `not code` Decision owner: Release manager. -->",
        )
    )

    assert result.returncode == 1
    assert any("Decision owner: missing" in error for error in _errors(result))


def test_indented_code_cannot_supply_a_missing_field() -> None:
    result = run_validator(
        valid_document().replace(
            "Decision owner: Release manager.\n",
            "\n    Decision owner: Release manager.\n\n",
        )
    )

    assert result.returncode == 1, result.stdout
    assert any("Decision owner: missing" in error for error in _errors(result))


def test_tab_indented_code_cannot_supply_a_missing_field() -> None:
    result = run_validator(
        valid_document().replace(
            "Decision owner: Release manager.\n",
            "\n\tDecision owner: Release manager.\n\n",
        )
    )

    assert result.returncode == 1, result.stdout
    assert any("Decision owner: missing" in error for error in _errors(result))


def test_indented_code_directly_after_the_gate_heading_is_code() -> None:
    result = run_validator(
        valid_document().replace(
            "## Human Decision Gate\n\nDecision owner: Release manager.\n",
            "## Human Decision Gate\n    Decision owner: Release manager.\n\n",
        )
    )

    assert result.returncode == 1, result.stdout
    assert any("Decision owner: missing" in error for error in _errors(result))


def test_indented_code_cannot_override_a_visible_invalid_class() -> None:
    result = run_validator(
        valid_document().replace(
            "Approval class: production-change.\n",
            "Approval class: internal.\n\n    Approval class: production-change.\n\n",
        )
    )

    assert result.returncode == 1, result.stdout
    assert any("internal work takes no gate" in error for error in _errors(result))


def test_indented_paragraph_continuation_stays_visible() -> None:
    """Four spaces cannot interrupt a paragraph, so a continuation line is text."""
    result = run_validator(
        valid_document().replace(
            "Decision owner: Release manager.\n",
            "Decision owner: Release manager.\n    continued on a second line.\n",
        )
    )

    assert result.returncode == 0, result.stdout


def test_field_in_a_list_item_continuation_paragraph_stays_visible() -> None:
    result = run_validator(
        valid_document().replace(
            "Decision owner: Release manager.\n",
            "- Gate notes\n\n    Decision owner: Release manager.\n\n",
        )
    )

    assert result.returncode == 0, result.stdout


def test_code_nested_in_a_list_item_cannot_supply_a_field() -> None:
    result = run_validator(
        valid_document().replace(
            "Decision owner: Release manager.\n",
            "- Gate notes\n\n      Decision owner: Release manager.\n\n",
        )
    )

    assert result.returncode == 1, result.stdout
    assert any("Decision owner: missing" in error for error in _errors(result))


def test_comment_opener_inside_indented_code_does_not_hide_a_second_gate() -> None:
    result = run_validator(valid_document() + "\n    <!-- example\n\n## Human Decision Gate" + GATE_BODY)

    assert result.returncode == 1, result.stdout
    assert any("one ## Human Decision Gate" in error for error in _errors(result))


def test_level_one_heading_ends_the_gate_section() -> None:
    doc = valid_document().replace("Minimum evidence plan: Run rollback smoke test and deployment dry run.\n", "")
    doc += "\n# Appendix\n\nMinimum evidence plan: Run rollback smoke test and deployment dry run.\n"
    result = run_validator(doc)

    assert result.returncode == 1, result.stdout
    assert any("Minimum evidence plan: missing" in error for error in _errors(result))


def test_indented_level_one_heading_ends_the_gate_section() -> None:
    doc = valid_document().replace("Decision owner: Release manager.\n", "")
    doc += "\n  #\nDecision owner: Release manager.\n"
    result = run_validator(doc)

    assert result.returncode == 1, result.stdout
    assert any("Decision owner: missing" in error for error in _errors(result))


def test_level_three_heading_stays_inside_the_gate_section() -> None:
    result = run_validator(
        valid_document().replace(
            "Minimum evidence plan:",
            "### Evidence\n\nMinimum evidence plan:",
        )
    )

    assert result.returncode == 0, result.stdout


def test_conflicting_duplicate_approval_class_fails() -> None:
    result = run_validator(
        valid_document().replace(
            "Approval class: production-change.",
            "Approval class: secret-creation.\nApproval class: production-change.",
        )
    )

    assert result.returncode == 1, result.stdout
    assert any("Approval class: declared 2 times" in error for error in _errors(result))


def test_identical_duplicate_control_field_fails() -> None:
    result = run_validator(
        valid_document().replace(
            "Decision owner: Release manager.",
            "Decision owner: Release manager.\n- **Decision owner:** Release manager.",
        )
    )

    assert result.returncode == 1, result.stdout
    assert any("Decision owner: declared 2 times" in error for error in _errors(result))


def test_duplicate_label_differing_only_in_case_fails() -> None:
    result = run_validator(
        valid_document().replace(
            "Allowed outcomes: ALLOW, BLOCK, REVISE, ESCALATE.",
            "Allowed outcomes: ALLOW, BLOCK, REVISE, ESCALATE.\nALLOWED OUTCOMES: ALLOW.",
        )
    )

    assert result.returncode == 1, result.stdout
    assert any("Allowed outcomes: declared 2 times" in error for error in _errors(result))


def test_hidden_duplicate_control_field_is_not_a_duplicate() -> None:
    result = run_validator(
        valid_document().replace(
            "Approval class: production-change.",
            "Approval class: production-change.\n<!-- Approval class: customer-message. -->",
        )
    )

    assert result.returncode == 0, result.stdout


def test_repeated_free_text_label_is_not_a_control_duplicate() -> None:
    result = run_validator(
        valid_document().replace(
            "Sequencing constraints:",
            "Note: first.\nNote: second.\nSequencing constraints:",
        )
    )

    assert result.returncode == 0, result.stdout


# Second repair round (cognovis/library-core#246 review residuals).


def _without_owner(replacement: str) -> subprocess.CompletedProcess[str]:
    return run_validator(valid_document().replace("Decision owner: Release manager.\n", replacement))


def _assert_owner_missing(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 1, result.stdout
    assert any("Decision owner: missing" in error for error in _errors(result))


def test_indented_code_after_a_thematic_break_cannot_supply_a_field() -> None:
    for rule in ("---", "***", "* * *", "___"):
        _assert_owner_missing(_without_owner(f"Note.\n\n{rule}\n    Decision owner: Release manager.\n\n"))


def test_indented_code_after_a_setext_underline_cannot_supply_a_field() -> None:
    _assert_owner_missing(_without_owner("Notes\n===\n    Decision owner: Release manager.\n\n"))


def test_fence_inside_a_list_item_cannot_supply_a_field() -> None:
    _assert_owner_missing(
        _without_owner("- Example\n\n    ```text\n    Decision owner: Release manager.\n    ```\n\n")
    )


def test_fence_inside_a_list_item_closes_and_later_fields_stay_visible() -> None:
    result = _without_owner("- Example\n\n    ```text\n    Note: x\n    ```\n\nDecision owner: Release manager.\n")

    assert result.returncode == 0, result.stdout


def test_list_fence_ends_with_its_list_item() -> None:
    """Fenced code takes no lazy continuation, so a column-0 line ends item and fence."""
    result = _without_owner("- Example\n  ```\n  code\nDecision owner: Release manager.\n")

    assert result.returncode == 0, result.stdout


def test_multiline_code_span_cannot_supply_a_field() -> None:
    _assert_owner_missing(_without_owner("An example `starts\nDecision owner: Release manager.\nends` here.\n"))


def test_field_before_a_multiline_code_span_stays_visible() -> None:
    result = run_validator(
        valid_document().replace(
            "Decision owner: Release manager.",
            "Decision owner: Release manager, see `a\nb` too.",
        )
    )

    assert result.returncode == 0, result.stdout


def test_escaped_backtick_does_not_open_a_span_so_a_genuine_comment_hides_a_gate() -> None:
    result = run_validator(
        valid_document() + "\nThe literal \\`<!-- draft marker \\` stays.\n\n## Human Decision Gate" + GATE_BODY
    )

    assert result.returncode == 0, result.stdout
    assert not any("one ## Human Decision Gate" in error for error in _errors(result))


def test_escaped_backslash_before_a_backtick_still_opens_a_span() -> None:
    result = run_validator(
        valid_document() + "\nThe literal \\\\`<!--` stays code.\n\n## Human Decision Gate" + GATE_BODY
    )

    assert result.returncode == 1, result.stdout
    assert any("one ## Human Decision Gate" in error for error in _errors(result))


def test_escaped_opener_leaves_the_rest_of_its_run_as_a_span() -> None:
    """In \\``x`` the first backtick is literal and the remaining one opens a span."""
    result = run_validator(
        valid_document() + "\nSee \\``<!--` here.\n\n## Human Decision Gate" + GATE_BODY
    )

    assert result.returncode == 1, result.stdout
    assert any("one ## Human Decision Gate" in error for error in _errors(result))


def test_span_lookahead_stops_at_block_boundaries() -> None:
    for boundary in ("- `<!--` here", "* `<!--` here", "1. `<!--` here", "***\n`<!--` here", "> `<!--` here"):
        result = run_validator(valid_document() + f"\nText `tick\n{boundary}\n\n## Human Decision Gate" + GATE_BODY)

        assert result.returncode == 1, (boundary, result.stdout)
        assert any("one ## Human Decision Gate" in error for error in _errors(result)), boundary


def test_ordered_item_not_starting_at_one_continues_the_paragraph() -> None:
    """``2.`` cannot interrupt a paragraph, so the span closes there and the comment is real."""
    result = run_validator(
        valid_document() + "\nText `tick\n2. ` <!-- hidden\n\n## Human Decision Gate" + GATE_BODY
    )

    assert result.returncode == 0, result.stdout


def test_unmatched_backtick_in_a_heading_does_not_reach_the_next_block() -> None:
    """A heading's inline content ends on its line, so its backtick stays literal."""
    result = _without_owner("### Notes `\nDecision owner: Release manager.\nClosing `\n")

    assert result.returncode == 0, result.stdout


def test_code_span_within_a_heading_line_still_hides_no_gate() -> None:
    result = run_validator(valid_document() + "\n### Notes `<!--` here\n\n## Human Decision Gate" + GATE_BODY)

    assert result.returncode == 1, result.stdout
    assert any("one ## Human Decision Gate" in error for error in _errors(result))


def test_brief_without_a_gate_remains_valid() -> None:
    result = run_validator(BRIEF_ONLY)

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)["data"]
    assert data == {"decision_brief": True, "human_decision_gate": False}


def test_escaped_comment_opener_on_its_own_line_does_not_hide_a_second_gate() -> None:
    """``\\<!--`` renders a literal ``<!--``, so the gate after it is visible."""
    result = run_validator(valid_document() + "\n\\<!--\n\n## Human Decision Gate" + GATE_BODY)

    assert result.returncode == 1, result.stdout
    assert any("one ## Human Decision Gate" in error for error in _errors(result))


def test_escaped_comment_opener_mid_line_does_not_hide_a_second_gate() -> None:
    result = run_validator(valid_document() + "\nThe marker \\<!-- stays literal.\n\n## Human Decision Gate" + GATE_BODY)

    assert result.returncode == 1, result.stdout
    assert any("one ## Human Decision Gate" in error for error in _errors(result))


def test_escaped_backslash_before_a_comment_opener_still_hides_a_gate() -> None:
    """In ``\\\\<!--`` the backslashes escape each other, so the comment is real."""
    result = run_validator(valid_document() + "\nA literal \\\\<!--\n## Human Decision Gate" + GATE_BODY + "-->\n")

    assert result.returncode == 0, result.stdout
    assert not any("one ## Human Decision Gate" in error for error in _errors(result))
