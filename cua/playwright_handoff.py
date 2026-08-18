from __future__ import annotations

import asyncio
import json
import uuid

from collections.abc import (
    Awaitable,
    Callable,
)
from typing import Any

from cua.handoff import (
    ControlOwner,
    ControlState,
    HandoffResult,
    HandoffStatus,
    HumanActionRecord,
    InterventionRequest,
)
from cua.playwright_surface import (
    PlaywrightSurface,
)
from cua.surface import ComputerSurface


OperatorCallback = Callable[
    [
        InterventionRequest,
        PlaywrightSurface,
    ],
    Awaitable[None],
]


class PlaywrightHumanHandoff:
    """
    Production-style same-session human handoff for the
    Playwright surface.

    Important properties:
      - the existing BrowserContext is preserved
      - the existing Page object is preserved
      - human actions are captured even if the operator
        navigates during the handoff
      - pressing Enter only REQUESTS resume
      - ReplayEngine must validate the live state before calling
        mark_automation_resumed()
    """

    def __init__(
        self,
        *,
        operator_id: str = (
            "local-operator"
        ),
        operator_callback: (
            OperatorCallback
            | None
        ) = None,
    ):
        self.operator_id = (
            operator_id
        )

        self.operator_callback = (
            operator_callback
        )

        self._state = (
            ControlState.AUTOMATION
        )

        self.completed_handoffs = 0

        self.last_actions: list[
            HumanActionRecord
        ] = []

        # Python-side event buffer. Because the browser reports
        # events through an exposed binding, actions survive
        # document navigation during the human-owned period.
        self._capture_active = False

        self._capture_buffer: list[
            HumanActionRecord
        ] = []

        self._instrumented = False

        self._binding_name = (
            "__cuaHumanRecord_"
            + uuid.uuid4().hex
        )

    # ========================================================
    # Ownership / state
    # ========================================================

    @property
    def state(
        self,
    ) -> ControlState:
        return self._state

    @property
    def owner(
        self,
    ) -> ControlOwner:
        # During VALIDATING_RESUME the human has released their
        # input turn, but automation has not yet accepted
        # ownership. Conservatively represent that boundary as
        # human-owned until validation passes.
        if (
            self._state
            == ControlState.AUTOMATION
        ):
            return (
                ControlOwner.AUTOMATION
            )

        return ControlOwner.HUMAN

    def mark_automation_resumed(
        self,
    ) -> None:
        if (
            self._state
            != ControlState
            .VALIDATING_RESUME
        ):
            raise RuntimeError(
                (
                    "Automation can only "
                    "resume from "
                    "VALIDATING_RESUME."
                )
            )

        self._state = (
            ControlState.AUTOMATION
        )

    def mark_resume_rejected(
        self,
    ) -> None:
        if (
            self._state
            != ControlState
            .VALIDATING_RESUME
        ):
            raise RuntimeError(
                (
                    "Resume can only be "
                    "rejected while validating."
                )
            )

        self._state = (
            ControlState
            .WAITING_FOR_HUMAN
        )

    # ========================================================
    # Surface validation
    # ========================================================

    @staticmethod
    def _as_playwright_surface(
        surface: ComputerSurface,
    ) -> PlaywrightSurface:
        if not isinstance(
            surface,
            PlaywrightSurface,
        ):
            raise TypeError(
                (
                    "PlaywrightHumanHandoff "
                    "requires "
                    "PlaywrightSurface."
                )
            )

        return surface

    # ========================================================
    # Cross-navigation human-action capture
    # ========================================================

    def _binding_callback(
        self,
        source: Any,
        payload: Any,
    ) -> None:
        del source

        if not self._capture_active:
            return

        if not isinstance(
            payload,
            dict,
        ):
            return

        try:
            record = (
                HumanActionRecord
                .model_validate(
                    payload
                )
            )
        except Exception:
            return

        self._capture_buffer.append(
            record
        )

    def _install_script(
        self,
    ) -> str:
        binding_literal = (
            json.dumps(
                self._binding_name
            )
        )

        return f"""
(() => {{
    if (
        window.__cuaHumanCaptureInstalled
    ) {{
        return;
    }}

    window.__cuaHumanCaptureInstalled = true;

    const bindingName = {binding_literal};

    const trim = (
        value,
        maxLength = 180
    ) => {{
        if (value == null) {{
            return null;
        }}

        const normalized = String(value)
            .replace(/\\s+/g, " ")
            .trim();

        if (!normalized) {{
            return null;
        }}

        return normalized.slice(
            0,
            maxLength
        );
    }};

    const isSensitive = (el) => {{
        if (!(el instanceof Element)) {{
            return false;
        }}

        if (
            el.matches(
                '[data-sensitive="true"]'
            )
        ) {{
            return true;
        }}

        if (
            el instanceof HTMLInputElement
            && el.type === "password"
        ) {{
            return true;
        }}

        return false;
    }};

    const accessibleName = (el) => {{
        if (!(el instanceof Element)) {{
            return null;
        }}

        return trim(
            el.getAttribute(
                "aria-label"
            )
            || el.getAttribute(
                "name"
            )
            || el.getAttribute(
                "title"
            )
            || el.getAttribute(
                "id"
            )
        );
    }};

    const emit = (payload) => {{
        const fn = window[
            bindingName
        ];

        if (
            typeof fn
            === "function"
        ) {{
            fn(payload);
        }}
    }};

    const handler = (event) => {{
        const el = (
            event.target
            instanceof Element
        )
            ? event.target
            : null;

        if (!el) {{
            return;
        }}

        const sensitive = (
            isSensitive(el)
        );

        let value = null;

        if (
            event.type === "input"
            || event.type === "change"
        ) {{
            if (sensitive) {{
                value = "[REDACTED]";
            }} else if (
                el instanceof
                    HTMLInputElement
                || el instanceof
                    HTMLTextAreaElement
                || el instanceof
                    HTMLSelectElement
            ) {{
                value = trim(
                    el.value
                );
            }}
        }}

        let text = null;

        if (!sensitive) {{
            text = trim(
                el.innerText
                || el.textContent
            );
        }}

        emit({{
            timestamp:
                new Date()
                .toISOString(),

            event_type:
                event.type,

            tag:
                el.tagName
                .toLowerCase(),

            role:
                trim(
                    el.getAttribute(
                        "role"
                    )
                ),

            accessible_name:
                accessibleName(el),

            text:
                text,

            href:
                (
                    el instanceof
                    HTMLAnchorElement
                )
                    ? trim(el.href)
                    : null,

            value:
                value,

            url:
                window.location.href,
        }});
    }};

    for (
        const eventName
        of [
            "click",
            "input",
            "change",
        ]
    ) {{
        document.addEventListener(
            eventName,
            handler,
            true
        );
    }}
}})();
"""

    async def _ensure_instrumented(
        self,
        surface: PlaywrightSurface,
    ) -> None:
        if self._instrumented:
            return

        await (
            surface
            .page
            .expose_binding(
                self._binding_name,
                self._binding_callback,
            )
        )

        script = (
            self._install_script()
        )

        # Install automatically in every future document loaded
        # by this same Page.
        await (
            surface
            .page
            .add_init_script(
                script=script
            )
        )

        # Also install in the current document because it was
        # loaded before add_init_script was registered.
        await (
            surface
            .page
            .evaluate(
                script
            )
        )

        self._instrumented = True

    async def _start_capture(
        self,
        surface: PlaywrightSurface,
    ) -> None:
        await self._ensure_instrumented(
            surface
        )

        self._capture_buffer = []

        self._capture_active = True

    async def _stop_capture(
        self,
    ) -> list[
        HumanActionRecord
    ]:
        self._capture_active = False

        return list(
            self._capture_buffer
        )

    # ========================================================
    # Operator interaction
    # ========================================================

    async def _manual_operator_wait(
        self,
        *,
        request: InterventionRequest,
        surface: PlaywrightSurface,
    ) -> None:
        print(
            "\n"
            + "=" * 70
        )
        print(
            "HUMAN INTERVENTION REQUIRED"
        )
        print(
            "=" * 70
        )

        print(
            "INTERVENTION:",
            request.intervention_id,
        )

        print(
            "CAPABILITY:",
            request.capability_id,
        )

        print(
            "STEP:",
            request.step_id,
        )

        print(
            "REASON:",
            request.reason_code,
        )

        print(
            "MESSAGE:",
            request.reason,
        )

        print(
            "LIVE URL:",
            surface.current_url,
        )

        print(
            (
                "RESUME ATTEMPT:"
                f" {request.resume_attempt}"
                "/"
                f"{request.max_resume_attempts}"
            )
        )

        if (
            request
            .resume_validation_message
        ):
            print(
                "\nPREVIOUS RESUME "
                "VALIDATION FAILED:"
            )

            print(
                request
                .resume_validation_message
            )

        print(
            "\nCONTROL OWNER: HUMAN"
        )

        print(
            (
                "Use the ALREADY-OPEN "
                "browser window. Do not "
                "open a new browser."
            )
        )

        print(
            (
                "When you believe the live "
                "state is ready for "
                "automation, return here "
                "and request resume."
            )
        )

        await asyncio.to_thread(
            input,
            (
                "\nPress Enter to REQUEST "
                "resume validation: "
            ),
        )

    async def handle(
        self,
        *,
        request: InterventionRequest,
        surface: ComputerSurface,
    ) -> HandoffResult:
        playwright_surface = (
            self._as_playwright_surface(
                surface
            )
        )

        # These identities must survive the entire control
        # transfer.
        page_before = (
            playwright_surface.page
        )

        context_before = (
            playwright_surface.context
        )

        self._state = (
            ControlState
            .WAITING_FOR_HUMAN
        )

        await self._start_capture(
            playwright_surface
        )

        self._state = (
            ControlState.HUMAN
        )

        actions: list[
            HumanActionRecord
        ] = []

        try:
            if (
                self.operator_callback
                is None
            ):
                await (
                    self
                    ._manual_operator_wait(
                        request=request,
                        surface=(
                            playwright_surface
                        ),
                    )
                )
            else:
                await (
                    self
                    .operator_callback(
                        request,
                        playwright_surface,
                    )
                )

            actions = (
                await self
                ._stop_capture()
            )

            if (
                playwright_surface.page
                is not page_before
            ):
                return HandoffResult(
                    intervention_id=(
                        request
                        .intervention_id
                    ),
                    status=(
                        HandoffStatus.FAILED
                    ),
                    operator_id=(
                        self.operator_id
                    ),
                    actions=actions,
                    message=(
                        "The live Page object "
                        "changed during "
                        "handoff."
                    ),
                    final_url=(
                        playwright_surface
                        .current_url
                    ),
                )

            if (
                playwright_surface.context
                is not context_before
            ):
                return HandoffResult(
                    intervention_id=(
                        request
                        .intervention_id
                    ),
                    status=(
                        HandoffStatus.FAILED
                    ),
                    operator_id=(
                        self.operator_id
                    ),
                    actions=actions,
                    message=(
                        "The live browser "
                        "context changed during "
                        "handoff."
                    ),
                    final_url=(
                        playwright_surface
                        .current_url
                    ),
                )

            # Give synchronous DOM mutations and any navigation
            # already triggered by the human a moment to settle.
            try:
                await (
                    playwright_surface
                    .page
                    .wait_for_load_state(
                        "domcontentloaded",
                        timeout=1500,
                    )
                )
            except Exception:
                # Pure DOM mutations such as modal dismissal do
                # not necessarily create a load event.
                pass

            await (
                playwright_surface
                .page
                .wait_for_timeout(
                    100
                )
            )

            self.completed_handoffs += 1

            self.last_actions = actions

            # Critical: automation does NOT own the browser yet.
            # Replay must validate the continuation state first.
            self._state = (
                ControlState
                .VALIDATING_RESUME
            )

            return HandoffResult(
                intervention_id=(
                    request
                    .intervention_id
                ),
                status=(
                    HandoffStatus
                    .RESUME_REQUESTED
                ),
                operator_id=(
                    self.operator_id
                ),
                actions=actions,
                message=(
                    "Human requested resume; "
                    "automation must validate "
                    "the live continuation "
                    "state."
                ),
                final_url=(
                    playwright_surface
                    .current_url
                ),
            )

        except (
            KeyboardInterrupt,
            EOFError,
        ):
            self._capture_active = False

            self._state = (
                ControlState.HUMAN
            )

            return HandoffResult(
                intervention_id=(
                    request
                    .intervention_id
                ),
                status=(
                    HandoffStatus.CANCELLED
                ),
                operator_id=(
                    self.operator_id
                ),
                actions=actions,
                message=(
                    "Human intervention was "
                    "cancelled."
                ),
                final_url=(
                    playwright_surface
                    .current_url
                ),
            )

        except Exception as exc:
            self._capture_active = False

            self._state = (
                ControlState.HUMAN
            )

            return HandoffResult(
                intervention_id=(
                    request
                    .intervention_id
                ),
                status=(
                    HandoffStatus.FAILED
                ),
                operator_id=(
                    self.operator_id
                ),
                actions=actions,
                message=(
                    "Human intervention "
                    "failed: "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
                final_url=(
                    playwright_surface
                    .current_url
                ),
            )