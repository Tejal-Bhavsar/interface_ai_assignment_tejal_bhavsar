#from anthropic.types import container_upload_block_param
from __future__ import annotations

import asyncio
import os

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    async_playwright,
)

from cua.models import (
    Condition,
    ConditionType,
    LocatorCandidate,
    LocatorKind,
    Observation,
    ObservedControl,
    ResolvedTargetInfo,
    TargetDescriptor,
)

from cua.redaction import (
    Redactor,
    SENSITIVE_DOM_SELECTOR,
)

from cua.surface import (
    ComputerSurface,
    ResolvedTarget,
    SurfaceNotReadyError,
    TargetAmbiguousError,
    TargetNotFoundError,
    UnsupportedSurfaceOperation,
)


class PlaywrightSurface(ComputerSurface):
    """
    Browser implementation of ComputerSurface.

    This class owns one Playwright browser context and one page.

    The same BrowserContext/Page remain alive for the lifetime
    of this surface, which will later allow same-session
    human takeover and resume.
    """

    def __init__(
        self,
        *,
        headless: bool = False,
        slow_mo_ms: int = 0,
        redactor: Redactor | None = None,
    ):
        self.headless = headless
        self.slow_mo_ms = slow_mo_ms

        self.redactor = (
            redactor
            or Redactor()
        )

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    # ========================================================
    # Public backend information
    # ========================================================

    @property
    def surface_type(self) -> str:
        return "web"

    @property
    def current_url(self) -> str:
        if self._page is None:
            return ""

        return self._page.url

    @property
    def page(self) -> Page:
        """
        Concrete Playwright page.

        Higher-level generic components should normally avoid
        using this directly.

        It is exposed for backend-specific integrations such as
        the human-handoff implementation later.
        """

        return self._require_page()

    @property
    def context(self) -> BrowserContext:
        """
        Current browser context.

        Keeping the same context is important because cookies,
        session state, local storage, etc. remain intact during
        human intervention.
        """

        if self._context is None:
            raise SurfaceNotReadyError(
                "Browser context is not ready."
            )

        return self._context

    # ========================================================
    # Lifecycle
    # ========================================================

    def _require_page(self) -> Page:
        if self._page is None:
            raise SurfaceNotReadyError(
                "Playwright surface has not been started."
            )

        return self._page

    async def start(self) -> None:
        """
        Start Playwright, Chromium, context, and page.
        """

        if self._page is not None:
            return

        self._playwright = (
            await async_playwright().start()
        )

        executable_path = os.getenv(
            "CUA_CHROMIUM_PATH"
        )

        launch_args: dict[str, Any] = {
            "headless": self.headless,
            "slow_mo": self.slow_mo_ms,
        }

        if executable_path:
            launch_args[
                "executable_path"
            ] = executable_path

        self._browser = (
            await self._playwright.chromium.launch(
                **launch_args
            )
        )

        self._context = (
            await self._browser.new_context(
                viewport={
                    "width": 1280,
                    "height": 900,
                }
            )
        )

        self._page = (
            await self._context.new_page()
        )

    async def close(self) -> None:
        """
        Close page/context/browser/Playwright safely.
        """

        if self._context is not None:
            await self._context.close()

        if self._browser is not None:
            await self._browser.close()

        if self._playwright is not None:
            await self._playwright.stop()

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    # ========================================================
    # Navigation
    # ========================================================

    async def navigate(
        self,
        url: str,
    ) -> None:

        page = self._require_page()

        await page.goto(
            url,
            wait_until="domcontentloaded",
        )

    async def reload(self) -> None:
        """
        Reload the current page.

        Later the application profile can use this for bounded
        recovery from SESSION_EXPIRED or TRANSIENT_BUSY.
        """

        page = self._require_page()

        await page.reload(
            wait_until="domcontentloaded"
        )

    # ========================================================
    # Observation
    # ========================================================

    async def observe(
        self,
    ) -> Observation:
        """
        Build a compact semantic representation of the
        currently visible UI.

        We intentionally do not send the entire DOM as the
        default LLM observation.
        """

        page = self._require_page()

        title = await page.title()

        body = page.locator("body")

        try:
            visible_text = (
                await body.inner_text()
            )
        except Exception:
            visible_text = ""

        # Avoid sending arbitrarily huge UI dumps later.
        visible_text = visible_text[:15000]

        controls = await self._observe_controls()

        aria_snapshot: str | None = None

        try:
            aria_snapshot = (
                await body.aria_snapshot()
            )

            if aria_snapshot:
                aria_snapshot = (
                    aria_snapshot[:15000]
                )

        except Exception:
            # aria_snapshot may not be available on every
            # Playwright/browser version. The observation
            # remains useful without it.
            aria_snapshot = None

        dialog_text = (
            await self._dialog_text()
        )

        return Observation(
            url=page.url,
            title=title,
            visible_text=visible_text,
            aria_snapshot=aria_snapshot,
            controls=controls,
            dialog_text=dialog_text,
        )

    async def _observe_controls(
        self,
    ) -> list[ObservedControl]:
        """
        Collect a compact representation of interactive
        controls visible on the current page.
        """

        page = self._require_page()

        locator = page.locator(
            (
                "input, "
                "button, "
                "select, "
                "textarea, "
                "a[href], "
                "[role]"
            )
        )

        raw_controls = await locator.evaluate_all(
            """
            elements => {
                function isVisible(el) {
                    const style =
                        window.getComputedStyle(el);

                    if (
                        style.display === "none" ||
                        style.visibility === "hidden"
                    ) {
                        return false;
                    }

                    const rect =
                        el.getBoundingClientRect();

                    return (
                        rect.width > 0 &&
                        rect.height > 0
                    );
                }

                function inferredRole(el) {
                    const explicit =
                        el.getAttribute("role");

                    if (explicit) {
                        return explicit;
                    }

                    const tag =
                        el.tagName.toLowerCase();

                    if (tag === "button") {
                        return "button";
                    }

                    if (
                        tag === "a" &&
                        el.hasAttribute("href")
                    ) {
                        return "link";
                    }

                    if (tag === "select") {
                        return "combobox";
                    }

                    if (tag === "textarea") {
                        return "textbox";
                    }

                    if (tag === "input") {
                        const type = (
                            el.getAttribute("type")
                            || "text"
                        ).toLowerCase();

                        if (
                            type === "button" ||
                            type === "submit" ||
                            type === "reset"
                        ) {
                            return "button";
                        }

                        if (
                            type === "checkbox"
                        ) {
                            return "checkbox";
                        }

                        if (
                            type === "radio"
                        ) {
                            return "radio";
                        }

                        return "textbox";
                    }

                    return null;
                }

                function labelText(el) {
                    if (!el.labels) {
                        return "";
                    }

                    return Array
                        .from(el.labels)
                        .map(label =>
                            (
                                label.innerText
                                || ""
                            ).trim()
                        )
                        .filter(Boolean)
                        .join(" ");
                }

                return elements
                    .filter(isVisible)
                    .slice(0, 100)
                    .map(el => {
                        const text = (
                            el.innerText
                            || el.textContent
                            || ""
                        ).trim();

                        const placeholder =
                            el.getAttribute(
                                "placeholder"
                            );

                        const ariaLabel =
                            el.getAttribute(
                                "aria-label"
                            );

                        const labels =
                            labelText(el);

                        const name = (
                            ariaLabel
                            || labels
                            || text
                            || placeholder
                            || el.getAttribute("name")
                            || null
                        );

                        return {
                            tag:
                                el.tagName
                                    .toLowerCase(),

                            role:
                                inferredRole(el),

                            name:
                                name,

                            text:
                                text
                                    ? text.slice(0, 500)
                                    : null,

                            placeholder:
                                placeholder,

                            input_type:
                                el.getAttribute(
                                    "type"
                                ),

                            disabled:
                                Boolean(
                                    el.disabled
                                    || el.getAttribute(
                                        "aria-disabled"
                                    ) === "true"
                                )
                        };
                    });
            }
            """
        )

        return [
            ObservedControl(
                tag=item["tag"],
                role=item.get("role"),
                name=item.get("name"),
                text=item.get("text"),
                placeholder=item.get(
                    "placeholder"
                ),
                input_type=item.get(
                    "input_type"
                ),
                disabled=item.get(
                    "disabled",
                    False,
                ),
            )
            for item in raw_controls
        ]

    async def _dialog_text(
        self,
    ) -> str | None:
        """
        Return visible dialog/modal text if present.

        Our synthetic app uses `.modal`, while real
        applications may use dialog or role=dialog.
        """

        page = self._require_page()

        dialogs = page.locator(
            (
                "dialog:visible, "
                "[role='dialog']:visible, "
                ".modal:visible"
            )
        )

        count = await dialogs.count()

        if count == 0:
            return None

        texts = await dialogs.all_inner_texts()

        cleaned = [
            text.strip()
            for text in texts
            if text.strip()
        ]

        if not cleaned:
            return None

        return "\n\n".join(
            cleaned[:3]
        )

    # ========================================================
    # Locator construction
    # ========================================================

    def _scope_for_candidate(
        self,
        candidate: LocatorCandidate,
    ):
        """
        Return Page or FrameLocator depending on whether the
        recorded locator includes a frame hint.

        frame_hint is treated as a frame selector.
        """

        page = self._require_page()

        if candidate.frame_hint:
            return page.frame_locator(
                candidate.frame_hint
            )

        return page

    def _locator_from_candidate(
        self,
        candidate: LocatorCandidate,
    ) -> Locator:
        """
        Convert one typed locator candidate into a concrete
        Playwright locator.
        """

        scope = self._scope_for_candidate(
            candidate
        )

        # ----------------------------------------------------
        # Accessible role
        # ----------------------------------------------------

        if candidate.kind == LocatorKind.ROLE:

            if not candidate.role:
                raise UnsupportedSurfaceOperation(
                    "ROLE locator requires 'role'."
                )

            if candidate.name is not None:
                return scope.get_by_role(
                    candidate.role,
                    name=candidate.name,
                    exact=candidate.exact,
                )

            return scope.get_by_role(
                candidate.role
            )

        # ----------------------------------------------------
        # Associated label
        # ----------------------------------------------------

        if candidate.kind == LocatorKind.LABEL:

            if candidate.value is None:
                raise UnsupportedSurfaceOperation(
                    "LABEL locator requires 'value'."
                )

            return scope.get_by_label(
                candidate.value,
                exact=candidate.exact,
            )

        # ----------------------------------------------------
        # Visible text
        # ----------------------------------------------------

        if candidate.kind == LocatorKind.TEXT:

            if candidate.value is None:
                raise UnsupportedSurfaceOperation(
                    "TEXT locator requires 'value'."
                )

            return scope.get_by_text(
                candidate.value,
                exact=candidate.exact,
            )

        # ----------------------------------------------------
        # Placeholder
        # ----------------------------------------------------

        if (
            candidate.kind
            == LocatorKind.PLACEHOLDER
        ):

            if candidate.value is None:
                raise UnsupportedSurfaceOperation(
                    "PLACEHOLDER locator "
                    "requires 'value'."
                )

            return scope.get_by_placeholder(
                candidate.value,
                exact=candidate.exact,
            )

        # ----------------------------------------------------
        # CSS
        # ----------------------------------------------------

        if candidate.kind == LocatorKind.CSS:

            if candidate.value is None:
                raise UnsupportedSurfaceOperation(
                    "CSS locator requires 'value'."
                )

            return scope.locator(
                candidate.value
            )

        # ----------------------------------------------------
        # XPath
        # ----------------------------------------------------

        if candidate.kind == LocatorKind.XPATH:

            if candidate.value is None:
                raise UnsupportedSurfaceOperation(
                    "XPATH locator requires 'value'."
                )

            if candidate.value.startswith(
                "xpath="
            ):
                selector = candidate.value
            else:
                selector = (
                    f"xpath={candidate.value}"
                )

            return scope.locator(
                selector
            )

        # ----------------------------------------------------
        # Contextual/relative target
        # ----------------------------------------------------

        if (
            candidate.kind
            == LocatorKind.RELATIVE_TEXT
        ):
            return self._relative_locator(
                candidate
            )

        raise UnsupportedSurfaceOperation(
            (
                "Unsupported locator kind: "
                f"{candidate.kind}"
            )
        )

    def _relative_locator(
    self,
    candidate: LocatorCandidate,
) -> Locator:
        """
    Build a contextual locator.

    Examples:

    1. Find a control inside the same row:

        reference_text = "Savings"
        relation = "same_row"
        role = "link"
        name = "View"

        means:

        find the table row containing Savings,
        then find the View link inside that row.

    2. Extract a structural value from the same row:

        reference_text = "Current Balance"
        relation = "same_row"
        value = None

        means:

        find the row containing Current Balance,
        then return the data cell (<td>) from that row.
    """

    # --------------------------------------------------------
    # Reference text is required
    # --------------------------------------------------------

        if not candidate.reference_text:
            raise UnsupportedSurfaceOperation(
            (
                "RELATIVE_TEXT requires "
                "'reference_text'."
            )
        )

    # --------------------------------------------------------
    # Determine page/frame scope
    # --------------------------------------------------------

        scope = self._scope_for_candidate(
        candidate
    )

    # Find the stable reference/anchor text.
        reference = scope.get_by_text(
        candidate.reference_text,
        exact=candidate.exact,
    )

    # --------------------------------------------------------
    # Determine contextual container
    # --------------------------------------------------------

        if (
        candidate.relation
        == "same_row"
    ):

            container = reference.locator(
                "xpath=ancestor::tr[1]"
            )

        elif (
            candidate.relation
            == "same_form"
        ):

            container = reference.locator(
            "xpath=ancestor::form[1]"
        )

        elif (
            candidate.relation
            == "same_container"
        ):

            container = reference.locator(
            "xpath=.."
        )

        else:
            raise UnsupportedSurfaceOperation(
            (
                "Unsupported relative "
                "relation: "
                f"{candidate.relation}"
            )
        )

    # --------------------------------------------------------
    # Case 1:
    # Find a role-based control inside the container
    # --------------------------------------------------------

        if candidate.role:

            if (
                candidate.name
                is not None
            ):
                return container.get_by_role(
                    candidate.role,
                    name=candidate.name,
                    exact=candidate.exact,
            )

            return container.get_by_role(
            candidate.role
        )

    # --------------------------------------------------------
    # Case 2:
    # Structural table-row extraction
    # --------------------------------------------------------
    #
    # Example HTML:
    #
    # <tr>
    #     <th>Current Balance</th>
    #     <td>$8,421.22</td>
    # </tr>
    #
    # Candidate:
    #
    # reference_text = "Current Balance"
    # relation = "same_row"
    # value = None
    #
    # We return the direct <td> child instead of locating
    # the dynamic balance text itself.
    #
    # resolve_target() will still enforce uniqueness, so
    # ambiguous rows fail closed rather than selecting
    # an arbitrary cell.
    # --------------------------------------------------------

        if (
            candidate.relation
            == "same_row"
            and candidate.value is None
            and candidate.name is None
        ):
            return container.locator(
                "xpath=./td"
            )

    # --------------------------------------------------------
    # Case 3:
    # Find explicit target text inside contextual container
    # --------------------------------------------------------

        target_text = (
            candidate.value
            or candidate.name
        )

        if not target_text:
            raise UnsupportedSurfaceOperation(
            (
                "RELATIVE_TEXT requires "
                "either role/name, "
                "target value, or a "
                "supported structural "
                "same_row extraction."
            )
        )

        return container.get_by_text(
            target_text,
            exact=candidate.exact,
        )

    # ========================================================
    # Target resolution
    # ========================================================

    async def resolve_target(
        self,
        target: TargetDescriptor,
    ) -> ResolvedTarget:
        """
        Try locator candidates in deterministic order.

        A candidate with:
            0 matches -> try next candidate
            1 match   -> use it
            >1 match  -> remember ambiguity and try a later,
                         potentially more-specific candidate

        If no unique locator exists, fail rather than using
        `.first()`.
        """

        if not target.locators:
            raise TargetNotFoundError(
                target
            )

        first_ambiguity: (
            tuple[
                LocatorCandidate,
                int,
            ]
            | None
        ) = None

        for index, candidate in enumerate(
            target.locators
        ):

            locator = (
                self._locator_from_candidate(
                    candidate
                )
            )

            count = await locator.count()

            if count == 0:
                continue

            if count > 1:

                if first_ambiguity is None:
                    first_ambiguity = (
                        candidate,
                        count,
                    )

                # Do not choose `.first()`.
                # A later recorded candidate may be more
                # specific, so continue deterministically.
                continue

            info = (
                await self._resolved_target_info(
                    locator
                )
            )

            return ResolvedTarget(
                descriptor=target,
                candidate=candidate,
                candidate_index=index,
                info=info,
                backend_ref=locator,
            )

        if first_ambiguity is not None:

            candidate, match_count = (
                first_ambiguity
            )

            raise TargetAmbiguousError(
                target=target,
                candidate=candidate,
                match_count=match_count,
            )

        raise TargetNotFoundError(
            target
        )

    async def _resolved_target_info(
        self,
        locator: Locator,
    ) -> ResolvedTargetInfo:
        """
        Read actual live semantics from the resolved element.

        Policy later uses this instead of trusting only the
        LLM's target description.
        """

        data = await locator.evaluate(
            """
            el => {
                const tag =
                    el.tagName.toLowerCase();

                const text = (
                    el.innerText
                    || el.textContent
                    || ""
                ).trim();

                const ariaLabel =
                    el.getAttribute("aria-label");

                let labels = "";

                if (el.labels) {
                    labels = Array
                        .from(el.labels)
                        .map(label =>
                            (
                                label.innerText
                                || ""
                            ).trim()
                        )
                        .filter(Boolean)
                        .join(" ");
                }

                function inferRole() {
                    const explicit =
                        el.getAttribute("role");

                    if (explicit) {
                        return explicit;
                    }

                    if (tag === "button") {
                        return "button";
                    }

                    if (
                        tag === "a" &&
                        el.hasAttribute("href")
                    ) {
                        return "link";
                    }

                    if (tag === "select") {
                        return "combobox";
                    }

                    if (
                        tag === "textarea"
                    ) {
                        return "textbox";
                    }

                    if (tag === "input") {
                        const type = (
                            el.getAttribute("type")
                            || "text"
                        ).toLowerCase();

                        if (
                            type === "button" ||
                            type === "submit" ||
                            type === "reset"
                        ) {
                            return "button";
                        }

                        if (
                            type === "checkbox"
                        ) {
                            return "checkbox";
                        }

                        if (
                            type === "radio"
                        ) {
                            return "radio";
                        }

                        return "textbox";
                    }

                    return null;
                }

                const placeholder =
                    el.getAttribute(
                        "placeholder"
                    );

                const name = (
                    ariaLabel
                    || labels
                    || text
                    || placeholder
                    || el.getAttribute("name")
                    || null
                );

                return {
                    tag: tag,
                    role: inferRole(),
                    text: text || null,
                    name: name,
                    aria_label:
                        ariaLabel,
                    placeholder:
                        placeholder,
                    href:
                        tag === "a"
                        ? el.href
                        : null
                };
            }
            """
        )

        return ResolvedTargetInfo(
            tag=data.get("tag"),
            role=data.get("role"),
            text=data.get("text"),
            name=data.get("name"),
            aria_label=data.get(
                "aria_label"
            ),
            placeholder=data.get(
                "placeholder"
            ),
            href=data.get("href"),
        )

    # ========================================================
    # Actions
    # ========================================================

    @staticmethod
    def _locator_from_resolved(
        target: ResolvedTarget,
    ) -> Locator:

        locator = target.backend_ref

        if not isinstance(
            locator,
            Locator,
        ):
            raise UnsupportedSurfaceOperation(
                (
                    "Resolved target does not "
                    "contain a Playwright Locator."
                )
            )

        return locator

    async def click(
        self,
        target: ResolvedTarget,
    ) -> None:

        locator = (
            self._locator_from_resolved(
                target
            )
        )

        await locator.click()

    async def fill(
        self,
        target: ResolvedTarget,
        value: str,
    ) -> None:

        locator = (
            self._locator_from_resolved(
                target
            )
        )

        await locator.fill(value)

    async def select(
        self,
        target: ResolvedTarget,
        value: str,
    ) -> None:

        locator = (
            self._locator_from_resolved(
                target
            )
        )

        # Our capability semantics treat the supplied value
        # as the visible option label.
        await locator.select_option(
            label=value
        )

    async def extract_text(
        self,
        target: ResolvedTarget,
    ) -> str:

        locator = (
            self._locator_from_resolved(
                target
            )
        )

        tag_name = await locator.evaluate(
            "el => el.tagName.toLowerCase()"
        )

        if tag_name in {
            "input",
            "textarea",
            "select",
        }:
            try:
                return (
                    await locator.input_value()
                ).strip()
            except Exception:
                pass

        try:
            return (
                await locator.inner_text()
            ).strip()

        except Exception:

            text = (
                await locator.text_content()
            )

            return (
                text
                or ""
            ).strip()

    # ========================================================
    # Waiting / conditions
    # ========================================================

    async def wait(
        self,
        milliseconds: int,
    ) -> None:

        page = self._require_page()

        await page.wait_for_timeout(
            milliseconds
        )

    async def _target_exists(
        self,
        target: TargetDescriptor,
    ) -> bool:
        """
        Determine whether at least one candidate currently
        matches an element.

        Uniqueness is not required for presence checks.
        """

        for candidate in target.locators:

            locator = (
                self._locator_from_candidate(
                    candidate
                )
            )

            if await locator.count() > 0:
                return True

        return False

    async def _condition_once(
        self,
        condition: Condition,
        outputs: Mapping[str, Any] | None,
    ) -> bool:

        page = self._require_page()

        if (
            condition.type
            == ConditionType.TEXT_PRESENT
        ):
            if condition.value is None:
                return False

            body_text = (
                await page.locator(
                    "body"
                ).inner_text()
            )

            return (
                condition.value
                in body_text
            )

        if (
            condition.type
            == ConditionType.TEXT_ABSENT
        ):
            if condition.value is None:
                return False

            body_text = (
                await page.locator(
                    "body"
                ).inner_text()
            )

            return (
                condition.value
                not in body_text
            )

        if (
            condition.type
            == ConditionType.ELEMENT_PRESENT
        ):
            if condition.target is None:
                return False

            return await self._target_exists(
                condition.target
            )

        if (
            condition.type
            == ConditionType.ELEMENT_ABSENT
        ):
            if condition.target is None:
                return False

            return not await self._target_exists(
                condition.target
            )

        if (
            condition.type
            == ConditionType.URL_MATCHES
        ):
            if condition.value is None:
                return False

            # In schema version 1.0 URL_MATCHES means
            # deterministic substring matching.
            return (
                condition.value
                in page.url
            )

        if (
            condition.type
            == ConditionType.OUTPUT_EXISTS
        ):
            if (
                outputs is None
                or condition.output_name is None
            ):
                return False

            return (
                condition.output_name
                in outputs
                and outputs[
                    condition.output_name
                ]
                is not None
            )

        raise UnsupportedSurfaceOperation(
            (
                "Unsupported condition type: "
                f"{condition.type}"
            )
        )

    async def check_condition(
        self,
        condition: Condition,
        outputs: Mapping[str, Any] | None = None,
    ) -> bool:
        """
        Poll a condition until it succeeds or its bounded
        timeout expires.
        """

        loop = asyncio.get_running_loop()

        deadline = (
            loop.time()
            + condition.timeout_ms / 1000
        )

        while True:

            if await self._condition_once(
                condition,
                outputs,
            ):
                return True

            if loop.time() >= deadline:
                return False

            await asyncio.sleep(
                0.1
            )

    # ========================================================
    # Evidence
    # ========================================================

    async def capture_screenshot(
        self,
        path: Path,
        *,
        mask_sensitive: bool = True,
    ) -> Path:
        """
        Capture screenshot evidence.

        Elements marked with:

            data-sensitive="true"

        are masked when mask_sensitive=True.
        """

        page = self._require_page()

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if mask_sensitive:

            sensitive_elements = (
                page.locator(
                    SENSITIVE_DOM_SELECTOR
                )
            )

            await page.screenshot(
                path=str(path),
                full_page=True,
                mask=[
                    sensitive_elements
                ],
            )

        else:

            await page.screenshot(
                path=str(path),
                full_page=True,
            )

        return path

    async def structure_snapshot(
        self,
    ) -> str | None:
        """
        Capture HTML evidence and sanitize sensitive values
        before returning it to the evidence layer.
        """

        page = self._require_page()

        html = await page.content()

        return self.redactor.dom(
            html
        )