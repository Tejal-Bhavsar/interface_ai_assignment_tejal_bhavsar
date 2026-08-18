from __future__ import annotations

import asyncio

from pathlib import Path

from cua.compiler import (
    load_capability_artifact,
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

ENTRY_URL = (
    "http://127.0.0.1:8000"
    "/legacy"
)


CASES = [
    {
        "member_id": "9999",
        "status":
            ReplayStatus
            .BUSINESS_OUTCOME,
        "code":
            "MEMBER_NOT_FOUND",
        "balance": None,
        "recoveries": 0,
    },
    {
        "member_id": "3333",
        "status":
            ReplayStatus
            .COMPLETED,
        "code": None,
        "balance":
            "$3,333.33",
        "recoveries": 1,
    },
    {
        "member_id": "5555",
        "status":
            ReplayStatus
            .COMPLETED,
        "code": None,
        "balance":
            "$5,555.55",
        "recoveries": 1,
    },
    {
        "member_id": "7007",
        "status":
            ReplayStatus
            .FAILED,
        "code":
            "PERMISSION_DENIED",
        "balance": None,
        "recoveries": 0,
    },
    {
        "member_id": "2222",
        "status":
            ReplayStatus
            .FAILED,
        "code":
            "APPLICATION_ERROR",
        "balance": None,
        "recoveries": 0,
    },
]


async def run_case(
    artifact,
    case,
):

    # Fresh browser context for every test case.
    #
    # This matters because 3333 and 5555 use cookies to
    # remember that their one-time failure was already seen.
    surface = PlaywrightSurface(
        headless=True,
    )

    await surface.start()

    try:

        engine = ReplayEngine(
            surface=surface,
            entry_url=ENTRY_URL,
            allow_draft=True,
        )

        result = await engine.run(
            artifact=artifact,
            inputs={
                "member_id":
                    case[
                        "member_id"
                    ],
            },
        )

        print(
            "\n"
            + "-" * 70
        )

        print(
            "MEMBER:",
            case["member_id"],
        )

        print(
            "STATUS:",
            result.status.value,
        )

        print(
            "RUNTIME CODE:",
            (
                result
                .runtime_state
                .code
                if result.runtime_state
                else None
            ),
        )

        print(
            "RECOVERIES:",
            result.recovery_count,
        )

        print(
            "OUTPUTS:",
            result.outputs,
        )

        assert (
            result.status
            == case["status"]
        )

        assert (
            result.recovery_count
            == case["recoveries"]
        )

        expected_code = (
            case["code"]
        )

        if expected_code:

            assert (
                result.runtime_state
                is not None
            )

            assert (
                result.runtime_state.code
                == expected_code
            )

        expected_balance = (
            case["balance"]
        )

        if expected_balance:

            assert (
                result.outputs[
                    "current_savings_balance"
                ]
                == expected_balance
            )

        return result

    finally:

        await surface.close()


async def main():

    print(
        "=" * 70
    )

    print(
        "STEP 12C — RUNTIME OUTCOME / RECOVERY SMOKE"
    )

    print(
        "=" * 70
    )

    artifact = (
        load_capability_artifact(
            CAPABILITY_PATH
        )
    )

    for case in CASES:

        await run_case(
            artifact,
            case,
        )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "BUSINESS OUTCOME: ✅"
    )

    print(
        "SESSION RECOVERY: ✅"
    )

    print(
        "TRANSIENT RECOVERY: ✅"
    )

    print(
        "PERMISSION FAILURE: ✅"
    )

    print(
        "APPLICATION FAILURE: ✅"
    )

    print(
        "ZERO LLM DECISIONS: ✅"
    )

    print(
        "\nSTEP 12C SMOKE TEST COMPLETE ✅"
    )


if __name__ == "__main__":

    asyncio.run(
        main()
    )