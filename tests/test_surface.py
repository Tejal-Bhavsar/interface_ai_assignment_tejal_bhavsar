from pathlib import Path
from typing import Any
from collections.abc import Mapping
from typing import Any

import pytest

from cua.models import (
    Condition,
    LocatorCandidate,
    LocatorKind,
    Observation,
    ResolvedTargetInfo,
    TargetDescriptor,
)

from cua.surface import (
    ComputerSurface,
    ResolvedTarget,
    TargetNotFoundError,
)


class FakeSurface(ComputerSurface):
    """
    Tiny fake backend used to test the ComputerSurface
    contract without Playwright.
    """

    def __init__(self):
        self.started = False
        self.closed = False

        self._current_url = (
            "http://127.0.0.1:8000/legacy"
        )

    @property
    def surface_type(self) -> str:
        return "fake"

    @property
    def current_url(self) -> str:
        return self._current_url

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    async def navigate(
        self,
        url: str,
    ) -> None:
        self._current_url = url

    async def reload(self) -> None:
        pass

    async def observe(
        self,
    ) -> Observation:

        return Observation(
            url=self.current_url,
            title="Fake Surface",
            visible_text=(
                "Member Search Member ID Search"
            ),
        )

    async def resolve_target(
        self,
        target: TargetDescriptor,
    ) -> ResolvedTarget:

        if not target.locators:
            raise TargetNotFoundError(
                target
            )

        candidate = target.locators[0]

        return ResolvedTarget(
            descriptor=target,
            candidate=candidate,
            candidate_index=0,
            info=ResolvedTargetInfo(
                tag="button",
                role="button",
                text="Search",
                name="Search",
            ),
            backend_ref={
                "fake_element": "search"
            },
        )

    async def click(
        self,
        target: ResolvedTarget,
    ) -> None:
        pass

    async def fill(
        self,
        target: ResolvedTarget,
        value: str,
    ) -> None:
        pass

    async def select(
        self,
        target: ResolvedTarget,
        value: str,
    ) -> None:
        pass

    async def extract_text(
        self,
        target: ResolvedTarget,
    ) -> str:
        return target.info.text or ""

    async def wait(
        self,
        milliseconds: int,
    ) -> None:
        pass

    async def check_condition(
        self,
        condition: Condition,
        outputs: Mapping[str, Any] | None = None,
    ) -> bool:
        return True

    async def capture_screenshot(
        self,
        path: Path,
        *,
        mask_sensitive: bool = True,
    ) -> Path:

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_bytes(
            b"fake screenshot"
        )

        return path

    async def structure_snapshot(
        self,
    ) -> str | None:

        return "<fake>structure</fake>"

    
@pytest.mark.asyncio
async def test_surface_context_manager():
    surface = FakeSurface()

    assert surface.started is False
    assert surface.closed is False

    async with surface:
        assert surface.started is True
        assert surface.closed is False

    assert surface.closed is True


@pytest.mark.asyncio
async def test_surface_returns_observation():
    surface = FakeSurface()

    observation = await surface.observe()

    assert (
        observation.url
        == "http://127.0.0.1:8000/legacy"
    )

    assert (
        observation.title
        == "Fake Surface"
    )

    assert (
        "Member Search"
        in observation.visible_text
    )


@pytest.mark.asyncio
async def test_surface_resolves_target():
    surface = FakeSurface()

    target = TargetDescriptor(
        description="Search button",
        locators=[
            LocatorCandidate(
                kind=LocatorKind.ROLE,
                role="button",
                name="Search",
            )
        ],
    )

    resolved = await surface.resolve_target(
        target
    )

    assert resolved.candidate_index == 0

    assert (
        resolved.candidate.kind
        == LocatorKind.ROLE
    )

    assert (
        resolved.info.text
        == "Search"
    )


@pytest.mark.asyncio
async def test_target_without_locator_fails():
    surface = FakeSurface()

    target = TargetDescriptor(
        description="Unknown target",
        locators=[],
    )

    with pytest.raises(
        TargetNotFoundError
    ):
        await surface.resolve_target(
            target
        )


@pytest.mark.asyncio
async def test_surface_can_navigate():
    surface = FakeSurface()

    await surface.navigate(
        (
            "http://127.0.0.1:8000"
            "/legacy/member/1001"
        )
    )

    assert (
        surface.current_url
        == (
            "http://127.0.0.1:8000"
            "/legacy/member/1001"
        )
    )


@pytest.mark.asyncio
async def test_surface_captures_evidence(
    tmp_path: Path,
):
    surface = FakeSurface()

    screenshot = (
        tmp_path
        / "screen.png"
    )

    result = (
        await surface.capture_screenshot(
            screenshot
        )
    )

    assert result.exists()

    assert (
        result.read_bytes()
        == b"fake screenshot"
    )

    structure = (
        await surface.structure_snapshot()
    )

    assert structure is not None

    assert "fake" in structure


