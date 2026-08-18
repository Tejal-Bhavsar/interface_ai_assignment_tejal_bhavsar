from __future__ import annotations

import hashlib
import json
import shutil

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REDACTED = "[REDACTED]"


class EvidenceBundleError(
    RuntimeError
):
    pass


class EvidenceRequirementError(
    EvidenceBundleError
):
    pass


@dataclass(frozen=True)
class ReplayEvidence:
    source_dir: Path
    run_id: str

    status: str | None
    runtime_state_code: str | None
    checkpoint_passed: bool

    recovery_count: int
    event_types: frozenset[str]

    has_screenshot: bool
    has_structure_snapshot: bool

    human_operator_ids: tuple[
        str,
        ...
    ] = ()

    llm_decision_event_count: int = 0

    artifact_integrity_sha256: (
        str | None
    ) = None

    artifact_discovery_run_id: (
        str | None
    ) = None

    @property
    def is_completed(
        self,
    ) -> bool:
        return (
            self.status == "completed"
            and self.checkpoint_passed
        )

    @property
    def is_business_outcome(
        self,
    ) -> bool:
        return (
            self.status
            == "business_outcome"
        )

    @property
    def has_recovery(
        self,
    ) -> bool:
        return (
            self.recovery_count > 0
            or (
                "recovery_started"
                in self.event_types
            )
            or (
                "recovery_completed"
                in self.event_types
            )
        )

    @property
    def is_hard_failure(
        self,
    ) -> bool:
        return (
            self.status == "failed"
            and self.runtime_state_code
            not in {
                "POLICY_URL_BLOCKED",
                "POLICY_CURRENT_URL_BLOCKED",
                "POLICY_DESTINATION_BLOCKED",
                "POLICY_BLOCKED_PHRASE",
                "POLICY_IRREVERSIBLE_BLOCKED",
                "POLICY_RISKY_BLOCKED",
                "POLICY_POST_ACTION_URL_BLOCKED",
            }
        )

    @property
    def is_handoff(
        self,
    ) -> bool:
        required = {
            "human_control_acquired",
            "human_action",
            "human_control_released",
            "automation_control_resumed",
        }

        return (
            self.is_completed
            and required.issubset(
                self.event_types
            )
        )

    @property
    def is_manual_handoff(
        self,
    ) -> bool:
        if not self.is_handoff:
            return False

        normalized = {
            value.strip().lower()
            for value
            in self.human_operator_ids
        }

        if any(
            "scripted"
            in value
            or "regression"
            in value
            or "auto"
            in value
            for value
            in normalized
        ):
            return False

        return bool(
            normalized
        )

    @property
    def is_policy_case(
        self,
    ) -> bool:
        return any(
            event in self.event_types
            for event in {
                "policy_blocked",
                "policy_human_required",
            }
        )


@dataclass(frozen=True)
class DiscoveryEvidence:
    source: Path
    run_id: str
    provider: str
    model: str | None

    @property
    def genuine(
        self,
    ) -> bool:
        provider = (
            self.provider
            .strip()
            .lower()
        )

        return provider not in {
            "",
            "mock",
            "fake",
            "test",
        }


@dataclass
class EvidenceSelection:
    discovery: (
        DiscoveryEvidence
        | None
    ) = None

    replay_success: (
        ReplayEvidence
        | None
    ) = None

    business_outcome: (
        ReplayEvidence
        | None
    ) = None

    recovery: (
        ReplayEvidence
        | None
    ) = None

    hard_failure: (
        ReplayEvidence
        | None
    ) = None

    human_handoff: (
        ReplayEvidence
        | None
    ) = None

    policy: (
        ReplayEvidence
        | None
    ) = None

    agent_api: (
        ReplayEvidence
        | None
    ) = None

    missing: list[str] = field(
        default_factory=list
    )


# ============================================================
# JSON helpers
# ============================================================


def _read_json(
    path: Path,
) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise EvidenceBundleError(
            (
                "Could not parse JSON: "
                f"{path}"
            )
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise EvidenceBundleError(
            (
                "Expected JSON object: "
                f"{path}"
            )
        )

    return payload


def _read_jsonl(
    path: Path,
) -> list[
    dict[str, Any]
]:
    rows: list[
        dict[str, Any]
    ] = []

    if not path.exists():
        return rows

    for line_number, raw in enumerate(
        path.read_text(
            encoding="utf-8"
        ).splitlines(),
        start=1,
    ):
        if not raw.strip():
            continue

        try:
            row = json.loads(
                raw
            )
        except json.JSONDecodeError as exc:
            raise EvidenceBundleError(
                (
                    "Invalid JSONL in "
                    f"{path}:"
                    f"{line_number}"
                )
            ) from exc

        if isinstance(
            row,
            dict,
        ):
            rows.append(
                row
            )

    return rows


def _event_types(
    events: list[
        dict[str, Any]
    ],
) -> frozenset[str]:
    return frozenset(
        str(
            event.get(
                "event_type",
                "",
            )
        )
        for event
        in events
        if event.get(
            "event_type"
        )
    )


def _runtime_code(
    result: dict[str, Any],
) -> str | None:
    runtime = result.get(
        "runtime_state"
    )

    if isinstance(
        runtime,
        dict,
    ):
        code = runtime.get(
            "code"
        )

        if code is not None:
            return str(
                code
            )

    code = result.get(
        "runtime_state_code"
    )

    if code is not None:
        return str(
            code
        )

    return None


def _status_value(
    value: Any,
) -> str | None:
    if value is None:
        return None

    if isinstance(
        value,
        str,
    ):
        return value

    return str(
        value
    )


def _human_operator_ids(
    events: list[
        dict[str, Any]
    ],
) -> tuple[
    str,
    ...
]:
    values: set[
        str
    ] = set()

    for event in events:
        data = event.get(
            "data"
        )

        if not isinstance(
            data,
            dict,
        ):
            continue

        operator_id = data.get(
            "operator_id"
        )

        if isinstance(
            operator_id,
            str,
        ) and operator_id.strip():
            values.add(
                operator_id.strip()
            )

    return tuple(
        sorted(
            values
        )
    )


def _llm_decision_events(
    events: list[
        dict[str, Any]
    ],
) -> int:
    """
    Replay evidence should not contain LLM decision-loop events.

    This is a heuristic audit signal, not proof by itself; the
    architectural proof is that ReplayEngine contains no LLM
    provider dependency.
    """

    count = 0

    for event in events:
        event_type = str(
            event.get(
                "event_type",
                "",
            )
        ).lower()

        if any(
            token in event_type
            for token in {
                "llm_decision",
                "model_decision",
                "agent_decision",
            }
        ):
            count += 1

    return count


# ============================================================
# Replay evidence discovery
# ============================================================


def parse_replay_run(
    run_dir: Path,
) -> ReplayEvidence | None:
    result_path = (
        run_dir
        / "result.json"
    )

    events_path = (
        run_dir
        / "events.jsonl"
    )

    if not result_path.exists():
        return None

    result = _read_json(
        result_path
    )

    artifact_path = (
        run_dir
        / "artifact.json"
    )

    artifact = (
        _read_json(
            artifact_path
        )
        if artifact_path.exists()
        else {}
    )

    artifact_integrity = (
        artifact.get(
            "integrity_sha256"
        )
        if isinstance(
            artifact,
            dict,
        )
        else None
    )

    artifact_discovery_run_id = None

    if isinstance(
        artifact,
        dict,
    ):
        discovery = artifact.get(
            "discovery"
        )

        if isinstance(
            discovery,
            dict,
        ):
            raw_run_id = discovery.get(
                "run_id"
            )

            if raw_run_id is not None:
                artifact_discovery_run_id = (
                    str(
                        raw_run_id
                    )
                )

    events = _read_jsonl(
        events_path
    )

    run_id = str(
        result.get(
            "run_id"
        )
        or run_dir.name
    )

    status = _status_value(
        result.get(
            "status"
        )
    )

    checkpoint = bool(
        result.get(
            "checkpoint_passed",
            False,
        )
    )

    recovery_count_raw = (
        result.get(
            "recovery_count",
            0,
        )
    )

    try:
        recovery_count = int(
            recovery_count_raw
        )
    except (
        TypeError,
        ValueError,
    ):
        recovery_count = 0

    files = [
        path
        for path
        in run_dir.iterdir()
        if path.is_file()
    ]

    return ReplayEvidence(
        source_dir=run_dir,
        run_id=run_id,
        status=status,
        runtime_state_code=(
            _runtime_code(
                result
            )
        ),
        checkpoint_passed=(
            checkpoint
        ),
        recovery_count=(
            recovery_count
        ),
        event_types=(
            _event_types(
                events
            )
        ),
        has_screenshot=any(
            path.suffix.lower()
            in {
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
            }
            for path
            in files
        ),
        has_structure_snapshot=any(
            path.suffix.lower()
            in {
                ".html",
                ".htm",
            }
            for path
            in files
        ),
        human_operator_ids=(
            _human_operator_ids(
                events
            )
        ),
        llm_decision_event_count=(
            _llm_decision_events(
                events
            )
        ),
        artifact_integrity_sha256=(
            str(
                artifact_integrity
            )
            if artifact_integrity
            is not None
            else None
        ),
        artifact_discovery_run_id=(
            artifact_discovery_run_id
        ),
    )


def scan_replay_runs(
    evidence_root: Path,
) -> list[
    ReplayEvidence
]:
    roots = [
        evidence_root
        / "replay",

        evidence_root
        / "policy",

        evidence_root
        / "agent_api",
    ]

    runs: list[
        ReplayEvidence
    ] = []

    seen: set[
        Path
    ] = set()

    for root in roots:
        if not root.exists():
            continue

        for result_path in (
            root.rglob(
                "result.json"
            )
        ):
            run_dir = (
                result_path.parent
            )

            if (
                "final"
                in run_dir.parts
            ):
                continue

            resolved = (
                run_dir.resolve()
            )

            if resolved in seen:
                continue

            seen.add(
                resolved
            )

            parsed = parse_replay_run(
                run_dir
            )

            if parsed is not None:
                runs.append(
                    parsed
                )

    return runs


# ============================================================
# Discovery evidence
# ============================================================


def artifact_discovery_contract(
    artifact_path: Path,
) -> tuple[
    str,
    str,
    str | None,
]:
    artifact = _read_json(
        artifact_path
    )

    discovery = artifact.get(
        "discovery"
    )

    if not isinstance(
        discovery,
        dict,
    ):
        raise EvidenceRequirementError(
            (
                "Capability artifact has no "
                "discovery metadata."
            )
        )

    run_id = discovery.get(
        "run_id"
    )

    provider = discovery.get(
        "provider"
    )

    model = discovery.get(
        "model"
    )

    if not isinstance(
        run_id,
        str,
    ) or not run_id.strip():
        raise EvidenceRequirementError(
            (
                "Capability artifact is "
                "missing discovery.run_id."
            )
        )

    if not isinstance(
        provider,
        str,
    ) or not provider.strip():
        raise EvidenceRequirementError(
            (
                "Capability artifact is "
                "missing discovery.provider."
            )
        )

    return (
        run_id.strip(),
        provider.strip(),
        (
            str(
                model
            )
            if model
            is not None
            else None
        ),
    )


def _file_contains(
    path: Path,
    needle: str,
) -> bool:
    try:
        return needle in (
            path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        )
    except OSError:
        return False


def find_discovery_evidence(
    *,
    evidence_root: Path,
    artifact_path: Path,
) -> DiscoveryEvidence | None:
    (
        run_id,
        provider,
        model,
    ) = artifact_discovery_contract(
        artifact_path
    )

    if provider.lower() in {
        "mock",
        "fake",
        "test",
    }:
        return DiscoveryEvidence(
            source=artifact_path,
            run_id=run_id,
            provider=provider,
            model=model,
        )

    candidates: list[
        Path
    ] = []

    preferred_root = (
        evidence_root
        / "discovery"
    )

    search_roots = [
        preferred_root,
        evidence_root,
    ]

    for root in search_roots:
        if not root.exists():
            continue

        for path in root.rglob(
            "*"
        ):
            if (
                path.is_dir()
                and path.name
                == "final"
            ):
                continue

            if path.is_file():
                if path.suffix.lower() not in {
                    ".json",
                    ".jsonl",
                    ".txt",
                    ".log",
                    ".md",
                }:
                    continue

                is_discovery_named = (
                    "discovery"
                    in {
                        part.lower()
                        for part
                        in path.parts
                    }
                    or "discovery"
                    in path.name.lower()
                    or run_id
                    in path.name
                )

                if not is_discovery_named:
                    continue

                if not _file_contains(
                    path,
                    run_id,
                ):
                    continue

                # A replay artifact snapshot also carries
                # discovery metadata, so require the discovery
                # evidence itself to name the provider.
                if not _file_contains(
                    path,
                    provider,
                ):
                    continue

                candidates.append(
                    path
                )

    if not candidates:
        return None

    def score(
        path: Path,
    ) -> tuple[
        int,
        float,
    ]:
        value = 0

        if (
            "discovery"
            in {
                part.lower()
                for part
                in path.parts
            }
        ):
            value += 50

        if (
            run_id
            in path.name
        ):
            value += 20

        if _file_contains(
            path,
            provider,
        ):
            value += 10

        if (
            model
            and _file_contains(
                path,
                model,
            )
        ):
            value += 10

        if _file_contains(
            path,
            "completed",
        ):
            value += 5

        return (
            value,
            path.stat().st_mtime,
        )

    best = max(
        candidates,
        key=score,
    )

    # If the run is stored as one or more files inside a
    # run-specific directory, copy that directory. Otherwise copy
    # the individual file.
    source = best.parent

    if (
        source == evidence_root
        or source
        == preferred_root
    ):
        source = best

    return DiscoveryEvidence(
        source=source,
        run_id=run_id,
        provider=provider,
        model=model,
    )


# ============================================================
# Selection
# ============================================================


def _latest(
    runs: list[
        ReplayEvidence
    ],
    predicate,
) -> ReplayEvidence | None:
    matches = [
        run
        for run
        in runs
        if predicate(
            run
        )
    ]

    if not matches:
        return None

    return max(
        matches,
        key=lambda run:
            run
            .source_dir
            .stat()
            .st_mtime,
    )


def _best_hard_failure(
    runs: list[
        ReplayEvidence
    ],
) -> ReplayEvidence | None:
    matches = [
        run
        for run
        in runs
        if run.is_hard_failure
    ]

    if not matches:
        return None

    def score(
        run: ReplayEvidence,
    ):
        value = 0

        if run.has_screenshot:
            value += 10

        if (
            run
            .has_structure_snapshot
        ):
            value += 10

        return (
            value,
            run
            .source_dir
            .stat()
            .st_mtime,
        )

    return max(
        matches,
        key=score,
    )


def _best_manual_handoff(
    runs: list[
        ReplayEvidence
    ],
) -> ReplayEvidence | None:
    matches = [
        run
        for run
        in runs
        if run.is_manual_handoff
    ]

    if not matches:
        return None

    def score(
        run: ReplayEvidence,
    ):
        value = 0

        if (
            "resume_validation_passed"
            in run.event_types
        ):
            value += 10

        if (
            "intervention_resolved"
            in run.event_types
        ):
            value += 10

        if (
            run.llm_decision_event_count
            == 0
        ):
            value += 10

        return (
            value,
            run
            .source_dir
            .stat()
            .st_mtime,
        )

    return max(
        matches,
        key=score,
    )


def select_evidence(
    *,
    project_root: Path,
) -> EvidenceSelection:
    evidence_root = (
        project_root
        / "evidence"
    )

    artifact_path = (
        project_root
        / "capabilities"
        / "lookup_savings_balance.v1.json"
    )

    if not artifact_path.exists():
        raise EvidenceRequirementError(
            (
                "Canonical capability "
                "artifact is missing: "
                f"{artifact_path}"
            )
        )

    canonical_artifact = (
        _read_json(
            artifact_path
        )
    )

    canonical_integrity = (
        canonical_artifact.get(
            "integrity_sha256"
        )
    )

    canonical_discovery_run_id = None

    canonical_discovery = (
        canonical_artifact.get(
            "discovery"
        )
    )

    if isinstance(
        canonical_discovery,
        dict,
    ):
        raw_discovery_run_id = (
            canonical_discovery.get(
                "run_id"
            )
        )

        if raw_discovery_run_id is not None:
            canonical_discovery_run_id = (
                str(
                    raw_discovery_run_id
                )
            )

    runs = scan_replay_runs(
        evidence_root
    )

    # Final replay proof should come from the exact canonical
    # artifact currently being submitted. Otherwise a stale run
    # from an older artifact revision could accidentally be
    # selected simply because it has a newer timestamp.
    if canonical_integrity:
        canonical_runs = [
            run
            for run
            in runs
            if (
                run
                .artifact_integrity_sha256
                == str(
                    canonical_integrity
                )
            )
        ]
    else:
        canonical_runs = list(
            runs
        )

    # Policy smoke cases may intentionally derive a temporary
    # artifact from the canonical one to exercise a risky/blocked
    # action. For those, preserve the discovery lineage even when
    # the temporary artifact's integrity hash differs.
    if canonical_discovery_run_id:
        canonical_lineage_runs = [
            run
            for run
            in runs
            if (
                run
                .artifact_discovery_run_id
                == canonical_discovery_run_id
            )
        ]
    else:
        canonical_lineage_runs = list(
            runs
        )

    selection = EvidenceSelection()

    selection.discovery = (
        find_discovery_evidence(
            evidence_root=(
                evidence_root
            ),
            artifact_path=(
                artifact_path
            ),
        )
    )

    replay_root_runs = [
        run
        for run
        in canonical_runs
        if "replay"
        in run.source_dir.parts
    ]

    success_predicate = (
        lambda run:
            run.is_completed
            and not run.is_handoff
            and not run.has_recovery
            and not run.is_policy_case
    )

    selection.replay_success = (
        _latest(
            replay_root_runs,
            success_predicate,
        )
        or _latest(
            canonical_runs,
            success_predicate,
        )
    )

    selection.business_outcome = (
        _latest(
            canonical_runs,
            lambda run:
                run.is_business_outcome,
        )
    )

    selection.recovery = (
        _latest(
            canonical_runs,
            lambda run:
                run.is_completed
                and run.has_recovery,
        )
    )

    selection.hard_failure = (
        _best_hard_failure(
            canonical_runs
        )
    )

    selection.human_handoff = (
        _best_manual_handoff(
            canonical_runs
        )
    )

    selection.policy = (
        _latest(
            canonical_lineage_runs,
            lambda run:
                run.is_policy_case,
        )
    )

    selection.agent_api = (
        _latest(
            [
                run
                for run
                in canonical_runs
                if (
                    "agent_api"
                    in run
                    .source_dir
                    .parts
                )
            ],
            lambda run:
                run.is_completed,
        )
    )

    # --------------------------------------------------------
    # Required final-submission proof
    # --------------------------------------------------------

    if (
        selection.discovery
        is None
    ):
        selection.missing.append(
            (
                "genuine discovery evidence "
                "matching the artifact's "
                "discovery.run_id"
            )
        )
    elif not (
        selection.discovery.genuine
    ):
        selection.missing.append(
            (
                "genuine non-mock discovery "
                "provider"
            )
        )

    if (
        selection.replay_success
        is None
    ):
        selection.missing.append(
            "successful deterministic replay"
        )

    if (
        selection.business_outcome
        is None
    ):
        selection.missing.append(
            "business-outcome replay"
        )

    if (
        selection.recovery
        is None
    ):
        selection.missing.append(
            "recoverable replay"
        )

    if (
        selection.hard_failure
        is None
    ):
        selection.missing.append(
            (
                "hard-failure replay with "
                "debuggable evidence"
            )
        )

    if (
        selection.human_handoff
        is None
    ):
        selection.missing.append(
            (
                "successful REAL MANUAL "
                "same-session human handoff "
                "(not --auto)"
            )
        )

    if (
        selection.policy
        is None
    ):
        selection.missing.append(
            "runtime policy evidence"
        )

    return selection


# ============================================================
# Redaction audit
# ============================================================


def audit_replay_redaction(
    run: ReplayEvidence,
) -> list[str]:
    """
    Verify sensitive fields declared by the copied artifact are
    redacted in persisted metadata/result JSON.

    This does not rely on knowing concrete member IDs/balances.
    """

    issues: list[
        str
    ] = []

    artifact_path = (
        run.source_dir
        / "artifact.json"
    )

    metadata_path = (
        run.source_dir
        / "metadata.json"
    )

    result_path = (
        run.source_dir
        / "result.json"
    )

    if not artifact_path.exists():
        return [
            "artifact.json missing"
        ]

    artifact = _read_json(
        artifact_path
    )

    inputs_schema = artifact.get(
        "inputs",
        {},
    )

    outputs_schema = artifact.get(
        "outputs",
        {},
    )

    if metadata_path.exists():
        metadata = _read_json(
            metadata_path
        )

        persisted_inputs = (
            metadata.get(
                "inputs",
                {},
            )
        )

        if isinstance(
            inputs_schema,
            dict,
        ) and isinstance(
            persisted_inputs,
            dict,
        ):
            for name, field_data in (
                inputs_schema.items()
            ):
                if not isinstance(
                    field_data,
                    dict,
                ):
                    continue

                if not field_data.get(
                    "sensitive",
                    False,
                ):
                    continue

                if (
                    name
                    in persisted_inputs
                    and (
                        persisted_inputs[
                            name
                        ]
                        != REDACTED
                    )
                ):
                    issues.append(
                        (
                            "Sensitive input "
                            f"'{name}' is not "
                            "redacted in metadata."
                        )
                    )

    if result_path.exists():
        result = _read_json(
            result_path
        )

        persisted_outputs = (
            result.get(
                "outputs",
                {},
            )
        )

        if isinstance(
            outputs_schema,
            dict,
        ) and isinstance(
            persisted_outputs,
            dict,
        ):
            for name, field_data in (
                outputs_schema.items()
            ):
                if not isinstance(
                    field_data,
                    dict,
                ):
                    continue

                if not field_data.get(
                    "sensitive",
                    False,
                ):
                    continue

                if (
                    name
                    in persisted_outputs
                    and (
                        persisted_outputs[
                            name
                        ]
                        != REDACTED
                    )
                ):
                    issues.append(
                        (
                            "Sensitive output "
                            f"'{name}' is not "
                            "redacted in result."
                        )
                    )

    return issues


# ============================================================
# Bundle creation
# ============================================================


def _copy_source(
    source: Path,
    destination: Path,
) -> None:
    if source.is_dir():
        shutil.copytree(
            source,
            destination,
        )
        return

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        source,
        destination
        / source.name,
    )


def _sha256(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:
        while True:
            block = handle.read(
                1024 * 1024
            )

            if not block:
                break

            digest.update(
                block
            )

    return digest.hexdigest()


def _manifest_entry_for_replay(
    run: ReplayEvidence,
) -> dict[str, Any]:
    return {
        "source":
            str(
                run.source_dir
            ),
        "run_id":
            run.run_id,
        "status":
            run.status,
        "runtime_state_code":
            run.runtime_state_code,
        "checkpoint_passed":
            run.checkpoint_passed,
        "recovery_count":
            run.recovery_count,
        "has_screenshot":
            run.has_screenshot,
        "has_structure_snapshot":
            (
                run
                .has_structure_snapshot
            ),
        "human_operator_ids":
            list(
                run
                .human_operator_ids
            ),
        "llm_decision_events_detected":
            (
                run
                .llm_decision_event_count
            ),
        "artifact_integrity_sha256":
            (
                run
                .artifact_integrity_sha256
            ),
        "artifact_discovery_run_id":
            (
                run
                .artifact_discovery_run_id
            ),
    }


def _selection_manifest(
    selection: EvidenceSelection,
) -> dict[str, Any]:
    result: dict[
        str,
        Any,
    ] = {
        "schema_version":
            "1.0",

        "purpose":
            (
                "Curated reviewer-facing "
                "evidence for the computer-use "
                "automation vertical slice."
            ),

        "missing_requirements":
            list(
                selection.missing
            ),
    }

    if selection.discovery:
        result[
            "discovery"
        ] = {
            "source":
                str(
                    selection
                    .discovery
                    .source
                ),
            "run_id":
                selection
                .discovery
                .run_id,
            "provider":
                selection
                .discovery
                .provider,
            "model":
                selection
                .discovery
                .model,
            "genuine_non_mock":
                selection
                .discovery
                .genuine,
        }

    mapping = {
        "replay_success":
            selection.replay_success,
        "business_outcome":
            selection.business_outcome,
        "recovery":
            selection.recovery,
        "hard_failure":
            selection.hard_failure,
        "human_handoff":
            selection.human_handoff,
        "policy":
            selection.policy,
        "agent_api":
            selection.agent_api,
    }

    for name, run in (
        mapping.items()
    ):
        if run is None:
            continue

        result[name] = (
            _manifest_entry_for_replay(
                run
            )
        )

    return result


def _readme_text(
    manifest: dict[str, Any],
) -> str:
    lines = [
        "# Final Evidence Bundle",
        "",
        (
            "This directory is generated "
            "from previously captured run "
            "evidence. Source evidence is "
            "left unchanged."
        ),
        "",
        (
            "All member/account records in "
            "the local LegacyCore target are "
            "synthetic demonstration data."
        ),
        "",
        "## What to inspect",
        "",
        (
            "1. `01_discovery/` — genuine "
            "LLM-driven discovery evidence "
            "for the run referenced by the "
            "capability artifact."
        ),
        (
            "2. `02_artifact/` — the saved "
            "typed/versioned reusable "
            "capability."
        ),
        (
            "3. `03_replay_success/` — "
            "deterministic successful replay "
            "with checkpoint verification."
        ),
        (
            "4. `04_business_outcome/` — "
            "known caller-visible business "
            "outcome."
        ),
        (
            "5. `05_recovery/` — bounded "
            "deterministic recovery."
        ),
        (
            "6. `06_hard_failure/` — hard "
            "failure with richer debug "
            "evidence."
        ),
        (
            "7. `07_human_handoff/` — real "
            "same-session human takeover and "
            "automation resume."
        ),
        (
            "8. `08_policy/` — global runtime "
            "policy block/escalation."
        ),
        (
            "9. `09_agent_api/` — optional "
            "agent-facing capability "
            "invocation evidence."
        ),
        "",
        "## Integrity",
        "",
        (
            "`checksums.sha256` contains "
            "SHA-256 hashes for every copied "
            "file in this bundle except the "
            "checksum file itself."
        ),
        "",
        "## Selection manifest",
        "",
        (
            "`manifest.json` records which "
            "source run was selected for each "
            "proof category and whether any "
            "required evidence was missing."
        ),
        "",
    ]

    if manifest.get(
        "missing_requirements"
    ):
        lines.extend(
            [
                "## WARNING",
                "",
                (
                    "This bundle was generated "
                    "with missing evidence:"
                ),
                "",
            ]
        )

        for item in manifest[
            "missing_requirements"
        ]:
            lines.append(
                f"- {item}"
            )

        lines.append(
            ""
        )

    return "\n".join(
        lines
    )


def build_final_bundle(
    *,
    project_root: Path,
    strict: bool = True,
) -> Path:
    project_root = (
        project_root
        .resolve()
    )

    evidence_root = (
        project_root
        / "evidence"
    )

    final_dir = (
        evidence_root
        / "final"
    )

    selection = select_evidence(
        project_root=(
            project_root
        )
    )

    if (
        strict
        and selection.missing
    ):
        formatted = "\n".join(
            (
                "- "
                + item
            )
            for item
            in selection.missing
        )

        raise EvidenceRequirementError(
            (
                "Final evidence bundle is "
                "not ready:\n"
                f"{formatted}"
            )
        )

    # --------------------------------------------------------
    # Redaction audit before copying replay evidence.
    # --------------------------------------------------------

    replay_runs = [
        selection.replay_success,
        selection.business_outcome,
        selection.recovery,
        selection.hard_failure,
        selection.human_handoff,
        selection.policy,
        selection.agent_api,
    ]

    redaction_issues: list[
        str
    ] = []

    checked_dirs: set[
        Path
    ] = set()

    for run in replay_runs:
        if run is None:
            continue

        resolved = (
            run
            .source_dir
            .resolve()
        )

        if resolved in checked_dirs:
            continue

        checked_dirs.add(
            resolved
        )

        for issue in (
            audit_replay_redaction(
                run
            )
        ):
            redaction_issues.append(
                (
                    f"{run.run_id}: "
                    f"{issue}"
                )
            )

    if redaction_issues:
        formatted = "\n".join(
            "- " + issue
            for issue
            in redaction_issues
        )

        raise EvidenceRequirementError(
            (
                "Redaction audit failed:\n"
                f"{formatted}"
            )
        )

    # --------------------------------------------------------
    # Rebuild only the generated final directory.
    # Source evidence is never removed or modified.
    # --------------------------------------------------------

    if final_dir.exists():
        shutil.rmtree(
            final_dir
        )

    final_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    artifact_path = (
        project_root
        / "capabilities"
        / "lookup_savings_balance.v1.json"
    )

    if selection.discovery:
        _copy_source(
            selection
            .discovery
            .source,
            final_dir
            / "01_discovery",
        )

    artifact_dir = (
        final_dir
        / "02_artifact"
    )

    artifact_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        artifact_path,
        artifact_dir
        / artifact_path.name,
    )

    copy_map = [
        (
            selection.replay_success,
            "03_replay_success",
        ),
        (
            selection.business_outcome,
            "04_business_outcome",
        ),
        (
            selection.recovery,
            "05_recovery",
        ),
        (
            selection.hard_failure,
            "06_hard_failure",
        ),
        (
            selection.human_handoff,
            "07_human_handoff",
        ),
        (
            selection.policy,
            "08_policy",
        ),
        (
            selection.agent_api,
            "09_agent_api",
        ),
    ]

    for run, folder_name in (
        copy_map
    ):
        if run is None:
            continue

        _copy_source(
            run.source_dir,
            final_dir
            / folder_name,
        )

    manifest = (
        _selection_manifest(
            selection
        )
    )

    (
        final_dir
        / "manifest.json"
    ).write_text(
        (
            json.dumps(
                manifest,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ),
        encoding="utf-8",
    )

    (
        final_dir
        / "README.md"
    ).write_text(
        _readme_text(
            manifest
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Bundle-level SHA-256 manifest
    # --------------------------------------------------------

    checksum_lines: list[
        str
    ] = []

    for path in sorted(
        final_dir.rglob(
            "*"
        )
    ):
        if not path.is_file():
            continue

        if (
            path.name
            == "checksums.sha256"
        ):
            continue

        relative = (
            path.relative_to(
                final_dir
            )
        )

        checksum_lines.append(
            (
                f"{_sha256(path)}  "
                f"{relative.as_posix()}"
            )
        )

    (
        final_dir
        / "checksums.sha256"
    ).write_text(
        (
            "\n".join(
                checksum_lines
            )
            + "\n"
        ),
        encoding="utf-8",
    )

    return final_dir