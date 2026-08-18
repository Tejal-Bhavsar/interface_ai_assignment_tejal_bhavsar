from __future__ import annotations

import asyncio

from pathlib import Path

from cua.compiler import (
    load_capability_artifact,
    verify_artifact_integrity,
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


async def main() -> None:

    print(
        "=" * 70
    )

    print(
        "STEP 11 — DETERMINISTIC CAPABILITY REPLAY"
    )

    print(
        "=" * 70
    )

    artifact = (
        load_capability_artifact(
            CAPABILITY_PATH
        )
    )

    print(
        f"CAPABILITY: "
        f"{artifact.identity.id}"
    )

    print(
        f"VERSION: "
        f"{artifact.identity.version}"
    )

    print(
        f"APPROVAL: "
        f"{artifact.identity.approval_state.value}"
    )

    print(
        f"INTEGRITY VALID: "
        f"{verify_artifact_integrity(artifact)}"
    )

    print(
        "\nREPLAY INPUT:"
    )

    print(
        "member_id = 1002"
    )

    surface = (
        PlaywrightSurface(
            headless=False,
            slow_mo_ms=250,
        )
    )

    await surface.start()

    try:

        engine = ReplayEngine(
            surface=surface,

            # Development/demo only.
            # Production replay rejects draft artifacts.
            entry_url=(
                "http://127.0.0.1:8000"
                "/legacy"
            ),
            allow_draft=True,
        )

        result = (
            await engine.run(
                artifact=artifact,

                inputs={
                    "member_id":
                        "1002",
                },
            )
        )

        print(
            "\n"
            + "=" * 70
        )

        print(
            "REPLAY RESULT"
        )

        print(
            "=" * 70
        )

        print(
            f"STATUS: "
            f"{result.status.value}"
        )

        print(
            "\nSTEPS:"
        )

        for (
            index,
            step,
        ) in enumerate(
            result.steps,
            start=1,
        ):

            print(
                f"{index}. "
                f"{step.action.value}"
            )

            print(
                f"   step: "
                f"{step.step_id}"
            )

            print(
                f"   status: "
                f"{step.status}"
            )

            print(
                f"   url: "
                f"{step.url}"
            )

        print(
            "\nOUTPUTS:"
        )

        for (
            name,
            value,
        ) in result.outputs.items():

            print(
                f"{name}={value}"
            )

        print(
            "\nCHECKPOINT PASSED:",
            result.checkpoint_passed,
        )

        # ----------------------------------------------------
        # Strong smoke assertions
        # ----------------------------------------------------

        assert (
            result.status
            == ReplayStatus.COMPLETED
        )

        assert (
            result.outputs[
                "current_savings_balance"
            ]
            == "$6,320.40"
        )

        assert (
            result.checkpoint_passed
            is True
        )

        assert len(
            result.steps
        ) == 4

        print(
            "\n"
            + "=" * 70
        )

        print(
            "ZERO-LLM REPLAY VERIFIED ✅"
        )

        print(
            "Expected new member "
            "balance returned: ✅"
        )

        print(
            "Checkpoint passed: ✅"
        )

        print(
            "Artifact integrity verified: ✅"
        )

        print(
            "\nSTEP 11 SMOKE TEST COMPLETE ✅"
        )

    finally:

        await surface.close()


if __name__ == "__main__":

    asyncio.run(
        main()
    )