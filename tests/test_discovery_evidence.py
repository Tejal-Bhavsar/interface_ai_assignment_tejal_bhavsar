from __future__ import annotations

import json

from pathlib import Path

from cua.discovery_evidence import (
    DiscoveryEvidenceRecorder,
)


def _all_text(
    run_dir: Path,
) -> str:
    return "\n".join(
        path.read_text(
            encoding="utf-8"
        )
        for path
        in run_dir.iterdir()
        if (
            path.is_file()
            and path.suffix
            in {
                ".json",
                ".jsonl",
            }
        )
    )


def test_discovery_evidence_redacts_runtime_values(
    tmp_path: Path,
):
    recorder = (
        DiscoveryEvidenceRecorder(
            root=tmp_path,
            sensitive_inputs={
                "member_id":
                    "1001",
            },
        )
    )

    recorder.start_run(
        run_id="disc_test",
        goal=(
            "Look up member 1001 "
            "and return savings."
        ),
        entry_url=(
            "http://127.0.0.1:8000/"
            "legacy"
        ),
        provider="gemini",
        model="gemini-test",
    )

    recorder.record_observation(
        step_index=1,
        observation={
            "url":
                (
                    "http://127.0.0.1:8000/"
                    "legacy/member/1001"
                ),
            "title":
                "Member",
            "visible_text":
                (
                    "Alex Rivera "
                    "$8,421.22"
                ),
            "aria_snapshot":
                "Member 1001 $8,421.22",
            "controls": [
                {
                    "tag":
                        "input",
                    "role":
                        "textbox",
                    "name":
                        "Member ID",
                    "value":
                        "1001",
                }
            ],
        },
    )

    recorder.record_llm_decision(
        step_index=1,
        action={
            "action":
                "fill",
            "value":
                "1001",
            "reason":
                "Enter member 1001.",
        },
    )

    recorder.record_execution(
        step_index=2,
        action_type="extract",
        url_after=(
            "http://127.0.0.1:8000/"
            "legacy/member/1001/"
            "account/savings"
        ),
        output_name=(
            "current_savings_balance"
        ),
        output_value="$8,421.22",
    )

    recorder.save_result(
        {
            "run_id":
                "disc_test",
            "status":
                "completed",
            "outputs": {
                (
                    "current_savings_balance"
                ):
                    "$8,421.22",
            },
            "steps": [],
        }
    )

    run_dir = (
        tmp_path
        / "disc_test"
    )

    persisted = (
        _all_text(
            run_dir
        )
    )

    assert "1001" not in persisted
    assert "$8,421.22" not in persisted
    assert "llm_decision" in persisted
    assert "observation" in persisted


def test_raw_visible_text_is_not_persisted(
    tmp_path: Path,
):
    recorder = (
        DiscoveryEvidenceRecorder(
            root=tmp_path
        )
    )

    recorder.start_run(
        run_id="disc_test_2",
        goal="test",
        entry_url=(
            "http://127.0.0.1:8000/"
            "legacy"
        ),
        provider="gemini",
        model="gemini-test",
    )

    secret_visible_text = (
        "RAW-VISIBLE-TEXT-MUST-NOT-"
        "BE-PERSISTED"
    )

    recorder.record_observation(
        step_index=1,
        observation={
            "url":
                (
                    "http://127.0.0.1:8000/"
                    "legacy"
                ),
            "title":
                "Search",
            "visible_text":
                secret_visible_text,
            "aria_snapshot":
                secret_visible_text,
            "controls":
                [],
        },
    )

    persisted = _all_text(
        tmp_path
        / "disc_test_2"
    )

    assert (
        secret_visible_text
        not in persisted
    )

    events = [
        json.loads(
            line
        )
        for line
        in (
            tmp_path
            / "disc_test_2"
            / "events.jsonl"
        )
        .read_text(
            encoding="utf-8"
        )
        .splitlines()
        if line.strip()
    ]

    observation = next(
        event
        for event
        in events
        if (
            event[
                "event_type"
            ]
            == "observation"
        )
    )

    assert (
        observation[
            "data"
        ][
            "observation_sha256"
        ]
    )

    assert (
        observation[
            "data"
        ][
            "visible_text_chars"
        ]
        == len(
            secret_visible_text
        )
    )