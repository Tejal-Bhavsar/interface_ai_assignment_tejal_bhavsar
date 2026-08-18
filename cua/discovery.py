from __future__ import annotations

from typing import Any
from uuid import uuid4

from cua.discovery_evidence import (
    DiscoveryEvidenceRecorder,
)

from cua.llm.base import (
    ActionProvider,
    LLMProviderError,
)

from cua.models import (
    ActionType,
    AgentAction,
    DiscoveryRunResult,
    DiscoveryStatus,
    DiscoveryStepRecord,
    PolicyDecision,
)

from cua.policy import (
    PolicyEngine,
)

from cua.surface import (
    ComputerSurface,
    ResolvedTarget,
    SurfaceError,
    TargetResolutionError,
)


TARGET_ACTIONS = {
    ActionType.CLICK,
    ActionType.FILL,
    ActionType.SELECT,
    ActionType.EXTRACT,
}


class DiscoveryExecutionError(
    RuntimeError
):
    """
    Raised for invalid runtime action semantics.

    Example:
        WAIT with value="forever"
    """

    pass


class DiscoveryEngine:
    """
    Genuine observe -> decide -> policy -> act discovery loop.

    The engine does not own browser lifecycle.

    The caller owns ComputerSurface.start()/close(), which is
    important because the same live session will later be
    handed to a human without destroying BrowserContext/Page.
    """

    def __init__(
        self,
        *,
        surface: ComputerSurface,
        provider: ActionProvider,
        policy: PolicyEngine,
        evidence: (
            DiscoveryEvidenceRecorder
            | None
        ) = None,
        max_steps: int = 12,
        max_wait_ms: int = 10_000,
    ):
        if max_steps < 1:
            raise ValueError(
                "max_steps must be >= 1"
            )

        if max_wait_ms < 0:
            raise ValueError(
                "max_wait_ms must be >= 0"
            )

        self.surface = surface

        self.provider = provider

        self.policy = policy

        self.evidence = evidence

        self.max_steps = max_steps

        self.max_wait_ms = (
            max_wait_ms
        )

    @staticmethod
    def _policy_record_value(
        evaluation,
    ):
        """
        DiscoveryStepRecord uses the policy snapshot schema from
        cua.models, while the runtime PolicyEngine returns the
        richer cua.policy.PolicyEvaluation model.

        Convert through a plain JSON-compatible dict at this
        persistence boundary so Pydantic validates it against the
        DiscoveryStepRecord schema instead of requiring the exact
        same Python class identity.
        """

        if evaluation is None:
            return None

        if hasattr(
            evaluation,
            "model_dump",
        ):
            return evaluation.model_dump(
                mode="json"
            )

        return evaluation

    # ========================================================
    # Result helper
    # ========================================================

    def _result(
        self,
        *,
        run_id: str,
        goal: str,
        entry_url: str,
        status: DiscoveryStatus,
        steps: list[
            DiscoveryStepRecord
        ],
        outputs: dict[
            str,
            Any,
        ],
        message: str,
    ) -> DiscoveryRunResult:

        result = DiscoveryRunResult(
            run_id=run_id,
            goal=goal,
            entry_url=entry_url,
            provider=(
                self.provider
                .provider_alias
            ),
            model=(
                self.provider
                .model_name
            ),
            status=status,
            steps=steps,
            outputs=outputs,
            message=message,
        )

        if self.evidence is not None:
            self.evidence.save_result(
                result
            )

        return result

    # ========================================================
    # Resolution
    # ========================================================

    async def _resolve_target(
        self,
        action: AgentAction,
    ) -> ResolvedTarget | None:
        """
        Resolve a live control when the action requires one.

        COMPLETE, WAIT, NAVIGATE, etc. do not necessarily
        require a target.
        """

        if (
            action.action
            not in TARGET_ACTIONS
        ):
            return None

        if action.target is None:
            raise DiscoveryExecutionError(
                (
                    f"{action.action.value} "
                    "requires a target."
                )
            )

        if not action.target.locators:
            raise DiscoveryExecutionError(
                (
                    f"{action.action.value} "
                    "requires at least one "
                    "locator candidate."
                )
            )

        return (
            await self.surface
            .resolve_target(
                action.target
            )
        )

    # ========================================================
    # Primitive execution
    # ========================================================

    async def _execute_action(
        self,
        *,
        action: AgentAction,
        resolved: (
            ResolvedTarget
            | None
        ),
        outputs: dict[
            str,
            Any,
        ],
    ) -> tuple[
        str | None,
        Any | None,
        bool | None,
    ]:
        """
        Execute one already-authorized AgentAction.

        Returns:

            extracted_output_name
            extracted_output_value
            assertion_result
        """

        # ----------------------------------------------------
        # NAVIGATE
        # ----------------------------------------------------

        if (
            action.action
            == ActionType.NAVIGATE
        ):
            if (
                not isinstance(
                    action.value,
                    str,
                )
                or not action.value.strip()
            ):
                raise (
                    DiscoveryExecutionError(
                        (
                            "navigate requires "
                            "a non-empty URL "
                            "string."
                        )
                    )
                )

            await self.surface.navigate(
                action.value
            )

            return None, None, None

        # ----------------------------------------------------
        # CLICK
        # ----------------------------------------------------

        if (
            action.action
            == ActionType.CLICK
        ):
            if resolved is None:
                raise (
                    DiscoveryExecutionError(
                        (
                            "click has no "
                            "resolved target."
                        )
                    )
                )

            await self.surface.click(
                resolved
            )

            return None, None, None

        # ----------------------------------------------------
        # FILL
        # ----------------------------------------------------

        if (
            action.action
            == ActionType.FILL
        ):
            if resolved is None:
                raise (
                    DiscoveryExecutionError(
                        (
                            "fill has no "
                            "resolved target."
                        )
                    )
                )

            if not isinstance(
                action.value,
                str,
            ):
                raise (
                    DiscoveryExecutionError(
                        (
                            "fill requires "
                            "a string value."
                        )
                    )
                )

            await self.surface.fill(
                resolved,
                action.value,
            )

            return None, None, None

        # ----------------------------------------------------
        # SELECT
        # ----------------------------------------------------

        if (
            action.action
            == ActionType.SELECT
        ):
            if resolved is None:
                raise (
                    DiscoveryExecutionError(
                        (
                            "select has no "
                            "resolved target."
                        )
                    )
                )

            if not isinstance(
                action.value,
                str,
            ):
                raise (
                    DiscoveryExecutionError(
                        (
                            "select requires "
                            "a string value."
                        )
                    )
                )

            await self.surface.select(
                resolved,
                action.value,
            )

            return None, None, None

        # ----------------------------------------------------
        # EXTRACT
        # ----------------------------------------------------

        if (
            action.action
            == ActionType.EXTRACT
        ):
            if resolved is None:
                raise (
                    DiscoveryExecutionError(
                        (
                            "extract has no "
                            "resolved target."
                        )
                    )
                )

            if not action.output_name:
                raise (
                    DiscoveryExecutionError(
                        (
                            "extract requires "
                            "output_name."
                        )
                    )
                )

            value = (
                await self.surface
                .extract_text(
                    resolved
                )
            )

            outputs[
                action.output_name
            ] = value

            return (
                action.output_name,
                value,
                None,
            )

        # ----------------------------------------------------
        # WAIT
        # ----------------------------------------------------

        if (
            action.action
            == ActionType.WAIT
        ):
            raw_value = (
                action.value
                if action.value
                is not None
                else "500"
            )

            try:
                milliseconds = int(
                    raw_value
                )

            except (
                TypeError,
                ValueError,
            ) as exc:
                raise (
                    DiscoveryExecutionError(
                        (
                            "wait value must "
                            "be milliseconds."
                        )
                    )
                ) from exc

            if (
                milliseconds < 0
                or milliseconds
                > self.max_wait_ms
            ):
                raise (
                    DiscoveryExecutionError(
                        (
                            "wait must be "
                            "between 0 and "
                            f"{self.max_wait_ms} "
                            "milliseconds."
                        )
                    )
                )

            await self.surface.wait(
                milliseconds
            )

            return None, None, None

        # ----------------------------------------------------
        # ASSERT
        # ----------------------------------------------------

        if (
            action.action
            == ActionType.ASSERT
        ):
            if (
                action.success_condition
                is None
            ):
                raise (
                    DiscoveryExecutionError(
                        (
                            "assert requires "
                            "success_condition."
                        )
                    )
                )

            passed = (
                await self.surface
                .check_condition(
                    (
                        action
                        .success_condition
                    ),
                    outputs=outputs,
                )
            )

            return (
                None,
                None,
                passed,
            )

        # COMPLETE and REQUEST_HUMAN are handled before this
        # method is called.

        raise DiscoveryExecutionError(
            (
                "Unsupported runtime "
                f"action: "
                f"{action.action.value}"
            )
        )

    # ========================================================
    # Main discovery loop
    # ========================================================

    async def run(
        self,
        *,
        goal: str,
        entry_url: str,
    ) -> DiscoveryRunResult:
        """
        Execute one genuine discovery run.

        The caller must already have started the surface.

        Example:

            async with PlaywrightSurface() as surface:
                result = await engine.run(...)
        """

        run_id = (
            "disc_"
            + uuid4().hex[:12]
        )

        if self.evidence is not None:
            self.evidence.start_run(
                run_id=run_id,
                goal=goal,
                entry_url=entry_url,
                provider=(
                    self.provider
                    .provider_alias
                ),
                model=(
                    self.provider
                    .model_name
                ),
            )

        steps: list[
            DiscoveryStepRecord
        ] = []

        outputs: dict[
            str,
            Any,
        ] = {}

        previous_actions: list[
            AgentAction
        ] = []

        # ----------------------------------------------------
        # Initial target navigation safety
        # ----------------------------------------------------

        initial_url_policy = (
            self.policy
            .evaluate_navigation(
                entry_url
            )
        )

        if self.evidence is not None:
            self.evidence.record_policy(
                step_index=0,
                evaluation=(
                    initial_url_policy
                ),
                phase=(
                    "entry_navigation"
                ),
            )

        if (
            initial_url_policy.decision
            == PolicyDecision.BLOCK
        ):
            return self._result(
                run_id=run_id,
                goal=goal,
                entry_url=entry_url,
                status=(
                    DiscoveryStatus
                    .POLICY_BLOCKED
                ),
                steps=steps,
                outputs=outputs,
                message=(
                    "Entry URL blocked by "
                    "policy: "
                    f"{initial_url_policy.reason}"
                ),
            )

        if (
            initial_url_policy.decision
            == (
                PolicyDecision
                .REQUIRE_HUMAN
            )
        ):
            return self._result(
                run_id=run_id,
                goal=goal,
                entry_url=entry_url,
                status=(
                    DiscoveryStatus
                    .INTERVENTION_REQUIRED
                ),
                steps=steps,
                outputs=outputs,
                message=(
                    "Entry navigation "
                    "requires human "
                    "authorization."
                ),
            )

        try:
            await self.surface.navigate(
                entry_url
            )

        except Exception as exc:
            return self._result(
                run_id=run_id,
                goal=goal,
                entry_url=entry_url,
                status=(
                    DiscoveryStatus.FAILED
                ),
                steps=steps,
                outputs=outputs,
                message=(
                    "Could not navigate to "
                    f"entry URL: {exc}"
                ),
            )

        # ----------------------------------------------------
        # Genuine observe -> decide -> act loop
        # ----------------------------------------------------

        for step_index in range(
            1,
            self.max_steps + 1,
        ):

            # =================================================
            # OBSERVE
            # =================================================

            try:
                observation = (
                    await self.surface
                    .observe()
                )

            except Exception as exc:
                return self._result(
                    run_id=run_id,
                    goal=goal,
                    entry_url=entry_url,
                    status=(
                        DiscoveryStatus
                        .FAILED
                    ),
                    steps=steps,
                    outputs=outputs,
                    message=(
                        "Observation failed "
                        f"at step "
                        f"{step_index}: "
                        f"{exc}"
                    ),
                )

            url_before = (
                self.surface.current_url
            )

            if self.evidence is not None:
                self.evidence.record_observation(
                    step_index=(
                        step_index
                    ),
                    observation=(
                        observation
                    ),
                )

            # =================================================
            # DECIDE
            # =================================================

            try:
                action = (
                    await self.provider
                    .decide(
                        goal=goal,
                        observation=(
                            observation
                        ),
                        previous_actions=(
                            previous_actions
                        ),
                        step_index=(
                            step_index
                        ),
                        max_steps=(
                            self.max_steps
                        ),
                    )
                )

            except LLMProviderError as exc:
                return self._result(
                    run_id=run_id,
                    goal=goal,
                    entry_url=entry_url,
                    status=(
                        DiscoveryStatus
                        .FAILED
                    ),
                    steps=steps,
                    outputs=outputs,
                    message=(
                        "LLM decision failed "
                        f"at step "
                        f"{step_index}: "
                        f"{exc}"
                    ),
                )

            if self.evidence is not None:
                self.evidence.record_llm_decision(
                    step_index=(
                        step_index
                    ),
                    action=action,
                )

            # =================================================
            # RESOLVE LIVE TARGET
            # =================================================

            resolved: (
                ResolvedTarget
                | None
            ) = None

            try:
                resolved = (
                    await self
                    ._resolve_target(
                        action
                    )
                )

            except (
                TargetResolutionError,
                DiscoveryExecutionError,
            ) as exc:

                steps.append(
                    DiscoveryStepRecord(
                        step_index=(
                            step_index
                        ),
                        url_before=(
                            url_before
                        ),
                        url_after=(
                            self.surface
                            .current_url
                        ),
                        action=action,
                    )
                )

                return self._result(
                    run_id=run_id,
                    goal=goal,
                    entry_url=entry_url,
                    status=(
                        DiscoveryStatus
                        .FAILED
                    ),
                    steps=steps,
                    outputs=outputs,
                    message=(
                        "Target resolution "
                        f"failed at step "
                        f"{step_index}: "
                        f"{exc}"
                    ),
                )

            if (
                self.evidence is not None
                and resolved is not None
            ):
                self.evidence.record_target_resolution(
                    step_index=(
                        step_index
                    ),
                    resolved_info=(
                        resolved.info
                    ),
                )

            # =================================================
            # POLICY
            # =================================================

            try:
                if (
                    action.action
                    == ActionType.NAVIGATE
                ):
                    if not isinstance(
                        action.value,
                        str,
                    ):
                        raise (
                            DiscoveryExecutionError(
                                (
                                    "navigate requires "
                                    "a URL string."
                                )
                            )
                        )

                    policy_evaluation = (
                        self.policy
                        .evaluate_navigation(
                            action.value
                        )
                    )

                elif (
                    action.action
                    in {
                        ActionType.COMPLETE,
                        ActionType.REQUEST_HUMAN,
                    }
                ):
                    # COMPLETE and REQUEST_HUMAN are discovery
                    # control-flow decisions, not live browser
                    # mutations. Ensure only that the current
                    # session remains inside the allowlist.
                    policy_evaluation = (
                        self.policy
                        .evaluate_current_url(
                            url_before
                        )
                    )

                else:
                    destination_url = None

                    if (
                        action.action
                        == ActionType.CLICK
                        and resolved
                        is not None
                    ):
                        destination_url = (
                            resolved
                            .info
                            .href
                        )

                    policy_evaluation = (
                        self.policy
                        .evaluate_action(
                            action=(
                                action.action
                            ),

                            current_url=(
                                url_before
                            ),

                            risk_level=(
                                action.risk_hint
                            ),

                            target_description=(
                                action
                                .target
                                .description
                                if (
                                    action.target
                                    is not None
                                )
                                else None
                            ),

                            resolved_info=(
                                resolved.info
                                if (
                                    resolved
                                    is not None
                                )
                                else None
                            ),

                            destination_url=(
                                destination_url
                            ),
                        )
                    )

                if self.evidence is not None:
                    self.evidence.record_policy(
                        step_index=(
                            step_index
                        ),
                        evaluation=(
                            policy_evaluation
                        ),
                        phase=(
                            "pre_action"
                        ),
                    )

            except Exception as exc:
                return self._result(
                    run_id=run_id,
                    goal=goal,
                    entry_url=entry_url,
                    status=(
                        DiscoveryStatus
                        .FAILED
                    ),
                    steps=steps,
                    outputs=outputs,
                    message=(
                        "Policy evaluation "
                        f"failed at step "
                        f"{step_index}: "
                        f"{exc}"
                    ),
                )

            # =================================================
            # BLOCK
            # =================================================

            if (
                policy_evaluation.decision
                == PolicyDecision.BLOCK
            ):
                steps.append(
                    DiscoveryStepRecord(
                        step_index=(
                            step_index
                        ),
                        url_before=(
                            url_before
                        ),
                        url_after=(
                            self.surface
                            .current_url
                        ),
                        action=action,
                        policy_evaluation=(
                            self
                            ._policy_record_value(
                                policy_evaluation
                            )
                        ),
                        resolved_target=(
                            resolved.info
                            if resolved
                            is not None
                            else None
                        ),
                    )
                )

                return self._result(
                    run_id=run_id,
                    goal=goal,
                    entry_url=entry_url,
                    status=(
                        DiscoveryStatus
                        .POLICY_BLOCKED
                    ),
                    steps=steps,
                    outputs=outputs,
                    message=(
                        "Action blocked by "
                        "policy at step "
                        f"{step_index}: "
                        f"{policy_evaluation.reason}"
                    ),
                )

            # =================================================
            # POLICY REQUIRES HUMAN
            # =================================================

            if (
                policy_evaluation.decision
                == (
                    PolicyDecision
                    .REQUIRE_HUMAN
                )
            ):
                steps.append(
                    DiscoveryStepRecord(
                        step_index=(
                            step_index
                        ),
                        url_before=(
                            url_before
                        ),
                        url_after=(
                            self.surface
                            .current_url
                        ),
                        action=action,
                        policy_evaluation=(
                            self
                            ._policy_record_value(
                                policy_evaluation
                            )
                        ),
                        resolved_target=(
                            resolved.info
                            if resolved
                            is not None
                            else None
                        ),
                    )
                )

                return self._result(
                    run_id=run_id,
                    goal=goal,
                    entry_url=entry_url,
                    status=(
                        DiscoveryStatus
                        .INTERVENTION_REQUIRED
                    ),
                    steps=steps,
                    outputs=outputs,
                    message=(
                        "Policy requires "
                        "human intervention "
                        f"at step "
                        f"{step_index}: "
                        f"{policy_evaluation.reason}"
                    ),
                )

            # =================================================
            # MODEL REQUESTS HUMAN
            # =================================================

            if (
                action.action
                == (
                    ActionType
                    .REQUEST_HUMAN
                )
            ):
                steps.append(
                    DiscoveryStepRecord(
                        step_index=(
                            step_index
                        ),
                        url_before=(
                            url_before
                        ),
                        url_after=(
                            self.surface
                            .current_url
                        ),
                        action=action,
                        policy_evaluation=(
                            self
                            ._policy_record_value(
                                policy_evaluation
                            )
                        ),
                    )
                )

                return self._result(
                    run_id=run_id,
                    goal=goal,
                    entry_url=entry_url,
                    status=(
                        DiscoveryStatus
                        .INTERVENTION_REQUIRED
                    ),
                    steps=steps,
                    outputs=outputs,
                    message=(
                        "Model requested "
                        "human intervention: "
                        f"{action.reason}"
                    ),
                )

            # =================================================
            # COMPLETE
            # =================================================

            if (
                action.action
                == ActionType.COMPLETE
            ):
                steps.append(
                    DiscoveryStepRecord(
                        step_index=(
                            step_index
                        ),
                        url_before=(
                            url_before
                        ),
                        url_after=(
                            self.surface
                            .current_url
                        ),
                        action=action,
                        policy_evaluation=(
                            self
                            ._policy_record_value(
                                policy_evaluation
                            )
                        ),
                    )
                )

                return self._result(
                    run_id=run_id,
                    goal=goal,
                    entry_url=entry_url,
                    status=(
                        DiscoveryStatus
                        .COMPLETED
                    ),
                    steps=steps,
                    outputs=outputs,
                    message=(
                        "Discovery completed "
                        "successfully."
                    ),
                )

            # =================================================
            # ACT
            # =================================================

            try:
                (
                    output_name,
                    output_value,
                    assertion_result,
                ) = await self._execute_action(
                    action=action,
                    resolved=resolved,
                    outputs=outputs,
                )

                if self.evidence is not None:
                    self.evidence.record_execution(
                        step_index=(
                            step_index
                        ),
                        action_type=(
                            action
                            .action
                            .value
                        ),
                        url_after=(
                            self.surface
                            .current_url
                        ),
                        output_name=(
                            output_name
                        ),
                        output_value=(
                            output_value
                        ),
                        assertion_result=(
                            assertion_result
                        ),
                    )

            except (
                DiscoveryExecutionError,
                SurfaceError,
                Exception,
            ) as exc:
                steps.append(
                    DiscoveryStepRecord(
                        step_index=(
                            step_index
                        ),
                        url_before=(
                            url_before
                        ),
                        url_after=(
                            self.surface
                            .current_url
                        ),
                        action=action,
                        policy_evaluation=(
                            self
                            ._policy_record_value(
                                policy_evaluation
                            )
                        ),
                        resolved_target=(
                            resolved.info
                            if resolved
                            is not None
                            else None
                        ),
                    )
                )

                return self._result(
                    run_id=run_id,
                    goal=goal,
                    entry_url=entry_url,
                    status=(
                        DiscoveryStatus
                        .FAILED
                    ),
                    steps=steps,
                    outputs=outputs,
                    message=(
                        "Action execution "
                        f"failed at step "
                        f"{step_index}: "
                        f"{exc}"
                    ),
                )

            # =================================================
            # VERIFY ACTION SUCCESS CONDITION
            # =================================================

            success_condition_passed = (
                assertion_result
            )

            if (
                action.action
                != ActionType.ASSERT
                and action.success_condition
                is not None
            ):
                try:
                    success_condition_passed = (
                        await self.surface
                        .check_condition(
                            (
                                action
                                .success_condition
                            ),
                            outputs=outputs,
                        )
                    )

                except Exception as exc:
                    success_condition_passed = (
                        False
                    )

                    steps.append(
                        DiscoveryStepRecord(
                            step_index=(
                                step_index
                            ),
                            url_before=(
                                url_before
                            ),
                            url_after=(
                                self.surface
                                .current_url
                            ),
                            action=action,
                            policy_evaluation=(
                                self
                                ._policy_record_value(
                                    policy_evaluation
                                )
                            ),
                            resolved_target=(
                                resolved.info
                                if resolved
                                is not None
                                else None
                            ),
                            extracted_output_name=(
                                output_name
                            ),
                            extracted_output_value=(
                                output_value
                            ),
                            success_condition_passed=(
                                False
                            ),
                        )
                    )

                    return self._result(
                        run_id=run_id,
                        goal=goal,
                        entry_url=entry_url,
                        status=(
                            DiscoveryStatus
                            .FAILED
                        ),
                        steps=steps,
                        outputs=outputs,
                        message=(
                            "Success-condition "
                            "evaluation failed "
                            f"at step "
                            f"{step_index}: "
                            f"{exc}"
                        ),
                    )

            # ASSERT false or ordinary postcondition false.
            if (
                success_condition_passed
                is False
            ):
                steps.append(
                    DiscoveryStepRecord(
                        step_index=(
                            step_index
                        ),
                        url_before=(
                            url_before
                        ),
                        url_after=(
                            self.surface
                            .current_url
                        ),
                        action=action,
                        policy_evaluation=(
                            self
                            ._policy_record_value(
                                policy_evaluation
                            )
                        ),
                        resolved_target=(
                            resolved.info
                            if resolved
                            is not None
                            else None
                        ),
                        extracted_output_name=(
                            output_name
                        ),
                        extracted_output_value=(
                            output_value
                        ),
                        success_condition_passed=(
                            False
                        ),
                    )
                )

                return self._result(
                    run_id=run_id,
                    goal=goal,
                    entry_url=entry_url,
                    status=(
                        DiscoveryStatus
                        .FAILED
                    ),
                    steps=steps,
                    outputs=outputs,
                    message=(
                        "Action success "
                        "condition failed at "
                        f"step {step_index}."
                    ),
                )

            # =================================================
            # DEFENSE-IN-DEPTH: POST-ACTION URL CHECK
            # =================================================

            url_after = (
                self.surface.current_url
            )

            if url_after:
                post_url_policy = (
                    self.policy
                    .evaluate_current_url(
                        url_after
                    )
                )

                if self.evidence is not None:
                    self.evidence.record_policy(
                        step_index=(
                            step_index
                        ),
                        evaluation=(
                            post_url_policy
                        ),
                        phase=(
                            "post_action_url"
                        ),
                    )

                if (
                    post_url_policy.decision
                    == PolicyDecision.BLOCK
                ):
                    steps.append(
                        DiscoveryStepRecord(
                            step_index=(
                                step_index
                            ),
                            url_before=(
                                url_before
                            ),
                            url_after=(
                                url_after
                            ),
                            action=action,
                            policy_evaluation=(
                                self
                                ._policy_record_value(
                                    policy_evaluation
                                )
                            ),
                            resolved_target=(
                                resolved.info
                                if resolved
                                is not None
                                else None
                            ),
                            extracted_output_name=(
                                output_name
                            ),
                            extracted_output_value=(
                                output_value
                            ),
                            success_condition_passed=(
                                success_condition_passed
                            ),
                        )
                    )

                    return self._result(
                        run_id=run_id,
                        goal=goal,
                        entry_url=entry_url,
                        status=(
                            DiscoveryStatus
                            .POLICY_BLOCKED
                        ),
                        steps=steps,
                        outputs=outputs,
                        message=(
                            "Browser reached a "
                            "URL blocked by "
                            "policy after step "
                            f"{step_index}: "
                            f"{post_url_policy.reason}"
                        ),
                    )

            # =================================================
            # RECORD SUCCESSFUL STEP
            # =================================================

            steps.append(
                DiscoveryStepRecord(
                    step_index=(
                        step_index
                    ),
                    url_before=(
                        url_before
                    ),
                    url_after=(
                        self.surface
                        .current_url
                    ),
                    action=action,
                    policy_evaluation=(
                        self
                        ._policy_record_value(
                            policy_evaluation
                        )
                    ),
                    resolved_target=(
                        resolved.info
                        if resolved
                        is not None
                        else None
                    ),
                    extracted_output_name=(
                        output_name
                    ),
                    extracted_output_value=(
                        output_value
                    ),
                    success_condition_passed=(
                        success_condition_passed
                    ),
                )
            )

            previous_actions.append(
                action
            )

        # ----------------------------------------------------
        # Bounded loop protection
        # ----------------------------------------------------

        return self._result(
            run_id=run_id,
            goal=goal,
            entry_url=entry_url,
            status=(
                DiscoveryStatus
                .MAX_STEPS
            ),
            steps=steps,
            outputs=outputs,
            message=(
                "Discovery reached the "
                f"maximum of "
                f"{self.max_steps} steps "
                "without completing."
            ),
        )