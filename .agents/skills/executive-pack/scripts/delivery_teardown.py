#!/usr/bin/env -S uv run python
"""Delivery teardown: stop delivery-owned Compose stacks and process groups.

Records delivery-started resources and tears them down safely before the
delivery's final report.  Called by executive-pack and session-retro closing
flows.  Produces a machine-readable ``Teardown:`` line.

STATUS: INVOCATION POLICY lives in the consuming skill instructions.
        SAFETY (ownership verification, foreign exclusion) is enforced here.
"""

from __future__ import annotations

import argparse
import calendar
import fcntl
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

CONTRACT = "cognovis.delivery-teardown.v1"
TERM_WAIT_SECONDS = 5
KILL_WAIT_SECONDS = 1

_ISSUE_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+#\d+$")


# ---------------------------------------------------------------------------
# Project name
# ---------------------------------------------------------------------------


def derive_project_name(worktree: str, token: str) -> str:
    """Derive a Compose project name from the canonical worktree and token."""
    repo_slug = Path(worktree).parent.name.lower()
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in repo_slug)
    safe = safe.lstrip("-_") or "delivery"
    return f"{safe}-{token}"


# ---------------------------------------------------------------------------
# /proc stat parsing
# ---------------------------------------------------------------------------


def _parse_stat_fields(stat_text: str) -> list[str] | None:
    """Parse ``/proc/<pid>/stat`` handling parenthesized comm with spaces."""
    close_paren = stat_text.rfind(")")
    if close_paren < 0:
        return None
    open_paren = stat_text.find("(")
    if open_paren < 0 or open_paren >= close_paren:
        return None
    pid = stat_text[:open_paren].strip()
    comm = stat_text[open_paren + 1 : close_paren]
    rest = stat_text[close_paren + 1 :].split()
    return [pid, comm] + rest


# ---------------------------------------------------------------------------
# Snapshot directory
# ---------------------------------------------------------------------------


def _snapshot_dir(token: str) -> Path:
    """Return the per-delivery snapshot directory outside any worktree."""
    cache = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    return Path(cache) / "cognovis" / "delivery-teardown" / token


# ---------------------------------------------------------------------------
# Lifecycle label validation
# ---------------------------------------------------------------------------


def _check_lifecycle_labels(
    labels: dict[str, str], worktree: str, entry_token: str,
    resource_id: str, resource_kind: str,
) -> str | None:
    """Return a blocking reason if labels are invalid, else None."""
    if labels.get("cognovis.worktree") != worktree:
        return f"foreign worktree on {resource_kind} {resource_id}"
    if labels.get("cognovis.delivery") != entry_token:
        return f"delivery token mismatch on {resource_kind} {resource_id}"
    eph = labels.get("de.cognovis.ephemeral")
    if eph != "true":
        return f"invalid ephemeral marker '{eph}' on {resource_kind} {resource_id}"
    issue = labels.get("de.cognovis.issue", "")
    if not issue or not _ISSUE_RE.match(issue):
        return f"invalid issue marker on {resource_kind} {resource_id}"
    expiry = labels.get("de.cognovis.expires-at", "")
    if not expiry:
        return f"empty expires-at marker on {resource_kind} {resource_id}"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", expiry):
        return f"invalid expires-at format '{expiry}' on {resource_kind} {resource_id} (UTC ISO-8601 required)"
    reason = _validate_utc_timestamp(expiry)
    if reason:
        return f"invalid expires-at '{expiry}' on {resource_kind} {resource_id}: {reason}"
    return None


def _validate_utc_timestamp(ts: str) -> str | None:
    """Validate calendar correctness of a UTC ISO-8601 timestamp (YYYY-MM-DDTHH:MM:SSZ)."""
    try:
        year = int(ts[0:4])
        month = int(ts[5:7])
        day = int(ts[8:10])
        hour = int(ts[11:13])
        minute = int(ts[14:16])
        second = int(ts[17:19])
    except (ValueError, IndexError):
        return "non-numeric components"
    if month < 1 or month > 12:
        return f"month {month} out of range"
    max_day = calendar.monthrange(year, month)[1]
    if day < 1 or day > max_day:
        return f"day {day} out of range for {year}-{month:02d} (max {max_day})"
    if hour > 23:
        return f"hour {hour} out of range"
    if minute > 59:
        return f"minute {minute} out of range"
    if second > 59:
        return f"second {second} out of range"
    return None


# ---------------------------------------------------------------------------
# Ledger validation
# ---------------------------------------------------------------------------


def _is_positive_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def _is_nonneg_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _validate_ledger(record: dict) -> str | None:
    """Validate complete ledger shape, types and required fields."""
    if not isinstance(record.get("worktree"), str) or not record["worktree"]:
        return "missing or empty worktree"
    if not isinstance(record.get("delivery_token"), str) or not record["delivery_token"]:
        return "missing or empty delivery_token"

    compose = record.get("compose_projects")
    if not isinstance(compose, list):
        return f"compose_projects must be a list, got {type(compose).__name__ if compose is not None else 'missing'}"
    root_wt = record["worktree"]
    root_dt = record["delivery_token"]
    for i, entry in enumerate(compose):
        if not isinstance(entry, dict):
            return f"compose_projects[{i}] must be a dict"
        if not isinstance(entry.get("project"), str) or not entry["project"]:
            return f"compose_projects[{i}] missing or empty project"
        if "compose_files" in entry and not isinstance(entry["compose_files"], list):
            return f"compose_projects[{i}] compose_files must be a list"
        if "delivery_token" in entry:
            dt = entry["delivery_token"]
            if not isinstance(dt, str) or not dt:
                return f"compose_projects[{i}] invalid delivery_token"
            if dt != root_dt:
                return f"compose_projects[{i}] delivery_token does not match root"
        if "worktree" in entry:
            ewt = entry["worktree"]
            if not isinstance(ewt, str) or not ewt:
                return f"compose_projects[{i}] invalid worktree"
            if ewt != root_wt:
                return f"compose_projects[{i}] worktree does not match root"

    groups = record.get("process_groups")
    if not isinstance(groups, list):
        return f"process_groups must be a list, got {type(groups).__name__ if groups is not None else 'missing'}"
    for i, entry in enumerate(groups):
        if not isinstance(entry, dict):
            return f"process_groups[{i}] must be a dict"
        if not _is_positive_int(entry.get("pgid")):
            return f"process_groups[{i}] invalid pgid"
        if not _is_positive_int(entry.get("pid")):
            return f"process_groups[{i}] invalid pid"
        if not _is_nonneg_int(entry.get("uid")):
            return f"process_groups[{i}] invalid uid"
        st = entry.get("start_time")
        if not isinstance(st, str) or not re.fullmatch(r"\d+", st):
            return f"process_groups[{i}] invalid start_time"
        wt = entry.get("worktree")
        if not isinstance(wt, str) or not wt:
            return f"process_groups[{i}] invalid worktree"
        wt_path = Path(wt)
        if not wt_path.is_absolute() or str(wt_path) != str(wt_path.resolve()):
            return f"process_groups[{i}] worktree is not canonical absolute"
        if wt != root_wt:
            return f"process_groups[{i}] worktree does not match root"
    return None


# ---------------------------------------------------------------------------
# Record management
# ---------------------------------------------------------------------------


def init_record(worktree: str, token: str, record_path: Path) -> dict:
    """Create a delivery record.  Fails if one already exists."""
    record_path.parent.mkdir(parents=True, exist_ok=True)
    with _locked_record(record_path):
        if record_path.exists():
            raise FileExistsError(f"Delivery record already exists: {record_path}")
        record: dict[str, Any] = {
            "contract": CONTRACT,
            "worktree": str(Path(worktree).resolve()),
            "delivery_token": token,
            "compose_projects": [],
            "process_groups": [],
        }
        _save(record, record_path)
    return record


def load_record(record_path: Path) -> dict:
    """Load and validate a delivery record."""
    data = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Record must be a JSON object, got {type(data).__name__}")
    if data.get("contract") != CONTRACT:
        raise ValueError(f"Unknown record contract: {data.get('contract')}")
    return data


def _save(record: dict, path: Path) -> None:
    """Atomically write a record, replacing the file via rename."""
    data = json.dumps(record, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    closed = False
    try:
        os.write(fd, data.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        closed = True
        os.rename(tmp, str(path))
    except BaseException:
        if not closed:
            os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _lock_path(record_path: Path) -> Path:
    return record_path.with_suffix(record_path.suffix + ".lock")


@contextmanager
def _locked_record(record_path: Path) -> Generator[None, None, None]:
    """Hold an exclusive fcntl lock for the duration of a ledger transaction."""
    lock_file = _lock_path(record_path)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


def _validate_rendered_labels(
    rendered_json: str, worktree: str, token: str,
) -> str | None:
    """Validate rendered Compose config labels for ownership and lifecycle."""
    try:
        cfg = json.loads(rendered_json)
    except (json.JSONDecodeError, TypeError):
        return "rendered config is not valid JSON"
    services = cfg.get("services") or {}
    for svc_name, svc in services.items():
        labels = svc.get("labels") or {}
        if isinstance(labels, list):
            d: dict[str, str] = {}
            for item in labels:
                if "=" in str(item):
                    k, v = str(item).split("=", 1)
                    d[k] = v
            labels = d
        reason = _check_lifecycle_labels(labels, worktree, token, svc_name, "service")
        if reason:
            return f"rendered service {svc_name}: {reason}"
        restart = svc.get("restart")
        if restart != "no":
            return f"rendered service {svc_name}: restart must be 'no', got {restart!r}"
    networks = cfg.get("networks") or {}
    for net_name, net_cfg in networks.items():
        if not isinstance(net_cfg, dict):
            continue
        if net_cfg.get("external"):
            continue
        net_labels = net_cfg.get("labels") or {}
        if isinstance(net_labels, list):
            nd: dict[str, str] = {}
            for item in net_labels:
                if "=" in str(item):
                    k, v = str(item).split("=", 1)
                    nd[k] = v
            net_labels = nd
        reason = _check_lifecycle_labels(net_labels, worktree, token, net_name, "network")
        if reason:
            return f"rendered network {net_name}: {reason}"
    return None


def _validate_prepared_entry(
    entry: dict, root_wt: str, root_token: str,
) -> str | None:
    """Validate a compose entry's bindings against root record and its frozen snapshot.

    Used by both reuse and teardown to ensure consistent ownership.
    Returns a blocking reason or None.
    """
    # Required typed fields.
    project = entry.get("project")
    if not isinstance(project, str) or not project:
        return "missing or empty project"
    entry_token = entry.get("delivery_token")
    if not isinstance(entry_token, str) or entry_token != root_token:
        return f"entry delivery_token {entry_token!r} != root {root_token!r}"
    entry_wt = entry.get("worktree")
    if not isinstance(entry_wt, str) or entry_wt != root_wt:
        return f"entry worktree {entry_wt!r} != root {root_wt!r}"
    entry_issue = entry.get("issue")
    if not isinstance(entry_issue, str) or not entry_issue or not _ISSUE_RE.match(entry_issue):
        return "missing or invalid issue binding"

    # Frozen config required and in canonical location.
    frozen_config = entry.get("frozen_config")
    if not isinstance(frozen_config, str) or not frozen_config or not Path(frozen_config).exists():
        return f"frozen config missing ({frozen_config!r})"
    canonical_snap_dir = str(_snapshot_dir(root_token))
    try:
        fc_resolved = str(Path(frozen_config).resolve())
    except OSError:
        fc_resolved = frozen_config
    if not fc_resolved.startswith(canonical_snap_dir + "/"):
        return f"frozen config {frozen_config!r} not in canonical snapshot directory"
    if is_contained_in(fc_resolved, root_wt):
        return "frozen config is inside worktree"

    # Canonical snapshot filename must match the project.
    expected_filename = f"{project}.compose-config.json"
    actual_filename = Path(frozen_config).name
    if actual_filename != expected_filename:
        return f"frozen config filename {actual_filename!r} != expected {expected_filename!r} for project {project!r}"

    # Digest.
    stored_digest = entry.get("snapshot_digest")
    if not isinstance(stored_digest, str) or not stored_digest:
        return "snapshot digest missing"
    actual_digest = hashlib.sha256(Path(frozen_config).read_bytes()).hexdigest()
    if actual_digest != stored_digest:
        return f"frozen config digest mismatch: stored={stored_digest}, actual={actual_digest}"

    # Validate frozen snapshot's parsed labels match entry bindings.
    try:
        snap_text = Path(frozen_config).read_text(encoding="utf-8")
    except OSError as exc:
        return f"cannot read frozen config: {exc}"
    label_err = _validate_rendered_labels(snap_text, root_wt, entry_token)
    if label_err:
        return f"frozen snapshot label mismatch: {label_err}"

    # Validate frozen snapshot issue matches entry issue.
    try:
        snap_cfg = json.loads(snap_text)
        for svc in (snap_cfg.get("services") or {}).values():
            slabels = svc.get("labels") or {}
            if isinstance(slabels, dict):
                snap_issue = slabels.get("de.cognovis.issue", "")
                if snap_issue != entry_issue:
                    return f"frozen snapshot issue {snap_issue!r} != entry issue {entry_issue!r}"
    except (json.JSONDecodeError, TypeError):
        return "cannot parse frozen snapshot for issue validation"

    return None


def _validate_live_resources(
    entry: dict, worktree: str, docker: Any,
) -> str | None:
    """Validate live container/network ownership against a prepared entry.

    Returns a blocking reason or None. Absent resources are acceptable
    (legitimate retry after a vanished stack). Foreign or mixed ownership
    blocks before any mutation.
    """
    project = entry["project"]
    entry_token = entry["delivery_token"]
    expected_issue = entry["issue"]
    try:
        container_ids = docker.ps_project(project)
        network_ids = docker.network_ls_project(project)
    except Exception as exc:
        return f"cannot enumerate project {project}: {exc}"

    # Validate every container (no-op if empty).
    for cid in container_ids:
        try:
            labels = docker.inspect_labels(cid)
        except Exception as exc:
            return f"cannot inspect container {cid}: {exc}"
        reason = _check_lifecycle_labels(labels, worktree, entry_token, cid, "container")
        if reason:
            return f"foreign container {cid}: {reason}"
        live_issue = labels.get("de.cognovis.issue")
        if live_issue != expected_issue:
            return f"container {cid} issue {live_issue!r} != expected {expected_issue!r}"

    # Validate every network.
    for nid in network_ids:
        try:
            labels = docker.network_inspect_labels(nid)
        except Exception as exc:
            return f"cannot inspect network {nid}: {exc}"
        reason = _check_lifecycle_labels(labels, worktree, entry_token, nid, "network")
        if reason:
            return f"foreign network {nid}: {reason}"
        live_issue = labels.get("de.cognovis.issue")
        if live_issue != expected_issue:
            return f"network {nid} issue {live_issue!r} != expected {expected_issue!r}"

    # Re-enumerate for topology stability.
    try:
        recheck_c = docker.ps_project(project)
        recheck_n = docker.network_ls_project(project)
    except Exception as exc:
        return f"re-enumeration failed: {exc}"
    if set(recheck_c) != set(container_ids):
        return "container topology changed during reuse validation"
    if set(recheck_n) != set(network_ids):
        return "network topology changed during reuse validation"

    return None


def prepare_compose_start(
    record_path: Path, project: str, compose_files: list[str],
    *, project_directory: str | None = None, docker: Any = None,
) -> dict:
    """Preflight check, frozen rendered config, and record entry.

    Refuses pre-existing project resources.  Renders the effective Compose
    configuration via ``docker compose config`` and saves it privately
    outside the worktree.
    """
    if docker is None:
        docker = RealDockerOps()

    with _locked_record(record_path):
        record = load_record(record_path)
        token = record["delivery_token"]
        wt = record["worktree"]

        for existing in record["compose_projects"]:
            if existing["project"] == project:
                # Validate ALL preparation bindings on reuse, not just digest.
                reuse_err = _validate_prepared_entry(existing, wt, token)
                if reuse_err:
                    raise RuntimeError(f"project {project} reuse refused: {reuse_err}")
                # PR-1: Validate live resources on reuse before returning snapshot.
                reuse_err2 = _validate_live_resources(
                    existing, wt, docker,
                )
                if reuse_err2:
                    raise RuntimeError(f"project {project} reuse refused: {reuse_err2}")
                return {"project": project, "frozen_config": existing["frozen_config"], "reused": True}

        existing_c = docker.ps_project(project)
        existing_n = docker.network_ls_project(project)
        if existing_c or existing_n:
            raise RuntimeError(
                f"project {project} has pre-existing resources: "
                f"containers={existing_c}, networks={existing_n}"
            )

        resolved_files = [str(Path(f).resolve()) for f in compose_files]
        resolved_dir = str(Path(project_directory).resolve()) if project_directory else None
        try:
            rendered = docker.compose_config(project, resolved_files, project_directory=resolved_dir)
        except Exception as exc:
            raise RuntimeError(f"cannot render compose config for {project}: {exc}") from exc

        # Validate rendered labels at preparation time.
        label_err = _validate_rendered_labels(rendered, wt, token)
        if label_err:
            raise RuntimeError(f"rendered config rejected: {label_err}")

        # Recheck that no project resources appeared during config rendering.
        recheck_c = docker.ps_project(project)
        recheck_n = docker.network_ls_project(project)
        if recheck_c or recheck_n:
            raise RuntimeError(
                f"project {project} acquired resources during preparation: "
                f"containers={recheck_c}, networks={recheck_n}"
            )

        # Store frozen snapshot OUTSIDE the worktree.
        snap_dir = _snapshot_dir(token)
        if is_contained_in(str(snap_dir.resolve()), wt):
            raise RuntimeError(
                f"snapshot directory {snap_dir} is inside worktree {wt}"
            )
        old_umask = os.umask(0o077)
        try:
            snap_dir.mkdir(parents=True, exist_ok=True)
        finally:
            os.umask(old_umask)
        config_path = snap_dir / f"{project}.compose-config.json"
        rendered_bytes = rendered.encode("utf-8")
        fd = os.open(str(config_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, rendered_bytes)
        finally:
            os.close(fd)

        snapshot_digest = hashlib.sha256(rendered_bytes).hexdigest()

        # Extract issue from rendered service labels — required.
        issue = None
        try:
            rcfg = json.loads(rendered)
            for svc in (rcfg.get("services") or {}).values():
                slabels = svc.get("labels") or {}
                if isinstance(slabels, dict):
                    issue = slabels.get("de.cognovis.issue")
                    if issue:
                        break
        except (json.JSONDecodeError, TypeError):
            pass
        if not issue:
            config_path.unlink(missing_ok=True)
            raise RuntimeError(f"no valid issue label found in rendered config for project {project}")

        # Validate consistent issue across all services and networks.
        try:
            rcfg2 = json.loads(rendered)
            for svc_name, svc in (rcfg2.get("services") or {}).items():
                slabels = svc.get("labels") or {}
                if isinstance(slabels, dict):
                    svc_issue = slabels.get("de.cognovis.issue", "")
                    if svc_issue != issue:
                        config_path.unlink(missing_ok=True)
                        raise RuntimeError(f"inconsistent issue in service {svc_name}: {svc_issue!r} != {issue!r}")
            for net_name, net_cfg in (rcfg2.get("networks") or {}).items():
                if isinstance(net_cfg, dict) and not net_cfg.get("external"):
                    nlabels = net_cfg.get("labels") or {}
                    if isinstance(nlabels, dict):
                        net_issue = nlabels.get("de.cognovis.issue", "")
                        if net_issue != issue:
                            config_path.unlink(missing_ok=True)
                            raise RuntimeError(f"inconsistent issue in network {net_name}: {net_issue!r} != {issue!r}")
        except (json.JSONDecodeError, TypeError):
            pass

        entry: dict[str, Any] = {
            "project": project, "compose_files": resolved_files,
            "delivery_token": token, "frozen_config": str(config_path),
            "snapshot_digest": snapshot_digest, "worktree": wt,
            "issue": issue,
        }
        if resolved_dir is not None:
            entry["project_directory"] = resolved_dir

        # Re-read under lock to merge concurrent registrations.
        record = load_record(record_path)
        record["compose_projects"].append(entry)
        _save(record, record_path)
    return {"project": project, "frozen_config": str(config_path), "reused": False}


def record_process_start(
    record_path: Path, *, pgid: int, pid: int, uid: int,
    start_time: str, worktree: str, command: str,
) -> None:
    """Append a process group to the delivery record."""
    record = load_record(record_path)
    resolved_wt = str(Path(worktree).resolve())

    # Worktree must be canonical (reject non-canonical input).
    if worktree != resolved_wt:
        raise ValueError(f"worktree {worktree!r} is not canonical (resolves to {resolved_wt!r})")

    # Worktree must match the ledger root.
    root_wt = record.get("worktree", "")
    if resolved_wt != root_wt:
        raise ValueError(f"worktree {resolved_wt!r} does not match ledger root {root_wt!r}")

    if pgid <= 0:
        raise ValueError(f"pgid must be positive, got {pgid}")
    if pid <= 0:
        raise ValueError(f"pid must be positive, got {pid}")
    if uid < 0:
        raise ValueError(f"uid must be non-negative, got {uid}")
    if not re.fullmatch(r"\d+", start_time):
        raise ValueError(f"start_time must be decimal numeric, got {start_time!r}")
    if int(start_time) <= 0:
        raise ValueError(f"start_time must be positive, got {start_time!r}")

    # PID must be alive.
    try:
        os.kill(pid, 0)
    except OSError as exc:
        raise ValueError(f"pid {pid} is not alive: {exc}") from exc

    # PGID check.
    try:
        actual_pgid = os.getpgid(pid)
    except OSError as exc:
        raise ValueError(f"cannot read pgid of pid {pid}: {exc}") from exc
    if actual_pgid != pgid:
        raise ValueError(f"pid {pid} pgid is {actual_pgid}, expected {pgid}")

    # Isolated session: require SID == PGID == PID.
    try:
        actual_sid = os.getsid(pid)
    except OSError as exc:
        raise ValueError(f"cannot read sid of pid {pid}: {exc}") from exc
    if actual_sid != pgid:
        raise ValueError(f"pid {pid} sid is {actual_sid}, expected {pgid} (isolated session required)")

    # UID match via /proc.
    try:
        status_text = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
        proc_uid = None
        for line in status_text.splitlines():
            if line.startswith("Uid:"):
                proc_uid = int(line.split()[1])
                break
        if proc_uid is None:
            raise ValueError(f"cannot read uid from /proc/{pid}/status")
        if proc_uid != uid:
            raise ValueError(f"pid {pid} uid is {proc_uid}, expected {uid}")
    except OSError as exc:
        raise ValueError(f"cannot read /proc/{pid}/status: {exc}") from exc

    # Verify actual start_time from /proc matches supplied value.
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        fields = _parse_stat_fields(stat_text)
        if not fields or len(fields) < 22:
            raise ValueError(f"cannot parse /proc/{pid}/stat for start_time")
        actual_start = fields[21]
        if actual_start != start_time:
            raise ValueError(
                f"pid {pid} actual start_time {actual_start} != supplied {start_time}"
            )
    except OSError as exc:
        raise ValueError(f"cannot read /proc/{pid}/stat: {exc}") from exc

    # CWD inside worktree.
    try:
        proc_cwd = str(Path(f"/proc/{pid}/cwd").resolve())
    except OSError as exc:
        raise ValueError(f"cannot read /proc/{pid}/cwd: {exc}") from exc
    if not is_contained_in(proc_cwd, resolved_wt):
        raise ValueError(f"pid {pid} cwd {proc_cwd!r} not inside worktree {resolved_wt!r}")

    # Delivery token in environment.
    delivery_token = record.get("delivery_token")
    if delivery_token:
        try:
            env_bytes = Path(f"/proc/{pid}/environ").read_bytes()
            found_token = None
            for entry_bytes in env_bytes.split(b"\x00"):
                if entry_bytes.startswith(b"COGNOVIS_DELIVERY_TOKEN="):
                    found_token = entry_bytes.split(b"=", 1)[1].decode()
                    break
            if found_token != delivery_token:
                raise ValueError(
                    f"pid {pid} COGNOVIS_DELIVERY_TOKEN={found_token!r}, "
                    f"expected {delivery_token!r}"
                )
        except OSError as exc:
            raise ValueError(f"cannot read /proc/{pid}/environ: {exc}") from exc

    # Final identity re-check after all metadata reads.
    try:
        os.kill(pid, 0)
    except OSError as exc:
        raise ValueError(f"pid {pid} died during registration: {exc}") from exc
    try:
        recheck_stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        recheck_fields = _parse_stat_fields(recheck_stat)
        if not recheck_fields or len(recheck_fields) < 22 or recheck_fields[21] != start_time:
            raise ValueError(f"pid {pid} identity changed during registration")
    except OSError as exc:
        raise ValueError(f"pid {pid} disappeared during registration: {exc}") from exc

    # Lock, re-read ledger to merge concurrent registrations, append and save.
    with _locked_record(record_path):
        record = load_record(record_path)
        record["process_groups"].append({
            "pgid": pgid, "pid": pid, "uid": uid, "start_time": start_time,
            "worktree": resolved_wt, "command": command,
        })
        _save(record, record_path)


# ---------------------------------------------------------------------------
# Path containment
# ---------------------------------------------------------------------------


def is_contained_in(child: str, parent: str) -> bool:
    """True when *child* is exactly within *parent*, resolving symlinks."""
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Compose teardown
# ---------------------------------------------------------------------------


def teardown_compose(record: dict, docker: Any) -> dict:
    """Stop delivery-owned Compose projects."""
    worktree = record["worktree"]
    delivery_token = record["delivery_token"]
    stopped: list[str] = []
    blocked: list[str] = []
    blocked_commands: list[str] = []
    errors: list[str] = []

    for entry in record.get("compose_projects", []):
        if not isinstance(entry, dict):
            errors.append("invalid compose entry")
            continue
        project = entry.get("project", "")
        if not project:
            errors.append("compose entry missing project name")
            continue
        # Validate all preparation bindings via shared validator.
        entry_err = _validate_prepared_entry(entry, worktree, delivery_token)
        if entry_err:
            blocked.append(project)
            errors.append(f"{project}: {entry_err}")
            blocked_commands.append(f"{project}: {entry_err}")
            continue

        entry_token = entry["delivery_token"]
        expected_issue = entry["issue"]

        try:
            container_ids = docker.ps_project(project)
            network_ids = docker.network_ls_project(project)
        except Exception as exc:
            errors.append(f"{project}: {exc}")
            blocked.append(project)
            blocked_commands.append(str(exc))
            continue

        if not container_ids and not network_ids:
            stopped.append(project)
            continue

        # Verify ALL containers.
        foreign = False
        for cid in container_ids:
            try:
                labels = docker.inspect_labels(cid)
            except Exception as exc:
                errors.append(f"{project}: cannot inspect {cid}: {exc}")
                blocked.append(project)
                blocked_commands.append(str(exc))
                foreign = True
                break
            reason = _check_lifecycle_labels(labels, worktree, entry_token, cid, "container")
            if reason:
                blocked.append(project)
                blocked_commands.append(
                    _harness_clean_cmd(project) + f"  # {reason}"
                )
                foreign = True
                break
            live_issue = labels.get("de.cognovis.issue")
            if live_issue != expected_issue:
                blocked.append(project)
                blocked_commands.append(
                    _harness_clean_cmd(project)
                    + f"  # issue changed: expected={expected_issue}, live={live_issue}"
                )
                errors.append(f"{project}: container {cid} issue changed from {expected_issue} to {live_issue}")
                foreign = True
                break
        if foreign:
            continue

        # Verify ALL networks.
        for nid in network_ids:
            try:
                labels = docker.network_inspect_labels(nid)
            except Exception as exc:
                errors.append(f"{project}: cannot inspect network {nid}: {exc}")
                blocked.append(project)
                blocked_commands.append(str(exc))
                foreign = True
                break
            reason = _check_lifecycle_labels(labels, worktree, entry_token, nid, "network")
            if reason:
                blocked.append(project)
                blocked_commands.append(
                    _harness_clean_cmd(project) + f"  # {reason}"
                )
                foreign = True
                break
            live_issue = labels.get("de.cognovis.issue")
            if live_issue != expected_issue:
                blocked.append(project)
                blocked_commands.append(
                    _harness_clean_cmd(project)
                    + f"  # network issue changed: expected={expected_issue}, live={live_issue}"
                )
                errors.append(f"{project}: network {nid} issue changed from {expected_issue} to {live_issue}")
                foreign = True
                break
        if foreign:
            continue

        # Re-enumerate BOTH containers AND networks immediately before down.
        try:
            recheck_c = docker.ps_project(project)
            recheck_n = docker.network_ls_project(project)
        except Exception as exc:
            errors.append(f"{project}: re-enumeration failed: {exc}")
            blocked.append(project)
            blocked_commands.append(str(exc))
            continue
        if set(recheck_c) != set(container_ids):
            nc = set(recheck_c) - set(container_ids)
            gc = set(container_ids) - set(recheck_c)
            rp = []
            if nc: rp.append(f"new={','.join(sorted(nc))}")
            if gc: rp.append(f"gone={','.join(sorted(gc))}")
            blocked.append(project)
            blocked_commands.append(_harness_clean_cmd(project) + f"  # membership changed: {'; '.join(rp)}")
            continue
        if set(recheck_n) != set(network_ids):
            nn = set(recheck_n) - set(network_ids)
            gn = set(network_ids) - set(recheck_n)
            rp = []
            if nn: rp.append(f"new_networks={','.join(sorted(nn))}")
            if gn: rp.append(f"gone_networks={','.join(sorted(gn))}")
            blocked.append(project)
            blocked_commands.append(_harness_clean_cmd(project) + f"  # network topology changed: {'; '.join(rp)}")
            continue

        down_evidence = _harness_clean_cmd(project)
        try:
            rc, _stdout, stderr = docker.harness_clean(project)
        except Exception as exc:
            errors.append(f"{project}: {exc}")
            blocked.append(project)
            blocked_commands.append(down_evidence)
            continue
        if rc != 0:
            blocked.append(project)
            blocked_commands.append(down_evidence)
            errors.append(f"{project}: harness docker-clean failed: {stderr.strip()}")
            continue

        try:
            post_c = docker.ps_project(project)
            post_n = docker.network_ls_project(project)
        except Exception as exc:
            errors.append(f"{project}: post-down inventory failed: {exc}")
            blocked.append(project)
            blocked_commands.append(str(exc))
            continue
        survivors: list[str] = []
        if post_c: survivors.append(f"containers={','.join(post_c)}")
        if post_n: survivors.append(f"networks={','.join(post_n)}")
        if survivors:
            errors.append(f"{project}: resources remain after down: {'; '.join(survivors)}")
            blocked.append(project)
            blocked_commands.append(down_evidence + f"  # survived: {'; '.join(survivors)}")
        else:
            stopped.append(project)

    return {"stopped": stopped, "blocked": blocked, "blocked_commands": blocked_commands, "errors": errors}


def _harness_clean_cmd(project: str) -> str:
    """Return the exact harness docker-clean command for evidence."""
    return shlex.join(["harness", "docker-clean", "compose", "-p", project, "down"])


# ---------------------------------------------------------------------------
# Process teardown
# ---------------------------------------------------------------------------


def _validate_members(
    proc: Any, members: list[int], expected_uid: int, expected_worktree: str, *,
    leader_pid: int | None = None, expected_start: str | None = None,
    delivery_token: str | None = None,
) -> tuple[bool, dict[int, str | None] | None, str | None]:
    """Validate uid, cwd, leader identity, and delivery token provenance."""
    identities: dict[int, str | None] = {}
    for pid in members:
        uid = proc.read_uid(pid)
        cwd = proc.read_cwd(pid)
        start_time = proc.read_start_time(pid)
        if uid != expected_uid:
            return False, None, f"member {pid} uid {uid} != expected {expected_uid}"
        if cwd is None or not is_contained_in(cwd, expected_worktree):
            return False, None, f"member {pid} cwd {cwd!r} not in {expected_worktree!r}"
        if start_time is None:
            return False, None, f"member {pid} disappeared during validation"
        if pid == leader_pid and expected_start and start_time != expected_start:
            return False, None, f"leader {pid} start_time {start_time} != expected {expected_start}"
        is_anchored = pid == leader_pid and expected_start is not None and start_time == expected_start
        if not is_anchored and delivery_token is not None:
            actual = proc.read_delivery_token(pid)
            if actual != delivery_token:
                return False, None, f"member {pid} missing delivery token provenance"
        identities[pid] = start_time
    return True, identities, None


def teardown_processes(record: dict, proc: Any, *, term_wait: float = TERM_WAIT_SECONDS) -> dict:
    """Stop delivery-started process groups with bounded TERM/wait/KILL."""
    worktree = record.get("worktree", "")
    delivery_token = record.get("delivery_token")
    stopped: list[int] = []
    retained: list[dict[str, Any]] = []
    errors: list[str] = []
    ancestor_pgids = proc.get_ancestor_pgids()

    for entry in record.get("process_groups", []):
        if not isinstance(entry, dict):
            errors.append("invalid process entry"); continue
        try:
            pgid = entry["pgid"]; leader_pid = entry["pid"]
            expected_uid = entry["uid"]; expected_start = entry["start_time"]
            expected_worktree = entry.get("worktree", worktree)
        except (KeyError, TypeError) as exc:
            errors.append(f"process entry error: {exc}"); continue

        if pgid in ancestor_pgids:
            retained.append({"pgid": pgid, "reason": "caller/ancestor group"}); continue

        # Check leader identity.
        actual_start = proc.read_start_time(leader_pid)
        leader_alive = actual_start is not None

        # OPUS-R1 fix: When leader PID is reused (alive but different start_time),
        # enumerate surviving group members before declaring stopped.
        if leader_alive and actual_start != expected_start:
            survivors = proc.list_group_pids(pgid)
            if not survivors:
                stopped.append(pgid); continue
            # Survivors exist with a reused leader — retain for safety.
            retained.append({"pgid": pgid, "reason": f"leader PID reused but {len(survivors)} group members survive"})
            continue

        members = proc.list_group_pids(pgid)
        if not members:
            stopped.append(pgid); continue

        if leader_alive:
            recheck = proc.read_start_time(leader_pid)
            if recheck != expected_start:
                retained.append({"pgid": pgid, "reason": "leader identity changed during enumeration"}); continue

        valid, identities, reason = _validate_members(
            proc, members, expected_uid, expected_worktree,
            leader_pid=leader_pid, expected_start=expected_start if leader_alive else None,
            delivery_token=delivery_token,
        )
        if not valid:
            retained.append({"pgid": pgid, "reason": reason}); continue

        # SOL-R2-001 fix: Re-enumerate and re-validate immediately before TERM.
        pre_term_members = proc.list_group_pids(pgid)
        if set(pre_term_members) != set(members):
            retained.append({"pgid": pgid, "reason": "group membership changed before TERM"})
            continue

        stable = True
        for pid in pre_term_members:
            st = proc.read_start_time(pid)
            if st != identities.get(pid):
                retained.append({"pgid": pgid, "reason": f"member {pid} identity changed before TERM"})
                stable = False; break
        if not stable: continue

        try:
            proc.send_signal(pgid, signal.SIGTERM)
        except OSError as exc:
            errors.append(f"SIGTERM pgid {pgid}: {exc}")
            retained.append({"pgid": pgid, "reason": f"SIGTERM failed: {exc}", "signal_cmd": f"kill -{signal.SIGTERM} -{pgid}"})
            continue

        deadline = time.monotonic() + term_wait
        while time.monotonic() < deadline:
            if not proc.list_group_pids(pgid): break
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))

        current = proc.list_group_pids(pgid)
        if not current:
            stopped.append(pgid); continue

        post_term_leader = proc.read_start_time(leader_pid)
        if post_term_leader is not None and post_term_leader != expected_start:
            retained.append({"pgid": pgid, "reason": "leader identity changed after TERM"}); continue

        # SOL-R2-001 fix: Re-enumerate and re-validate immediately before KILL.
        pre_kill_members = proc.list_group_pids(pgid)
        if set(pre_kill_members) != set(current):
            retained.append({"pgid": pgid, "reason": "group membership changed before KILL"})
            continue

        ptla = post_term_leader is not None and post_term_leader == expected_start
        valid, kill_identities, reason = _validate_members(
            proc, pre_kill_members, expected_uid, expected_worktree,
            leader_pid=leader_pid, expected_start=expected_start if ptla else None,
            delivery_token=delivery_token,
        )
        if not valid:
            errors.append(f"pgid {pgid}: pre-KILL revalidation failed: {reason}")
            retained.append({"pgid": pgid, "reason": f"pre-KILL revalidation failed: {reason}"})
            continue

        # Final membership AND identity stability check before KILL.
        final_members = proc.list_group_pids(pgid)
        if set(final_members) != set(pre_kill_members):
            retained.append({"pgid": pgid, "reason": "group membership changed during pre-KILL validation"})
            continue
        kill_stable = True
        for pid in final_members:
            st = proc.read_start_time(pid)
            if st != kill_identities.get(pid):
                retained.append({"pgid": pgid, "reason": f"member {pid} identity changed before KILL"})
                kill_stable = False; break
        if not kill_stable: continue

        try:
            proc.send_signal(pgid, signal.SIGKILL)
        except OSError as exc:
            errors.append(f"SIGKILL pgid {pgid}: {exc}")
            retained.append({"pgid": pgid, "reason": f"SIGKILL failed: {exc}", "signal_cmd": f"kill -{signal.SIGKILL} -{pgid}"})
            continue

        kd = time.monotonic() + KILL_WAIT_SECONDS
        while time.monotonic() < kd:
            if not proc.list_group_pids(pgid): break
            time.sleep(0.05)
        remaining = proc.list_group_pids(pgid)
        if remaining:
            retained.append({"pgid": pgid, "reason": f"processes survived SIGKILL: {remaining}"}); continue
        stopped.append(pgid)

    return {"stopped": stopped, "retained": retained, "errors": errors}


# ---------------------------------------------------------------------------
# Combined teardown
# ---------------------------------------------------------------------------


def teardown(record_path: Path, *, docker: Any = None, proc: Any = None) -> dict:
    if docker is None: docker = RealDockerOps()
    if proc is None: proc = RealProcessOps()
    empty: dict[str, Any] = {"stopped_projects": [], "stopped_groups": [], "retained_groups": [], "blocked_commands": [], "errors": []}
    if not record_path.exists():
        return {**empty, "status": "blocked", "errors": [f"record file not found: {record_path}"]}
    try:
        record = load_record(record_path)
    except Exception as exc:
        return {**empty, "status": "blocked", "errors": [f"record unreadable: {exc}"]}
    error = _validate_ledger(record)
    if error:
        return {**empty, "status": "blocked", "errors": [f"invalid record: {error}"]}

    try:
        compose_result = teardown_compose(record, docker)
    except Exception as exc:
        compose_result = {"stopped": [], "blocked": [], "blocked_commands": [str(exc)], "errors": [f"compose teardown failed: {exc}"]}
    try:
        process_result = teardown_processes(record, proc)
    except Exception as exc:
        process_result = {"stopped": [], "retained": [], "errors": [f"process teardown failed: {exc}"]}

    all_errors = compose_result["errors"] + process_result["errors"]
    all_blocked = compose_result["blocked_commands"]
    retained = process_result["retained"]
    non_benign = [r for r in retained if r.get("reason") != "caller/ancestor group"]
    has_blocked = bool(all_blocked) or bool(compose_result["blocked"]) or bool(all_errors) or bool(non_benign)
    return {
        "status": "blocked" if has_blocked else "complete",
        "stopped_projects": compose_result["stopped"], "stopped_groups": process_result["stopped"],
        "retained_groups": retained, "blocked_commands": all_blocked, "errors": all_errors,
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_teardown_line(result: dict) -> str:
    parts = [f"Teardown: {result['status']}"]
    if result["stopped_projects"]: parts.append(f"projects={','.join(result['stopped_projects'])}")
    if result["stopped_groups"]: parts.append(f"groups={','.join(str(g) for g in result['stopped_groups'])}")
    if result.get("retained_groups"):
        rs = []
        for r in result["retained_groups"]:
            s = f"{r['pgid']}:{r['reason']}"
            if r.get("signal_cmd"): s += f" ({r['signal_cmd']})"
            rs.append(s)
        parts.append(f"retained={'; '.join(rs)}")
    if result["blocked_commands"]: parts.append(f"blocked_commands={'; '.join(result['blocked_commands'])}")
    if result["errors"]: parts.append(f"errors={'; '.join(result['errors'])}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Real implementations
# ---------------------------------------------------------------------------


class RealDockerOps:
    @staticmethod
    def _run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
        try: return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError: raise RuntimeError(f"command not found: {shlex.join(cmd)}")
        except PermissionError: raise RuntimeError(f"permission denied: {shlex.join(cmd)}")
        except subprocess.TimeoutExpired: raise RuntimeError(f"timed out after {timeout}s: {shlex.join(cmd)}")

    def ps_project(self, project: str) -> list[str]:
        cmd = ["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={project}", "--format", "{{.ID}}"]
        r = self._run(cmd)
        if r.returncode != 0: raise RuntimeError(f"{shlex.join(cmd)}: {r.stderr.strip()}")
        return [l.strip() for l in r.stdout.strip().splitlines() if l.strip()]

    def inspect_labels(self, cid: str) -> dict[str, str]:
        cmd = ["docker", "inspect", "--format", "{{json .Config.Labels}}", cid]
        r = self._run(cmd)
        if r.returncode != 0: raise RuntimeError(f"{shlex.join(cmd)}: {r.stderr.strip()}")
        try: return json.loads(r.stdout.strip()) or {}
        except json.JSONDecodeError: raise RuntimeError(f"{shlex.join(cmd)}: invalid JSON output")

    def network_ls_project(self, project: str) -> list[str]:
        cmd = ["docker", "network", "ls", "--filter", f"label=com.docker.compose.project={project}", "--format", "{{.ID}}"]
        r = self._run(cmd)
        if r.returncode != 0: raise RuntimeError(f"{shlex.join(cmd)}: {r.stderr.strip()}")
        return [l.strip() for l in r.stdout.strip().splitlines() if l.strip()]

    def network_inspect_labels(self, nid: str) -> dict[str, str]:
        cmd = ["docker", "network", "inspect", nid]
        r = self._run(cmd)
        if r.returncode != 0: raise RuntimeError(f"{shlex.join(cmd)}: {r.stderr.strip()}")
        try: data = json.loads(r.stdout)
        except json.JSONDecodeError: raise RuntimeError(f"{shlex.join(cmd)}: invalid JSON output")
        return (data[0].get("Labels") or {}) if data else {}

    def harness_clean(self, project: str) -> tuple[int, str, str]:
        cmd = ["harness", "docker-clean", "compose", "-p", project, "down"]
        try: r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except FileNotFoundError: raise RuntimeError(f"command not found: {shlex.join(cmd)}")
        except PermissionError: raise RuntimeError(f"permission denied: {shlex.join(cmd)}")
        except subprocess.TimeoutExpired: raise RuntimeError(f"timed out after 120s: {shlex.join(cmd)}")
        return (r.returncode, r.stdout, r.stderr)

    def compose_config(self, project: str, compose_files: list[str], *, project_directory: str | None = None) -> str:
        cmd = ["docker", "compose"]
        if project_directory: cmd.extend(["--project-directory", project_directory])
        for f in compose_files: cmd.extend(["-f", f])
        cmd.extend(["-p", project, "config", "--format", "json"])
        r = self._run(cmd)
        if r.returncode != 0: raise RuntimeError(f"{shlex.join(cmd)}: {r.stderr.strip()}")
        return r.stdout


class RealProcessOps:
    def read_start_time(self, pid: int) -> str | None:
        try:
            fields = _parse_stat_fields(Path(f"/proc/{pid}/stat").read_text(encoding="utf-8"))
            return fields[21] if fields and len(fields) >= 22 else None
        except (OSError, IndexError): return None
    def read_uid(self, pid: int) -> int | None:
        try:
            for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
                if line.startswith("Uid:"): return int(line.split()[1])
        except (OSError, ValueError, IndexError): pass
        return None
    def read_cwd(self, pid: int) -> str | None:
        try: return str(Path(f"/proc/{pid}/cwd").resolve())
        except OSError: return None
    def read_delivery_token(self, pid: int) -> str | None:
        try:
            for entry in Path(f"/proc/{pid}/environ").read_bytes().split(b"\x00"):
                if entry.startswith(b"COGNOVIS_DELIVERY_TOKEN="):
                    return entry.split(b"=", 1)[1].decode()
        except (OSError, UnicodeDecodeError): pass
        return None
    def get_pgid(self, pid: int) -> int | None:
        try: return os.getpgid(pid)
        except OSError: return None
    def list_group_pids(self, pgid: int) -> list[int]:
        pids: list[int] = []
        try:
            for e in Path("/proc").iterdir():
                if e.name.isdigit():
                    try:
                        pid = int(e.name)
                        if os.getpgid(pid) == pgid:
                            # Exclude zombies and dead processes.
                            fields = _parse_stat_fields(Path(f"/proc/{pid}/stat").read_text(encoding="utf-8"))
                            if fields and len(fields) > 2 and fields[2] not in ("Z", "X", "x"):
                                pids.append(pid)
                    except (OSError, ValueError): pass
        except OSError: pass
        return pids
    def send_signal(self, pgid: int, sig: int) -> None: os.killpg(pgid, sig)
    def getpid(self) -> int: return os.getpid()
    def get_ancestor_pgids(self) -> set[int]:
        pgids: set[int] = set(); pid = os.getpid()
        while pid > 0:
            try:
                pgids.add(os.getpgid(pid))
                fields = _parse_stat_fields(Path(f"/proc/{pid}/stat").read_text(encoding="utf-8"))
                if not fields or len(fields) < 4: break
                ppid = int(fields[3])
                if ppid == pid: break
                pid = ppid
            except (OSError, ValueError, IndexError): break
        return pgids
    def is_alive(self, pid: int) -> bool:
        try: os.kill(pid, 0); return True
        except OSError: return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delivery teardown: stop delivery-owned resources.")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p = sub.add_parser("init"); p.add_argument("--worktree", required=True); p.add_argument("--token", required=True); p.add_argument("--record-file", required=True, type=Path)
    p = sub.add_parser("record-compose"); p.add_argument("--record-file", required=True, type=Path); p.add_argument("--project", required=True)
    p.add_argument("--compose-file", action="append", default=[], dest="compose_files"); p.add_argument("--project-directory", default=None)
    p = sub.add_parser("record-process"); p.add_argument("--record-file", required=True, type=Path)
    p.add_argument("--pgid", required=True, type=int); p.add_argument("--pid", required=True, type=int)
    p.add_argument("--uid", required=True, type=int); p.add_argument("--start-time", required=True)
    p.add_argument("--worktree", required=True); p.add_argument("--command", required=True)
    p = sub.add_parser("teardown"); p.add_argument("--record-file", required=True, type=Path)
    p = sub.add_parser("project-name"); p.add_argument("--worktree", required=True); p.add_argument("--token", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.subcommand == "init":
        init_record(args.worktree, args.token, args.record_file); return 0
    if args.subcommand == "record-compose":
        try:
            result = prepare_compose_start(args.record_file, args.project, args.compose_files, project_directory=args.project_directory)
        except (RuntimeError, OSError) as exc:
            sys.stderr.write(f"record-compose: {exc}\n"); return 1
        if result.get("frozen_config"): sys.stdout.write(result["frozen_config"] + "\n")
        return 0
    if args.subcommand == "record-process":
        try:
            record_process_start(args.record_file, pgid=args.pgid, pid=args.pid, uid=args.uid,
                                 start_time=args.start_time, worktree=args.worktree, command=args.command)
        except ValueError as exc:
            sys.stderr.write(f"record-process: {exc}\n")
            return 1
        return 0
    if args.subcommand == "teardown":
        sys.stdout.write(format_teardown_line(teardown(args.record_file)) + "\n"); return 0
    if args.subcommand == "project-name":
        sys.stdout.write(derive_project_name(args.worktree, args.token) + "\n"); return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
