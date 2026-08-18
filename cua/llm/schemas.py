from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from cua.models import (
    ActionType,
    AgentAction,
    Condition,
    ConditionType,
    LocatorKind,
    RiskLevel,
    TargetDescriptor,
)


class StrictLLMModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )


class LLMProposedLocator(
    StrictLLMModel
):
    kind: LocatorKind

    role: str | None
    name: str | None
    value: str | None

    reference_text: str | None

    relation: Literal[
        "same_row",
        "same_form",
        "same_container",
    ] | None

    exact: bool

    frame_hint: str | None

    description: str | None


class LLMProposedTarget(
    StrictLLMModel
):
    description: str = Field(
        min_length=1,
        max_length=300,
    )

    locators: list[
        LLMProposedLocator
    ]


class LLMProposedCondition(
    StrictLLMModel
):
    type: ConditionType

    value: str | None

    target: (
        LLMProposedTarget
        | None
    )

    output_name: str | None

    timeout_ms: int = Field(
        ge=0,
        le=30_000,
    )


class LLMActionProposal(
    StrictLLMModel
):
    action: ActionType

    target: (
        LLMProposedTarget
        | None
    )

    value: str | None

    output_name: str | None

    reason: str = Field(
        min_length=1,
        max_length=300,
    )

    success_condition: (
        LLMProposedCondition
        | None
    )

    risk_hint: RiskLevel

    def to_agent_action(
        self,
    ) -> AgentAction:

        target: (
            TargetDescriptor
            | None
        ) = None

        if self.target is not None:
            target = (
                TargetDescriptor
                .model_validate(
                    self.target.model_dump(
                        mode="python"
                    )
                )
            )

        success_condition: (
            Condition
            | None
        ) = None

        if (
            self.success_condition
            is not None
        ):
            success_condition = (
                Condition.model_validate(
                    self
                    .success_condition
                    .model_dump(
                        mode="python"
                    )
                )
            )

        return AgentAction(
            action=self.action,
            target=target,
            value=self.value,
            output_name=(
                self.output_name
            ),
            reason=self.reason,
            success_condition=(
                success_condition
            ),
            risk_hint=self.risk_hint,
        )