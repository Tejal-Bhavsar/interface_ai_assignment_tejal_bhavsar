from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path

from cua.evidence_bundle import (
    EvidenceRequirementError,
    build_final_bundle,
    select_evidence,
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)


def _print_run(
    label: str,
    run,
) -> None:
    if run is None:
        print(
            f"{label:<22} MISSING"
        )
        return

    print(
        (
            f"{label:<22} "
            f"{run.run_id} "
            f"[{run.status}]"
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Audit and curate final "
            "submission evidence."
        )
    )

    parser.add_argument(
        "--audit-only",
        action="store_true",
        help=(
            "Inspect evidence and print "
            "selection without rebuilding "
            "evidence/final."
        ),
    )

    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help=(
            "Build a diagnostic bundle even "
            "if required final evidence is "
            "missing. Do not use this for "
            "submission."
        ),
    )

    args = parser.parse_args()

    selection = select_evidence(
        project_root=PROJECT_ROOT
    )

    print(
        "=" * 72
    )
    print(
        "STEP 18 — FINAL EVIDENCE AUDIT"
    )
    print(
        "=" * 72
    )

    if selection.discovery is None:
        print(
            "DISCOVERY              MISSING"
        )
    else:
        print(
            (
                "DISCOVERY              "
                f"{selection.discovery.run_id} "
                f"[{selection.discovery.provider}"
                f"/{selection.discovery.model}]"
            )
        )

    _print_run(
        "REPLAY SUCCESS",
        selection.replay_success,
    )

    _print_run(
        "BUSINESS OUTCOME",
        selection.business_outcome,
    )

    _print_run(
        "RECOVERY",
        selection.recovery,
    )

    _print_run(
        "HARD FAILURE",
        selection.hard_failure,
    )

    _print_run(
        "HUMAN HANDOFF",
        selection.human_handoff,
    )

    _print_run(
        "POLICY",
        selection.policy,
    )

    _print_run(
        "AGENT API (optional)",
        selection.agent_api,
    )

    print()

    if selection.missing:
        print(
            "FINAL BUNDLE NOT READY ❌"
        )

        for item in (
            selection.missing
        ):
            print(
                f"  - {item}"
            )

        print()

        if any(
            "REAL MANUAL"
            in item
            for item
            in selection.missing
        ):
            print(
                (
                    "Run this once without "
                    "--auto, complete the "
                    "browser handoff, then "
                    "rerun Step 18:"
                )
            )

            print(
                (
                    "  python -m "
                    "scripts.smoke_handoff"
                )
            )

        if any(
            "discovery"
            in item.lower()
            for item
            in selection.missing
        ):
            print(
                (
                    "Do NOT rerun the LLM "
                    "yet. First locate the "
                    "existing genuine "
                    "discovery log and place "
                    "it under "
                    "evidence/discovery/."
                )
            )

        if (
            args.audit_only
            or not args.allow_incomplete
        ):
            sys.exit(
                1
            )

    else:
        print(
            "ALL REQUIRED EVIDENCE FOUND ✅"
        )

    if args.audit_only:
        return

    try:
        final_dir = (
            build_final_bundle(
                project_root=(
                    PROJECT_ROOT
                ),
                strict=(
                    not args
                    .allow_incomplete
                ),
            )
        )
    except (
        EvidenceRequirementError
    ) as exc:
        print(
            str(exc)
        )
        sys.exit(
            1
        )

    manifest = json.loads(
        (
            final_dir
            / "manifest.json"
        )
        .read_text(
            encoding="utf-8"
        )
    )

    print()
    print(
        (
            "FINAL EVIDENCE BUNDLE: "
            f"{final_dir}"
        )
    )
    print(
        (
            "MISSING REQUIREMENTS: "
            f"{len(manifest.get('missing_requirements', []))}"
        )
    )

    print()
    print(
        "=" * 72
    )
    print(
        "SOURCE EVIDENCE LEFT UNCHANGED: ✅"
    )
    print(
        "CANONICAL ARTIFACT COPIED: ✅"
    )
    print(
        "REPLAY REDACTION AUDITED: ✅"
    )
    print(
        "MANIFEST GENERATED: ✅"
    )
    print(
        "BUNDLE CHECKSUMS GENERATED: ✅"
    )

    if not manifest.get(
        "missing_requirements"
    ):
        print(
            "STEP 18 COMPLETE ✅"
        )
    else:
        print(
            (
                "STEP 18 DIAGNOSTIC "
                "BUNDLE ONLY ⚠️"
            )
        )


if __name__ == "__main__":
    main()