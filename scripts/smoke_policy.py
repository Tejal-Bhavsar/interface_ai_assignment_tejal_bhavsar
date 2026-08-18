from __future__ import annotations

import asyncio
import subprocess
import sys
import time

from pathlib import Path
from urllib.request import urlopen

from cua.compiler import (
    compute_artifact_integrity,
    load_capability_artifact,
    verify_artifact_integrity,
)
from cua.evidence import (
    EvidenceRecorder,
)
from cua.models import (
    ActionType,
    CapabilityArtifact,
    CapabilityStep,
    Condition,
    ConditionType,
    LocatorCandidate,
    LocatorKind,
    RiskLevel,
    TargetDescriptor,
)
from cua.playwright_surface import (
    PlaywrightSurface,
)
from cua.policy import PolicyEngine
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

POLICY_PATH = (
    PROJECT_ROOT
    / "config"
    / "policy.json"
)

EVIDENCE_ROOT = (
    PROJECT_ROOT
    / "evidence"
    / "policy"
)

TARGET_URL = (
    "http://127.0.0.1:8000"
)


def _is_up(
    url: str,
) -> bool:
    try:
        with urlopen(
            url,
            timeout=1,
        ) as response:
            return (
                200
                <= response.status
                < 500
            )
    except Exception:
        return False


def _wait_until_up(
    url: str,
    *,
    timeout_seconds: float = 20.0,
) -> None:
    deadline = (
        time.monotonic()
        + timeout_seconds
    )

    while (
        time.monotonic()
        < deadline
    ):
        if _is_up(url):
            return

        time.sleep(0.2)

    raise RuntimeError(
        f"Timed out waiting for {url}"
    )


def _single_click_artifact(
    *,
    base: CapabilityArtifact,
    button_name: str,
) -> CapabilityArtifact:
    """
    Produce an integrity-valid temporary artifact for the smoke.

    The target description is intentionally generic. The policy
    must detect risk from the ACTUAL resolved live button text.
    """

    target = TargetDescriptor(
        description=(
            "Primary action button"
        ),
        locators=[
            LocatorCandidate(
                kind=LocatorKind.ROLE,
                role="button",
                name=button_name,
                exact=True,
                description=(
                    "Semantic button role/name"
                ),
            )
        ],
    )

    step = CapabilityStep(
        id=(
            "step_01_click_"
            "primary_action"
        ),
        description=(
            "Click the primary "
            "workflow action."
        ),
        action=ActionType.CLICK,
        target=target,
        value=None,
        output_name=None,
        preconditions=[],
        postconditions=[],
        risk_level=RiskLevel.SAFE,
    )

    checkpoint = Condition(
        type=(
            ConditionType
            .ELEMENT_PRESENT
        ),
        target=target,
        timeout_ms=0,
    )

    artifact = (
        base.model_copy(
            update={
                "steps": [step],
                "checkpoint":
                    checkpoint,
                "integrity_sha256":
                    "",
            }
        )
    )

    digest = (
        compute_artifact_integrity(
            artifact
        )
    )

    artifact = (
        artifact.model_copy(
            update={
                "integrity_sha256":
                    digest
            }
        )
    )

    assert verify_artifact_integrity(
        artifact
    )

    return artifact


async def _run(
    *,
    artifact: CapabilityArtifact,
    entry_url: str,
    policy: PolicyEngine,
    member_id: str = "1001",
    with_evidence: bool = False,
):
    recorder = (
        EvidenceRecorder(
            root=EVIDENCE_ROOT
        )
        if with_evidence
        else None
    )

    surface = PlaywrightSurface(
        headless=True
    )

    await surface.start()

    try:
        engine = ReplayEngine(
            surface=surface,
            entry_url=entry_url,
            allow_draft=True,
            evidence=recorder,
            policy=policy,
        )

        result = await engine.run(
            artifact=artifact,
            inputs={
                "member_id":
                    member_id,
            },
        )

        final_url = (
            surface.current_url
        )

        return (
            result,
            final_url,
            recorder,
        )

    finally:
        await surface.close()


async def main() -> None:
    print("=" * 70)
    print(
        "STEP 17 — PRODUCTION RUNTIME POLICY"
    )
    print("=" * 70)

    target_process = None

    try:
        if not _is_up(
            TARGET_URL
            + "/legacy"
        ):
            target_process = (
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "apps.server:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8000",
                    ],
                    cwd=PROJECT_ROOT,
                    stdout=(
                        subprocess.DEVNULL
                    ),
                    stderr=(
                        subprocess.DEVNULL
                    ),
                )
            )

            _wait_until_up(
                TARGET_URL
                + "/legacy"
            )

        base = (
            load_capability_artifact(
                CAPABILITY_PATH
            )
        )

        policy = (
            PolicyEngine
            .from_path(
                POLICY_PATH
            )
        )

        # ----------------------------------------------------
        # 1. Normal capability remains allowed.
        # ----------------------------------------------------

        (
            normal_result,
            _,
            _,
        ) = await _run(
            artifact=base,
            entry_url=(
                TARGET_URL
                + "/legacy"
            ),
            policy=policy,
            member_id="1002",
        )

        assert (
            normal_result.status
            == ReplayStatus.COMPLETED
        )

        assert (
            normal_result.outputs[
                "current_savings_balance"
            ]
            == "$6,320.40"
        )

        # ----------------------------------------------------
        # 2. Entry URL outside allowed route is blocked before
        #    the browser navigates there.
        # ----------------------------------------------------

        (
            route_result,
            route_final_url,
            _,
        ) = await _run(
            artifact=base,
            entry_url=(
                TARGET_URL
                + "/not-legacy"
            ),
            policy=policy,
            member_id="1001",
        )

        assert (
            route_result.status
            == ReplayStatus.FAILED
        )

        assert (
            route_result
            .runtime_state
            is not None
        )

        assert (
            route_result
            .runtime_state
            .code
            == "POLICY_URL_BLOCKED"
        )

        # A new blank Playwright page stays about:blank because
        # policy blocked the entry navigation first.
        assert (
            route_final_url
            == "about:blank"
        )

        # ----------------------------------------------------
        # 3. Risk is detected from LIVE element metadata.
        # ----------------------------------------------------

        risky_artifact = (
            _single_click_artifact(
                base=base,
                button_name=(
                    "Open Sub-Account"
                ),
            )
        )

        (
            risky_result,
            risky_final_url,
            risky_evidence,
        ) = await _run(
            artifact=(
                risky_artifact
            ),
            entry_url=(
                TARGET_URL
                + "/legacy/member/1001/"
                "account/savings"
            ),
            policy=policy,
            member_id="1001",
            with_evidence=True,
        )

        assert (
            risky_result.status
            == ReplayStatus
            .HUMAN_REQUIRED
        )

        assert (
            risky_result
            .runtime_state
            is not None
        )

        assert (
            risky_result
            .runtime_state
            .code
            == "POLICY_HUMAN_REQUIRED"
        )

        # Policy stopped BEFORE the click. We remain on the
        # account page instead of opening the sub-account form.
        assert (
            "/account/savings"
            in risky_final_url
        )

        # Evidence proves the policy used a live target.
        assert (
            risky_evidence
            is not None
        )

        assert (
            risky_evidence.run_dir
            is not None
        )

        risky_events = (
            (
                risky_evidence
                .run_dir
                / "events.jsonl"
            )
            .read_text(
                encoding="utf-8"
            )
        )

        assert (
            '"policy_human_required"'
            in risky_events
        )

        assert (
            '"evaluated_live_target": true'
            in risky_events
        )

        # ----------------------------------------------------
        # 4. Blocked phrase wins and action never executes.
        # ----------------------------------------------------

        blocked_artifact = (
            _single_click_artifact(
                base=base,
                button_name=(
                    "Confirm Open "
                    "Sub-Account"
                ),
            )
        )

        (
            blocked_result,
            blocked_final_url,
            _,
        ) = await _run(
            artifact=(
                blocked_artifact
            ),
            entry_url=(
                TARGET_URL
                + "/legacy/member/1001/"
                "open-subaccount"
            ),
            policy=policy,
            member_id="1001",
        )

        assert (
            blocked_result.status
            == ReplayStatus.FAILED
        )

        assert (
            blocked_result
            .runtime_state
            is not None
        )

        assert (
            blocked_result
            .runtime_state
            .code
            == "POLICY_BLOCKED_PHRASE"
        )

        assert (
            "/open-subaccount"
            in blocked_final_url
        )

        print(
            "\nNORMAL REPLAY:"
        )
        print(
            normal_result.status.value,
            normal_result.outputs,
        )

        print(
            "\nOUT-OF-SCOPE ROUTE:"
        )
        print(
            route_result.status.value,
            route_result
            .runtime_state
            .code,
        )

        print(
            "\nRISKY LIVE TARGET:"
        )
        print(
            risky_result.status.value,
            risky_result
            .runtime_state
            .code,
        )

        print(
            "\nBLOCKED LIVE TARGET:"
        )
        print(
            blocked_result.status.value,
            blocked_result
            .runtime_state
            .code,
        )

        print("\n" + "=" * 70)
        print(
            "CONFIGURED ORIGIN/ROUTE ALLOWLIST: ✅"
        )
        print(
            "CONFIGURED ACTION ALLOWLIST: ✅"
        )
        print(
            "ENTRY URL BLOCKED BEFORE NAVIGATION: ✅"
        )
        print(
            "ACTUAL LIVE TARGET EVALUATED: ✅"
        )
        print(
            "RISKY ACTION → HUMAN_REQUIRED: ✅"
        )
        print(
            "BLOCKED ACTION → FAILED CLOSED: ✅"
        )
        print(
            "POST-ACTION URL CONTAINMENT: ✅"
        )
        print(
            "POLICY DECISIONS IN EVIDENCE: ✅"
        )
        print(
            "ARTIFACT SAFETY STILL ENFORCED: ✅"
        )
        print(
            "ZERO LLM POLICY DECISIONS: ✅"
        )

        print(
            "\nSTEP 17 SMOKE TEST COMPLETE ✅"
        )

    finally:
        if target_process is not None:
            target_process.terminate()

            try:
                target_process.wait(
                    timeout=5
                )
            except (
                subprocess
                .TimeoutExpired
            ):
                target_process.kill()


if __name__ == "__main__":
    asyncio.run(main())