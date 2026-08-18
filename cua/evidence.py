from __future__ import annotations

import json
import uuid

from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any, cast

from pydantic import BaseModel, Field

from cua.models import CapabilityArtifact


REDACTED = "[REDACTED]"


def _utc_now_iso() -> str:
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


def _iter_scalar_strings(
    value: Any,
):
    """
    Yield scalar runtime values as strings so they can be
    removed from persisted evidence.

    We intentionally recurse through lists/dicts because
    typed capability inputs/outputs may become structured.
    """

    if value is None:
        return

    if isinstance(
        value,
        str,
    ):
        if value:
            yield value
        return

    if (
        isinstance(
            value,
            (int, float),
        )
        and not isinstance(
            value,
            bool,
        )
    ):
        yield str(
            value
        )
        return

    if isinstance(
        value,
        dict,
    ):
        for item in value.values():
            yield from _iter_scalar_strings(
                item
            )
        return

    if isinstance(
        value,
        (list, tuple),
    ):
        for item in value:
            yield from _iter_scalar_strings(
                item
            )


class EvidenceEvent(BaseModel):
    """
    One structured JSONL event from a replay run.
    """

    timestamp: str
    run_id: str
    event_type: str

    capability_id: str

    step_id: str | None = None
    action: str | None = None
    status: str | None = None
    url: str | None = None

    duration_ms: float | None = None

    runtime_state_code: (
        str | None
    ) = None

    recovery_action: (
        str | None
    ) = None

    recovery_attempt: (
        int | None
    ) = None

    message: str | None = None

    data: dict[str, Any] = Field(
        default_factory=dict
    )


class EvidenceRecorder:
    """
    Persist replay evidence without changing replay decisions.

    Responsibilities:
      - create a per-run evidence directory
      - write structured JSONL events
      - persist a redacted final result
      - persist the compiled artifact used for replay
      - capture masked screenshots on failure
      - capture sanitized structure snapshots on failure

    The recorder never controls the browser and never decides
    what replay should do.
    """

    def __init__(
        self,
        *,
        root: Path | str = (
            "evidence/replay"
        ),
    ):
        self.root = Path(
            root
        )

        self.run_id: str | None = None

        self.run_dir: (
            Path | None
        ) = None

        self.events_path: (
            Path | None
        ) = None

        self._artifact: (
            CapabilityArtifact | None
        ) = None

        self._secret_strings: set[
            str
        ] = set()

    # ========================================================
    # Redaction
    # ========================================================

    def _remember_secret(
        self,
        value: Any,
    ) -> None:
        for scalar in (
            _iter_scalar_strings(
                value
            )
        ):
            self._secret_strings.add(
                scalar
            )

    def _remember_sensitive_inputs(
        self,
        *,
        artifact: CapabilityArtifact,
        inputs: dict[
            str,
            Any,
        ],
    ) -> None:
        for (
            name,
            field,
        ) in artifact.inputs.items():
            if not field.sensitive:
                continue

            if name not in inputs:
                continue

            self._remember_secret(
                inputs[
                    name
                ]
            )

    def remember_sensitive_outputs(
        self,
        *,
        artifact: CapabilityArtifact,
        outputs: dict[
            str,
            Any,
        ],
    ) -> None:
        for (
            name,
            field,
        ) in artifact.outputs.items():
            if not field.sensitive:
                continue

            if name not in outputs:
                continue

            self._remember_secret(
                outputs[
                    name
                ]
            )

    def redact_text(
        self,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        result = value

        # Longest first prevents a short value from partially
        # consuming a longer sensitive value.
        for secret in sorted(
            self._secret_strings,
            key=len,
            reverse=True,
        ):
            if not secret:
                continue

            result = result.replace(
                secret,
                REDACTED,
            )

        return result

    def sanitize(
        self,
        value: Any,
    ) -> Any:
        """
        Recursively redact known sensitive runtime values from
        arbitrary evidence payloads.
        """

        if isinstance(
            value,
            str,
        ):
            return self.redact_text(
                value
            )

        if isinstance(
            value,
            dict,
        ):
            return {
                key: self.sanitize(
                    item
                )
                for (
                    key,
                    item,
                ) in value.items()
            }

        if isinstance(
            value,
            list,
        ):
            return [
                self.sanitize(
                    item
                )
                for item in value
            ]

        if isinstance(
            value,
            tuple,
        ):
            return [
                self.sanitize(
                    item
                )
                for item in value
            ]

        return value

    def sanitized_inputs(
        self,
        *,
        artifact: CapabilityArtifact,
        inputs: dict[
            str,
            Any,
        ],
    ) -> dict[str, Any]:
        safe: dict[
            str,
            Any,
        ] = {}

        for (
            name,
            field,
        ) in artifact.inputs.items():
            if name not in inputs:
                continue

            if field.sensitive:
                safe[
                    name
                ] = REDACTED
            else:
                safe[
                    name
                ] = self.sanitize(
                    inputs[
                        name
                    ]
                )

        return safe

    def sanitized_outputs(
        self,
        *,
        artifact: CapabilityArtifact,
        outputs: dict[
            str,
            Any,
        ],
    ) -> dict[str, Any]:
        self.remember_sensitive_outputs(
            artifact=artifact,
            outputs=outputs,
        )

        safe: dict[
            str,
            Any,
        ] = {}

        for (
            name,
            value,
        ) in outputs.items():
            field = (
                artifact
                .outputs
                .get(
                    name
                )
            )

            if (
                field is not None
                and field.sensitive
            ):
                safe[
                    name
                ] = REDACTED
            else:
                safe[
                    name
                ] = self.sanitize(
                    value
                )

        return safe

    # ========================================================
    # Run lifecycle
    # ========================================================

    def start_run(
        self,
        *,
        artifact: CapabilityArtifact,
        inputs: dict[
            str,
            Any,
        ],
        entry_url: str,
    ) -> str:
        """
        Start a new replay evidence run.

        A recorder instance is intended for one active run at a
        time. Calling start_run resets its in-memory secrets.
        """

        self._artifact = artifact

        self._secret_strings = set()

        self._remember_sensitive_inputs(
            artifact=artifact,
            inputs=inputs,
        )

        self.run_id = (
            "replay_"
            + uuid.uuid4().hex[:12]
        )

        self.run_dir = (
            self.root
            / self.run_id
        )

        self.run_dir.mkdir(
            parents=True,
            exist_ok=False,
        )

        self.events_path = (
            self.run_dir
            / "events.jsonl"
        )

        metadata = {
            "run_id":
                self.run_id,

            "started_at":
                _utc_now_iso(),

            "capability_id":
                artifact.identity.id,

            "capability_version":
                artifact.identity.version,

            "approval_state":
                artifact
                .identity
                .approval_state
                .value,

            "entry_url":
                self.redact_text(
                    entry_url
                ),

            "inputs":
                self.sanitized_inputs(
                    artifact=artifact,
                    inputs=inputs,
                ),

            "artifact_integrity_sha256":
                artifact.integrity_sha256,
        }

        self._write_json(
            self.run_dir
            / "metadata.json",
            metadata,
        )

        # The compiler already guarantees that concrete
        # sensitive discovery data does not survive in the
        # reusable capability artifact.
        self._write_json(
            self.run_dir
            / "artifact.json",
            artifact.model_dump(
                mode="json"
            ),
        )

        self.record_event(
            event_type="run_started",
            status="started",
            url=entry_url,
            data={
                "inputs":
                    metadata[
                        "inputs"
                    ],
            },
        )

        return self.run_id

    # ========================================================
    # Event recording
    # ========================================================

    def record_event(
        self,
        *,
        event_type: str,
        step_id: str | None = None,
        action: str | None = None,
        status: str | None = None,
        url: str | None = None,
        duration_ms: (
            float | None
        ) = None,
        runtime_state_code: (
            str | None
        ) = None,
        recovery_action: (
            str | None
        ) = None,
        recovery_attempt: (
            int | None
        ) = None,
        message: str | None = None,
        data: dict[
            str,
            Any,
        ] | None = None,
    ) -> None:
        if (
            self.run_id is None
            or self.events_path
            is None
            or self._artifact
            is None
        ):
            raise RuntimeError(
                (
                    "EvidenceRecorder.start_run() "
                    "must be called before "
                    "record_event()."
                )
            )

        event = EvidenceEvent(
            timestamp=_utc_now_iso(),
            run_id=self.run_id,
            event_type=event_type,
            capability_id=(
                self._artifact
                .identity
                .id
            ),
            step_id=step_id,
            action=action,
            status=status,
            url=self.redact_text(
                url
            ),
            duration_ms=duration_ms,
            runtime_state_code=(
                runtime_state_code
            ),
            recovery_action=(
                recovery_action
            ),
            recovery_attempt=(
                recovery_attempt
            ),
            message=self.redact_text(
                message
            ),
            data=self.sanitize(
                data
                or {}
            ),
        )

        line = json.dumps(
            event.model_dump(
                mode="json"
            ),
            ensure_ascii=False,
            sort_keys=True,
        )

        with self.events_path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                line
                + "\n"
            )

    # ========================================================
    # Result / exception persistence
    # ========================================================

    def save_result(
        self,
        result: BaseModel | dict[
            str,
            Any,
        ],
    ) -> Path:
        if (
            self.run_dir is None
            or self._artifact
            is None
        ):
            raise RuntimeError(
                (
                    "EvidenceRecorder.start_run() "
                    "must be called before "
                    "save_result()."
                )
            )

        if isinstance(
            result,
            BaseModel,
        ):
            payload = (
                result.model_dump(
                    mode="json"
                )
            )
        else:
            payload = dict(
                result
            )

        outputs = payload.get(
            "outputs",
            {},
        )

        if isinstance(
            outputs,
            dict,
        ):
            payload[
                "outputs"
            ] = (
                self
                .sanitized_outputs(
                    artifact=(
                        self._artifact
                    ),
                    outputs=outputs,
                )
            )

        payload = self.sanitize(
            payload
        )

        destination = (
            self.run_dir
            / "result.json"
        )

        self._write_json(
            destination,
            payload,
        )

        status = payload.get(
            "status"
        )

        self.record_event(
            event_type="run_finished",
            status=(
                str(status)
                if status is not None
                else "unknown"
            ),
            data={
                "checkpoint_passed":
                    payload.get(
                        "checkpoint_passed",
                        False,
                    ),
                "recovery_count":
                    payload.get(
                        "recovery_count",
                        0,
                    ),
            },
        )

        return destination

    def save_exception(
        self,
        *,
        exc: Exception,
        step_id: str | None,
        url: str | None,
    ) -> Path:
        if self.run_dir is None:
            raise RuntimeError(
                (
                    "EvidenceRecorder.start_run() "
                    "must be called before "
                    "save_exception()."
                )
            )

        payload = {
            "timestamp":
                _utc_now_iso(),

            "run_id":
                self.run_id,

            "step_id":
                step_id,

            "url":
                self.redact_text(
                    url
                ),

            "exception_type":
                type(
                    exc
                ).__name__,

            "message":
                self.redact_text(
                    str(
                        exc
                    )
                ),
        }

        destination = (
            self.run_dir
            / "exception.json"
        )

        self._write_json(
            destination,
            payload,
        )

        return destination

    # ========================================================
    # Rich failure evidence
    # ========================================================

    async def capture_failure(
        self,
        *,
        surface: Any,
        step_id: str | None,
        reason: str,
    ) -> dict[
        str,
        str,
    ]:
        """
        Capture richer failure evidence from the live surface.

        PlaywrightSurface already exposes:
          capture_screenshot(..., mask_sensitive=True)
          structure_snapshot()

        We access these through a narrow optional capability so
        evidence recording remains surface-agnostic.
        """

        if self.run_dir is None:
            raise RuntimeError(
                (
                    "EvidenceRecorder.start_run() "
                    "must be called before "
                    "capture_failure()."
                )
            )

        artifacts: dict[
            str,
            str,
        ] = {}

        safe_step = (
            step_id
            or "run"
        )

        screenshot_method = cast(
            Callable[
                ...,
                Awaitable[Path],
            ]
            | None,
            getattr(
                surface,
                "capture_screenshot",
                None,
            ),
        )

        if screenshot_method is not None:
            screenshot_path = (
                self.run_dir
                / (
                    "failure_"
                    f"{safe_step}.png"
                )
            )

            try:
                await screenshot_method(
                    screenshot_path,
                    mask_sensitive=True,
                )

                artifacts[
                    "screenshot"
                ] = str(
                    screenshot_path
                )

            except Exception as exc:
                self.record_event(
                    event_type=(
                        "evidence_capture_error"
                    ),
                    step_id=step_id,
                    status="failed",
                    message=(
                        "Could not capture "
                        "failure screenshot: "
                        f"{exc}"
                    ),
                )

        snapshot_method = cast(
            Callable[
                [],
                Awaitable[
                    str | None
                ],
            ]
            | None,
            getattr(
                surface,
                "structure_snapshot",
                None,
            ),
        )

        if snapshot_method is not None:
            try:
                snapshot = (
                    await snapshot_method()
                )

                if snapshot:
                    snapshot_path = (
                        self.run_dir
                        / (
                            "failure_"
                            f"{safe_step}.html"
                        )
                    )

                    snapshot_path.write_text(
                        self.redact_text(
                            snapshot
                        )
                        or "",
                        encoding="utf-8",
                    )

                    artifacts[
                        "structure_snapshot"
                    ] = str(
                        snapshot_path
                    )

            except Exception as exc:
                self.record_event(
                    event_type=(
                        "evidence_capture_error"
                    ),
                    step_id=step_id,
                    status="failed",
                    message=(
                        "Could not capture "
                        "structure snapshot: "
                        f"{exc}"
                    ),
                )

        self.record_event(
            event_type=(
                "failure_evidence_captured"
            ),
            step_id=step_id,
            status="captured",
            url=getattr(
                surface,
                "current_url",
                None,
            ),
            message=reason,
            data={
                "artifacts":
                    artifacts,
            },
        )

        return artifacts

    # ========================================================
    # File helpers
    # ========================================================

    @staticmethod
    def _write_json(
        path: Path,
        payload: Any,
    ) -> None:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            (
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ),
            encoding="utf-8",
        )