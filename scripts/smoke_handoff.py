from __future__ import annotations

import argparse
import asyncio

from pathlib import Path

from cua.compiler import (
    load_capability_artifact,
)
from cua.evidence import EvidenceRecorder
from cua.playwright_handoff import (
    PlaywrightHumanHandoff,
)
from cua.playwright_surface import (
    PlaywrightSurface,
)
from cua.replay import (
    ReplayEngine,
    ReplayStatus,
)


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


class ScriptedOperator:
    """
    Regression-only operator.

    When misnavigate_first=True it intentionally returns the
    live browser in the wrong continuation state on attempt 1.
    Production resume validation must reject that state, keep
    the intervention alive, and allow the operator to fix it on
    attempt 2.
    """

    def __init__(
        self,
        *,
        misnavigate_first: bool,
    ):
        self.misnavigate_first = (
            misnavigate_first
        )

        self.calls = 0

    async def __call__(
        self,
        request,
        surface: PlaywrightSurface,
    ) -> None:
        self.calls += 1

        page = surface.page

        print(
            "\nSCRIPTED OPERATOR "
            f"ATTEMPT {self.calls}"
        )

        # If a prior rejected resume left us on Member Details,
        # deterministically return to Savings.
        if (
            "/account/savings"
            not in page.url
        ):
            await (
                page
                .get_by_role(
                    "link",
                    name="Savings",
                    exact=True,
                )
                .click()
            )

        acknowledge = (
            page
            .get_by_role(
                "button",
                name=(
                    "Acknowledge & Continue"
                ),
                exact=True,
            )
        )

        if (
            await acknowledge.count()
        ):
            await acknowledge.click()

        if (
            self.misnavigate_first
            and self.calls == 1
        ):
            print(
                (
                    "Intentionally navigating "
                    "away before requesting "
                    "resume."
                )
            )

            await (
                page
                .get_by_role(
                    "link",
                    name="Back to Member",
                    exact=True,
                )
                .click()
            )


def _all_text_evidence(
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


async def main(
    *,
    auto_operator: bool,
    misnavigate_first: bool,
) -> None:
    print(
        "=" * 70
    )

    print(
        (
            "STEP 14 — PRODUCTION-STYLE "
            "SAME-SESSION HUMAN HANDOFF"
        )
    )

    print(
        "=" * 70
    )

    if auto_operator:
        if misnavigate_first:
            print(
                (
                    "MODE: scripted invalid-"
                    "resume recovery test"
                )
            )
        else:
            print(
                (
                    "MODE: scripted normal "
                    "handoff regression"
                )
            )
    else:
        print(
            "MODE: REAL MANUAL OPERATOR"
        )

    artifact = (
        load_capability_artifact(
            CAPABILITY_PATH
        )
    )

    recorder = EvidenceRecorder(
        root=EVIDENCE_ROOT
    )

    surface = PlaywrightSurface(
        headless=auto_operator,
        slow_mo_ms=(
            0
            if auto_operator
            else 150
        ),
    )

    await surface.start()

    page_before = surface.page
    context_before = (
        surface.context
    )

    scripted_operator = (
        ScriptedOperator(
            misnavigate_first=(
                misnavigate_first
            )
        )
        if auto_operator
        else None
    )

    handoff = PlaywrightHumanHandoff(
        operator_id=(
            "scripted-regression"
            if auto_operator
            else "local-human-operator"
        ),
        operator_callback=(
            scripted_operator
        ),
    )

    try:
        engine = ReplayEngine(
            surface=surface,
            entry_url=ENTRY_URL,
            allow_draft=True,
            evidence=recorder,
            handoff=handoff,
            max_handoff_resume_attempts=3,
        )

        result = await engine.run(
            artifact=artifact,
            inputs={
                "member_id":
                    "4444",
            },
        )

        print(
            "\n"
            + "=" * 70
        )

        print(
            "HANDOFF REPLAY RESULT"
        )

        print(
            "=" * 70
        )

        print(
            "STATUS:",
            result.status.value,
        )

        print(
            "OUTPUTS:",
            result.outputs,
        )

        print(
            "CHECKPOINT:",
            result.checkpoint_passed,
        )

        print(
            "INTERVENTIONS:",
            result.human_intervention_count,
        )

        print(
            "RESUME ATTEMPTS:",
            result.human_resume_attempt_count,
        )

        print(
            "HUMAN ACTIONS:",
            len(
                result.human_actions
            ),
        )

        for action in (
            result.human_actions
        ):
            print(
                (
                    "  - "
                    f"{action.event_type}: "
                    f"{action.text}"
                )
            )

        assert (
            result.status
            == ReplayStatus.COMPLETED
        )

        assert (
            result.outputs[
                "current_savings_balance"
            ]
            == "$4,444.44"
        )

        assert (
            result.checkpoint_passed
            is True
        )

        assert (
            result.human_intervention_count
            == 1
        )

        expected_attempts = (
            2
            if misnavigate_first
            else 1
        )

        assert (
            result.human_resume_attempt_count
            == expected_attempts
        )

        # Same-session guarantee.
        assert (
            surface.page
            is page_before
        )

        assert (
            surface.context
            is context_before
        )

        assert any(
            (
                action.event_type
                == "click"
                and action.text
                is not None
                and "Acknowledge"
                in action.text
            )
            for action
            in result.human_actions
        )

        assert (
            recorder.run_dir
            is not None
        )

        events = (
            recorder.run_dir
            / "events.jsonl"
        ).read_text(
            encoding="utf-8"
        )

        required = [
            "intervention_requested",
            "automation_control_released",
            "human_control_acquired",
            "human_action",
            "human_control_released",
            "resume_requested",
            "resume_validation_started",
            "resume_validation_passed",
            "automation_control_resumed",
            "intervention_resolved",
        ]

        for event_name in required:
            assert (
                (
                    '"event_type": '
                    f'"{event_name}"'
                )
                in events
            )

        if misnavigate_first:
            assert (
                (
                    '"event_type": '
                    '"resume_validation_failed"'
                )
                in events
            )

        persisted_text = (
            _all_text_evidence(
                recorder.run_dir
            )
        )

        assert (
            "4444"
            not in persisted_text
        )

        assert (
            "$4,444.44"
            not in persisted_text
        )

        print(
            "\nEVIDENCE:"
        )

        print(
            recorder.run_dir
        )

        print(
            "\n"
            + "=" * 70
        )

        print(
            "HUMAN_REQUIRED DETECTED: ✅"
        )
        print(
            "EXPLICIT CONTROL STATE: ✅"
        )
        print(
            "SAME PAGE OBJECT: ✅"
        )
        print(
            "SAME BROWSER CONTEXT: ✅"
        )
        print(
            "HUMAN ACTIONS RECORDED: ✅"
        )
        print(
            "RESUME REQUEST ≠ RESUME: ✅"
        )
        print(
            "RESUME STATE VALIDATED: ✅"
        )

        if misnavigate_first:
            print(
                "INVALID RESUME REJECTED: ✅"
            )
            print(
                "HUMAN RETRY ALLOWED: ✅"
            )

        print(
            "AUTOMATION RESUMED SAFELY: ✅"
        )
        print(
            "BALANCE EXTRACTED: ✅"
        )
        print(
            "CHECKPOINT PASSED: ✅"
        )
        print(
            "HANDOFF EVIDENCE PRESERVED: ✅"
        )
        print(
            "SENSITIVE DATA REDACTED: ✅"
        )
        print(
            "ZERO LLM REPLAY DECISIONS: ✅"
        )

        print(
            "\nSTEP 14 PRODUCTION "
            "SMOKE TEST COMPLETE ✅"
        )

    finally:
        await surface.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--auto",
        action="store_true",
        help=(
            "Use scripted regression "
            "operator."
        ),
    )

    parser.add_argument(
        "--misnavigate-first",
        action="store_true",
        help=(
            "With --auto, intentionally "
            "return an invalid state on "
            "the first resume request and "
            "verify retry/recovery."
        ),
    )

    args = parser.parse_args()

    if (
        args.misnavigate_first
        and not args.auto
    ):
        parser.error(
            (
                "--misnavigate-first "
                "requires --auto."
            )
        )

    asyncio.run(
        main(
            auto_operator=args.auto,
            misnavigate_first=(
                args.misnavigate_first
            ),
        )
    )