import socket
import subprocess
import sys
import time

from pathlib import Path

import httpx
import pytest

from cua.models import (
    Condition,
    ConditionType,
    LocatorCandidate,
    LocatorKind,
    TargetDescriptor,
)

from cua.playwright_surface import (
    PlaywrightSurface,
)

from cua.redaction import REDACTED

from cua.surface import (
    TargetAmbiguousError,
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)


def find_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(
            ("127.0.0.1", 0)
        )

        return sock.getsockname()[1]


@pytest.fixture(
    scope="session"
)
def live_server():
    port = find_free_port()

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "apps.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    base_url = (
        f"http://127.0.0.1:{port}"
    )

    deadline = (
        time.time() + 10
    )

    while time.time() < deadline:
        try:
            response = httpx.get(
                f"{base_url}/legacy",
                timeout=0.5,
            )

            if response.status_code == 200:
                break

        except Exception:
            time.sleep(0.1)

    else:
        process.terminate()

        raise RuntimeError(
            "Test LegacyCore server "
            "did not start."
        )

    yield base_url

    process.terminate()

    try:
        process.wait(
            timeout=5
        )

    except subprocess.TimeoutExpired:
        process.kill()


@pytest.mark.asyncio
async def test_observe_search_page(
    live_server,
):
    async with PlaywrightSurface(
        headless=True
    ) as surface:

        await surface.navigate(
            f"{live_server}/legacy"
        )

        observation = (
            await surface.observe()
        )

        assert (
            observation.title
            == "LegacyCore Search"
        )

        assert (
            "Member Search"
            in observation.visible_text
        )

        names = {
            control.name
            for control
            in observation.controls
        }

        assert "Member ID" in names
        assert "Search" in names


@pytest.mark.asyncio
async def test_fill_and_search_member(
    live_server,
):
    async with PlaywrightSurface(
        headless=True
    ) as surface:

        await surface.navigate(
            f"{live_server}/legacy"
        )

        member_input = (
            TargetDescriptor(
                description=(
                    "Member ID input"
                ),
                locators=[
                    LocatorCandidate(
                        kind=(
                            LocatorKind.LABEL
                        ),
                        value="Member ID",
                    )
                ],
            )
        )

        search_button = (
            TargetDescriptor(
                description=(
                    "Search button"
                ),
                locators=[
                    LocatorCandidate(
                        kind=(
                            LocatorKind.ROLE
                        ),
                        role="button",
                        name="Search",
                    )
                ],
            )
        )

        resolved_input = (
            await surface.resolve_target(
                member_input
            )
        )

        await surface.fill(
            resolved_input,
            "1001",
        )

        resolved_button = (
            await surface.resolve_target(
                search_button
            )
        )

        await surface.click(
            resolved_button
        )

        condition = Condition(
            type=(
                ConditionType.TEXT_PRESENT
            ),
            value="Member Details",
            timeout_ms=3000,
        )

        assert (
            await surface.check_condition(
                condition
            )
            is True
        )

        assert (
            "/legacy/member/1001"
            in surface.current_url
        )


@pytest.mark.asyncio
async def test_locator_fallback_order(
    live_server,
):
    async with PlaywrightSurface(
        headless=True
    ) as surface:

        await surface.navigate(
            f"{live_server}/legacy"
        )

        target = TargetDescriptor(
            description="Search button",
            locators=[
                LocatorCandidate(
                    kind=LocatorKind.LABEL,
                    value=(
                        "Definitely Not Here"
                    ),
                ),
                LocatorCandidate(
                    kind=LocatorKind.ROLE,
                    role="button",
                    name="Search",
                ),
            ],
        )

        resolved = (
            await surface.resolve_target(
                target
            )
        )

        assert (
            resolved.candidate_index
            == 1
        )


@pytest.mark.asyncio
async def test_ambiguous_locator_is_rejected(
    live_server,
):
    async with PlaywrightSurface(
        headless=True
    ) as surface:

        await surface.navigate(
            (
                f"{live_server}"
                "/legacy/member/1001"
            )
        )

        target = TargetDescriptor(
            description=(
                "Account status"
            ),
            locators=[
                LocatorCandidate(
                    kind=LocatorKind.TEXT,
                    value="Open",
                    exact=True,
                )
            ],
        )

        with pytest.raises(
            TargetAmbiguousError
        ):
            await surface.resolve_target(
                target
            )


@pytest.mark.asyncio
async def test_extract_and_redact_evidence(
    live_server,
    tmp_path: Path,
):
    async with PlaywrightSurface(
        headless=True
    ) as surface:

        await surface.navigate(
            (
                f"{live_server}"
                "/legacy/member/1001"
                "/account/savings"
            )
        )

        balance_target = (
            TargetDescriptor(
                description=(
                    "Current savings balance"
                ),
                locators=[
                    LocatorCandidate(
                        kind=LocatorKind.CSS,
                        value=(
                            "td"
                            "[data-sensitive='true']"
                        ),
                    )
                ],
            )
        )

        resolved = (
            await surface.resolve_target(
                balance_target
            )
        )

        balance = (
            await surface.extract_text(
                resolved
            )
        )

        assert balance == "$8,421.22"

        snapshot = (
            await surface.structure_snapshot()
        )

        assert snapshot is not None

        assert (
            "$8,421.22"
            not in snapshot
        )

        assert REDACTED in snapshot

        screenshot_path = (
            tmp_path
            / "account.png"
        )

        result = (
            await surface.capture_screenshot(
                screenshot_path
            )
        )

        assert result.exists()

        assert (
            result.stat().st_size
            > 0
        )


@pytest.mark.asyncio
async def test_output_condition(
    live_server,
):
    async with PlaywrightSurface(
        headless=True
    ) as surface:

        await surface.navigate(
            f"{live_server}/legacy"
        )

        condition = Condition(
            type=(
                ConditionType.OUTPUT_EXISTS
            ),
            output_name=(
                "savings_balance"
            ),
            timeout_ms=100,
        )

        assert (
            await surface.check_condition(
                condition,
                outputs={
                    "savings_balance":
                        "$8,421.22"
                },
            )
            is True
        )