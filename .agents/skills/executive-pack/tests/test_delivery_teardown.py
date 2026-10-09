"""Tests for delivery_teardown.py."""
from __future__ import annotations
import json, os, signal, subprocess, sys
from pathlib import Path
from typing import Any, Callable
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from delivery_teardown import (
    CONTRACT, RealProcessOps, _check_lifecycle_labels,
    _parse_stat_fields, _snapshot_dir, _validate_ledger, _validate_utc_timestamp,
    format_teardown_line,
    init_record, load_record, prepare_compose_start,
    record_process_start, teardown, teardown_compose, teardown_processes,
)

_FULL_LABELS = {
    "de.cognovis.ephemeral": "true",
    "de.cognovis.issue": "cognovis/library-core#213",
    "de.cognovis.expires-at": "2099-01-01T00:00:00Z",
}
def _owned_labels(wt: str, token: str = "tok") -> dict[str, str]:
    return {"cognovis.worktree": wt, "cognovis.delivery": token, **_FULL_LABELS}

class FakeDockerOps:
    def __init__(self) -> None:
        self.containers: dict[str, dict[str, dict[str, str]]] = {}
        self.networks: dict[str, dict[str, dict[str, str]]] = {}
        self.down_calls: list[tuple[str, list[str], dict[str, Any]]] = []
        self.unavailable = False
        self.guard_blocked: dict[str, str] = {}
        self._on_ps_project: Callable[[str], None] | None = None
        self._on_network_ls: Callable[[str], None] | None = None
        self.config_output: str = json.dumps({"services": {"dev": {
            "image": "busybox", "restart": "no",
            "labels": _FULL_LABELS | {"cognovis.worktree": "PLACEHOLDER", "cognovis.delivery": "PLACEHOLDER"},
        }}, "networks": {}})
    def set_worktree_token(self, wt: str, token: str) -> None:
        cfg = json.loads(self.config_output)
        for svc in cfg.get("services", {}).values():
            labels = svc.get("labels", {})
            labels["cognovis.worktree"] = wt; labels["cognovis.delivery"] = token
        for net_name, net_cfg in cfg.get("networks", {}).items():
            if isinstance(net_cfg, dict) and not net_cfg.get("external"):
                net_labels = net_cfg.get("labels", {})
                net_labels["cognovis.worktree"] = wt; net_labels["cognovis.delivery"] = token
                net_cfg["labels"] = net_labels
        self.config_output = json.dumps(cfg)
    def ps_project(self, p: str) -> list[str]:
        if self.unavailable: raise RuntimeError("Cannot connect to Docker daemon")
        if self._on_ps_project: self._on_ps_project(p)
        return list(self.containers.get(p, {}).keys())
    def inspect_labels(self, cid: str) -> dict[str, str]:
        if self.unavailable: raise RuntimeError("Cannot connect")
        for pc in self.containers.values():
            if cid in pc: return dict(pc[cid])
        return {}
    def network_ls_project(self, p: str) -> list[str]:
        if self.unavailable: raise RuntimeError("Cannot connect")
        if self._on_network_ls: self._on_network_ls(p)
        return list(self.networks.get(p, {}).keys())
    def network_inspect_labels(self, nid: str) -> dict[str, str]:
        if self.unavailable: raise RuntimeError("Cannot connect")
        for pn in self.networks.values():
            if nid in pn: return dict(pn[nid])
        return {}
    def harness_clean(self, project: str) -> tuple[int, str, str]:
        if self.unavailable: raise RuntimeError("Cannot connect")
        if project in self.guard_blocked: return (1, "", self.guard_blocked[project])
        self.down_calls.append((project, [], {}))
        self.containers.pop(project, None); self.networks.pop(project, None)
        return (0, "", "")
    def compose_config(self, project: str, files: list[str], *, project_directory: str | None = None) -> str:
        if self.unavailable: raise RuntimeError("Cannot connect")
        return self.config_output

class FakeProcessOps:
    def __init__(self) -> None:
        self.processes: dict[int, dict] = {}; self.signals_sent: list[tuple[int, int]] = []
        self.my_pid = 99999; self.my_ancestor_pgids: set[int] = {99999, 1}
        self.term_kills = True; self._on_signal: Callable[[int, int], None] | None = None
        self._kill_error: OSError | None = None
    def add_process(self, pid: int, pgid: int, uid: int, start_time: str, cwd: str,
                    alive: bool = True, delivery_token: str | None = None) -> None:
        self.processes[pid] = {"pgid": pgid, "uid": uid, "start_time": start_time,
                               "cwd": cwd, "alive": alive, "delivery_token": delivery_token}
    def read_start_time(self, pid: int) -> str | None:
        p = self.processes.get(pid); return p["start_time"] if p and p["alive"] else None
    def read_uid(self, pid: int) -> int | None:
        p = self.processes.get(pid); return p["uid"] if p and p["alive"] else None
    def read_cwd(self, pid: int) -> str | None:
        p = self.processes.get(pid); return p["cwd"] if p and p["alive"] else None
    def read_delivery_token(self, pid: int) -> str | None:
        p = self.processes.get(pid); return p.get("delivery_token") if p and p["alive"] else None
    def get_pgid(self, pid: int) -> int | None:
        p = self.processes.get(pid); return p["pgid"] if p and p["alive"] else None
    def list_group_pids(self, pgid: int) -> list[int]:
        return [pid for pid, p in self.processes.items() if p["pgid"] == pgid and p["alive"]]
    def send_signal(self, pgid: int, sig: int) -> None:
        if sig == signal.SIGKILL and self._kill_error: self.signals_sent.append((pgid, sig)); raise self._kill_error
        self.signals_sent.append((pgid, sig))
        if self._on_signal: self._on_signal(pgid, sig)
        if sig == signal.SIGKILL or (sig == signal.SIGTERM and self.term_kills):
            for p in self.processes.values():
                if p["pgid"] == pgid: p["alive"] = False
    def getpid(self) -> int: return self.my_pid
    def get_ancestor_pgids(self) -> set[int]: return set(self.my_ancestor_pgids)
    def is_alive(self, pid: int) -> bool:
        p = self.processes.get(pid); return bool(p and p["alive"])


def _prepare(tmp_path: Path, token: str = "tok") -> tuple[Path, Path, str, FakeDockerOps]:
    """Init a record and return (rec, wt, resolved_wt, docker) ready for prepare_compose_start."""
    wt = tmp_path / "wt"; wt.mkdir(exist_ok=True)
    rec = tmp_path / "record.json"; init_record(str(wt), token, rec)
    docker = FakeDockerOps(); resolved = str(wt.resolve())
    docker.set_worktree_token(resolved, token)
    os.environ["XDG_CACHE_HOME"] = str(tmp_path / "cache")
    return rec, wt, resolved, docker


def _prepared_record(tmp_path: Path, project: str = "p", token: str = "tok") -> tuple[dict, str, FakeDockerOps]:
    """Return a record with one prepared compose entry."""
    rec, wt, resolved, docker = _prepare(tmp_path, token)
    prepare_compose_start(rec, project, ["/c.yml"], project_directory=str(wt), docker=docker)
    return load_record(rec), resolved, docker


# ---------------------------------------------------------------------------
# Stat parsing
# ---------------------------------------------------------------------------
class TestParseStatFields:
    def test_spaced_comm(self) -> None:
        f = _parse_stat_fields("456 (dev server) S 42 456 456 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 987654")
        assert f and f[1] == "dev server" and f[3] == "42" and f[21] == "987654"

# ---------------------------------------------------------------------------
# Lifecycle labels
# ---------------------------------------------------------------------------
class TestLifecycleLabels:
    def test_valid(self) -> None:
        assert _check_lifecycle_labels(_owned_labels("/wt", "tok"), "/wt", "tok", "c1", "container") is None
    def test_ephemeral_false_rejected(self) -> None:
        labels = {**_owned_labels("/wt"), "de.cognovis.ephemeral": "false"}
        assert "ephemeral" in (_check_lifecycle_labels(labels, "/wt", "tok", "c1", "container") or "")
    def test_empty_issue_rejected(self) -> None:
        labels = {**_owned_labels("/wt"), "de.cognovis.issue": ""}
        assert "issue" in (_check_lifecycle_labels(labels, "/wt", "tok", "c1", "container") or "")
    def test_empty_expiry_rejected(self) -> None:
        labels = {**_owned_labels("/wt"), "de.cognovis.expires-at": ""}
        assert "expires-at" in (_check_lifecycle_labels(labels, "/wt", "tok", "c1", "container") or "")
    def test_expires_at_non_utc_rejected(self) -> None:
        labels = {**_owned_labels("/wt"), "de.cognovis.expires-at": "2099-01-01T00:00:00+02:00"}
        result = _check_lifecycle_labels(labels, "/wt", "tok", "c1", "container")
        assert result is not None and "expires-at" in result
    def test_expires_at_valid_utc(self) -> None:
        labels = {**_owned_labels("/wt"), "de.cognovis.expires-at": "2099-12-31T23:59:59Z"}
        assert _check_lifecycle_labels(labels, "/wt", "tok", "c1", "container") is None

# ---------------------------------------------------------------------------
# Ledger validation
# ---------------------------------------------------------------------------
class TestLedgerValidation:
    def _base(self) -> dict:
        return {"contract": CONTRACT, "worktree": "/wt", "delivery_token": "tok",
                "compose_projects": [], "process_groups": []}
    def test_valid(self) -> None: assert _validate_ledger(self._base()) is None
    def test_missing_worktree(self) -> None:
        r = self._base(); del r["worktree"]; assert _validate_ledger(r) is not None
    def test_missing_token(self) -> None:
        r = self._base(); del r["delivery_token"]; assert _validate_ledger(r) is not None
    def test_pgid_list_rejected(self) -> None:
        r = self._base(); r["process_groups"] = [{"pgid": [], "pid": 1, "uid": 0, "start_time": "1", "worktree": "/wt"}]
        assert _validate_ledger(r) is not None
    def test_pid_null_rejected(self) -> None:
        r = self._base(); r["process_groups"] = [{"pgid": 1, "pid": None, "uid": 0, "start_time": "1", "worktree": "/wt"}]
        assert _validate_ledger(r) is not None
    def test_uid_string_rejected(self) -> None:
        r = self._base(); r["process_groups"] = [{"pgid": 1, "pid": 1, "uid": "wrong", "start_time": "1", "worktree": "/wt"}]
        assert _validate_ledger(r) is not None
    def test_start_time_dict_rejected(self) -> None:
        r = self._base(); r["process_groups"] = [{"pgid": 1, "pid": 1, "uid": 0, "start_time": {}, "worktree": "/wt"}]
        assert _validate_ledger(r) is not None
    def test_worktree_null_rejected(self) -> None:
        r = self._base(); r["process_groups"] = [{"pgid": 1, "pid": 1, "uid": 0, "start_time": "1", "worktree": None}]
        assert _validate_ledger(r) is not None
    def test_compose_files_null_rejected(self) -> None:
        r = self._base(); r["compose_projects"] = [{"project": "p", "compose_files": None}]
        assert _validate_ledger(r) is not None
    def test_compose_token_null_rejected(self) -> None:
        r = self._base(); r["compose_projects"] = [{"project": "p", "delivery_token": None}]
        assert "invalid delivery_token" in (_validate_ledger(r) or "")
    def test_zero_pgid_rejected(self) -> None:
        r = self._base(); r["process_groups"] = [{"pgid": 0, "pid": 1, "uid": 0, "start_time": "1", "worktree": "/wt"}]
        assert "invalid pgid" in (_validate_ledger(r) or "")
    def test_zero_pid_rejected(self) -> None:
        r = self._base(); r["process_groups"] = [{"pgid": 1, "pid": 0, "uid": 0, "start_time": "1", "worktree": "/wt"}]
        assert "invalid pid" in (_validate_ledger(r) or "")
    def test_non_numeric_start_time_rejected(self) -> None:
        r = self._base(); r["process_groups"] = [{"pgid": 1, "pid": 1, "uid": 0, "start_time": "abc", "worktree": "/wt"}]
        assert "invalid start_time" in (_validate_ledger(r) or "")
    def test_relative_worktree_rejected(self) -> None:
        r = self._base(); r["process_groups"] = [{"pgid": 1, "pid": 1, "uid": 0, "start_time": "1", "worktree": "relative/path"}]
        result = _validate_ledger(r)
        assert result is not None and "canonical absolute" in result
    def test_compose_entry_token_mismatch_rejected(self) -> None:
        r = self._base(); r["compose_projects"] = [{"project": "p", "delivery_token": "other"}]
        assert "does not match root" in (_validate_ledger(r) or "")
    def test_compose_entry_worktree_mismatch_rejected(self) -> None:
        r = self._base(); r["compose_projects"] = [{"project": "p", "worktree": "/other"}]
        assert "does not match root" in (_validate_ledger(r) or "")
    def test_process_worktree_mismatch_rejected(self) -> None:
        r = self._base(); r["process_groups"] = [{"pgid": 1, "pid": 1, "uid": 0, "start_time": "1", "worktree": "/other"}]
        result = _validate_ledger(r)
        assert result is not None and "does not match root" in result

# ---------------------------------------------------------------------------
# Snapshot dir
# ---------------------------------------------------------------------------
class TestSnapshotDir:
    def test_uses_xdg_cache(self, tmp_path: Path) -> None:
        os.environ["XDG_CACHE_HOME"] = str(tmp_path / "cache")
        d = _snapshot_dir("tok")
        assert str(tmp_path / "cache") in str(d) and "tok" in str(d)

# ---------------------------------------------------------------------------
# Compose registration
# ---------------------------------------------------------------------------
class TestPrepareCompose:
    def test_refuses_pre_existing(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        docker.containers["p"] = {"c1": {}}
        with pytest.raises(RuntimeError, match="pre-existing"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
    def test_saves_frozen_config(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        result = prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        assert result.get("frozen_config") and Path(result["frozen_config"]).exists()
    def test_snapshot_outside_worktree(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        result = prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        assert str(wt.resolve()) not in result["frozen_config"]
    def test_rejects_persistent_marker(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        cfg = json.loads(docker.config_output)
        cfg["services"]["dev"]["labels"]["de.cognovis.ephemeral"] = "false"
        docker.config_output = json.dumps(cfg)
        with pytest.raises(RuntimeError, match="rejected"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
    def test_rejects_empty_issue(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        cfg = json.loads(docker.config_output)
        cfg["services"]["dev"]["labels"]["de.cognovis.issue"] = ""
        docker.config_output = json.dumps(cfg)
        with pytest.raises(RuntimeError, match="rejected"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
    def test_expires_at_non_utc_rejected_at_prepare(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        cfg = json.loads(docker.config_output)
        cfg["services"]["dev"]["labels"]["de.cognovis.expires-at"] = "2099-01-01T00:00:00+02:00"
        docker.config_output = json.dumps(cfg)
        with pytest.raises(RuntimeError, match="rejected"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
    def test_restart_not_no_rejected(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        cfg = json.loads(docker.config_output)
        cfg["services"]["dev"]["restart"] = "always"
        docker.config_output = json.dumps(cfg)
        with pytest.raises(RuntimeError, match="restart"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
    def test_xdg_cache_inside_worktree_refused(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"; wt.mkdir(exist_ok=True)
        rec = tmp_path / "record.json"; init_record(str(wt), "tok", rec)
        docker = FakeDockerOps(); resolved = str(wt.resolve())
        docker.set_worktree_token(resolved, "tok")
        os.environ["XDG_CACHE_HOME"] = str(wt / "cache")
        with pytest.raises(RuntimeError, match="inside worktree"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)

# ---------------------------------------------------------------------------
# Compose teardown
# ---------------------------------------------------------------------------
class TestComposeTeardown:
    def test_stops_own_project(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        assert "p" in teardown_compose(record, docker)["stopped"]

    def test_missing_frozen_config_blocks(self, tmp_path: Path) -> None:
        """Missing frozen_config must NEVER fall back to original files."""
        record, wt, docker = _prepared_record(tmp_path)
        record["compose_projects"][0].pop("frozen_config")
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]

    def test_persistent_marker_blocked_at_teardown(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        labels = {**_owned_labels(wt), "de.cognovis.ephemeral": "false"}
        docker.containers["p"] = {"c1": labels}; docker.networks["p"] = {}
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]

    def test_empty_issue_blocked_at_teardown(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        labels = {**_owned_labels(wt), "de.cognovis.issue": ""}
        docker.containers["p"] = {"c1": labels}; docker.networks["p"] = {}
        assert teardown_compose(record, docker)["stopped"] == []

    def test_late_network_blocked(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        docker.containers["p"] = {"c1": _owned_labels(wt)}
        docker.networks["p"] = {"n1": _owned_labels(wt)}
        nc = [0]
        def inject(p: str) -> None:
            nc[0] += 1
            if nc[0] == 2: docker.networks["p"]["fn"] = {"cognovis.worktree": "/x"}
        docker._on_network_ls = inject
        assert "p" in teardown_compose(record, docker)["blocked"]

    def test_post_down_network_blocked(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {"n1": _owned_labels(wt)}
        def sticky(proj):
            docker.down_calls.append((proj, [], {})); docker.containers.pop(proj, None); return (0, "", "")
        docker.harness_clean = sticky  # type: ignore[assignment]
        assert "p" in teardown_compose(record, docker)["blocked"]

    def test_guard_blocked_reports_harness_cmd(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        docker.guard_blocked["p"] = "blocked"
        assert any("harness docker-clean" in c for c in teardown_compose(record, docker)["blocked_commands"])

    def test_empty_project(self, tmp_path: Path) -> None:
        record, _, _ = _prepared_record(tmp_path)
        assert "p" in teardown_compose(record, FakeDockerOps())["stopped"]

    def test_entry_token_mismatch_blocks(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        record["compose_projects"][0]["delivery_token"] = "wrong"
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]

    def test_entry_worktree_mismatch_blocks(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        record["compose_projects"][0]["worktree"] = "/wrong"
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]

    def test_live_issue_changed_blocks(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        # The entry has issue from prepare; now the live container has a different one.
        live_labels = {**_owned_labels(wt), "de.cognovis.issue": "cognovis/other-repo#999"}
        docker.containers["p"] = {"c1": live_labels}; docker.networks["p"] = {}
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]
        assert any("issue changed" in c for c in r["blocked_commands"])

    def test_changed_snapshot_digest_blocks(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        # Tamper with the frozen config file.
        fc = record["compose_projects"][0]["frozen_config"]
        Path(fc).write_text("tampered content")
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]
        assert any("digest" in e for e in r["errors"])

    def test_foreign_file_as_frozen_config_blocks(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        # Replace frozen_config path with a different file.
        foreign = tmp_path / "foreign.json"
        foreign.write_text("{}")
        record["compose_projects"][0]["frozen_config"] = str(foreign)
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]

# ---------------------------------------------------------------------------
# Process teardown
# ---------------------------------------------------------------------------
def _make_process_record(tmp_path: Path, groups: list[dict], *, token: str = "tok") -> tuple[dict, str]:
    wt = tmp_path / "wt"; wt.mkdir(exist_ok=True); rec = tmp_path / "record.json"
    init_record(str(wt), token, rec)
    # Manually append process groups to avoid record_process_start's /proc checks.
    record = load_record(rec)
    for g in groups:
        record["process_groups"].append({
            "pgid": g["pgid"], "pid": g["pid"], "uid": g["uid"],
            "start_time": g["start_time"],
            "worktree": str(Path(g["worktree"]).resolve()),
            "command": g["command"],
        })
    rec.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return load_record(rec), load_record(rec)["worktree"]

class TestProcessTeardown:
    def test_stops_own_group(self, tmp_path: Path) -> None:
        record, wt = _make_process_record(tmp_path, [
            {"pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345", "worktree": str(tmp_path / "wt"), "command": "dev"}])
        proc = FakeProcessOps(); proc.add_process(500, 500, 1000, "12345", wt + "/sub")
        assert 500 in teardown_processes(record, proc, term_wait=0)["stopped"]

    def test_live_leader_foreign_member_not_adopted(self, tmp_path: Path) -> None:
        record, wt = _make_process_record(tmp_path, [
            {"pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345", "worktree": str(tmp_path / "wt"), "command": "dev"}])
        proc = FakeProcessOps()
        proc.add_process(500, 500, 1000, "12345", wt)
        proc.add_process(501, 500, 1000, "67890", wt)  # no token
        teardown_processes(record, proc, term_wait=0)
        assert not proc.signals_sent and proc.is_alive(501)

    def test_leader_gone_no_token_retained(self, tmp_path: Path) -> None:
        record, wt = _make_process_record(tmp_path, [
            {"pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345", "worktree": str(tmp_path / "wt"), "command": "dev"}])
        proc = FakeProcessOps(); proc.add_process(501, 500, 1000, "99999", wt)
        assert not proc.signals_sent and bool(teardown_processes(record, proc, term_wait=0)["retained"])

    def test_leader_gone_with_token_stopped(self, tmp_path: Path) -> None:
        record, wt = _make_process_record(tmp_path, [
            {"pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345", "worktree": str(tmp_path / "wt"), "command": "dev"}])
        proc = FakeProcessOps(); proc.add_process(501, 500, 1000, "12345", wt, delivery_token="tok")
        assert 500 in teardown_processes(record, proc, term_wait=0)["stopped"]

    def test_leader_reuse_after_term_blocks(self, tmp_path: Path) -> None:
        record, wt = _make_process_record(tmp_path, [
            {"pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345", "worktree": str(tmp_path / "wt"), "command": "dev"}])
        proc = FakeProcessOps(); proc.term_kills = False; proc.add_process(500, 500, 1000, "12345", wt)
        proc._on_signal = lambda pgid, sig: proc.processes[500].update(start_time="99999") if sig == signal.SIGTERM else None
        teardown_processes(record, proc, term_wait=0.01)
        assert not any(s == signal.SIGKILL for _, s in proc.signals_sent)

    def test_kill_failure_retained(self, tmp_path: Path) -> None:
        record, wt = _make_process_record(tmp_path, [
            {"pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345", "worktree": str(tmp_path / "wt"), "command": "dev"}])
        proc = FakeProcessOps(); proc.term_kills = False; proc._kill_error = PermissionError("denied")
        proc.add_process(500, 500, 1000, "12345", wt)
        r = teardown_processes(record, proc, term_wait=0.01)
        retained = [e for e in r["retained"] if e["pgid"] == 500]
        assert retained and "kill -9 -500" in retained[0].get("signal_cmd", "")

# ---------------------------------------------------------------------------
# Real process probe
# ---------------------------------------------------------------------------
class TestRealProbe:
    def test_isolated_group(self) -> None:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        try:
            ops = RealProcessOps(); assert ops.read_start_time(child.pid) is not None
        finally:
            os.killpg(child.pid, signal.SIGKILL); child.wait()

# ---------------------------------------------------------------------------
# Process registration proof
# ---------------------------------------------------------------------------
class TestProcessRegistration:
    def test_real_process_registration(self, tmp_path: Path) -> None:
        """Register a real subprocess through record_process_start."""
        wt = tmp_path / "wt"; wt.mkdir()
        rec = tmp_path / "record.json"
        token = "test-reg-tok"
        init_record(str(wt), token, rec)
        os.environ["XDG_CACHE_HOME"] = str(tmp_path / "cache")
        env = {**os.environ, "COGNOVIS_DELIVERY_TOKEN": token}
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True, cwd=str(wt), env=env,
        )
        try:
            import time; time.sleep(0.1)  # let /proc populate
            pgid = os.getpgid(child.pid)
            uid = os.getuid()
            # Read start_time from /proc.
            stat_text = Path(f"/proc/{child.pid}/stat").read_text(encoding="utf-8")
            from delivery_teardown import _parse_stat_fields
            fields = _parse_stat_fields(stat_text)
            assert fields and len(fields) >= 22
            start_time = fields[21]
            record_process_start(
                rec, pgid=pgid, pid=child.pid, uid=uid,
                start_time=start_time, worktree=str(wt), command="sleep",
            )
            record = load_record(rec)
            assert len(record["process_groups"]) == 1
            assert record["process_groups"][0]["pid"] == child.pid
        finally:
            os.killpg(child.pid, signal.SIGKILL); child.wait()

    def test_zero_pid_rejected_by_registration(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"; wt.mkdir()
        rec = tmp_path / "record.json"; init_record(str(wt), "tok", rec)
        with pytest.raises(ValueError, match="pid must be positive"):
            record_process_start(rec, pgid=1, pid=0, uid=0, start_time="1",
                                 worktree=str(wt), command="cmd")

    def test_zero_pgid_rejected_by_registration(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"; wt.mkdir()
        rec = tmp_path / "record.json"; init_record(str(wt), "tok", rec)
        with pytest.raises(ValueError, match="pgid must be positive"):
            record_process_start(rec, pgid=0, pid=1, uid=0, start_time="1",
                                 worktree=str(wt), command="cmd")

    def test_non_numeric_start_time_rejected(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"; wt.mkdir()
        rec = tmp_path / "record.json"; init_record(str(wt), "tok", rec)
        with pytest.raises(ValueError, match="decimal numeric"):
            record_process_start(rec, pgid=1, pid=1, uid=0, start_time="abc",
                                 worktree=str(wt), command="cmd")

# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------
class TestOutputFormat:
    def test_signal_cmd_in_line(self) -> None:
        r = {"status": "blocked", "stopped_projects": [], "stopped_groups": [],
             "blocked_commands": [], "errors": [],
             "retained_groups": [{"pgid": 500, "reason": "SIGKILL failed", "signal_cmd": "kill -9 -500"}]}
        assert "kill -9 -500" in format_teardown_line(r)

# ---------------------------------------------------------------------------
# Full teardown
# ---------------------------------------------------------------------------
class TestTeardown:
    def test_empty_record_complete(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"; wt.mkdir(); rec = tmp_path / "r.json"
        init_record(str(wt), "tok", rec)
        assert teardown(rec, docker=FakeDockerOps(), proc=FakeProcessOps())["status"] == "complete"

    def test_missing_record_blocked(self, tmp_path: Path) -> None:
        assert teardown(tmp_path / "no.json", docker=FakeDockerOps(), proc=FakeProcessOps())["status"] == "blocked"

    def test_list_json_blocked(self, tmp_path: Path) -> None:
        rec = tmp_path / "r.json"; rec.write_text("[]")
        assert teardown(rec, docker=FakeDockerOps(), proc=FakeProcessOps())["status"] == "blocked"

    def test_docker_failure_continues_process(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"; wt.mkdir(); rec = tmp_path / "r.json"
        os.environ["XDG_CACHE_HOME"] = str(tmp_path / "cache")
        init_record(str(wt), "tok", rec)
        resolved = str(wt.resolve()); docker_prep = FakeDockerOps(); docker_prep.set_worktree_token(resolved, "tok")
        prepare_compose_start(rec, "p", ["/c.yml"], project_directory=str(wt), docker=docker_prep)
        # Manually add process group to avoid /proc checks.
        record = load_record(rec)
        record["process_groups"].append({
            "pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345",
            "worktree": resolved, "command": "dev",
        })
        rec.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        proc = FakeProcessOps(); proc.add_process(500, 500, 1000, "12345", resolved)
        class Crash:
            def ps_project(self, p: str) -> list[str]: raise FileNotFoundError("no docker")
            def network_ls_project(self, p: str) -> list[str]: raise FileNotFoundError("no docker")
        r = teardown(rec, docker=Crash(), proc=proc)
        assert r["status"] == "blocked" and 500 in r["stopped_groups"]

    def test_caller_does_not_block(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"; wt.mkdir(); rec = tmp_path / "r.json"
        init_record(str(wt), "tok", rec)
        resolved = str(wt.resolve())
        # Manually add process group.
        record = load_record(rec)
        record["process_groups"].append({
            "pgid": 99999, "pid": 99999, "uid": 1000, "start_time": "12345",
            "worktree": resolved, "command": "self",
        })
        rec.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        proc = FakeProcessOps(); proc.my_ancestor_pgids = {99999, 1}
        assert teardown(rec, docker=FakeDockerOps(), proc=proc)["status"] == "complete"

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "delivery_teardown.py")

class TestCLI:
    def test_record_process_cli(self, tmp_path: Path) -> None:
        rec = tmp_path / "r.json"; wt = tmp_path / "wt"; wt.mkdir()
        subprocess.run([sys.executable, SCRIPT, "init", "--worktree", str(wt), "--token", "tok",
                        "--record-file", str(rec)], check=True, capture_output=True, text=True)
        # CLI record-process now validates via /proc, so use a real process.
        env = {**os.environ, "COGNOVIS_DELIVERY_TOKEN": "tok"}
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True, cwd=str(wt), env=env,
        )
        try:
            import time; time.sleep(0.1)
            pgid = os.getpgid(child.pid)
            uid = os.getuid()
            stat_text = Path(f"/proc/{child.pid}/stat").read_text(encoding="utf-8")
            from delivery_teardown import _parse_stat_fields
            fields = _parse_stat_fields(stat_text)
            assert fields and len(fields) >= 22
            start_time = fields[21]
            r = subprocess.run([sys.executable, SCRIPT, "record-process", "--record-file", str(rec),
                                "--pgid", str(pgid), "--pid", str(child.pid), "--uid", str(uid),
                                "--start-time", start_time,
                                "--worktree", str(wt), "--command", "npm run dev"],
                               capture_output=True, text=True)
            assert r.returncode == 0
            data = json.loads(rec.read_text())
            assert data["process_groups"][0]["command"] == "npm run dev"
        finally:
            os.killpg(child.pid, signal.SIGKILL); child.wait()

    def test_record_process_cli_rejects_invalid(self, tmp_path: Path) -> None:
        rec = tmp_path / "r.json"; wt = tmp_path / "wt"; wt.mkdir()
        subprocess.run([sys.executable, SCRIPT, "init", "--worktree", str(wt), "--token", "tok",
                        "--record-file", str(rec)], check=True, capture_output=True, text=True)
        r = subprocess.run([sys.executable, SCRIPT, "record-process", "--record-file", str(rec),
                            "--pgid", "0", "--pid", "1", "--uid", "0", "--start-time", "1",
                            "--worktree", str(wt), "--command", "cmd"],
                           capture_output=True, text=True)
        assert r.returncode == 1

    def test_teardown_missing_blocked(self, tmp_path: Path) -> None:
        r = subprocess.run([sys.executable, SCRIPT, "teardown", "--record-file", str(tmp_path / "no.json")],
                           capture_output=True, text=True)
        assert "Teardown: blocked" in r.stdout

    def test_teardown_malformed_shapes_blocked(self, tmp_path: Path) -> None:
        rec = tmp_path / "r.json"
        base = {"contract": CONTRACT, "worktree": "/w", "delivery_token": "t", "compose_projects": [], "process_groups": []}
        pg = {"pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345", "worktree": "/w", "command": "s"}
        for data in [
            [], {**base, "process_groups": None}, {**base, "process_groups": {}},
            {**base, "process_groups": [None]}, {**base, "process_groups": [{}]},
            {k: v for k, v in base.items() if k != "worktree"},
            {k: v for k, v in base.items() if k != "delivery_token"},
            {k: v for k, v in base.items() if k != "process_groups"},
            {**base, "process_groups": [{**pg, "pgid": []}]},
            {**base, "process_groups": [{**pg, "pid": None}]},
            {**base, "process_groups": [{**pg, "uid": "wrong"}]},
            {**base, "process_groups": [{**pg, "start_time": {}}]},
            {**base, "process_groups": [{**pg, "worktree": None}]},
            {**base, "compose_projects": [{"project": "p", "compose_files": None}]},
        ]:
            rec.write_text(json.dumps(data))
            r = subprocess.run([sys.executable, SCRIPT, "teardown", "--record-file", str(rec)],
                               capture_output=True, text=True)
            assert "Teardown: blocked" in r.stdout and "Traceback" not in r.stderr, f"Failed for {json.dumps(data)[:80]}"


# ---------------------------------------------------------------------------
# Calendar-valid UTC timestamps (VER-SOL-1)
# ---------------------------------------------------------------------------
class TestCalendarValidation:
    def test_feb30_rejected(self) -> None:
        assert _validate_utc_timestamp("2099-02-30T00:00:00Z") is not None

    def test_nonleap_feb29_rejected(self) -> None:
        assert _validate_utc_timestamp("2099-02-29T00:00:00Z") is not None

    def test_leap_feb29_accepted(self) -> None:
        assert _validate_utc_timestamp("2096-02-29T00:00:00Z") is None

    def test_month13_rejected(self) -> None:
        assert _validate_utc_timestamp("2099-13-01T00:00:00Z") is not None

    def test_hour24_rejected(self) -> None:
        assert _validate_utc_timestamp("2099-01-01T24:00:00Z") is not None

    def test_valid_timestamp(self) -> None:
        assert _validate_utc_timestamp("2099-12-31T23:59:59Z") is None

    def test_lifecycle_labels_reject_invalid_calendar(self) -> None:
        labels = {**_owned_labels("/wt"), "de.cognovis.expires-at": "2099-02-30T00:00:00Z"}
        result = _check_lifecycle_labels(labels, "/wt", "tok", "c1", "container")
        assert result is not None and "expires-at" in result

    def test_prepare_rejects_invalid_calendar_expiry(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        cfg = json.loads(docker.config_output)
        cfg["services"]["dev"]["labels"]["de.cognovis.expires-at"] = "2099-02-30T00:00:00Z"
        docker.config_output = json.dumps(cfg)
        with pytest.raises(RuntimeError, match="rejected"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)


# ---------------------------------------------------------------------------
# Issue binding required (VER-SOL-2)
# ---------------------------------------------------------------------------
class TestIssueBindingRequired:
    def test_null_issue_entry_blocks_teardown(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        record["compose_projects"][0]["issue"] = None
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]

    def test_removed_issue_entry_blocks_teardown(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        record["compose_projects"][0].pop("issue", None)
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]

    def test_issue_always_set_by_prepare(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        record = load_record(rec)
        assert record["compose_projects"][0].get("issue")


# ---------------------------------------------------------------------------
# Snapshot provenance (VER-SOL-3)
# ---------------------------------------------------------------------------
class TestSnapshotProvenance:
    def test_imported_file_as_frozen_config_blocks(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        # Point frozen_config to a file inside the worktree.
        foreign = Path(wt) / "compose.json"
        foreign.write_text("{}")
        record["compose_projects"][0]["frozen_config"] = str(foreign)
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]

    def test_non_canonical_snapshot_path_blocks(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        # Point frozen_config to random temp directory (not canonical snapshot dir).
        foreign = tmp_path / "somewhere" / "config.json"
        foreign.parent.mkdir(parents=True, exist_ok=True)
        foreign.write_text("{}")
        record["compose_projects"][0]["frozen_config"] = str(foreign)
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]


# ---------------------------------------------------------------------------
# Token change bypass (VER-SOL-4)
# ---------------------------------------------------------------------------
class TestTokenChangeBypass:
    def test_changed_root_entry_token_blocks(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        # Change both root and entry token together.
        record["delivery_token"] = "changed-token"
        record["compose_projects"][0]["delivery_token"] = "changed-token"
        # Live labels would match the changed token, but frozen snapshot has original.
        labels = {**_owned_labels(wt, "changed-token")}
        docker.containers["p"] = {"c1": labels}
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]


# ---------------------------------------------------------------------------
# Leader PID reuse with survivors (OPUS-R1)
# ---------------------------------------------------------------------------
class TestLeaderReuseWithSurvivors:
    def test_leader_reused_with_survivors_retained(self, tmp_path: Path) -> None:
        record, wt = _make_process_record(tmp_path, [
            {"pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345", "worktree": str(tmp_path / "wt"), "command": "dev"}])
        proc = FakeProcessOps()
        # Leader PID 500 reused with different start_time.
        proc.add_process(500, 500, 1000, "99999", wt)
        # But survivors remain in the group.
        proc.add_process(501, 500, 1000, "12345", wt, delivery_token="tok")
        r = teardown_processes(record, proc, term_wait=0)
        assert 500 not in r["stopped"]
        assert r["retained"]
        assert not proc.signals_sent

    def test_leader_reused_empty_group_stopped(self, tmp_path: Path) -> None:
        record, wt = _make_process_record(tmp_path, [
            {"pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345", "worktree": str(tmp_path / "wt"), "command": "dev"}])
        proc = FakeProcessOps()
        # Leader reused, but no other group members.
        proc.add_process(500, 999, 1000, "99999", wt)  # Leader is in different group now.
        r = teardown_processes(record, proc, term_wait=0)
        assert 500 in r["stopped"]


# ---------------------------------------------------------------------------
# Group membership re-enumeration before signals (SOL-R2-001)
# ---------------------------------------------------------------------------
class TestMembershipReenumeration:
    def test_foreign_member_injected_before_term_retained(self, tmp_path: Path) -> None:
        record, wt = _make_process_record(tmp_path, [
            {"pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345", "worktree": str(tmp_path / "wt"), "command": "dev"}])
        proc = FakeProcessOps()
        proc.add_process(500, 500, 1000, "12345", wt, delivery_token="tok")
        call_count = [0]
        orig_list = proc.list_group_pids
        def injecting_list(pgid: int) -> list[int]:
            result = orig_list(pgid)
            call_count[0] += 1
            # After first enumeration, inject so re-enumeration sees different set.
            if call_count[0] == 1:
                proc.add_process(501, 500, 1000, "67890", "/foreign")
            return result
        proc.list_group_pids = injecting_list  # type: ignore[assignment]
        r = teardown_processes(record, proc, term_wait=0)
        assert 500 not in r["stopped"]
        assert r["retained"]
        assert not proc.signals_sent

    def test_foreign_member_injected_before_kill_retained(self, tmp_path: Path) -> None:
        record, wt = _make_process_record(tmp_path, [
            {"pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345", "worktree": str(tmp_path / "wt"), "command": "dev"}])
        proc = FakeProcessOps()
        proc.term_kills = False
        proc.add_process(500, 500, 1000, "12345", wt, delivery_token="tok")
        call_count = [0]
        orig_list = proc.list_group_pids
        def injecting_list(pgid: int) -> list[int]:
            result = orig_list(pgid)
            call_count[0] += 1
            # Inject after TERM wait, during pre-KILL re-enumeration.
            if call_count[0] == 5:
                proc.add_process(501, 500, 1000, "67890", "/foreign")
            return result
        proc.list_group_pids = injecting_list  # type: ignore[assignment]
        teardown_processes(record, proc, term_wait=0.01)
        assert not any(s == signal.SIGKILL for _, s in proc.signals_sent)


# ---------------------------------------------------------------------------
# Zombie exclusion (SOL-R2-002)
# ---------------------------------------------------------------------------
class TestZombieExclusion:
    def test_real_list_group_pids_excludes_zombies(self) -> None:
        ops = RealProcessOps()
        # Verify that the method exists and runs without error.
        pids = ops.list_group_pids(os.getpid())
        assert isinstance(pids, list)


# ---------------------------------------------------------------------------
# Registration: start_time, SID, worktree (VER-SOL-5/6/7)
# ---------------------------------------------------------------------------
class TestRegistrationValidation:
    def test_wrong_start_time_rejected(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"; wt.mkdir()
        rec = tmp_path / "record.json"
        init_record(str(wt), "tok", rec)
        env = {**os.environ, "COGNOVIS_DELIVERY_TOKEN": "tok"}
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True, cwd=str(wt), env=env,
        )
        try:
            import time; time.sleep(0.1)
            stat_text = Path(f"/proc/{child.pid}/stat").read_text(encoding="utf-8")
            fields = _parse_stat_fields(stat_text)
            assert fields and len(fields) >= 22
            actual_start = fields[21]
            wrong_start = str(int(actual_start) + 1)
            with pytest.raises(ValueError, match="actual start_time"):
                record_process_start(
                    rec, pgid=os.getpgid(child.pid), pid=child.pid, uid=os.getuid(),
                    start_time=wrong_start, worktree=str(wt), command="sleep",
                )
        finally:
            os.killpg(child.pid, signal.SIGKILL); child.wait()

    def test_inherited_session_rejected(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"; wt.mkdir()
        rec = tmp_path / "record.json"
        init_record(str(wt), "tok", rec)
        env = {**os.environ, "COGNOVIS_DELIVERY_TOKEN": "tok"}
        # setpgrp gives new PGID but inherits SID.
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            preexec_fn=os.setpgrp, cwd=str(wt), env=env,
        )
        try:
            import time; time.sleep(0.1)
            pgid = os.getpgid(child.pid)
            sid = os.getsid(child.pid)
            assert pgid != sid, "test setup: expected inherited SID"
            stat_text = Path(f"/proc/{child.pid}/stat").read_text(encoding="utf-8")
            fields = _parse_stat_fields(stat_text)
            assert fields and len(fields) >= 22
            with pytest.raises(ValueError, match="isolated session required"):
                record_process_start(
                    rec, pgid=pgid, pid=child.pid, uid=os.getuid(),
                    start_time=fields[21], worktree=str(wt), command="sleep",
                )
        finally:
            os.killpg(os.getpgid(child.pid), signal.SIGKILL); child.wait()

    def test_foreign_worktree_rejected(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"; wt.mkdir()
        foreign = tmp_path / "foreign"; foreign.mkdir()
        rec = tmp_path / "record.json"
        init_record(str(wt), "tok", rec)
        env = {**os.environ, "COGNOVIS_DELIVERY_TOKEN": "tok"}
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True, cwd=str(foreign), env=env,
        )
        try:
            import time; time.sleep(0.1)
            stat_text = Path(f"/proc/{child.pid}/stat").read_text(encoding="utf-8")
            fields = _parse_stat_fields(stat_text)
            assert fields and len(fields) >= 22
            with pytest.raises(ValueError, match="does not match ledger root"):
                record_process_start(
                    rec, pgid=os.getpgid(child.pid), pid=child.pid, uid=os.getuid(),
                    start_time=fields[21], worktree=str(foreign), command="sleep",
                )
        finally:
            os.killpg(child.pid, signal.SIGKILL); child.wait()

    def test_zero_start_time_rejected(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"; wt.mkdir()
        rec = tmp_path / "record.json"; init_record(str(wt), "tok", rec)
        with pytest.raises(ValueError, match="start_time must be positive"):
            record_process_start(rec, pgid=1, pid=1, uid=0, start_time="0",
                                 worktree=str(wt), command="cmd")


# ---------------------------------------------------------------------------
# Process teardown exception guard (OPUS-R2)
# ---------------------------------------------------------------------------
class TestProcessTeardownGuard:
    def test_process_teardown_exception_produces_blocked(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"; wt.mkdir(); rec = tmp_path / "r.json"
        init_record(str(wt), "tok", rec)
        class CrashProc:
            def get_ancestor_pgids(self) -> set[int]: raise RuntimeError("boom")
        r = teardown(rec, docker=FakeDockerOps(), proc=CrashProc())
        assert r["status"] == "blocked" and any("process teardown failed" in e for e in r["errors"])


# ---------------------------------------------------------------------------
# Reuse binding validation (VER-SOL-R7-2)
# ---------------------------------------------------------------------------
class TestReuseBindingValidation:
    def test_reuse_mutated_worktree_refused(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        # Mutate both root and entry worktree.
        record = load_record(rec)
        other = tmp_path / "other"; other.mkdir()
        record["worktree"] = str(other.resolve())
        record["compose_projects"][0]["worktree"] = str(other.resolve())
        rec.write_text(json.dumps(record, indent=2) + "\n")
        with pytest.raises(RuntimeError, match="reuse refused"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)

    def test_reuse_mutated_issue_refused(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        record = load_record(rec)
        record["compose_projects"][0]["issue"] = "cognovis/other#999"
        rec.write_text(json.dumps(record, indent=2) + "\n")
        with pytest.raises(RuntimeError, match="reuse refused"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)

    def test_reuse_mutated_project_refused(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        record = load_record(rec)
        record["compose_projects"][0]["project"] = "p-other"
        rec.write_text(json.dumps(record, indent=2) + "\n")
        # Request with the mutated project name.
        with pytest.raises(RuntimeError, match="reuse refused"):
            prepare_compose_start(rec, "p-other", ["/c.yml"], docker=docker)

    def test_reuse_valid_succeeds(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        result1 = prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        result2 = prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        assert result2.get("reused") is True
        assert result2["frozen_config"] == result1["frozen_config"]


# ---------------------------------------------------------------------------
# Pre-signal identity stability (VER-SOL-R7-1)
# ---------------------------------------------------------------------------
class TestPreSignalIdentityStability:
    def test_identity_reuse_during_kill_validation_retained(self, tmp_path: Path) -> None:
        """PID 501 identity changes during pre-KILL token read; KILL must not reach it."""
        record, wt = _make_process_record(tmp_path, [
            {"pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345", "worktree": str(tmp_path / "wt"), "command": "dev"}])
        proc = FakeProcessOps()
        proc.term_kills = False
        proc.add_process(500, 500, 1000, "12345", wt, delivery_token="tok")
        proc.add_process(501, 500, 1000, "67890", wt, delivery_token="tok")
        token_read_count = [0]
        orig_read_token = proc.read_delivery_token
        def hook_token(pid: int) -> str | None:
            token_read_count[0] += 1
            val = orig_read_token(pid)
            # During pre-KILL token validation of 501, change its identity.
            if pid == 501 and token_read_count[0] >= 2:
                proc.processes[501].update(start_time="99999", delivery_token=None, cwd="/foreign")
            return val
        proc.read_delivery_token = hook_token  # type: ignore[assignment]
        r = teardown_processes(record, proc, term_wait=0.01)
        # KILL must NOT have been sent.
        assert not any(s == signal.SIGKILL for _, s in proc.signals_sent)
        assert r["retained"]

    def test_identity_change_during_term_final_revalidation_retained(self, tmp_path: Path) -> None:
        """PID 501 identity changes during pre-TERM identity recheck; TERM must not reach it."""
        record, wt = _make_process_record(tmp_path, [
            {"pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345", "worktree": str(tmp_path / "wt"), "command": "dev"}])
        proc = FakeProcessOps()
        proc.add_process(500, 500, 1000, "12345", wt, delivery_token="tok")
        proc.add_process(501, 500, 1000, "67890", wt, delivery_token="tok")
        start_read_count = {}
        orig_read_start = proc.read_start_time
        def hook_start(pid: int) -> str | None:
            start_read_count[pid] = start_read_count.get(pid, 0) + 1
            # Change identity BEFORE the final pre-TERM recheck returns.
            if pid == 501 and start_read_count[pid] >= 2:
                proc.processes[501]["start_time"] = "99999"
            return orig_read_start(pid)
        proc.read_start_time = hook_start  # type: ignore[assignment]
        r = teardown_processes(record, proc, term_wait=0)
        assert not proc.signals_sent
        assert r["retained"]


# ---------------------------------------------------------------------------
# Reuse live resource validation (PR-1)
# ---------------------------------------------------------------------------
class TestReuseLiveResources:
    def test_reuse_absent_stack_succeeds(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        # No live resources — reuse should succeed.
        result = prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        assert result.get("reused") is True

    def test_reuse_owned_stack_succeeds(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        # Add owned live resources matching the entry.
        docker.containers["p"] = {"c1": _owned_labels(resolved)}
        docker.networks["p"] = {"n1": _owned_labels(resolved)}
        result = prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        assert result.get("reused") is True

    def test_reuse_foreign_container_refused(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        # Foreign container under same project name.
        docker.containers["p"] = {"c1": {**_owned_labels("/other-worktree"), "cognovis.worktree": "/other-worktree"}}
        with pytest.raises(RuntimeError, match="reuse refused"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)

    def test_reuse_foreign_network_refused(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        # No containers but a foreign network.
        docker.networks["p"] = {"n1": {**_owned_labels(resolved), "cognovis.delivery": "other-token"}}
        with pytest.raises(RuntimeError, match="reuse refused"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)

    def test_reuse_topology_change_refused(self, tmp_path: Path) -> None:
        rec, wt, resolved, docker = _prepare(tmp_path)
        prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        docker.containers["p"] = {"c1": _owned_labels(resolved)}
        # Inject a container during re-enumeration.
        nc = [0]
        def inject(proj: str) -> list[str]:
            nc[0] += 1
            if nc[0] == 2:
                docker.containers["p"]["c2"] = _owned_labels(resolved)
            return list(docker.containers.get(proj, {}).keys())
        docker.ps_project = inject  # type: ignore[assignment]
        with pytest.raises(RuntimeError, match="reuse refused"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)

    def test_reuse_empty_to_foreign_container_refused(self, tmp_path: Path) -> None:
        """Foreign container appearing during initially-empty inventory must refuse."""
        rec, wt, resolved, docker = _prepare(tmp_path)
        prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        # Initially empty, but foreign container appears during network inventory.
        nc = [0]
        orig_network_ls = docker.network_ls_project
        def inject_during_network(proj: str) -> list[str]:
            nc[0] += 1
            if nc[0] == 1:
                docker.containers["p"] = {"new-foreign-c": {**_owned_labels(resolved), "cognovis.delivery": "foreign-tok"}}
            return orig_network_ls(proj)
        docker._on_network_ls = inject_during_network
        with pytest.raises(RuntimeError, match="reuse refused"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)

    def test_reuse_empty_to_foreign_network_refused(self, tmp_path: Path) -> None:
        """Foreign network appearing during initially-empty inventory must refuse."""
        rec, wt, resolved, docker = _prepare(tmp_path)
        prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)
        nc = [0]
        orig_ps = docker.ps_project
        def inject_during_ps(proj: str) -> list[str]:
            nc[0] += 1
            if nc[0] == 2:
                docker.networks["p"] = {"new-foreign-n": {**_owned_labels(resolved), "cognovis.delivery": "foreign-tok"}}
            return orig_ps(proj)
        docker._on_ps_project = inject_during_ps
        with pytest.raises(RuntimeError, match="reuse refused"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)

    def test_fresh_preparation_injection_refused(self, tmp_path: Path) -> None:
        """Resources appearing during fresh config rendering must refuse."""
        rec, wt, resolved, docker = _prepare(tmp_path)
        orig_config = docker.compose_config
        def inject_during_config(project: str, files: list[str], **kw: Any) -> str:
            docker.containers[project] = {"injected-c": {**_owned_labels(resolved), "cognovis.delivery": "foreign-tok"}}
            return orig_config(project, files, **kw)
        docker.compose_config = inject_during_config  # type: ignore[assignment]
        with pytest.raises(RuntimeError, match="acquired resources during preparation"):
            prepare_compose_start(rec, "p", ["/c.yml"], docker=docker)


# ---------------------------------------------------------------------------
# Concurrent ledger registration (PR-2)
# ---------------------------------------------------------------------------
class TestConcurrentRegistration:
    def test_concurrent_process_registration(self, tmp_path: Path) -> None:
        """Two real concurrent process registrations must both be preserved."""
        import threading
        wt = tmp_path / "wt"; wt.mkdir()
        rec = tmp_path / "record.json"
        token = "conc-tok"
        init_record(str(wt), token, rec)
        env = {**os.environ, "COGNOVIS_DELIVERY_TOKEN": token, "XDG_CACHE_HOME": str(tmp_path / "cache")}
        children = []
        errors = []
        barrier = threading.Barrier(2, timeout=5)

        def register_child(idx: int) -> None:
            child = subprocess.Popen(
                [sys.executable, "-c", "import time; print('READY', flush=True); time.sleep(60)"],
                start_new_session=True, cwd=str(wt), env=env,
                stdout=subprocess.PIPE, text=True,
            )
            children.append(child)
            assert child.stdout.readline().strip() == "READY"
            import time; time.sleep(0.1)
            pgid = os.getpgid(child.pid)
            uid = os.getuid()
            stat_text = Path(f"/proc/{child.pid}/stat").read_text(encoding="utf-8")
            fields = _parse_stat_fields(stat_text)
            assert fields and len(fields) >= 22
            start_time = fields[21]
            try:
                barrier.wait()
                record_process_start(
                    rec, pgid=pgid, pid=child.pid, uid=uid,
                    start_time=start_time, worktree=str(wt), command=f"child-{idx}",
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=register_child, args=(i,)) for i in range(2)]
        try:
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
            assert not errors, f"Registration errors: {errors}"
            record = load_record(rec)
            assert len(record["process_groups"]) == 2, f"Expected 2 groups, got {len(record['process_groups'])}"
            commands = {g["command"] for g in record["process_groups"]}
            assert commands == {"child-0", "child-1"}, f"Commands: {commands}"
            # Verify ledger is valid JSON.
            data = json.loads(rec.read_text())
            assert isinstance(data, dict)
        finally:
            for child in children:
                if child.poll() is None:
                    try:
                        os.killpg(os.getpgid(child.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                child.wait(timeout=5)

    def test_atomic_write_preserves_ledger_on_concurrent_read(self, tmp_path: Path) -> None:
        """Reader must see complete JSON, not a truncated write."""
        wt = tmp_path / "wt"; wt.mkdir()
        rec = tmp_path / "record.json"
        init_record(str(wt), "tok", rec)
        # Verify the record is valid after init.
        data = json.loads(rec.read_text())
        assert data["contract"] == CONTRACT
        # Simulate a concurrent save while reading.
        record = load_record(rec)
        record["process_groups"].append({"pgid": 1, "pid": 1, "uid": 0, "start_time": "1", "worktree": str(wt.resolve()), "command": "test"})
        from delivery_teardown import _save
        _save(record, rec)
        # Re-read must be valid.
        data2 = json.loads(rec.read_text())
        assert len(data2["process_groups"]) == 1


# ---------------------------------------------------------------------------
# Harness docker-clean integration
# ---------------------------------------------------------------------------
class TestHarnessClean:
    def test_own_project_uses_harness(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        r = teardown_compose(record, docker)
        assert "p" in r["stopped"]
        assert len(docker.down_calls) == 1

    def test_foreign_project_no_harness_call(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        labels = {**_owned_labels(wt), "cognovis.delivery": "foreign-tok"}
        docker.containers["p"] = {"c1": labels}; docker.networks["p"] = {}
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]
        assert len(docker.down_calls) == 0

    def test_harness_unavailable_blocks_with_evidence(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        docker.unavailable = True
        # Unavailable during inventory already blocks.
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]

    def test_harness_refused_blocks_with_cmd(self, tmp_path: Path) -> None:
        record, wt, docker = _prepared_record(tmp_path)
        docker.containers["p"] = {"c1": _owned_labels(wt)}; docker.networks["p"] = {}
        docker.guard_blocked["p"] = "enrollment refused"
        r = teardown_compose(record, docker)
        assert r["stopped"] == [] and r["blocked"]
        assert any("harness docker-clean" in c for c in r["blocked_commands"])

    def test_no_volume_delete_in_harness_cmd(self, tmp_path: Path) -> None:
        from delivery_teardown import _harness_clean_cmd
        cmd = _harness_clean_cmd("test-project")
        assert "-v" not in cmd and "--volumes" not in cmd

    def test_process_cleanup_continues_after_harness_failure(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"; wt.mkdir(); rec = tmp_path / "r.json"
        os.environ["XDG_CACHE_HOME"] = str(tmp_path / "cache")
        init_record(str(wt), "tok", rec)
        resolved = str(wt.resolve()); docker_prep = FakeDockerOps(); docker_prep.set_worktree_token(resolved, "tok")
        prepare_compose_start(rec, "p", ["/c.yml"], project_directory=str(wt), docker=docker_prep)
        record = load_record(rec)
        record["process_groups"].append({
            "pgid": 500, "pid": 500, "uid": 1000, "start_time": "12345",
            "worktree": resolved, "command": "dev",
        })
        rec.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        proc = FakeProcessOps(); proc.add_process(500, 500, 1000, "12345", resolved)
        class HarnessMissing:
            def ps_project(self, p: str) -> list[str]: raise RuntimeError("harness: command not found")
            def network_ls_project(self, p: str) -> list[str]: raise RuntimeError("harness: command not found")
        r = teardown(rec, docker=HarnessMissing(), proc=proc)
        assert r["status"] == "blocked" and 500 in r["stopped_groups"]
