"""Every delivery lands through `ccore pr merge`, the only landing route."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"
STANDARD = (
    Path(__file__).resolve().parents[3]
    / "standards"
    / "executive-pack"
    / "executive-pack.md"
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


def _step_7() -> str:
    return _flat(_section(SKILL, "## 7. Merge decision"))


def _conditions() -> str:
    step_7 = _step_7()
    start = step_7.index("lands only when all of the following hold")
    return step_7[start : step_7.index("These two conditions are the product owner's rule")]


def test_ccore_pr_merge_is_the_only_landing_route_for_every_repository() -> None:
    step_7 = _step_7()
    assert "Every repository lands through `ccore pr merge`" in step_7
    assert "`ccore pr merge` is the only landing route" in step_7
    assert "from the delivery worktree" in step_7


def test_the_split_into_a_script_route_and_a_merge_route_is_gone() -> None:
    text = SKILL.read_text(encoding="utf-8")
    flat = _flat(text)
    for retired in (
        "landing script",
        "### Landing route",
        "[landing route](#landing-route)",
        "merge route below, unchanged",
        "runs the script again",
        "Merge with the head commit SHA pinned",
        "read after the last edit of the pull request body",
    ):
        assert retired not in flat, retired


def test_skill_stays_repository_generic() -> None:
    text = SKILL.read_text(encoding="utf-8")
    for specific in ("land.sh", "MIRA", "CHANGELOG.md", "changelog entry"):
        assert specific not in text, specific


def test_the_main_session_never_merges_through_the_forge() -> None:
    step_7 = _step_7()
    never = step_7[step_7.index("never merges the pull request through the forge") :]
    assert "no `gh pr merge`, no `fgj` merge, no merge button" in never


def test_landing_keeps_verification_findings_assessments_risk_and_human_gate() -> None:
    conditions = _conditions()
    assert "`PASS` or `PASS+NOTES` for the head `ccore pr merge` starts from" in conditions
    assert "no accepted local finding is unrepaired" in conditions
    assert "no unresolved finding that Review decisions does not cover" in conditions
    assert "no product decision deviates" in conditions
    assert "no economic damage is to be expected" in conditions
    assert "Merge assessment section of the pull request body names both" in conditions
    assert "Risk statement section names every field" in conditions
    assert "no explicit human merge gate" in conditions


def test_verification_names_the_full_sha_of_the_head_ccore_lands() -> None:
    conditions = _conditions()
    verification = conditions[conditions.index("the Verification section records") :]
    verification = verification[: verification.index("- when the target's")]
    assert "names that head's full 40-character SHA" in verification
    assert "an abbreviated SHA does not count" in verification


def test_product_owner_rule_is_quoted_verbatim() -> None:
    assert (
        '"Wenn hier keine Produktentscheidung anders getroffen wurde als im Ticket und '
        'kein wirtschaftlicher Schaden zu erwarten ist, dann selber mergen."'
    ) in _step_7()


def test_pr_agent_evidence_holds_the_landing_unless_agents_md_waives_it() -> None:
    conditions = _conditions()
    assert "pr-agent's latest classification comment names the current head commit SHA" in (
        conditions
    )
    assert "a pr-agent review comment written or last edited at or after" in conditions
    step_7 = _step_7()
    assert (
        "unless the repository's `AGENTS.md` explicitly waives pr-agent evidence for "
        "landing" in step_7
    )


def test_a_pr_agent_waiver_is_written_as_the_body_line_ccore_reads() -> None:
    step_7 = _step_7()
    waiver = step_7[step_7.index("explicitly waives pr-agent evidence for landing") :]
    waiver = waiver[: waiver.index("The Atlas missing-review notice")]
    assert "a line `pr-agent review not required: <reason>`" in waiver
    assert "whose reason cites that `AGENTS.md` waiver" in waiver
    assert "without such an explicit waiver the main session never writes that line" in (
        waiver
    )


def test_the_review_condition_needs_a_review_newer_than_the_head_push() -> None:
    conditions = _conditions()
    review = conditions[conditions.index("a pr-agent review comment written") :]
    review = review[: review.index("- the Verification section records")]
    assert (
        "written or last edited at or after the host recorded the push of the current "
        "head" in review
    )
    assert "A review that predates the push of the current head" in review
    assert "a repair push or a `ccore pr ensure` rebase" in review
    assert "`pr_land_review_missing`" in review


def test_a_review_older_than_the_head_is_requested_once_per_head() -> None:
    step_7 = _step_7()
    stale = step_7[step_7.index("When the latest pr-agent review predates the push") :]
    assert "comments `/review` on the pull request once for that head" in stale
    assert "waits for the review to be written or edited instead of landing" in stale
    assert (
        "authorizes these two `/review` comments on the delivery's own pull request, "
        "once per notice and once per head; it authorizes no other comment" in stale
    )
    assert "stays open for a human with the missing review as the reason" in stale


def test_step_6_does_not_promise_a_single_review_covers_later_pushes() -> None:
    step_6 = _flat(_section(SKILL, "## 6. Pull request (`cognovis-pr`)"))
    assert "reviews the pull request once," not in step_6
    assert "reviews the pull request when it is first pushed" in step_6
    assert "on later pushes it only classifies again" in step_6


def test_step_6_hands_cognovis_pr_the_agents_md_waiver() -> None:
    step_6 = _flat(_section(SKILL, "## 6. Pull request (`cognovis-pr`)"))
    hand = step_6[step_6.index("Hand it the") : step_6.index("Publish the result")]
    assert "explicitly waives pr-agent evidence for landing, that waiver" in hand
    assert "`pr-agent review not required: <reason>` line" in hand


def test_required_checks_are_read_unless_ccore_waits_for_ci() -> None:
    conditions = _conditions()
    checks = conditions[conditions.index("does not declare `[landing] wait_for_ci = true`") :]
    assert (
        "the pull request's required checks on the head `ccore pr merge` starts from have "
        "passed; a failing or pending one holds the landing" in checks
    )
    assert "the CI wait inside `ccore pr merge` is the check" in checks
    step_7 = _step_7()
    lead = "pushes the squashed candidate through the repository's pre-push hook"
    wait = step_7[step_7.index(lead) :]
    assert "waits for CI on that candidate" in wait
    assert "every check named in `[landing] required_checks`" in wait
    assert "replaces the main session's own reading of the required checks" in wait
    assert "Required checks run inside `ccore pr merge`" not in step_7


def _stop_kind(lead: str) -> str:
    step_7 = _step_7()
    start = step_7.index(lead)
    ends = [
        step_7.find(marker, start + 1)
        for marker in (
            "- A candidate defect",
            "- A retryable or transport stop",
            "- A precondition stop",
            "- A configuration blocker",
            "Run `ccore pr merge` from",
        )
    ]
    return step_7[start : min(end for end in ends if end != -1)]


def test_a_candidate_defect_stop_goes_to_repair_and_verification() -> None:
    defect = _stop_kind("- A candidate defect")
    for code in ("`pr_prepush_gate_failed`", "`pr_land_ci_failed`", "`pr_rebase_conflict`"):
        assert code in defect, code
    for part in (
        "later finding",
        "designated repair author",
        "verification again",
        "runs `ccore pr merge` again",
    ):
        assert part in defect, part


def test_a_retryable_stop_is_rerun_without_repair() -> None:
    retry = _stop_kind("- A retryable or transport stop")
    assert "rerun as it is, with no repair" in retry
    for code in (
        "`pr_land_target_moving`",
        "`pr_branch_moved`",
        "`pr_push_failed`",
        "`pr_land_push_failed`",
        "`pr_land_ci_missing`",
        "`pr_land_ci_timeout`",
    ):
        assert code in retry, code
    assert "designated repair author" not in retry
    assert "pre-push hook rejecting the candidate is a candidate defect" in retry


def test_a_precondition_lookup_failure_is_rerun_as_it_is() -> None:
    retry = _stop_kind("- A retryable or transport stop")
    assert "`pr_land_precondition_lookup_failed`" in retry


def test_a_precondition_stop_is_missing_evidence_the_delivery_produces() -> None:
    precondition = _stop_kind("- A precondition stop")
    for code in (
        "`pr_land_review_missing`",
        "`pr_land_risk_statement_missing`",
        "`pr_land_verification_stale`",
    ):
        assert code in precondition, code
    assert "missing evidence the delivery produces before rerunning" in precondition
    for evidence in (
        "a pr-agent review written after the head's push",
        "the `/review` rules above",
        "a Risk statement",
        "recording its full SHA in Verification",
    ):
        assert evidence in precondition, evidence
    assert "never a skip and never a repair" in precondition
    assert "designated repair author" not in precondition


def test_a_configuration_blocker_is_reported_not_repaired() -> None:
    blocker = _stop_kind("- A configuration blocker")
    assert "reported as a blocker, not repaired in the delivery" in blocker
    assert "`pr_land_fast_forward_disallowed`" in blocker
    assert "`pr_land_config_invalid`" in blocker


def test_a_rerun_from_ccore_s_own_squashed_head_keeps_the_verdict() -> None:
    step_7 = _step_7()
    rerun = step_7[step_7.index("A stop after `ccore pr merge` pushed its candidate") :]
    assert "leaves the delivery branch at that squashed commit" in rerun
    assert "keeps the verdict (no new verification)" in rerun
    pending = rerun[rerun.index("When that head is not yet on the target") :]
    pending = pending[: pending.index("When that head is already")]
    assert "records the squashed head's full SHA in the Verification section" in pending
    assert "pr-agent review written after that head's push" in pending
    landed = rerun[rerun.index("When that head is already") :]
    assert "the target's landing commit of this pull request" in landed
    assert "records the preconditions as `checked_by_earlier_run`" in landed
    assert "the rerun only confirms the landing" in landed
    assert "Any delivery commit on top of it still invalidates the verdict" in rerun
    assert "does not re-open the pr-agent head conditions" not in step_7


def test_human_decision_sets_the_merge_human_label_and_does_not_land() -> None:
    step_7 = _step_7()
    human = step_7[step_7.index("When either assessment fails") :]
    assert "explicit human merge gate" in human
    assert "sets the label `merge:human` on the delivery's own pull request" in human
    assert "does not land" in human
    assert "`ccore pr merge` refuses a pull request that carries that label" in human
    assert (
        "delivery request that invokes this skill authorizes setting that label on the "
        "delivery's own pull request" in human
    )


def test_landing_runs_on_the_checked_out_branch_with_hooks_and_pr_text() -> None:
    step_7 = _step_7()
    run = step_7[step_7.index("Run `ccore pr merge`") :]
    assert "delivery branch checked out (not a detached HEAD)" in run
    assert "no uncommitted or untracked changes" in run
    assert "no rebase, merge, cherry-pick or revert in progress" in run
    assert "Never skip the repository's hooks: no `--no-verify` and no hook path override" in (
        run
    )
    assert "Never pass `--message`" in run


def test_the_main_session_never_skips_a_ccore_precondition() -> None:
    step_7 = _step_7()
    run = step_7[step_7.index("Run `ccore pr merge` from") :]
    assert "Never pass `--skip-precondition`" in run


def test_only_a_commit_the_delivery_adds_invalidates_the_verdict() -> None:
    step_7 = _step_7()
    assert (
        "`ccore pr merge`'s own rebase and squash onto a moved default branch is covered "
        "by the pre-push hook on the squashed candidate and does not invalidate the "
        "verdict; any commit the delivery adds does" in step_7
    )


def test_after_landing_confirm_merged_state_and_closed_work_order() -> None:
    step_7 = _step_7()
    after = step_7[step_7.index("After landing") :]
    assert "record the landed commit `ccore pr merge` reports" in after
    assert "pull request shows as merged" in after
    assert "`ccore tracker show <ref>`" in after
    assert "`ccore tracker close <ref>`" in after
    assert "post-merge postcondition" in after


def test_step_6_opens_the_pull_request_as_the_record_before_landing() -> None:
    step_6 = _flat(_section(SKILL, "## 6. Pull request (`cognovis-pr`)"))
    record = step_6[step_6.index("before landing, as the delivery record") :]
    for part in ("Review decisions", "Verification", "Merge assessment", "Risk statement"):
        assert part in record, part
    assert "the forge can mark it merged" in record
    assert "`merge:human` label" in record


def test_step_6_pull_request_text_becomes_the_landed_commit() -> None:
    step_6 = _flat(_section(SKILL, "## 6. Pull request (`cognovis-pr`)"))
    assert "Its title becomes the squash commit subject" in step_6
    assert "its `## Summary` section the commit body" in step_6
    assert "final before landing" in step_6
    assert "changes the landed commit text" in step_6


def test_pull_requests_without_a_work_order_land_through_ccore_too() -> None:
    section = _flat(_section(SKILL, "## Pull requests without a work order"))
    assert "lands through `ccore pr merge` as well, under the same conditions" in section
    assert "with the same two substitutions" in section
    assert "after the last body edit" not in section


def test_pull_requests_without_a_work_order_name_the_full_sha() -> None:
    section = _flat(_section(SKILL, "## Pull requests without a work order"))
    satisfies = section[section.index("the evidence above") :]
    assert (
        "recorded in the `## Verification` section with the current head's full "
        "40-character SHA, satisfies its Verification condition" in satisfies
    )


def test_standard_step_7_names_ccore_pr_merge_as_the_only_route() -> None:
    steps = _flat(_section(STANDARD, "## One delivery"))
    step_7 = steps[steps.index("7. merge decision") : steps.index("8. session retro")]
    assert "every repository lands through `ccore pr merge`" in step_7
    assert "never merges through the forge" in step_7
    assert "landing script" not in step_7


def test_standard_pr_agent_evidence_holds_the_landing_unless_waived() -> None:
    boundaries = _flat(_section(STANDARD, "## Boundaries"))
    both = boundaries[boundaries.index("merge needs both") :]
    assert (
        "unless the repository's `AGENTS.md` explicitly waives pr-agent evidence for "
        "landing" in both
    )
    unconfigured = boundaries[boundaries.index("pr-agent evidence exists only where") :]
    assert "does not land unless the repository's `AGENTS.md` explicitly waives" in (
        unconfigured
    )
    assert "an unconfigured pr-agent is no waiver by itself" in unconfigured
    # The retired implicit exemption let an unconfigured repository land on the
    # product owner rule alone.
    assert "owner merge rule of the shared AGENTS.md decides" not in boundaries
    assert "records that pr-agent is not configured" not in boundaries


def test_standard_required_checks_follow_the_ci_wait_declaration() -> None:
    boundaries = _flat(_section(STANDARD, "## Boundaries"))
    checks = boundaries[boundaries.index("Required checks:") :]
    assert "`[landing] wait_for_ci = true`, the CI wait inside `ccore pr merge` is the check" in (
        checks
    )
    assert (
        "reads the pull request's required checks on the head `ccore pr merge` starts from "
        "and does not land while one fails or is pending" in checks
    )


def test_standard_verified_head_survives_only_ccore_s_own_rebase() -> None:
    verification = _flat(_section(STANDARD, "## Verification"))
    head = verification[verification.index("The verified head is the head that lands") :]
    assert "`ccore pr merge`'s own rebase and squash onto a moved default branch" in head
    assert "covered by the pre-push hook on the squashed candidate" in head
    assert "a commit the delivery adds invalidates the verdict" in head
    retry = head[head.index("A head that `ccore pr merge` produced in an earlier") :]
    assert "keeps the verdict" in retry
    assert "the Verification section names its full SHA" in retry
    assert "a pr-agent review written after its push is needed again" in retry
    assert "records the preconditions as checked by the earlier run" in retry
    assert "landing script" not in _flat(STANDARD.read_text(encoding="utf-8"))


def test_standard_and_step_7_agree_that_a_ccore_retry_head_needs_a_new_review() -> None:
    retired = "does not re-open the pr-agent head conditions"
    assert retired not in _flat(STANDARD.read_text(encoding="utf-8"))
    assert retired not in _flat(SKILL.read_text(encoding="utf-8"))


def _record_file_expression() -> str:
    tracking = _section(SKILL, "## Delivery resource tracking")
    init = tracking[tracking.index("delivery_teardown.py init") :]
    init = init[: init.index("```")]
    match = re.search(r"--record-file (\"[^\"]+\"|\S+)", init)
    assert match, init
    return match.group(1)


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_delivery_record_lives_outside_the_working_tree(tmp_path: Path) -> None:
    expression = _record_file_expression()
    assert "rev-parse --absolute-git-dir" in expression

    main = tmp_path / "repo"
    main.mkdir()
    _git("init", "-q", "-b", "main", cwd=main)
    _git(
        "-c", "user.name=t", "-c", "user.email=t@t",
        "commit", "-q", "--allow-empty", "-m", "base",
        cwd=main,
    )
    worktree = tmp_path / "delivery"
    _git("worktree", "add", "-q", "-b", "task", str(worktree), cwd=main)

    record = Path(
        subprocess.run(
            ["bash", "-c", "printf %s " + expression.replace("<worktree>", str(worktree))],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    assert not record.resolve().is_relative_to(worktree.resolve())

    sys.path.insert(0, str(SKILL.parent / "scripts"))
    from delivery_teardown import init_record

    init_record(str(worktree), "tok", record)
    assert record.exists()
    assert record.with_suffix(record.suffix + ".lock").exists()
    assert _git("status", "--porcelain", "--untracked-files=all", cwd=worktree) == ""
