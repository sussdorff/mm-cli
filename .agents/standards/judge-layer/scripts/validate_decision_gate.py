#!/usr/bin/env python3
"""Validate Decision Brief and Human Decision Gate markdown shape."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


DECISION_BRIEF_FIELDS = {
    "Decision required",
    "Recommended default",
    "Operational risk",
    "Operational do-nothing/default outcome",
    "Delivery consequence",
    "Decision needed by",
    "Evidence appendix references",
    "Blast radius",
    "Rollback path",
    "Alternatives considered",
}
DECISION_GATE_FIELDS = {
    "Decision owner",
    "Approval class",
    "Allowed outcomes",
    "Trigger timing",
    "Minimum evidence plan",
    "Operational do-nothing/default outcome",
    "Delivery consequence",
    "Overrideability",
    "Sequencing constraints",
}
JUDGE_OUTCOMES = {"ALLOW", "BLOCK", "REVISE", "ESCALATE"}
# A human gate exists only for these two classes (AGENTS.md, Scope and
# authorization, 2026-10-04). Internal work never takes a gate.
APPROVAL_CLASSES = {"production-change", "customer-message"}
MANDATE_FIELDS = {
    "scope",
    "limits",
    "evidence_refs",
    "granted_at",
    "granted_by",
    "expires_at",
    "supersedes",
}


def load_document(path: str) -> str:
    """Load a markdown document."""
    return sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")


def is_non_empty_string(value: Any) -> bool:
    """Return whether value is a non-empty string."""
    return isinstance(value, str) and bool(value.strip())


def _make_visible(markdown: str) -> str:
    """Return the rendered-visible text of ``markdown``, one output line per input line.

    The single visibility seam for gate counting, section extraction and field
    parsing. Fenced code blocks (backtick or tilde, opened by three or more
    characters with up to three spaces of indent, closed only by a bare fence of
    the same character at least as long) are blanked whole, comment markers
    included. Indented code blocks are blanked too: a line indented four columns
    (tabs to the next multiple of four) beyond its container, where it cannot
    continue an open paragraph, and its indented or blank continuation lines.
    Inside a list item the code indent counts from the item's content column, so
    a list item's own indented paragraph stays visible. Outside code an HTML
    comment removes only the text from ``<!--`` to ``-->``, across lines if it
    is unterminated; text before and after it stays visible, so
    ``## Human Decision Gate <!-- note -->`` is still that heading. A ``<!--``
    behind an odd number of backslashes is escaped and literal, so it opens no
    comment; behind an even number the backslashes escape each other and the
    comment is real. A ``-->`` inside a comment is never escaped. A code span -
    a backtick run closed by the next run of the same length within its
    paragraph - is visible text, so a ``<!--`` inside it opens no comment; an
    unmatched or backslash-escaped backtick is literal, and a paragraph ends at
    a blank line or at a line that starts another block (heading, fence, HTML
    comment, thematic break, setext underline, blockquote, or a list item that
    may interrupt a paragraph); a span opened in an ATX heading must close on
    that line. A line that begins inside a code span is code
    text: it is emitted behind a backtick so it never reads as a field. A
    thematic break or setext underline closes the paragraph like a heading, and
    inside a list item a fence is recognised relative to the item's content
    column and ends with the item. Line count is preserved.
    """
    lines = markdown.splitlines()
    result: list[str] = []
    fence: str | None = None
    fence_base = 0
    in_comment = False
    span: int | None = None
    code_indent: int | None = None
    paragraph = False
    list_content: int | None = None
    after_blank = False
    for number, line in enumerate(lines):
        blank = not line.strip()
        indent = _indent_columns(line)
        if fence is not None:
            if fence_base and not blank and indent < fence_base:
                # Fenced code takes no lazy continuation: the list item ends here.
                fence = None
                list_content = None
            else:
                close = _FENCE_CLOSE_RE.match(_strip_columns(line, fence_base))
                if close and close["marker"][0] == fence[0] and len(close["marker"]) >= len(fence):
                    fence = None
                result.append("")
                continue
        if code_indent is not None:
            if blank or indent >= code_indent:
                result.append("")
                continue
            code_indent = None
        if not in_comment and span is None:
            if blank:
                paragraph = False
                after_blank = True
                result.append("")
                continue
            threshold = 4 if list_content is None else list_content + 4
            if indent >= threshold and not paragraph:
                code_indent = threshold
                result.append("")
                continue
            base = list_content if list_content is not None and indent >= list_content else 0
            opening = _FENCE_OPEN_RE.match(_strip_columns(line, base))
            if opening and not (opening["marker"][0] == "`" and "`" in opening["info"]):
                fence = opening["marker"]
                fence_base = base
                if not base:
                    list_content = None
                paragraph = False
                result.append("")
                continue
        starts_html_block = not in_comment and span is None and bool(_HTML_COMMENT_BLOCK_RE.match(line))
        in_span_at_start = span is not None
        # An ATX heading's inline content ends on its own line.
        one_line_block = not in_comment and span is None and bool(_ATX_ANY_RE.match(line))
        visible: list[str] = []
        rest = line
        while rest:
            if in_comment:
                end = rest.find("-->")
                if end < 0:
                    rest = ""
                    break
                in_comment = False
                rest = rest[end + 3 :]
            elif span is not None:
                close = _closing_ticks(rest, span)
                if close is None:
                    visible.append(rest)
                    rest = ""
                    break
                visible.append(rest[: close + span])
                rest = rest[close + span :]
                span = None
            else:
                comment = _next_comment(rest)
                tick = _next_opener(rest)
                if tick is not None and (comment < 0 or tick[0] < comment):
                    start, end = tick
                    visible.append(rest[:end])
                    rest = rest[end:]
                    following = [] if one_line_block else lines[number + 1 :]
                    if _span_closes(rest, end - start, following):
                        span = end - start
                    continue
                if comment < 0:
                    visible.append(rest)
                    break
                visible.append(rest[:comment])
                in_comment = True
                rest = rest[comment + 4 :]
        shown = "".join(visible).rstrip()
        if in_span_at_start:
            shown = "`" + shown
        result.append(shown)
        if blank:
            continue
        if not shown.strip() or starts_html_block:
            # A comment-only line is an HTML block: it ends the paragraph, so
            # an indented line after it is code.
            paragraph = False
            continue
        if _ATX_ANY_RE.match(shown):
            paragraph = False
            list_content = None
        elif not in_span_at_start and (
            _THEMATIC_BREAK_RE.match(shown) or (paragraph and _SETEXT_UNDERLINE_RE.match(shown))
        ):
            paragraph = False
            if list_content is not None and indent < list_content:
                list_content = None
        else:
            item = _LIST_ITEM_RE.match(shown)
            limit = 4 if list_content is None else list_content + 4
            if item is not None and _indent_columns(shown) < limit:
                list_content = len(item.group("lead").expandtabs(4))
            elif list_content is not None and after_blank and indent < list_content:
                list_content = None
            paragraph = True
        after_blank = False
    return "\n".join(result) + "\n"


def _indent_columns(line: str) -> int:
    """Return the leading indentation width, expanding tabs to multiples of four."""
    width = 0
    for char in line:
        if char == " ":
            width += 1
        elif char == "\t":
            width += 4 - width % 4
        else:
            break
    return width


def _strip_columns(line: str, columns: int) -> str:
    """Remove up to ``columns`` columns of leading whitespace, tabs counted to multiples of four."""
    if not columns:
        return line
    body = line.lstrip(" \t")
    lead = line[: len(line) - len(body)].expandtabs(4)
    return lead[min(columns, len(lead)) :] + body


def _next_opener(text: str) -> tuple[int, int] | None:
    """Return (start, end) of the first backtick run that may open a code span.

    A backtick behind an odd number of backslashes is escaped and literal; the
    rest of its run may still open a span.
    """
    for run in _TICK_RE.finditer(text):
        start, end = run.span()
        slashes = len(text[:start]) - len(text[:start].rstrip("\\"))
        if slashes % 2:
            start += 1
        if start < end:
            return start, end
    return None


def _next_comment(text: str) -> int:
    """Return the start of the first ``<!--`` in ``text`` that opens a comment, or -1.

    A ``<`` behind an odd number of backslashes is escaped and literal, so its
    ``<!--`` opens no comment; behind an even number the backslashes escape each
    other and the comment is real.
    """
    start = text.find("<!--")
    while start >= 0:
        slashes = len(text[:start]) - len(text[:start].rstrip("\\"))
        if not slashes % 2:
            return start
        start = text.find("<!--", start + 1)
    return -1


def _ends_paragraph(line: str) -> bool:
    """Return whether ``line`` starts a block that interrupts an open paragraph."""
    return bool(
        not line.strip()
        or _ATX_ANY_RE.match(line)
        or _FENCE_OPEN_RE.match(line)
        or _HTML_COMMENT_BLOCK_RE.match(line)
        or _THEMATIC_BREAK_RE.match(line)
        or _SETEXT_UNDERLINE_RE.match(line)
        or _BLOCKQUOTE_RE.match(line)
        or _INTERRUPTING_ITEM_RE.match(line)
    )


def _closing_ticks(text: str, length: int) -> int | None:
    """Return the start of the first backtick run of exactly ``length`` in ``text``."""
    for run in _TICK_RE.finditer(text):
        if len(run.group()) == length:
            return run.start()
    return None


def _span_closes(rest: str, length: int, following_lines: list[str]) -> bool:
    """Return whether a code span opened by ``length`` backticks closes in its block.

    ``rest`` is the opening line after the opener; ``following_lines`` are the
    lines after it that its block may continue onto (none for a heading).
    """
    if _closing_ticks(rest, length) is not None:
        return True
    for following in following_lines:
        if _ends_paragraph(following):
            return False
        if _closing_ticks(following, length) is not None:
            return True
    return False


def extract_section(markdown: str, heading: str) -> str | None:
    """Return the body for a level-2 markdown section.

    Recognises CommonMark ATX headings: 0-3 leading spaces, ``##`` marker,
    space/tab separator, heading text, optional closing ``#`` sequence preceded
    by a space or tab. The section ends at the next heading of the same or a
    higher level (``#`` or ``##``); level-3 and deeper headings stay inside it.
    """
    pattern = re.compile(
        rf"^ {{0,3}}##[ \t]+{re.escape(heading)}(?:[ \t]+#*)?\s*$",
        re.MULTILINE,
    )
    match = pattern.search(markdown)
    if match is None:
        return None
    next_heading = re.search(r"^ {0,3}#{1,2}(?:[ \t]+|[ \t]*$)", markdown[match.end() :], re.MULTILINE)
    if next_heading is None:
        return markdown[match.end() :]
    return markdown[match.end() : match.end() + next_heading.start()]


def has_subheading(section: str, heading: str) -> bool:
    """Return whether a section contains a level-3 markdown heading."""
    return bool(
        re.search(
            rf"^ {{0,3}}###[ \t]+{re.escape(heading)}(?:[ \t]+#*)?\s*$",
            section,
            re.MULTILINE,
        )
    )


def _field_lines(section: str) -> list[tuple[str, str]]:
    """Return every `Label: value` line of ``section`` as (lower-case label, value)."""
    found: list[tuple[str, str]] = []
    for line in section.splitlines():
        match = re.match(r"^\s*(?:[-*]\s*)?(?:\*\*)?([^:\n`*][^:\n]*?)(?:\*\*)?:\s*(.*?)\s*$", line)
        if match is None:
            continue
        found.append((match.group(1).strip().lower(), match.group(2).strip()))
    return found


def parse_fields(section: str) -> dict[str, str]:
    """Parse simple markdown field labels of the form `Label: value`."""
    return dict(_field_lines(section))


def validate_unique_control_fields(section: str, fields: set[str], section_name: str, errors: list[str]) -> None:
    """Reject a control field declared more than once; no declaration may override another."""
    counts: dict[str, int] = {}
    for label, _ in _field_lines(section):
        counts[label] = counts.get(label, 0) + 1
    for field in sorted(fields):
        count = counts.get(field.lower(), 0)
        if count > 1:
            errors.append(f"{section_name}.{field}: declared {count} times; declare each control field once")


def validate_required_fields(
    *,
    section_name: str,
    fields: dict[str, str],
    required: set[str],
    errors: list[str],
) -> None:
    """Validate required non-empty fields."""
    for field in sorted(required):
        value = fields.get(field.lower())
        if not is_non_empty_string(value):
            errors.append(f"{section_name}.{field}: missing required field")


def validate_allowed_outcomes(value: str | None, errors: list[str]) -> None:
    """Validate gate outcome vocabulary without deciding the outcome."""
    if not is_non_empty_string(value):
        return
    tokens = [token.strip().strip(".`").upper() for token in re.split(r"[,/]", value or "") if token.strip()]
    invalid = [token for token in tokens if token not in JUDGE_OUTCOMES]
    if not tokens or invalid:
        errors.append(
            "Human Decision Gate.Allowed outcomes: expected comma-separated values from "
            "ALLOW, BLOCK, REVISE, ESCALATE"
        )


def validate_approval_class(value: str | None, errors: list[str]) -> None:
    """Accept a gate only for a production change or a customer message."""
    if not is_non_empty_string(value):
        return
    if (value or "").strip().strip(".`").lower() not in APPROVAL_CLASSES:
        errors.append(
            "Human Decision Gate.Approval class: expected one of "
            "production-change, customer-message; internal work takes no gate"
        )


def validate_mandate_field_disjointness(fields: dict[str, str], errors: list[str]) -> None:
    """Reject inline Mandate field redefinitions in a gate."""
    for field in sorted(MANDATE_FIELDS & set(fields)):
        errors.append(
            f"Human Decision Gate: Mandate field {field!r} must not be redefined; "
            "reference mandate-schema.md instead"
        )


GATE_HEADING_RE = re.compile(r"^ {0,3}##[ \t]+human decision gate\b", re.IGNORECASE)


_FENCE_OPEN_RE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
_FENCE_CLOSE_RE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})[ \t]*$")
_TICK_RE = re.compile(r"`+")
_HTML_COMMENT_BLOCK_RE = re.compile(r"^ {0,3}<!--")
_ATX_ANY_RE = re.compile(r"^ {0,3}#{1,6}(?:[ \t]|$)")
_LIST_ITEM_RE = re.compile(r"^(?P<lead>[ \t]*(?:[-*+]|\d{1,9}[.)])(?:[ \t]{1,4}|$))")
_THEMATIC_BREAK_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_SETEXT_UNDERLINE_RE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
_BLOCKQUOTE_RE = re.compile(r"^ {0,3}>")
# A list item interrupts a paragraph only with content, and an ordered one
# only when it starts at 1.
_INTERRUPTING_ITEM_RE = re.compile(r"^ {0,3}(?:[-*+]|1[.)])[ \t]+\S")


def count_gate_headings(markdown: str) -> int:
    """Count gate headings of any case or qualifier in already-visible markdown."""
    return sum(1 for line in markdown.splitlines() if GATE_HEADING_RE.match(line))


def validate_decision_document(markdown: str) -> list[str]:
    """Return structural errors for Decision Brief and Human Decision Gate markdown."""
    errors: list[str] = []
    visible = _make_visible(markdown)
    brief_section = extract_section(visible, "Decision Brief")
    gate_section = extract_section(visible, "Human Decision Gate")
    if brief_section is None and gate_section is None:
        gate_count = count_gate_headings(visible)
        if gate_count > 0:
            return [
                "Human Decision Gate: visible gate heading found but section could "
                "not be extracted; use the exact heading '## Human Decision Gate' "
                "without qualifiers"
            ]
        return ["document: expected ## Decision Brief or ## Human Decision Gate section"]

    if brief_section is not None:
        if not has_subheading(brief_section, "Compact Manager View"):
            errors.append("Decision Brief.Compact Manager View: missing required section")
        if not has_subheading(brief_section, "Evidence Appendix"):
            errors.append("Decision Brief.Evidence Appendix: missing required section")
        validate_required_fields(
            section_name="Decision Brief",
            fields=parse_fields(brief_section),
            required=DECISION_BRIEF_FIELDS,
            errors=errors,
        )

    gate_count = count_gate_headings(visible)
    if gate_section is not None:
        if gate_count > 1:
            errors.append(
                "Human Decision Gate: expected one ## Human Decision Gate per work order; "
                "one ALLOW covers every listed action, so do not stage approvals"
            )
        gate_fields = parse_fields(gate_section)
        validate_unique_control_fields(gate_section, DECISION_GATE_FIELDS, "Human Decision Gate", errors)
        validate_required_fields(
            section_name="Human Decision Gate",
            fields=gate_fields,
            required=DECISION_GATE_FIELDS,
            errors=errors,
        )
        validate_allowed_outcomes(gate_fields.get("allowed outcomes"), errors)
        validate_approval_class(gate_fields.get("approval class"), errors)
        validate_mandate_field_disjointness(gate_fields, errors)
    elif gate_count > 0:
        errors.append(
            "Human Decision Gate: visible gate heading found but section could "
            "not be extracted; use the exact heading '## Human Decision Gate' "
            "without qualifiers"
        )

    return errors


def envelope(status: str, summary: str, data: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    """Build the execution-result JSON envelope."""
    return {
        "status": status,
        "summary": summary,
        "data": data,
        "errors": errors,
        "next_steps": [] if status == "ok" else ["Fix the Decision Brief or Human Decision Gate structure."],
    }


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Validate Decision Brief and Human Decision Gate markdown.")
    parser.add_argument("document", help="Markdown path, or '-' for stdin")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the validator."""
    args = build_parser().parse_args(argv)
    try:
        markdown = load_document(args.document)
    except Exception as exc:
        result = envelope("error", "Decision document could not be parsed", {}, [str(exc)])
        print(json.dumps(result, indent=2))
        return 2

    errors = validate_decision_document(markdown)
    status = "error" if errors else "ok"
    visible = _make_visible(markdown)
    data = {
        "decision_brief": extract_section(visible, "Decision Brief") is not None,
        "human_decision_gate": extract_section(visible, "Human Decision Gate") is not None,
    }
    summary = "Decision document schema valid" if not errors else "Decision document schema invalid"
    print(json.dumps(envelope(status, summary, data, errors), indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
