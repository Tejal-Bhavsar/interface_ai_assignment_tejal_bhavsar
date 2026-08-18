from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cua.models import (
    Condition,
    LocatorCandidate,
    Observation,
    ResolvedTargetInfo,
    TargetDescriptor,
)


# ============================================================
# Surface errors
# ============================================================


class SurfaceError(RuntimeError):
    """
    Base exception for computer-surface failures.

    Discovery and replay should be able to distinguish
    UI/backend problems from ordinary Python errors.
    """

    pass


class SurfaceNotReadyError(SurfaceError):
    """
    Raised when a surface operation is attempted before the
    underlying browser/desktop session is ready.
    """

    pass


class TargetResolutionError(SurfaceError):
    """
    Base error for failures while resolving a logical target
    into a real UI element.
    """

    def __init__(
        self,
        target: TargetDescriptor,
        message: str,
    ):
        super().__init__(message)

        self.target = target


class TargetNotFoundError(TargetResolutionError):
    """
    No locator candidate uniquely matched the requested target.
    """

    def __init__(
        self,
        target: TargetDescriptor,
    ):
        super().__init__(
            target,
            (
                "Could not resolve target: "
                f"{target.description}"
            ),
        )


class TargetAmbiguousError(TargetResolutionError):
    """
    A locator matched multiple controls when exactly one
    control was expected.

    We deliberately reject ambiguity instead of silently
    choosing the first element.
    """

    def __init__(
        self,
        target: TargetDescriptor,
        candidate: LocatorCandidate,
        match_count: int,
    ):
        super().__init__(
            target,
            (
                f"Target '{target.description}' "
                f"was ambiguous: locator matched "
                f"{match_count} elements."
            ),
        )

        self.candidate = candidate
        self.match_count = match_count


class UnsupportedSurfaceOperation(
    SurfaceError
):
    """
    Raised when a particular backend cannot perform a requested
    surface operation.
    """

    pass


# ============================================================
# Resolved target
# ============================================================


@dataclass(
    frozen=True,
    slots=True,
)
class ResolvedTarget:
    """
    Internal representation of a logical TargetDescriptor
    after a concrete surface successfully resolves it.

    `backend_ref` is deliberately opaque.

    For Playwright it may contain a Locator.
    A future desktop implementation could store an
    accessibility element or another platform-specific handle.
    """

    descriptor: TargetDescriptor

    candidate: LocatorCandidate

    candidate_index: int

    info: ResolvedTargetInfo

    backend_ref: Any = field(
        repr=False,
        compare=False,
    )


# ============================================================
# ComputerSurface contract
# ============================================================


class ComputerSurface(ABC):
    """
    Generic contract for interacting with a computer UI.

    Higher-level components should depend on ComputerSurface,
    not directly on Playwright.

    Discovery asks the surface to:
        observe
        resolve
        click
        fill
        extract

    Replay uses the exact same primitives without needing to
    know which backend implements them.
    """

    # --------------------------------------------------------
    # Lifecycle
    # --------------------------------------------------------

    @property
    @abstractmethod
    def surface_type(self) -> str:
        """
        Backend type.

        Examples:
            web
            desktop
            accessibility
            vision
        """

        raise NotImplementedError

    @property
    @abstractmethod
    def current_url(self) -> str:
        """
        Current logical location of the surface.

        For a web backend this is the browser URL.

        A future desktop backend could return an application
        URI or another meaningful location identifier.
        """

        raise NotImplementedError

    @abstractmethod
    async def start(self) -> None:
        """
        Start the underlying computer-use session.
        """

        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """
        Cleanly close the underlying session.
        """

        raise NotImplementedError

    async def __aenter__(
        self,
    ) -> "ComputerSurface":
        """
        Allow:

            async with PlaywrightSurface(...) as surface:
                ...
        """

        await self.start()

        return self

    async def __aexit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:

        await self.close()

    # --------------------------------------------------------
    # Navigation
    # --------------------------------------------------------

    @abstractmethod
    async def navigate(
        self,
        url: str,
    ) -> None:
        """
        Navigate to a logical location.
        """

        raise NotImplementedError

    @abstractmethod
    async def reload(self) -> None:
        """
        Reload/re-establish the current screen.

        This is required by recoveries such as:

            SESSION_EXPIRED
            TRANSIENT_BUSY
        """

        raise NotImplementedError

    # --------------------------------------------------------
    # Observation
    # --------------------------------------------------------

    @abstractmethod
    async def observe(
        self,
    ) -> Observation:
        """
        Produce a compact, structured observation of the
        current UI.

        This is what the discovery LLM will see.
        """

        raise NotImplementedError

    # --------------------------------------------------------
    # Target resolution
    # --------------------------------------------------------

    @abstractmethod
    async def resolve_target(
        self,
        target: TargetDescriptor,
    ) -> ResolvedTarget:
        """
        Resolve a logical target into exactly one live UI
        element.

        Implementations must try locator candidates in their
        recorded order.

        They must NOT silently choose `.first()` when a
        candidate is ambiguous.
        """

        raise NotImplementedError

    # --------------------------------------------------------
    # UI actions
    # --------------------------------------------------------

    @abstractmethod
    async def click(
        self,
        target: ResolvedTarget,
    ) -> None:
        """
        Click a previously resolved target.
        """

        raise NotImplementedError

    @abstractmethod
    async def fill(
        self,
        target: ResolvedTarget,
        value: str,
    ) -> None:
        """
        Fill text into a previously resolved target.
        """

        raise NotImplementedError

    @abstractmethod
    async def select(
        self,
        target: ResolvedTarget,
        value: str,
    ) -> None:
        """
        Select a value from a select/list-like control.
        """

        raise NotImplementedError

    @abstractmethod
    async def extract_text(
        self,
        target: ResolvedTarget,
    ) -> str:
        """
        Extract readable text from a resolved control.
        """

        raise NotImplementedError

    # --------------------------------------------------------
    # Waiting / validation
    # --------------------------------------------------------

    @abstractmethod
    async def wait(
        self,
        milliseconds: int,
    ) -> None:
        """
        Perform an explicit bounded wait.
        """

        raise NotImplementedError

    @abstractmethod
    async def check_condition(
        self,
        condition: Condition,
        outputs: Mapping[str, Any] | None = None,
    ) -> bool:
        """
        Evaluate a typed condition against the live UI.

        Examples:
            text_present
            text_absent
            element_present
            url_matches
            output_exists
        """

        raise NotImplementedError

    # --------------------------------------------------------
    # Evidence
    # --------------------------------------------------------

    @abstractmethod
    async def capture_screenshot(
        self,
        path: Path,
        *,
        mask_sensitive: bool = True,
    ) -> Path:
        """
        Capture screenshot evidence.

        Implementations should mask sensitive regions when
        mask_sensitive=True.
        """

        raise NotImplementedError

    @abstractmethod
    async def structure_snapshot(
        self,
    ) -> str | None:
        """
        Capture backend-specific structural evidence.

        Browser backend:
            sanitized DOM / accessibility structure

        Desktop backend:
            accessibility tree

        Some backends may return None.
        """

        raise NotImplementedError