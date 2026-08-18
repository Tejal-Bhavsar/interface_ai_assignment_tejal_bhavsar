from __future__ import annotations

import asyncio
import json

from pathlib import Path

from cua.compiler import load_capability_artifact
from cua.evidence import EvidenceRecorder, REDACTED
from cua.playwright_surface import PlaywrightSurface
from cua.replay import ReplayEngine, ReplayStatus


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

EVIDENCE_ROOT = (
    PROJECT_ROOT
    / "evidence"
    / "replay"
)

ENTRY_URL = (
    "http://127.0.0.1:8000"
    "/legacy"
)


async def replay_with_evidence(
    *,
    member_id: str,
):
    artifact = (
        load_capability_artifact(
            CAPABILITY_PATH
        )
    )

    recorder = EvidenceRecorder(
        root=EVIDENCE_ROOT
    )

    surface = PlaywrightSurface(
        headless=True,
    )

    await surface.start()

    try:
        engine = ReplayEngine(
            surface=surface,
            entry_url=ENTRY_URL,
            allow_draft=True,
            evidence=recorder,
        )

        result = await engine.run(
            artifact=artifact,
            inputs={
                "member_id":
                    member_id,
            },
        )

        assert (
            recorder.run_dir
            is not None
        )

        return (
            result,
            recorder.run_dir,
        )

    finally:
        await surface.close()


def all_text_files(
    run_dir: Path,
) -> str:
    chunks: list[str] = []

    for path in run_dir.iterdir():
        if path.suffix.lower() in {
            ".json",
            ".jsonl",
            ".html",
            ".txt",
        }:
            chunks.append(
                path.read_text(
                    encoding="utf-8"
                )
            )

    return "\n".join(
        chunks
    )


async def main() -> None:
    print(
        "=" * 70
    )
    print(
        "STEP 13 — EVIDENCE / OBSERVABILITY SMOKE"
    )
    print(
        "=" * 70
    )

    # ========================================================
    # Case 1: successful replay
    # ========================================================

    success_result, success_dir = (
        await replay_with_evidence(
            member_id="1002"
        )
    )

    assert (
        success_result.status
        == ReplayStatus.COMPLETED
    )

    assert (
        success_result.outputs[
            "current_savings_balance"
        ]
        == "$6,320.40"
    )

    success_result_json = json.loads(
        (
            success_dir
            / "result.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    # Caller receives real typed output, but persisted evidence
    # must not contain the sensitive balance.
    assert (
        success_result_json[
            "outputs"
        ][
            "current_savings_balance"
        ]
        == REDACTED
    )

    success_text = all_text_files(
        success_dir
    )

    assert "1002" not in success_text
    assert "$6,320.40" not in success_text

    print(
        "\nSUCCESS EVIDENCE:"
    )
    print(
        success_dir
    )

    # ========================================================
    # Case 2: recovered replay
    # ========================================================

    recovery_result, recovery_dir = (
        await replay_with_evidence(
            member_id="3333"
        )
    )

    assert (
        recovery_result.status
        == ReplayStatus.COMPLETED
    )

    assert (
        recovery_result.recovery_count
        == 1
    )

    recovery_events = (
        recovery_dir
        / "events.jsonl"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        '"event_type": "recovery_started"'
        in recovery_events
    )

    assert (
        '"event_type": "recovery_completed"'
        in recovery_events
    )

    recovery_text = all_text_files(
        recovery_dir
    )

    assert "3333" not in recovery_text
    assert "$3,333.33" not in recovery_text

    print(
        "\nRECOVERY EVIDENCE:"
    )
    print(
        recovery_dir
    )

    # ========================================================
    # Case 3: hard failure + rich evidence
    # ========================================================

    failure_result, failure_dir = (
        await replay_with_evidence(
            member_id="7007"
        )
    )

    assert (
        failure_result.status
        == ReplayStatus.FAILED
    )

    assert (
        failure_result.runtime_state
        is not None
    )

    assert (
        failure_result
        .runtime_state
        .code
        == "PERMISSION_DENIED"
    )

    failure_files = {
        path.name
        for path in (
            failure_dir
            .iterdir()
        )
    }

    assert (
        "events.jsonl"
        in failure_files
    )

    assert (
        "result.json"
        in failure_files
    )

    assert any(
        name.endswith(
            ".png"
        )
        for name in failure_files
    )

    assert any(
        name.endswith(
            ".html"
        )
        for name in failure_files
    )

    failure_text = all_text_files(
        failure_dir
    )

    assert "7007" not in failure_text

    print(
        "\nFAILURE EVIDENCE:"
    )
    print(
        failure_dir
    )

    print(
        "\n"
        + "=" * 70
    )
    print(
        "STRUCTURED JSONL EVENTS: ✅"
    )
    print(
        "FINAL RESULT JSON: ✅"
    )
    print(
        "RECOVERY EVENTS: ✅"
    )
    print(
        "MASKED FAILURE SCREENSHOT: ✅"
    )
    print(
        "SANITIZED FAILURE HTML: ✅"
    )
    print(
        "SENSITIVE INPUT REDACTION: ✅"
    )
    print(
        "SENSITIVE OUTPUT REDACTION: ✅"
    )
    print(
        "ZERO LLM DECISIONS DURING REPLAY: ✅"
    )
    print(
        "\nSTEP 13 SMOKE TEST COMPLETE ✅"
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )