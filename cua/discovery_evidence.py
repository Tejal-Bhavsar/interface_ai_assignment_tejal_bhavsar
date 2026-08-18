from __future__ import annotations

import hashlib
import json
import re

from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from typing import Any


REDACTED = "[REDACTED]"
REDACTED_AMOUNT = "[REDACTED_AMOUNT]"


class DiscoveryEvidenceError(
    RuntimeError
):
    pass


class DiscoveryEvidenceRecorder:
    """
    Persist reviewer-facing evidence for a genuine discovery run.

    We deliberately do NOT persist raw visible page text or raw
    model prompts/responses because they may contain regulated
    financial data. Instead we persist:

      - provider/model identity
      - a fingerprint + compact semantic summary of observations
      - the LLM-decided action
      - resolved target metadata
      - policy decision
      - execution result
      - final DiscoveryRunResult, sanitized

    This is enough to prove observe -> decide -> policy -> act
    without storing raw sensitive UI content.
    """

    def __init__(
        self,
        *,
        root: Path | str,
        sensitive_inputs: (
            dict[str, Any]
            | None
        ) = None,
    ):
        self.root = Path(root)

        self.sensitive_inputs = (
            sensitive_inputs
            or {}
        )

        self.run_id: (
            str | None
        ) = None

        self.run_dir: (
            Path | None
        ) = None

        self._events_path: (
            Path | None
        ) = None

    # ========================================================
    # Helpers
    # ========================================================

    @staticmethod
    def _now() -> str:
        return (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )

    def _require_run_dir(
        self,
    ) -> Path:
        if self.run_dir is None:
            raise (
                DiscoveryEvidenceError(
                    (
                        "Discovery evidence "
                        "run has not started."
                    )
                )
            )

        return self.run_dir

    def _known_sensitive_strings(
        self,
    ) -> list[str]:
        values: list[str] = []

        for value in (
            self.sensitive_inputs
            .values()
        ):
            if value is None:
                continue

            text = str(value)

            if text:
                values.append(
                    text
                )

        return values

    def _sanitize_text(
        self,
        value: str,
    ) -> str:
        sanitized = value

        for sensitive in (
            self
            ._known_sensitive_strings()
        ):
            sanitized = (
                sanitized.replace(
                    sensitive,
                    REDACTED,
                )
            )

        # Member IDs embedded in URLs.
        sanitized = re.sub(
            r"(/member/)[^/?#\s]+",
            (
                r"\1"
                + REDACTED
            ),
            sanitized,
            flags=re.IGNORECASE,
        )

        # Query/form-like member identifiers.
        sanitized = re.sub(
            r"(?i)(member_id=)[^&\s]+",
            (
                r"\1"
                + REDACTED
            ),
            sanitized,
        )

        # Financial amounts. Discovery evidence should never
        # persist raw balances even for the synthetic demo.
        sanitized = re.sub(
            (
                r"\$"
                r"\s?"
                r"\d[\d,]*"
                r"(?:\.\d{2})?"
            ),
            REDACTED_AMOUNT,
            sanitized,
        )

        return sanitized

    def _sanitize(
        self,
        value: Any,
    ) -> Any:
        if value is None:
            return None

        if isinstance(
            value,
            str,
        ):
            return (
                self._sanitize_text(
                    value
                )
            )

        if isinstance(
            value,
            dict,
        ):
            return {
                str(key):
                    self._sanitize(
                        item
                    )
                for (
                    key,
                    item,
                )
                in value.items()
            }

        if isinstance(
            value,
            list,
        ):
            return [
                self._sanitize(
                    item
                )
                for item
                in value
            ]

        if isinstance(
            value,
            tuple,
        ):
            return [
                self._sanitize(
                    item
                )
                for item
                in value
            ]

        return value

    @staticmethod
    def _model_dump(
        value: Any,
    ) -> Any:
        if hasattr(
            value,
            "model_dump",
        ):
            return value.model_dump(
                mode="json"
            )

        return value

    @staticmethod
    def _fingerprint(
        value: Any,
    ) -> str:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            ensure_ascii=False,
            default=str,
        )

        return hashlib.sha256(
            payload.encode(
                "utf-8"
            )
        ).hexdigest()

    def _append_event(
        self,
        payload: dict[
            str,
            Any,
        ],
    ) -> None:
        if self._events_path is None:
            raise (
                DiscoveryEvidenceError(
                    (
                        "Discovery evidence "
                        "event log is not ready."
                    )
                )
            )

        sanitized = (
            self._sanitize(
                payload
            )
        )

        with self._events_path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    sanitized,
                    sort_keys=True,
                )
                + "\n"
            )

    # ========================================================
    # Lifecycle
    # ========================================================

    def start_run(
        self,
        *,
        run_id: str,
        goal: str,
        entry_url: str,
        provider: str,
        model: str,
    ) -> Path:
        self.run_id = run_id

        self.run_dir = (
            self.root
            / run_id
        )

        self.run_dir.mkdir(
            parents=True,
            exist_ok=False,
        )

        self._events_path = (
            self.run_dir
            / "events.jsonl"
        )

        self._events_path.write_text(
            "",
            encoding="utf-8",
        )

        metadata = {
            "schema_version":
                "1.0",

            "run_id":
                run_id,

            "provider":
                provider,

            "model":
                model,

            "goal":
                goal,

            "entry_url":
                entry_url,

            "inputs": {
                name:
                    REDACTED
                for name
                in self
                .sensitive_inputs
            },

            "evidence_policy": {
                (
                    "raw_visible_text_"
                    "persisted"
                ):
                    False,

                (
                    "raw_model_response_"
                    "persisted"
                ):
                    False,

                (
                    "observation_fingerprint_"
                    "persisted"
                ):
                    True,

                "sensitive_values_redacted":
                    True,
            },
        }

        (
            self.run_dir
            / "metadata.json"
        ).write_text(
            json.dumps(
                self._sanitize(
                    metadata
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        self.record_event(
            event_type=(
                "discovery_started"
            ),
            data={
                "provider":
                    provider,
                "model":
                    model,
            },
        )

        return self.run_dir

    # ========================================================
    # Events
    # ========================================================

    def record_event(
        self,
        *,
        event_type: str,
        step_index: (
            int | None
        ) = None,
        data: (
            dict[str, Any]
            | None
        ) = None,
    ) -> None:
        payload = {
            "timestamp":
                self._now(),

            "event_type":
                event_type,

            "run_id":
                self.run_id,

            "step_index":
                step_index,

            "data":
                data
                or {},
        }

        self._append_event(
            payload
        )

    def record_observation(
        self,
        *,
        step_index: int,
        observation: Any,
    ) -> None:
        raw = self._model_dump(
            observation
        )

        if not isinstance(
            raw,
            dict,
        ):
            raw = {
                "value":
                    raw
            }

        controls = raw.get(
            "controls",
            [],
        )

        safe_controls: list[
            dict[str, Any]
        ] = []

        if isinstance(
            controls,
            list,
        ):
            for control in controls:
                if not isinstance(
                    control,
                    dict,
                ):
                    continue

                # Do not persist input values.
                safe_controls.append(
                    {
                        key:
                            control.get(
                                key
                            )
                        for key
                        in (
                            "tag",
                            "role",
                            "name",
                            "label",
                            "text",
                            "placeholder",
                            "href",
                        )
                        if (
                            control.get(
                                key
                            )
                            is not None
                        )
                    }
                )

        visible_text = str(
            raw.get(
                "visible_text",
                "",
            )
            or ""
        )

        aria_snapshot = str(
            raw.get(
                "aria_snapshot",
                "",
            )
            or ""
        )

        self.record_event(
            event_type=(
                "observation"
            ),
            step_index=(
                step_index
            ),
            data={
                "url":
                    raw.get(
                        "url"
                    ),

                "title":
                    raw.get(
                        "title"
                    ),

                "control_count":
                    len(
                        safe_controls
                    ),

                "controls":
                    safe_controls,

                "dialog_present":
                    bool(
                        raw.get(
                            "dialog_text"
                        )
                    ),

                "visible_text_chars":
                    len(
                        visible_text
                    ),

                "aria_snapshot_chars":
                    len(
                        aria_snapshot
                    ),

                (
                    "observation_"
                    "sha256"
                ):
                    self
                    ._fingerprint(
                        raw
                    ),
            },
        )

    def record_llm_decision(
        self,
        *,
        step_index: int,
        action: Any,
    ) -> None:
        payload = (
            self._model_dump(
                action
            )
        )

        if not isinstance(
            payload,
            dict,
        ):
            payload = {
                "value":
                    payload
            }

        # FILL values are runtime inputs. Always redact them.
        if (
            payload.get(
                "action"
            )
            == "fill"
            and (
                "value"
                in payload
            )
        ):
            payload[
                "value"
            ] = REDACTED

        self.record_event(
            event_type=(
                "llm_decision"
            ),
            step_index=(
                step_index
            ),
            data={
                "action":
                    payload,
            },
        )

    def record_target_resolution(
        self,
        *,
        step_index: int,
        resolved_info: Any,
    ) -> None:
        self.record_event(
            event_type=(
                "target_resolved"
            ),
            step_index=(
                step_index
            ),
            data={
                "resolved_target":
                    self._model_dump(
                        resolved_info
                    ),
            },
        )

    def record_policy(
        self,
        *,
        step_index: int,
        evaluation: Any,
        phase: str,
    ) -> None:
        self.record_event(
            event_type=(
                "policy_evaluated"
            ),
            step_index=(
                step_index
            ),
            data={
                "phase":
                    phase,

                "evaluation":
                    self._model_dump(
                        evaluation
                    ),
            },
        )

    def record_execution(
        self,
        *,
        step_index: int,
        action_type: str,
        url_after: str,
        output_name: (
            str | None
        ) = None,
        output_value: Any = None,
        assertion_result: (
            bool | None
        ) = None,
    ) -> None:
        data: dict[
            str,
            Any,
        ] = {
            "action_type":
                action_type,

            "url_after":
                url_after,

            "assertion_result":
                assertion_result,
        }

        if output_name is not None:
            data[
                "output_name"
            ] = output_name

            # Extracted outputs may contain regulated data.
            data[
                "output_value"
            ] = REDACTED

        self.record_event(
            event_type=(
                "action_executed"
            ),
            step_index=(
                step_index
            ),
            data=data,
        )

    # ========================================================
    # Final result
    # ========================================================

    def save_result(
        self,
        result: Any,
    ) -> Path:
        run_dir = (
            self._require_run_dir()
        )

        payload = (
            self._model_dump(
                result
            )
        )

        if not isinstance(
            payload,
            dict,
        ):
            payload = {
                "result":
                    payload
            }

        # Explicit output redaction in addition to recursive
        # string sanitization.
        outputs = payload.get(
            "outputs"
        )

        if isinstance(
            outputs,
            dict,
        ):
            payload[
                "outputs"
            ] = {
                name:
                    REDACTED
                for name
                in outputs
            }

        steps = payload.get(
            "steps"
        )

        if isinstance(
            steps,
            list,
        ):
            for step in steps:
                if not isinstance(
                    step,
                    dict,
                ):
                    continue

                if (
                    step.get(
                        "extracted_output_name"
                    )
                    is not None
                ):
                    step[
                        "extracted_output_value"
                    ] = REDACTED

                action = step.get(
                    "action"
                )

                if (
                    isinstance(
                        action,
                        dict,
                    )
                    and action.get(
                        "action"
                    )
                    == "fill"
                ):
                    action[
                        "value"
                    ] = REDACTED

        path = (
            run_dir
            / "result.json"
        )

        path.write_text(
            json.dumps(
                self._sanitize(
                    payload
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        status = None

        if isinstance(
            payload,
            dict,
        ):
            status = payload.get(
                "status"
            )

        self.record_event(
            event_type=(
                "discovery_finished"
            ),
            data={
                "status":
                    status,
            },
        )

        return path

    # ========================================================
    # Audit helper
    # ========================================================

    def assert_values_not_persisted(
        self,
        values: list[Any],
    ) -> None:
        run_dir = (
            self._require_run_dir()
        )

        persisted = "\n".join(
            path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
            for path
            in run_dir.iterdir()
            if (
                path.is_file()
                and path.suffix.lower()
                in {
                    ".json",
                    ".jsonl",
                    ".txt",
                    ".log",
                }
            )
        )

        leaks: list[str] = []

        for raw in values:
            if raw is None:
                continue

            text = str(raw)

            if (
                text
                and text
                in persisted
            ):
                leaks.append(
                    text
                )

        if leaks:
            raise (
                DiscoveryEvidenceError(
                    (
                        "Sensitive discovery "
                        "values remained in "
                        "persisted evidence."
                    )
                )
            )