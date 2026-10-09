---
name: executive-pack
description: Deliver one hosted work order in the invoking session - grilling, tdd implementation, three-model adversarial review with triage, independent verification, one pull request, merge decision and session retro.
requires_standards: [executive-pack, dispatch/model-routing]
requires:
  - script:ccore
  - skill:playwright-cli
  - skill:cognovis-pr
  - skill:session-retro
  - agent:implementer
  - standard:executive-pack
scripts:
  - path: scripts/finding_triage.py
    role: helper
    entrypoint: true
    language: python
    output_contract: json-envelope
  - path: scripts/delivery_teardown.py
    role: helper
    entrypoint: true
    language: python
    output_contract: teardown-line
compatibility: {}
metadata: {}
---

# Delivery

The invoking session is the main session (`opus`). It owns one hosted work order from
grilling to the merge decision and never hands that ownership to another agent. Work
happens in the delivery worktree the session already owns (the T3 thread worktree, or a
self-managed linked worktree). Read the work order with `ccore tracker show <ref>`.

The Pocock skills `grilling`, `tdd`, `code-review` and `pr` are installed globally per
host; `playwright-cli` comes from the Library. Model aliases and their `ccore agent`
fallback routes are in the injected `dispatch/model-routing` standard: use the native
subagent with the alias first, the named `ccore agent` route only when the alias is
unavailable.

Resolve the installed helper root local-first and fail closed if none exists:
`<repo>/.agents/skills/executive-pack`, `<repo>/.claude/skills/executive-pack`,
`~/.agents/skills/executive-pack`, `~/.claude/skills/executive-pack`. Helpers are
`scripts/finding_triage.py` (review triage) and `scripts/delivery_teardown.py`
(resource teardown).

## 1. Grilling (main session, `opus`)

Run `grilling` against the work order until the intent, the acceptance criteria and the
boundaries are unambiguous. A question that reading code, running the artifact or
building a throwaway prototype can answer is answered by the agent, not asked. Only
product or preference decisions go to the human. When the answers change the work
order, update it with the intake author check and `ccore tracker update`.

## 2. Implementation (`implementer` subagent on `opus`, with `tdd`)

Dispatch one `implementer` subagent on `opus` in the delivery worktree. It receives the
work order, the grilling outcome, the worktree and its base commit, implements with
`tdd`, runs the affected checks and commits the candidate. It does not review or verify
its own change.

## 3. Adversarial review (three models, read-only, in parallel)

Dispatch three read-only reviewer subagents in parallel, one each on `opus` (a fresh
context, not the implementer's), `sonnet` and `haiku`. Name the `opus` reviewer the
**designated repair author** in its brief before dispatching: it reviews read-only like
the others now, and it is the one actor that may later receive write authority for the
triaged repair set. Dispatch it as an agent type that has write tools and instruct it
to stay read-only during review: a read-only agent type (for example `Explore`) cannot
take the repair later, and the hand-off then needs a replacement. All three review the
same fixed candidate commit. All three get the
same adversarial brief, with no per-model persona:

- the stated intent and the acceptance criteria of the work order,
- the complete diff from the base commit to the candidate,
- the instruction: find where this change fails its intent - incorrect behaviour,
  missing cases, and claims the change or its tests do not prove. Return each finding
  with an id, a severity (`nit`, `low`, `medium`, `high`, `critical`), the paths, the
  acceptance criterion it concerns (or the literal `own-behaviour` when it concerns the
  change's own behaviour) and a one-sentence summary.

Each reviewer applies the `code-review` skill's review method and checklist itself; it
does not start that skill's own subagents. Each reviewer works alone and returns one
finding list. When a native alias fails, that
reviewer runs through its `ccore agent` fallback route. When no route works for a
reviewer, stop and report the dispatch failure; never continue with fewer reviewers and
never treat a transport failure as a clean review. Record the route each reviewer used.

The main session merges the three result sets into one deduplicated finding list. This
review looks for failures against intent; pr-agent covers the standards and conventions
lens later. Neither a green CI nor a pr-agent approval counts as the verification verdict.

## 4. Triage (one repair round, by the designated repair author)

Run `scripts/finding_triage.py --findings-file <merged.json> --diff-path <path>...
--ac-ref <AC>...`. Its `repair` set goes to the designated `opus` reviewer from step 3,
in one round, all findings at once, ending in one repair commit.

That hand-off is where its write authority starts, and the accepted repair set is all of
it. Give it the bounded set, the candidate it reviewed and the worktree; it applies
every finding in that set, runs the affected checks, commits, and reports the repaired
finding ids, the new head SHA and the checks it ran. It becomes a coauthor of the
delivery. The `implementer` and the other two reviewers write nothing while it works —
one writer at a time, so a finding is never repaired twice or reverted by a concurrent
edit. A finding whose requirement is ambiguous, or whose fix would exceed the accepted
set, goes back to the main session instead of being decided in the repair commit.

The repair author cannot verify or approve its own repair, and the main session keeps
acceptance and the merge decision. If that reviewer's session is gone when triage
finishes, a replacement takes the role only after reading the pinned candidate and the
accepted findings; record why the original was unavailable and which route the
replacement used. There is no silent fall back to the implementer.

Run `finding_triage.py` again with `--review-decisions --repair-rounds-used 1` and one
`--repaired <id>` per finding the repair commit fixed, to render the deferred and the
repaired findings as the "Review decisions" section of the pull request body. An unknown
repaired id fails the call. A second repair round needs a reason the main session states
in that section.

## 5. Verification (always, by a non-author agent)

Every delivery is verified by an agent that authored neither the implementation nor any
repair — so never the `implementer` and never the designated repair author once it has
committed. Only evidence from running the changed artifact counts: a command, a request or a UI path, with its
observed result. Tests passing are not verification.

- When the delivered repository has a skill matching `.agents/skills/verify-*`, the
  verifier uses it.
- UI changes are driven with `playwright-cli` by a `haiku` subagent. When that alias is
  unavailable or cannot operate `playwright-cli`, run the verifier through
  `ccore agent run --model gpt-6-luna --harness codex`.
- Other changes are verified by a `haiku` subagent that runs the changed command,
  endpoint or script.

The verifier returns one verdict - `PASS`, `PASS+NOTES` or `FAIL` - together with the
head commit SHA it verified and each run path with its outcome. A new commit on the
branch invalidates the verdict; verify again. A `FAIL`, and any later finding from
verification or from the pull request, goes back through the main session to the same
designated repair author, so the delivery keeps one writer after review. When the change cannot be run at all, record that reason instead of a verdict;
such a delivery is never merged by the main session. A documentation-only change, with
or without a work order, is not such a delivery: its step 5 evidence is the relevant
link and metadata checks plus an instruction review of the changed text by a non-author
agent, recorded in the Verification section. A generated/sync or documentation-only
pull request without a work order has its evidence defined under
[Pull requests without a work order](#pull-requests-without-a-work-order).

## 6. Pull request (`cognovis-pr`)

Always open a pull request. Write its text with `cognovis-pr`, which reads the
installed `pr` skill for the template and owns the sections a Cognovis delivery adds;
do not restate those sections here. Hand it the `finding_triage.py --review-decisions`
output from step 4, the verifier's verdict and verified head SHA from step 5, the work
order reference, the model route each of the three reviewers used, the product
decision and economic damage assessments of step 7, when the review risk is not `none`
the Risk statement content, and, when the repository's `AGENTS.md` explicitly waives
pr-agent evidence for landing, that waiver for the
`pr-agent review not required: <reason>` line. The injected `executive-pack` standard's
Review risk section defines when a class is valid; `cognovis-pr` holds the statement
format.

Publish the result with `ccore pr ensure --repo <worktree> --summary <text>`, which
picks `gh` or `fgj` from the remote. `ccore pr ensure` rebases the branch onto the
target before its first push; when that changes the head commit, verify again (step 5)
and update the Verification section. Push later repair commits with a plain `git push`.
Rerunning `ccore pr ensure` on an already published branch can rebase and force-push it;
that history rewrite of the delivery's own task branch is internal work and needs no
confirmation; never force-push a shared or default branch.

pr-agent on Atlas reviews the pull request when it is first pushed, from
`.agents/standards/review.md` and `AGENTS.md`, and does not re-raise findings listed
under Review decisions; on later pushes it only classifies again, so a later head needs
the `/review` request of step 7. It sets
exactly one `review-risk:*` label, as classification, and names the head SHA it
classified. When that class is not `none` and the body has no Risk statement yet, add
it. For each pr-agent finding, repair it (then verify again) or add it to Review
decisions with the reason.

The pull request is always opened this way before landing, as the delivery record. Its
body records Review decisions, the Verification, the Merge assessment and, when the
review risk is not `none`, the Risk statement. It exists before landing so the forge can
mark it merged and `ccore pr merge` can check its `merge:human` label. Its title becomes
the squash commit subject and its `## Summary` section the commit body, so both are
written as release-note text (`cognovis-pr` holds the rules) and are final before
landing: `ccore pr merge` reads them when it lands, so any edit of the title or the
Summary up to then changes the landed commit text.

## 7. Merge decision

Every repository lands through `ccore pr merge`, run by the main session from the
delivery worktree. It rebases the delivery branch onto the fetched target, squashes it
into one commit from the pull request text, pushes that candidate to the delivery branch
so the repository's pre-push hook runs on it, fast-forwards the target to it and
confirms the host shows the pull request merged. `ccore pr merge` is the only landing
route; the main session never merges the pull request through the forge otherwise: no
`gh pr merge`, no `fgj` merge, no merge button.

The main session lands only when all of the following hold for the current head commit;
otherwise it does not land and lists the missing evidence. A pull request without a work
order reads the Verification and product-decision conditions as substituted under
[Pull requests without a work order](#pull-requests-without-a-work-order):

- pr-agent's latest classification comment names the current head commit SHA. A
  missing or stale classification, or `review-risk:unclassified`, is missing pr-agent
  evidence. The class itself (`none`, `payment`, `pii`, `auth`, `compliance`) classifies
  and informs; it does not block the landing. The main session never sets, changes or
  removes that label.
- a pr-agent review comment written or last edited at or after the host recorded the
  push of the current head exists on the pull request: it starts with
  `## PR Reviewer Guide`, is edited in place on later reviews, and is written by the
  provider's pr-agent identity (`cognovis-pr-agent` on git.cognovis.de, the GitHub App
  `cognovis-atlas-pr-agent[bot]` on GitHub). The classification and the review are
  separate outputs, so a missing review is missing pr-agent evidence even when a
  classification exists. A review that predates the push of the current head (for
  example after a repair push or a `ccore pr ensure` rebase) does not cover it, and
  `ccore pr merge` refuses it (`pr_land_review_missing`). The delivery does not land
  until a writer's `/review` produces one.
- the Verification section records `PASS` or `PASS+NOTES` for the head `ccore pr merge`
  starts from and names that head's full 40-character SHA; an abbreviated SHA does not
  count, and `ccore pr merge` refuses the landing without it
  (`pr_land_verification_stale`).
- when the target's `.cognovis/repo.toml` does not declare
  `[landing] wait_for_ci = true`, the pull request's required checks on the head
  `ccore pr merge` starts from have passed; a failing or pending one holds the landing.
  When it declares it, the CI wait inside `ccore pr merge` is the check (see below).
- no accepted local finding is unrepaired.
- the pr-agent review has no unresolved finding that Review decisions does not cover.
- no product decision deviates: the main session compared the delivered behaviour with
  the work order's decisions, Scope-In/Scope-Out and acceptance criteria, and found no
  default, rule, scope boundary, user-visible behaviour or data-model choice that the
  work order does not state or states otherwise.
- no economic damage is to be expected: the main session assessed money movement,
  billing or invoices, irreversible customer-data loss, a realistic personal-data leak,
  and contractual or legal exposure. Damage is expected when the delivered and verified
  behaviour would cause one of these, or when a known open risk of that kind remains;
  touching such an area with verified behaviour is not damage by itself. An actual PII
  boundary crossing with a realistic scenario that reaches real personal data is
  expected damage; a `pii` label without such a scenario is not (the `executive-pack`
  standard, Review risk).
- the Merge assessment section of the pull request body names both assessments for the
  current head, each with its reason.
- when the review risk is not `none`, the Risk statement section names every field for
  the current head, and a `pii` class cites its crossing from the repository's PII
  boundary standard or the assumed boundary. A missing Risk statement is missing
  evidence; a statement that names no concrete scenario does not hold the landing.
- no explicit human merge gate from the user or the repository applies.

These two conditions are the product owner's rule (2026-09-28), adopted verbatim with no
category carved out: "Wenn hier keine Produktentscheidung anders getroffen wurde als im
Ticket und kein wirtschaftlicher Schaden zu erwarten ist, dann selber mergen."

The pr-agent conditions (classification, review comment, and the missing-review notice
below) hold the landing unless the repository's `AGENTS.md` explicitly waives pr-agent
evidence for landing. The waiver takes the form `ccore pr merge` reads: the pull request
body carries a line `pr-agent review not required: <reason>` whose reason cites that
`AGENTS.md` waiver; without such an explicit waiver the main session never writes that
line.

The Atlas missing-review notice carries the hidden marker
`<!-- pr-agent-webhook:review-missing head=<sha> -->`, where `head=<sha>` names the head
it concerns. The notice stays on the pull request, so it holds the landing only while no
pr-agent review comment was written or edited after it; once such a review exists, the
review condition above holds and the notice no longer blocks. While the notice holds,
the main session comments `/review` on the pull request once per notice, not on every
pass, and waits for the review instead of landing.

When the latest pr-agent review predates the push of the current head, for example after
a repair push or a `ccore pr ensure` rebase, the main session comments `/review` on the
pull request once for that head and waits for the review to be written or edited instead
of landing. The delivery request that invokes this skill authorizes these two `/review`
comments on the delivery's own pull request, once per notice and once per head; it
authorizes no other comment. If no review arrives after a `/review`, for example because
Atlas posts a further notice, the pull request stays open for a human with the missing
review as the reason.

When either assessment fails, or an explicit human merge gate applies, the decision
stays with a human: the main session sets the label `merge:human` on the delivery's own
pull request and does not land; `ccore pr merge` refuses a pull request that carries
that label. The delivery request that invokes this skill authorizes setting that label
on the delivery's own pull request. When evidence the delivery can still produce is
missing, the main session does not land yet and produces it first.

`ccore pr merge` pushes the squashed candidate through the repository's pre-push hook.
When the target's `.cognovis/repo.toml` declares `[landing] wait_for_ci = true`, it
also waits for CI on that candidate and moves the target only once CI passed, including
every check named in `[landing] required_checks`; that wait replaces the main session's
own reading of the required checks.

A `ccore pr merge` stop is handled by its kind:

- A candidate defect is a later finding: a failing pre-push hook
  (`pr_prepush_gate_failed`), failing CI (`pr_land_ci_failed`) or a rebase conflict
  (`pr_rebase_conflict`). It goes through the main session to the designated repair
  author, then to verification again, and the main session then runs `ccore pr merge`
  again.
- A retryable or transport stop is rerun as it is, with no repair: the target kept
  moving (`pr_land_target_moving`), the branch moved (`pr_branch_moved`), a push failed
  (`pr_push_failed`, `pr_land_push_failed`), or CI was not reported or did not finish in
  time (`pr_land_ci_missing`, `pr_land_ci_timeout`), or the host lookup for the merge
  preconditions failed (`pr_land_precondition_lookup_failed`). A push failure whose
  output is the pre-push hook rejecting the candidate is a candidate defect, and a
  remote commit that `pr_branch_moved` asks to integrate is a delivery commit.
- A precondition stop (`pr_land_review_missing`, `pr_land_risk_statement_missing`,
  `pr_land_verification_stale`) is missing evidence the delivery produces before
  rerunning: a pr-agent review written after the head's push (waiting for it, or the
  `/review` rules above), a Risk statement, or verifying the head and recording its full
  SHA in Verification. It is never a skip and never a repair.
- A configuration blocker is reported as a blocker, not repaired in the delivery: for
  example Forgejo not allowing the fast-forward-only merge style
  (`pr_land_fast_forward_disallowed`) or an invalid `[landing]` declaration
  (`pr_land_config_invalid`).

Run `ccore pr merge` from the delivery worktree, with the delivery branch checked out
(not a detached HEAD), no uncommitted or untracked changes and no rebase, merge,
cherry-pick or revert in progress. Never skip the repository's hooks: no `--no-verify`
and no hook path override. Never pass `--message`; the commit text comes from the pull
request. Never pass `--skip-precondition`; a precondition `ccore pr merge` refuses on is
evidence the delivery produces.

`ccore pr merge`'s own rebase and squash onto a moved default branch is covered by the
pre-push hook on the squashed candidate and does not invalidate the verdict; any commit
the delivery adds does. A stop after `ccore pr merge` pushed its candidate leaves the
delivery branch at that squashed commit. A rerun from such a head (the verified tree plus
`ccore pr merge`'s own rebase and squash, no delivery commit) keeps the verdict (no new
verification). When that head is not yet on the target, the main session records the
squashed head's full SHA in the Verification section as that same verdict's tree plus
`ccore pr merge`'s own rebase and squash, and `ccore pr merge` needs a pr-agent review
written after that head's push, which the delivery obtains as above. When that head is
already the target's landing commit of this pull request, `ccore pr merge` records the
preconditions as `checked_by_earlier_run` and the rerun only confirms the landing. Any
delivery commit on top of it still invalidates the verdict.

After landing, record the landed commit `ccore pr merge` reports and confirm the pull
request shows as merged. Confirm with `ccore tracker show <ref>` that the work order
closed and close it with `ccore tracker close <ref>` otherwise. Run any post-merge
postcondition the repository's `AGENTS.md` names.

## Delivery resource tracking

STATUS: INVOCATION POLICY — the helper enforces ownership verification and foreign
exclusion; these instructions say when to call it.

At delivery start, before any Compose or long-lived process start, create a delivery
record:

```text
uv run --no-project python <helper-root>/scripts/delivery_teardown.py init \
  --worktree <worktree> --token <delivery-token> \
  --record-file "$(git -C <worktree> rev-parse --absolute-git-dir)/delivery-teardown.json"
```

The record and its `.lock` live in the worktree's own git directory: bound to that
worktree, but outside its working tree, so they never appear as untracked changes. That
path is `<record>` below.

The project name for Compose stacks is
`delivery_teardown.py project-name --worktree <wt> --token <token>`. Use it with
`-p <name>` and add `cognovis.worktree=<resolved-worktree>` and
`cognovis.delivery=<delivery-token>` as labels on every container and network. The
ephemeral-compose-stacks lifecycle markers remain required alongside these delivery
labels. Before each `docker compose up`, register the project with preflight:

```text
uv run --no-project python <helper-root>/scripts/delivery_teardown.py record-compose \
  --record-file <record> --project <name> --compose-file <file> \
  --project-directory <compose-working-directory>
```

Registration checks that no pre-existing project resources exist (start provenance),
renders the effective Compose configuration via `docker compose config --format json`,
validates ownership and lifecycle labels (`de.cognovis.ephemeral=true`, valid
`de.cognovis.issue`, nonempty `de.cognovis.expires-at`) in the rendered output, and
saves the frozen snapshot under
`${XDG_CACHE_HOME:-~/.cache}/cognovis/delivery-teardown/<token>/` (outside the tracked
worktree, not committed).  Use the snapshot path printed to stdout for
`docker compose -f <snapshot> -p <name> up -d`; teardown uses the same frozen snapshot
even if source files change or original interpolation variables disappear.  Run
`docker compose up` after registration, not before. If the project already has
containers or networks, registration fails and the project must not be adopted.  A
retry of an already-recorded project reuses the existing entry.  Entries without a
valid frozen configuration snapshot are blocked at teardown.

Before each long-lived process start, launch it in an isolated process group
(`start_new_session=True` or `setsid`) with `COGNOVIS_DELIVERY_TOKEN=<token>` in the
process environment (children inherit this marker for ownership proof) and record it:

```text
uv run --no-project python <helper-root>/scripts/delivery_teardown.py record-process \
  --record-file <record> \
  --pgid <pgid> --pid <pid> --uid <uid> --start-time <starttime> \
  --worktree <worktree> --command <cmd>
```

Record before or immediately after the start so partial starts can be torn down.

## Delivery teardown

Before the final report — after the merge decision, after handing the pull request to a
human, or after a delivery failure — stop all delivery-started resources:

```text
uv run --no-project python <helper-root>/scripts/delivery_teardown.py teardown --record-file <record>
```

The helper verifies all project containers and networks carry `cognovis.worktree`,
`cognovis.delivery`, and the required ephemeral lifecycle markers
(`de.cognovis.ephemeral`, `de.cognovis.issue`, `de.cognovis.expires-at`) before
running `harness docker-clean compose -p <project> down` through the released
constrained harness route (`cognovis-harness-cli` 2026.10.4). The harness verifies
Fleet development enrollment, refuses remote selectors and non-default Docker
context, and protects volumes by `cognovis.ephemeral=true`. Volumes are always
preserved; no volume-delete option is used. Raw `docker compose down` is never
called; if the harness is absent, refuses enrollment or context, the exact
attempted command is reported as blocked. It re-enumerates both containers and
networks immediately before cleanup and verifies both are gone after. Foreign, mixed,
token-mismatched or lifecycle-incomplete projects are not touched. Process groups
are validated (uid, cwd containment, anchored leader identity, delivery token
provenance for non-leader members) before each signal and stopped with bounded
TERM/wait/KILL; group membership and ownership are revalidated before KILL. The
caller's own process group and ancestors are excluded. Retained groups with reasons
appear on the Teardown line.

The helper's stdout contains a `Teardown:` line with `complete` or `blocked` status,
stopped resources, retained groups with reasons, and any exact blocked commands. Include
that line in the final report. A guard-blocked command is reported exactly, without
asking the human to paste it. A missing record file is an explicit blocker (`Teardown:
blocked`): it may indicate failed initialization, lost state or a wrong record path. An
initialized record with no entries produces `Teardown: complete`.

Teardown failure does not prevent the session retro from running. The existing lifecycle
markers in `standards/containers/ephemeral-compose-stacks.md` remain required.

After teardown, remove a self-managed worktree with `worktree-cleanup`; a T3 thread
worktree belongs to T3 and stays. The delivery record in the worktree's git directory
must survive until teardown completes; do not remove the worktree before teardown.

## 8. Session retro

After teardown, or after handing the pull request to a human, run `session-retro` on
the finished session. It encodes learnings as structure first and stores them in Open
Brain and the standards; it does not merge, push, close issues or clean worktrees.
Report the pull request, its merge state, the verdict and the retro result.

## Pull requests without a work order

Two kinds of pull request may have no work order and are then not a full delivery
through steps 1 to 5:

- a generated or sync pull request, whose diff is only generator output, for example a
  Library sync;
- a documentation-only pull request, whose diff changes only documentation or
  instruction text.

This clarifies how the product owner's rule of 2026-09-28 quoted in step 7 applies to
them; it is not a new merge permission. A pull request that changes behaviour beyond
the generated output or the documentation is a normal delivery and needs a work order.
So does any change to merge, authorization, review or guard rules, even when it touches
only instruction text: it is never on this route.

The pull request body records this minimal evidence for the current head commit:

- the user's explicit authorization for this pull request, cited in place of the work
  order reference; it stands in for the work order.
- generated or sync: re-running the generator yields no diff, and the tests of the
  synced helpers pass.
- documentation-only: the relevant link and metadata checks pass, and an instruction
  review of the changed text by a non-author agent left no open finding.
- the Merge assessment. The product-decision assessment compares the change with the
  user's authorization instead of a work order; the economic-damage assessment is
  unchanged.
- the Risk statement, when the review risk is not `none`.

For this kind of pull request these items replace step 5's verification, and step 7
applies with two substitutions: the evidence above, recorded in the `## Verification`
section with the current head's full 40-character SHA, satisfies its Verification
condition, and its product-decision condition compares against the user's
authorization. Every other step 7 condition still holds: pr-agent's latest
classification names the current head commit, a pr-agent review comment written or last
edited at or after the push of the current head exists on the pull request, the
required checks hold as in step 7, no accepted local finding is unrepaired, the
pr-agent review has no unresolved finding, the Merge assessment names both assessments,
the Risk statement is complete when the class is not `none`, and an explicit human
merge gate still requires the human. Such a pull request lands through
`ccore pr merge` as well, under the same conditions with the same two substitutions.
