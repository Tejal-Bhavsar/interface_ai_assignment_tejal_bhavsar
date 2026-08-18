from __future__ import annotations

import json

from pathlib import Path

import pytest

from cua.evidence_bundle import (
    REDACTED,
    audit_replay_redaction,
    build_final_bundle,
    parse_replay_run,
    select_evidence,
)


def _write_json(
    path: Path,
    payload,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _artifact_payload():
    return {
        "schema_version": "1.0",
        "identity": {
            "id": (
                "lookup_savings_balance"
            ),
            "version": "1.0.0",
        },
        "inputs": {
            "member_id": {
                "type": "string",
                "sensitive": True,
            }
        },
        "outputs": {
            "current_savings_balance": {
                "type": "string",
                "sensitive": True,
            }
        },
        "discovery": {
            "run_id":
                "disc_real_123",
            "provider":
                "gemini",
            "model":
                "gemini-test",
        },
    }


def _write_run(
    root: Path,
    name: str,
    *,
    status: str,
    checkpoint: bool = False,
    runtime_code: str | None = None,
    recovery_count: int = 0,
    events: list[dict] | None = None,
    rich_failure: bool = False,
) -> Path:
    run_dir = (
        root
        / name
    )

    run_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    artifact = (
        _artifact_payload()
    )

    _write_json(
        run_dir
        / "artifact.json",
        artifact,
    )

    _write_json(
        run_dir
        / "metadata.json",
        {
            "run_id": name,
            "inputs": {
                "member_id":
                    REDACTED,
            },
        },
    )

    result = {
        "run_id": name,
        "status": status,
        "checkpoint_passed":
            checkpoint,
        "recovery_count":
            recovery_count,
        "outputs": {
            "current_savings_balance":
                REDACTED,
        },
    }

    if runtime_code:
        result[
            "runtime_state"
        ] = {
            "code":
                runtime_code,
        }

    _write_json(
        run_dir
        / "result.json",
        result,
    )

    with (
        run_dir
        / "events.jsonl"
    ).open(
        "w",
        encoding="utf-8",
    ) as handle:
        for event in (
            events
            or []
        ):
            handle.write(
                json.dumps(
                    event
                )
                + "\n"
            )

    if rich_failure:
        (
            run_dir
            / "failure_step.png"
        ).write_bytes(
            b"fake-png"
        )

        (
            run_dir
            / "failure_step.html"
        ).write_text(
            "<html>sanitized</html>",
            encoding="utf-8",
        )

    return run_dir


def test_parse_replay_run_detects_manual_handoff(
    tmp_path: Path,
):
    run_dir = _write_run(
        tmp_path,
        "replay_manual",
        status="completed",
        checkpoint=True,
        events=[
            {
                "event_type":
                    "human_control_acquired",
                "data": {},
            },
            {
                "event_type":
                    "human_action",
                "data": {},
            },
            {
                "event_type":
                    "human_control_released",
                "data": {
                    "operator_id":
                        "local-human-operator",
                },
            },
            {
                "event_type":
                    "automation_control_resumed",
                "data": {
                    "operator_id":
                        "local-human-operator",
                },
            },
            {
                "event_type":
                    "resume_validation_passed",
                "data": {},
            },
        ],
    )

    run = parse_replay_run(
        run_dir
    )

    assert run is not None
    assert run.is_handoff
    assert run.is_manual_handoff


def test_scripted_handoff_is_not_manual(
    tmp_path: Path,
):
    run_dir = _write_run(
        tmp_path,
        "replay_scripted",
        status="completed",
        checkpoint=True,
        events=[
            {
                "event_type":
                    "human_control_acquired",
                "data": {},
            },
            {
                "event_type":
                    "human_action",
                "data": {},
            },
            {
                "event_type":
                    "human_control_released",
                "data": {
                    "operator_id":
                        "scripted-regression",
                },
            },
            {
                "event_type":
                    "automation_control_resumed",
                "data": {
                    "operator_id":
                        "scripted-regression",
                },
            },
        ],
    )

    run = parse_replay_run(
        run_dir
    )

    assert run is not None
    assert run.is_handoff
    assert not run.is_manual_handoff


def test_redaction_audit_detects_sensitive_output_leak(
    tmp_path: Path,
):
    run_dir = _write_run(
        tmp_path,
        "replay_bad",
        status="completed",
        checkpoint=True,
    )

    result = json.loads(
        (
            run_dir
            / "result.json"
        )
        .read_text(
            encoding="utf-8"
        )
    )

    result[
        "outputs"
    ][
        "current_savings_balance"
    ] = "$123.45"

    _write_json(
        run_dir
        / "result.json",
        result,
    )

    run = parse_replay_run(
        run_dir
    )

    assert run is not None

    issues = (
        audit_replay_redaction(
            run
        )
    )

    assert issues
    assert (
        "Sensitive output"
        in issues[0]
    )


def test_full_bundle_selects_required_proof(
    tmp_path: Path,
):
    project = tmp_path

    artifact_path = (
        project
        / "capabilities"
        / "lookup_savings_balance.v1.json"
    )

    _write_json(
        artifact_path,
        _artifact_payload(),
    )

    discovery_dir = (
        project
        / "evidence"
        / "discovery"
        / "disc_real_123"
    )

    discovery_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    _write_json(
        discovery_dir
        / "run.json",
        {
            "run_id":
                "disc_real_123",
            "status":
                "completed",
            "provider":
                "gemini",
            "model":
                "gemini-test",
        },
    )

    replay_root = (
        project
        / "evidence"
        / "replay"
    )

    _write_run(
        replay_root,
        "replay_success",
        status="completed",
        checkpoint=True,
    )

    _write_run(
        replay_root,
        "replay_business",
        status="business_outcome",
        runtime_code=(
            "MEMBER_NOT_FOUND"
        ),
    )

    _write_run(
        replay_root,
        "replay_recovery",
        status="completed",
        checkpoint=True,
        recovery_count=1,
        events=[
            {
                "event_type":
                    "recovery_started",
                "data": {},
            },
            {
                "event_type":
                    "recovery_completed",
                "data": {},
            },
        ],
    )

    _write_run(
        replay_root,
        "replay_failure",
        status="failed",
        runtime_code=(
            "PERMISSION_DENIED"
        ),
        rich_failure=True,
    )

    _write_run(
        replay_root,
        "replay_handoff",
        status="completed",
        checkpoint=True,
        events=[
            {
                "event_type":
                    "human_control_acquired",
                "data": {},
            },
            {
                "event_type":
                    "human_action",
                "data": {},
            },
            {
                "event_type":
                    "human_control_released",
                "data": {
                    "operator_id":
                        "local-human-operator",
                },
            },
            {
                "event_type":
                    "automation_control_resumed",
                "data": {
                    "operator_id":
                        "local-human-operator",
                },
            },
            {
                "event_type":
                    "resume_validation_passed",
                "data": {},
            },
            {
                "event_type":
                    "intervention_resolved",
                "data": {},
            },
        ],
    )

    policy_root = (
        project
        / "evidence"
        / "policy"
    )

    _write_run(
        policy_root,
        "replay_policy",
        status="human_required",
        runtime_code=(
            "POLICY_HUMAN_REQUIRED"
        ),
        events=[
            {
                "event_type":
                    "policy_human_required",
                "data": {},
            }
        ],
        rich_failure=True,
    )

    selection = (
        select_evidence(
            project_root=(
                project
            )
        )
    )

    assert not (
        selection.missing
    )

    assert (
        selection.discovery
        is not None
    )

    assert (
        selection.discovery.genuine
    )

    assert (
        selection.human_handoff
        is not None
    )

    assert (
        selection.human_handoff
        .is_manual_handoff
    )

    final_dir = (
        build_final_bundle(
            project_root=(
                project
            ),
            strict=True,
        )
    )

    assert (
        final_dir
        / "manifest.json"
    ).exists()

    assert (
        final_dir
        / "checksums.sha256"
    ).exists()

    assert (
        final_dir
        / "01_discovery"
    ).exists()

    assert (
        final_dir
        / "07_human_handoff"
    ).exists()

    assert (
        final_dir
        / "08_policy"
    ).exists()


def test_final_bundle_is_non_destructive(
    tmp_path: Path,
):
    project = tmp_path

    artifact_path = (
        project
        / "capabilities"
        / "lookup_savings_balance.v1.json"
    )

    _write_json(
        artifact_path,
        _artifact_payload(),
    )

    discovery = (
        project
        / "evidence"
        / "discovery"
        / "disc_real_123"
    )

    discovery.mkdir(
        parents=True,
        exist_ok=True,
    )

    _write_json(
        discovery
        / "run.json",
        {
            "run_id":
                "disc_real_123",
            "status":
                "completed",
            "provider":
                "gemini",
        },
    )

    replay_root = (
        project
        / "evidence"
        / "replay"
    )

    success = _write_run(
        replay_root,
        "replay_success",
        status="completed",
        checkpoint=True,
    )

    _write_run(
        replay_root,
        "replay_business",
        status="business_outcome",
        runtime_code=(
            "MEMBER_NOT_FOUND"
        ),
    )

    _write_run(
        replay_root,
        "replay_recovery",
        status="completed",
        checkpoint=True,
        recovery_count=1,
    )

    _write_run(
        replay_root,
        "replay_failure",
        status="failed",
        runtime_code=(
            "APPLICATION_ERROR"
        ),
        rich_failure=True,
    )

    _write_run(
        replay_root,
        "replay_handoff",
        status="completed",
        checkpoint=True,
        events=[
            {
                "event_type":
                    "human_control_acquired",
                "data": {},
            },
            {
                "event_type":
                    "human_action",
                "data": {},
            },
            {
                "event_type":
                    "human_control_released",
                "data": {
                    "operator_id":
                        "local-human-operator",
                },
            },
            {
                "event_type":
                    "automation_control_resumed",
                "data": {
                    "operator_id":
                        "local-human-operator",
                },
            },
        ],
    )

    _write_run(
        (
            project
            / "evidence"
            / "policy"
        ),
        "replay_policy",
        status="failed",
        runtime_code=(
            "POLICY_BLOCKED_PHRASE"
        ),
        events=[
            {
                "event_type":
                    "policy_blocked",
                "data": {},
            }
        ],
    )

    original_result = (
        success
        / "result.json"
    ).read_text(
        encoding="utf-8"
    )

    build_final_bundle(
        project_root=project,
        strict=True,
    )

    assert (
        success
        / "result.json"
    ).read_text(
        encoding="utf-8"
    ) == original_result