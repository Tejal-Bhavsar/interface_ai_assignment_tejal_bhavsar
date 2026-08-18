from __future__ import annotations

import asyncio

from pathlib import Path

from cua.discovery import (
    DiscoveryEngine,
)

from cua.discovery_evidence import (
    DiscoveryEvidenceRecorder,
)

from cua.llm import (
    create_action_provider,
)

from cua.playwright_surface import (
    PlaywrightSurface,
)

from cua.policy import (
    PolicyEngine,
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

POLICY_PATH = (
    PROJECT_ROOT
    / "config"
    / "policy.json"
)

DISCOVERY_EVIDENCE_ROOT = (
    PROJECT_ROOT
    / "evidence"
    / "discovery"
)

DISCOVERY_MEMBER_ID = "1001"

ENTRY_URL = (
    "http://127.0.0.1:8000"
    "/legacy"
)

DISCOVERY_GOAL = (
    "Look up member 1001 "
    "and return the current "
    "savings balance. "
    "Extract the balance using "
    "the output name "
    "'current_savings_balance'."
)


async def main() -> None:
    provider = (
        create_action_provider()
    )

    policy = (
        PolicyEngine.from_path(
            POLICY_PATH
        )
    )

    evidence = (
        DiscoveryEvidenceRecorder(
            root=(
                DISCOVERY_EVIDENCE_ROOT
            ),
            sensitive_inputs={
                "member_id":
                    DISCOVERY_MEMBER_ID,
            },
        )
    )

    print(
        "PROVIDER:",
        provider.provider_alias,
    )

    print(
        "MODEL:",
        provider.model_name,
    )

    print()

    async with (
        PlaywrightSurface(
            headless=False,
            slow_mo_ms=250,
        )
    ) as surface:

        engine = DiscoveryEngine(
            surface=surface,
            provider=provider,
            policy=policy,
            evidence=evidence,
            max_steps=12,
        )

        result = await engine.run(
            goal=(
                DISCOVERY_GOAL
            ),
            entry_url=(
                ENTRY_URL
            ),
        )

        print()
        print(
            "RUN ID:",
            result.run_id,
        )

        print(
            "STATUS:",
            result.status.value,
        )

        print(
            "MESSAGE:",
            result.message,
        )

        print()
        print(
            "DISCOVERY STEPS:"
        )

        for step in result.steps:
            print(
                (
                    f"{step.step_index}. "
                    f"{step.action.action.value}"
                    " | "
                    f"{step.action.reason}"
                )
            )

            if (
                step.action.target
                is not None
            ):
                print(
                    (
                        "   target: "
                        f"{step.action.target.description}"
                    )
                )

            if (
                step.extracted_output_name
                is not None
            ):
                print(
                    (
                        "   output: "
                        f"{step.extracted_output_name}"
                        "="
                        f"{step.extracted_output_value}"
                    )
                )

            print(
                (
                    "   url: "
                    f"{step.url_after}"
                )
            )

        print()
        print(
            "OUTPUTS:",
            result.outputs,
        )

        (
            evidence
            .assert_values_not_persisted(
                [
                    DISCOVERY_MEMBER_ID,
                    *result
                    .outputs
                    .values(),
                ]
            )
        )

        print()
        print(
            "DISCOVERY EVIDENCE:"
        )
        print(
            evidence.run_dir
        )
        print(
            "DISCOVERY EVIDENCE REDACTED: ✅"
        )

        await surface.wait(
            3000
        )


if __name__ == "__main__":
    asyncio.run(
        main()
    )