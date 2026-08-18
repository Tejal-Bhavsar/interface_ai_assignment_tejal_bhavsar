from __future__ import annotations

import json

from pathlib import Path

from cua.compiler import load_capability_artifact
from cua.evidence import EvidenceRecorder, REDACTED


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

CAPABILITY_PATH = (
    PROJECT_ROOT
    / "capabilities"
    / "lookup_savings_balance.v1.json"
)


def test_evidence_redacts_sensitive_input_and_url(
    tmp_path,
):
    artifact = (
        load_capability_artifact(
            CAPABILITY_PATH
        )
    )

    recorder = EvidenceRecorder(
        root=tmp_path
    )

    recorder.start_run(
        artifact=artifact,
        inputs={
            "member_id":
                "1002",
        },
        entry_url=(
            "http://127.0.0.1:8000"
            "/legacy"
        ),
    )

    recorder.record_event(
        event_type="test",
        url=(
            "http://127.0.0.1:8000"
            "/legacy/member/1002"
        ),
        message=(
            "Opened member 1002"
        ),
    )

    assert recorder.run_dir is not None

    metadata = (
        recorder.run_dir
        / "metadata.json"
    ).read_text(
        encoding="utf-8"
    )

    events = (
        recorder.run_dir
        / "events.jsonl"
    ).read_text(
        encoding="utf-8"
    )

    assert "1002" not in metadata
    assert "1002" not in events
    assert REDACTED in metadata
    assert REDACTED in events


def test_evidence_redacts_sensitive_output(
    tmp_path,
):
    artifact = (
        load_capability_artifact(
            CAPABILITY_PATH
        )
    )

    recorder = EvidenceRecorder(
        root=tmp_path
    )

    recorder.start_run(
        artifact=artifact,
        inputs={
            "member_id":
                "1002",
        },
        entry_url=(
            "http://127.0.0.1:8000"
            "/legacy"
        ),
    )

    recorder.remember_sensitive_outputs(
        artifact=artifact,
        outputs={
            "current_savings_balance":
                "$6,320.40",
        },
    )

    recorder.save_result(
        {
            "status":
                "completed",

            "outputs": {
                "current_savings_balance":
                    "$6,320.40",
            },

            "steps": [
                {
                    "url":
                        (
                            "http://127.0.0.1:8000"
                            "/legacy/member/1002"
                        )
                }
            ],

            "checkpoint_passed":
                True,

            "recovery_count":
                0,
        }
    )

    assert recorder.run_dir is not None

    raw = (
        recorder.run_dir
        / "result.json"
    ).read_text(
        encoding="utf-8"
    )

    assert "$6,320.40" not in raw
    assert "1002" not in raw

    payload = json.loads(
        raw
    )

    assert (
        payload[
            "outputs"
        ][
            "current_savings_balance"
        ]
        == REDACTED
    )


def test_evidence_writes_artifact_and_metadata(
    tmp_path,
):
    artifact = (
        load_capability_artifact(
            CAPABILITY_PATH
        )
    )

    recorder = EvidenceRecorder(
        root=tmp_path
    )

    recorder.start_run(
        artifact=artifact,
        inputs={
            "member_id":
                "1002",
        },
        entry_url=(
            "http://127.0.0.1:8000"
            "/legacy"
        ),
    )

    assert recorder.run_dir is not None

    assert (
        recorder.run_dir
        / "artifact.json"
    ).exists()

    assert (
        recorder.run_dir
        / "metadata.json"
    ).exists()

    assert (
        recorder.run_dir
        / "events.jsonl"
    ).exists()