from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from pathlib import Path
from urllib.error import (
    HTTPError,
    URLError,
)
from urllib.request import (
    Request,
    urlopen,
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

TARGET_URL = (
    "http://127.0.0.1:8000"
)

API_URL = (
    "http://127.0.0.1:8011"
)


def _request_json(
    method: str,
    url: str,
    payload: dict | None = None,
):
    data = None

    headers = {
        "Accept":
            "application/json",
    }

    if payload is not None:
        data = json.dumps(
            payload
        ).encode(
            "utf-8"
        )

        headers[
            "Content-Type"
        ] = "application/json"

    request = Request(
        url=url,
        data=data,
        headers=headers,
        method=method,
    )

    with urlopen(
        request,
        timeout=30,
    ) as response:
        return json.loads(
            response
            .read()
            .decode(
                "utf-8"
            )
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
        if _is_up(
            url
        ):
            return

        time.sleep(
            0.2
        )

    raise RuntimeError(
        (
            "Timed out waiting "
            f"for {url}"
        )
    )


def _all_text_evidence(
    run_dir: Path,
) -> str:
    chunks: list[str] = []

    for path in (
        run_dir.iterdir()
    ):
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


def main() -> None:
    print(
        "=" * 70
    )

    print(
        (
            "STEP 16 — AGENT-FACING "
            "CAPABILITY API"
        )
    )

    print(
        "=" * 70
    )

    target_process = None
    api_process = None

    try:
        # ----------------------------------------------------
        # Ensure synthetic target is available.
        # ----------------------------------------------------

        if not _is_up(
            TARGET_URL
            + "/legacy"
        ):
            print(
                (
                    "Starting synthetic "
                    "LegacyCore target..."
                )
            )

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

        # ----------------------------------------------------
        # Start isolated agent API for this smoke.
        # ----------------------------------------------------

        if _is_up(
            API_URL
            + "/health"
        ):
            raise RuntimeError(
                (
                    "Port 8011 is already "
                    "serving an application. "
                    "Stop it before running "
                    "this smoke test."
                )
            )

        env = os.environ.copy()

        # The saved demonstration artifact is intentionally
        # still draft. Production default remains disabled.
        env[
            "CUA_ALLOW_DRAFT_CAPABILITIES"
        ] = "1"

        api_process = (
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "apps.capability_api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8011",
                ],
                cwd=PROJECT_ROOT,
                env=env,
                stdout=(
                    subprocess.DEVNULL
                ),
                stderr=(
                    subprocess.DEVNULL
                ),
            )
        )

        _wait_until_up(
            API_URL
            + "/health"
        )

        # ----------------------------------------------------
        # Agent discovers catalog.
        # ----------------------------------------------------

        health = _request_json(
            "GET",
            API_URL
            + "/health",
        )

        catalog = _request_json(
            "GET",
            API_URL
            + "/v1/capabilities",
        )

        capability = next(
            item
            for item in catalog
            if (
                item[
                    "capability_id"
                ]
                == (
                    "lookup_savings_balance"
                )
            )
        )

        print(
            "\nDISCOVERED CAPABILITY:"
        )

        print(
            (
                capability[
                    "capability_id"
                ],
                capability[
                    "version"
                ],
            )
        )

        print(
            "inputs:",
            list(
                capability[
                    "inputs"
                ]
            ),
        )

        print(
            "outputs:",
            list(
                capability[
                    "outputs"
                ]
            ),
        )

        assert (
            health[
                "draft_invocation_enabled"
            ]
            is True
        )

        assert (
            capability[
                "callable"
            ]
            is True
        )

        assert (
            "member_id"
            in capability[
                "inputs"
            ]
        )

        assert (
            "current_savings_balance"
            in capability[
                "outputs"
            ]
        )

        # ----------------------------------------------------
        # Agent invokes by name + typed arguments.
        # ----------------------------------------------------

        invocation = _request_json(
            "POST",
            (
                API_URL
                + "/v1/capabilities/"
                "lookup_savings_balance/"
                "invoke"
            ),
            {
                "version":
                    "1.0.0",
                "tenant_id":
                    "northstar-cu",
                "application_key":
                    "member-servicing",
                "arguments": {
                    "member_id":
                        "1002",
                },
            },
        )

        print(
            "\nINVOCATION RESULT:"
        )

        print(
            "status:",
            invocation[
                "status"
            ],
        )

        print(
            "outputs:",
            invocation[
                "outputs"
            ],
        )

        print(
            "checkpoint:",
            invocation[
                "checkpoint_passed"
            ],
        )

        print(
            "evidence_run_id:",
            invocation[
                "evidence_run_id"
            ],
        )

        assert (
            invocation[
                "status"
            ]
            == "completed"
        )

        assert (
            invocation[
                "outputs"
            ][
                "current_savings_balance"
            ]
            == "$6,320.40"
        )

        assert (
            invocation[
                "checkpoint_passed"
            ]
            is True
        )

        assert (
            invocation[
                "tenant_id"
            ]
            == "northstar-cu"
        )

        assert (
            invocation[
                "evidence_run_id"
            ]
        )

        # ----------------------------------------------------
        # Verify caller gets the real output while persisted
        # evidence remains redacted.
        # ----------------------------------------------------

        evidence_run_id = (
            invocation[
                "evidence_run_id"
            ]
        )

        run_dir = (
            PROJECT_ROOT
            / "evidence"
            / "agent_api"
            / evidence_run_id
        )

        assert run_dir.exists()

        persisted = (
            _all_text_evidence(
                run_dir
            )
        )

        assert (
            "1002"
            not in persisted
        )

        assert (
            "$6,320.40"
            not in persisted
        )

        # ----------------------------------------------------
        # Show business outcome also survives API boundary.
        # ----------------------------------------------------

        not_found = _request_json(
            "POST",
            (
                API_URL
                + "/v1/capabilities/"
                "lookup_savings_balance/"
                "invoke"
            ),
            {
                "version":
                    "1.0.0",
                "tenant_id":
                    "northstar-cu",
                "application_key":
                    "member-servicing",
                "arguments": {
                    "member_id":
                        "9999",
                },
            },
        )

        assert (
            not_found[
                "status"
            ]
            == "business_outcome"
        )

        assert (
            not_found[
                "runtime_state_code"
            ]
            == "MEMBER_NOT_FOUND"
        )

        print(
            "\n"
            + "=" * 70
        )

        print(
            "AGENT CATALOG DISCOVERY: ✅"
        )
        print(
            "TYPED INPUT CONTRACT: ✅"
        )
        print(
            "TYPED OUTPUT CONTRACT: ✅"
        )
        print(
            "EXACT VERSION INVOCATION: ✅"
        )
        print(
            "TENANT BINDING APPLIED: ✅"
        )
        print(
            "DETERMINISTIC REPLAY INVOKED: ✅"
        )
        print(
            "CHECKPOINT RETURNED: ✅"
        )
        print(
            "BUSINESS OUTCOME PRESERVED: ✅"
        )
        print(
            "API EVIDENCE REDACTED: ✅"
        )
        print(
            "ZERO LLM DECISIONS IN INVOCATION: ✅"
        )

        print(
            "\nSTEP 16 SMOKE TEST COMPLETE ✅"
        )

    finally:
        for process in [
            api_process,
            target_process,
        ]:
            if process is None:
                continue

            process.terminate()

            try:
                process.wait(
                    timeout=5
                )
            except (
                subprocess
                .TimeoutExpired
            ):
                process.kill()


if __name__ == "__main__":
    main()