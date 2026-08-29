"""Reference-data bounded context for governed measurement definitions.

The registry owns construct, criterion, rubric, task, rater-configuration,
validation-study, rights, and provenance revision metadata. It is an Open Host
Service for other bounded contexts and deliberately excludes responses,
criterion observations, numerical parameters, scores, adjudication state, and
product decisions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any


MAX_MEASUREMENT_REFERENCE_LENGTH = 256
MAX_MEASUREMENT_CRITERIA = 128
MAX_MEASUREMENT_TASKS = 512
MAX_RATER_CONFIGURATIONS = 128
MAX_VALIDATION_STUDIES = 128

_PROHIBITED_FIELDS = frozenset(
    {
        "raw_response",
        "response_content",
        "criterion_observation",
        "observations",
        "provider_payload",
        "parameter_snapshot",
        "score",
        "final_score",
        "latent_trait",
        "placement",
        "pass_fail",
        "certification",
        "employment_decision",
        "adjudication_state",
    }
)


class MeasurementRegistryError(ValueError):
    """Raised when reference metadata violates a registry aggregate invariant."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _reference(value: Any, field_name: str) -> str:
    """Return one exact bounded opaque reference or fail closed."""
    if type(value) is not str:
        raise MeasurementRegistryError(
            "invalid_reference", f"{field_name} must be a string"
        )
    normalized = value.strip()
    numeric_like = any(character.isnumeric() for character in normalized) and all(
        character.isnumeric() or character in "+-.,eE" for character in normalized
    )
    if (
        not normalized
        or normalized != value
        or len(normalized) > MAX_MEASUREMENT_REFERENCE_LENGTH
        or numeric_like
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
    ):
        raise MeasurementRegistryError(
            "invalid_reference", f"{field_name} must be an exact opaque reference"
        )
    return value


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    """Return a mapping with string keys or reject the boundary input."""
    if not isinstance(value, Mapping):
        raise MeasurementRegistryError(
            "invalid_object", f"{field_name} must be an object"
        )
    if any(type(key) is not str for key in value):
        raise MeasurementRegistryError(
            "invalid_object_key", f"{field_name} keys must be strings"
        )
    return value


def _reject_unknown_fields(
    payload: Mapping[str, Any], allowed: frozenset[str], field_name: str
) -> None:
    """Reject decision leakage and all undeclared boundary fields."""
    unknown = set(payload) - allowed
    if unknown.intersection(_PROHIBITED_FIELDS):
        raise MeasurementRegistryError(
            "authority_leakage",
            f"{field_name} contains data owned by another bounded context",
        )
    if unknown:
        raise MeasurementRegistryError(
            "unknown_field",
            f"{field_name} contains unsupported fields: {sorted(unknown)}",
        )


def _exact_reference_sequence(
    value: Any, field_name: str, *, maximum: int, allow_empty: bool
) -> tuple[str, ...]:
    """Validate a bounded unique sequence of opaque references."""
    if not isinstance(value, (list, tuple)):
        raise MeasurementRegistryError(
            "invalid_reference_set", f"{field_name} must be an array"
        )
    if (not allow_empty and not value) or len(value) > maximum:
        lower_bound = 0 if allow_empty else 1
        raise MeasurementRegistryError(
            "invalid_reference_set",
            f"{field_name} must contain {lower_bound}..{maximum} references",
        )
    references = tuple(_reference(item, field_name) for item in value)
    if len(references) != len(set(references)):
        raise MeasurementRegistryError(
            "duplicate_reference", f"{field_name} must contain unique references"
        )
    return references


class MeasurementDefinitionState(str, Enum):
    """Lifecycle of one immutable-revision measurement definition."""

    DRAFT = "draft"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class CriterionRegistration:
    """Reference metadata for one criterion and its governing rubric revision."""

    criterion_ref: str
    criterion_revision_ref: str
    rubric_revision_ref: str

    _FIELDS = frozenset(
        {"criterion_ref", "criterion_revision_ref", "rubric_revision_ref"}
    )

    def __post_init__(self) -> None:
        for field_name in self._FIELDS:
            object.__setattr__(
                self, field_name, _reference(getattr(self, field_name), field_name)
            )

    @classmethod
    def from_mapping(cls, value: Any) -> CriterionRegistration:
        """Translate untrusted criterion metadata into a registry entity."""
        payload = _mapping(value, "criterion")
        _reject_unknown_fields(payload, cls._FIELDS, "criterion")
        missing = cls._FIELDS - set(payload)
        if missing:
            raise MeasurementRegistryError(
                "missing_field", f"criterion is missing fields: {sorted(missing)}"
            )
        return cls(**{field_name: payload[field_name] for field_name in cls._FIELDS})

    def to_payload(self) -> dict[str, str]:
        """Return the criterion's Open Host Service representation."""
        return {
            "criterion_ref": self.criterion_ref,
            "criterion_revision_ref": self.criterion_revision_ref,
            "rubric_revision_ref": self.rubric_revision_ref,
        }


@dataclass(frozen=True)
class TaskRegistration:
    """Reference metadata for one task revision and its criterion coverage."""

    task_ref: str
    task_revision_ref: str
    criterion_refs: tuple[str, ...]

    _FIELDS = frozenset({"task_ref", "task_revision_ref", "criterion_refs"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_ref", _reference(self.task_ref, "task_ref"))
        object.__setattr__(
            self,
            "task_revision_ref",
            _reference(self.task_revision_ref, "task_revision_ref"),
        )
        object.__setattr__(
            self,
            "criterion_refs",
            _exact_reference_sequence(
                self.criterion_refs,
                "criterion_refs",
                maximum=MAX_MEASUREMENT_CRITERIA,
                allow_empty=False,
            ),
        )

    @classmethod
    def from_mapping(cls, value: Any) -> TaskRegistration:
        """Translate untrusted task metadata into a registry entity."""
        payload = _mapping(value, "task")
        _reject_unknown_fields(payload, cls._FIELDS, "task")
        missing = cls._FIELDS - set(payload)
        if missing:
            raise MeasurementRegistryError(
                "missing_field", f"task is missing fields: {sorted(missing)}"
            )
        return cls(
            task_ref=payload["task_ref"],
            task_revision_ref=payload["task_revision_ref"],
            criterion_refs=payload["criterion_refs"],
        )

    def to_payload(self) -> dict[str, Any]:
        """Return the task's Open Host Service representation."""
        return {
            "task_ref": self.task_ref,
            "task_revision_ref": self.task_revision_ref,
            "criterion_refs": list(self.criterion_refs),
        }


@dataclass(frozen=True)
class RaterConfigurationRegistration:
    """Reference metadata for one exact reusable rater configuration."""

    configuration_ref: str
    rater_family_ref: str
    provider_authority_ref: str
    implementation_revision_ref: str
    instruction_revision_ref: str
    response_schema_revision_ref: str
    workflow_mode_ref: str
    modality_channel_ref: str

    _FIELDS = frozenset(
        {
            "configuration_ref",
            "rater_family_ref",
            "provider_authority_ref",
            "implementation_revision_ref",
            "instruction_revision_ref",
            "response_schema_revision_ref",
            "workflow_mode_ref",
            "modality_channel_ref",
        }
    )

    def __post_init__(self) -> None:
        for field_name in self._FIELDS:
            object.__setattr__(
                self, field_name, _reference(getattr(self, field_name), field_name)
            )

    @classmethod
    def from_mapping(cls, value: Any) -> RaterConfigurationRegistration:
        """Translate untrusted rater metadata into a registry entity."""
        payload = _mapping(value, "rater_configuration")
        _reject_unknown_fields(payload, cls._FIELDS, "rater_configuration")
        missing = cls._FIELDS - set(payload)
        if missing:
            raise MeasurementRegistryError(
                "missing_field",
                f"rater_configuration is missing fields: {sorted(missing)}",
            )
        return cls(**{field_name: payload[field_name] for field_name in cls._FIELDS})

    def to_payload(self) -> dict[str, str]:
        """Return the rater configuration's Open Host Service representation."""
        return {
            "configuration_ref": self.configuration_ref,
            "rater_family_ref": self.rater_family_ref,
            "provider_authority_ref": self.provider_authority_ref,
            "implementation_revision_ref": self.implementation_revision_ref,
            "instruction_revision_ref": self.instruction_revision_ref,
            "response_schema_revision_ref": self.response_schema_revision_ref,
            "workflow_mode_ref": self.workflow_mode_ref,
            "modality_channel_ref": self.modality_channel_ref,
        }


class MeasurementDefinition:
    """Aggregate root for one governable measurement-definition revision."""

    _FIELDS = frozenset(
        {
            "definition_ref",
            "definition_revision_ref",
            "construct_revision_ref",
            "rights_ref",
            "provenance_ref",
            "state",
            "criteria",
            "tasks",
            "rater_configurations",
            "validation_study_refs",
            "successor_revision_ref",
        }
    )

    def __init__(
        self,
        definition_ref: str,
        definition_revision_ref: str,
        construct_revision_ref: str,
        rights_ref: str,
        provenance_ref: str,
    ) -> None:
        """Create an empty draft aggregate with mandatory rights and provenance."""
        self._definition_ref = _reference(definition_ref, "definition_ref")
        self._definition_revision_ref = _reference(
            definition_revision_ref, "definition_revision_ref"
        )
        self._construct_revision_ref = _reference(
            construct_revision_ref, "construct_revision_ref"
        )
        self._rights_ref = _reference(rights_ref, "rights_ref")
        self._provenance_ref = _reference(provenance_ref, "provenance_ref")
        self._state = MeasurementDefinitionState.DRAFT
        self._criteria: list[CriterionRegistration] = []
        self._tasks: list[TaskRegistration] = []
        self._rater_configurations: list[RaterConfigurationRegistration] = []
        self._validation_study_refs: list[str] = []
        self._successor_revision_ref: str | None = None

    @classmethod
    def from_mapping(cls, value: Any) -> MeasurementDefinition:
        """Rehydrate a complete aggregate through a strict Anti-Corruption Layer."""
        payload = _mapping(value, "measurement_definition")
        _reject_unknown_fields(payload, cls._FIELDS, "measurement_definition")
        missing = cls._FIELDS - set(payload)
        if missing:
            raise MeasurementRegistryError(
                "missing_field",
                f"measurement_definition is missing fields: {sorted(missing)}",
            )
        aggregate = cls(
            definition_ref=payload["definition_ref"],
            definition_revision_ref=payload["definition_revision_ref"],
            construct_revision_ref=payload["construct_revision_ref"],
            rights_ref=payload["rights_ref"],
            provenance_ref=payload["provenance_ref"],
        )
        criteria = payload["criteria"]
        tasks = payload["tasks"]
        configurations = payload["rater_configurations"]
        if not isinstance(criteria, Sequence) or isinstance(criteria, (str, bytes)):
            raise MeasurementRegistryError(
                "invalid_collection", "criteria must be an array"
            )
        if not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes)):
            raise MeasurementRegistryError("invalid_collection", "tasks must be an array")
        if not isinstance(configurations, Sequence) or isinstance(
            configurations, (str, bytes)
        ):
            raise MeasurementRegistryError(
                "invalid_collection", "rater_configurations must be an array"
            )
        for criterion in criteria:
            aggregate.add_criterion(CriterionRegistration.from_mapping(criterion))
        for task in tasks:
            aggregate.add_task(TaskRegistration.from_mapping(task))
        for configuration in configurations:
            aggregate.add_rater_configuration(
                RaterConfigurationRegistration.from_mapping(configuration)
            )
        for study_ref in _exact_reference_sequence(
            payload["validation_study_refs"],
            "validation_study_refs",
            maximum=MAX_VALIDATION_STUDIES,
            allow_empty=True,
        ):
            aggregate.add_validation_study(study_ref)
        try:
            state = MeasurementDefinitionState(payload["state"])
        except (TypeError, ValueError) as exc:
            raise MeasurementRegistryError(
                "invalid_state", "measurement_definition has an invalid state"
            ) from exc
        successor = payload["successor_revision_ref"]
        if state is MeasurementDefinitionState.PUBLISHED:
            if successor is not None:
                raise MeasurementRegistryError(
                    "invalid_state", "a published definition has no successor reference"
                )
            aggregate.publish()
        elif state is MeasurementDefinitionState.SUPERSEDED:
            aggregate.publish()
            aggregate.supersede(successor)
        elif successor is not None:
            raise MeasurementRegistryError(
                "invalid_state", "a draft definition has no successor reference"
            )
        return aggregate

    def _require_draft(self) -> None:
        """Reject changes outside the aggregate's draft transaction boundary."""
        if self._state is not MeasurementDefinitionState.DRAFT:
            raise MeasurementRegistryError(
                "definition_not_draft", "only a draft definition may be changed"
            )

    def add_criterion(self, criterion: CriterionRegistration) -> None:
        """Add one criterion revision and its rubric reference to a draft."""
        self._require_draft()
        if type(criterion) is not CriterionRegistration:
            raise MeasurementRegistryError(
                "invalid_entity", "criterion has the wrong domain type"
            )
        if len(self._criteria) >= MAX_MEASUREMENT_CRITERIA:
            raise MeasurementRegistryError(
                "collection_limit", "criterion registration limit exceeded"
            )
        if any(
            current.criterion_ref == criterion.criterion_ref
            or current.criterion_revision_ref == criterion.criterion_revision_ref
            for current in self._criteria
        ):
            raise MeasurementRegistryError(
                "duplicate_criterion", "criterion identities and revisions must be unique"
            )
        self._criteria.append(criterion)

    def add_task(self, task: TaskRegistration) -> None:
        """Add one task revision to a draft definition."""
        self._require_draft()
        if type(task) is not TaskRegistration:
            raise MeasurementRegistryError("invalid_entity", "task has the wrong domain type")
        if len(self._tasks) >= MAX_MEASUREMENT_TASKS:
            raise MeasurementRegistryError(
                "collection_limit", "task registration limit exceeded"
            )
        if any(
            current.task_ref == task.task_ref
            or current.task_revision_ref == task.task_revision_ref
            for current in self._tasks
        ):
            raise MeasurementRegistryError(
                "duplicate_task", "task identities and revisions must be unique"
            )
        self._tasks.append(task)

    def add_rater_configuration(
        self, configuration: RaterConfigurationRegistration
    ) -> None:
        """Add one exact reusable rater configuration to a draft definition."""
        self._require_draft()
        if type(configuration) is not RaterConfigurationRegistration:
            raise MeasurementRegistryError(
                "invalid_entity", "rater_configuration has the wrong domain type"
            )
        if len(self._rater_configurations) >= MAX_RATER_CONFIGURATIONS:
            raise MeasurementRegistryError(
                "collection_limit", "rater configuration limit exceeded"
            )
        if any(
            current.configuration_ref == configuration.configuration_ref
            for current in self._rater_configurations
        ):
            raise MeasurementRegistryError(
                "duplicate_rater_configuration",
                "rater configuration identities must be unique",
            )
        self._rater_configurations.append(configuration)

    def add_validation_study(self, validation_study_ref: str) -> None:
        """Add one immutable validation-study reference to a draft definition."""
        self._require_draft()
        validation_study_ref = _reference(
            validation_study_ref, "validation_study_ref"
        )
        if len(self._validation_study_refs) >= MAX_VALIDATION_STUDIES:
            raise MeasurementRegistryError(
                "collection_limit", "validation study limit exceeded"
            )
        if validation_study_ref in self._validation_study_refs:
            raise MeasurementRegistryError(
                "duplicate_validation_study",
                "validation study references must be unique",
            )
        self._validation_study_refs.append(validation_study_ref)

    def publish(self) -> None:
        """Freeze a complete definition for Open Host Service consumption."""
        self._require_draft()
        if not self._criteria:
            raise MeasurementRegistryError(
                "empty_criterion_set", "publication requires at least one criterion"
            )
        if not self._tasks:
            raise MeasurementRegistryError(
                "empty_task_set", "publication requires at least one task"
            )
        if not self._rater_configurations:
            raise MeasurementRegistryError(
                "empty_rater_configuration_set",
                "publication requires at least one rater configuration",
            )
        registered_criteria = {criterion.criterion_ref for criterion in self._criteria}
        unregistered = {
            criterion_ref
            for task in self._tasks
            for criterion_ref in task.criterion_refs
            if criterion_ref not in registered_criteria
        }
        if unregistered:
            raise MeasurementRegistryError(
                "task_criterion_outside_definition",
                f"tasks reference unregistered criteria: {sorted(unregistered)}",
            )
        self._state = MeasurementDefinitionState.PUBLISHED

    def supersede(self, successor_revision_ref: Any) -> None:
        """Close a published revision in favor of one exact successor revision."""
        if self._state is not MeasurementDefinitionState.PUBLISHED:
            raise MeasurementRegistryError(
                "invalid_transition", "only a published definition may be superseded"
            )
        self._successor_revision_ref = _reference(
            successor_revision_ref, "successor_revision_ref"
        )
        self._state = MeasurementDefinitionState.SUPERSEDED

    @property
    def state(self) -> MeasurementDefinitionState:
        """Return the current definition lifecycle state."""
        return self._state

    @property
    def definition_ref(self) -> str:
        """Return the stable definition identity."""
        return self._definition_ref

    @property
    def definition_revision_ref(self) -> str:
        """Return the exact definition revision identity."""
        return self._definition_revision_ref

    @property
    def construct_revision_ref(self) -> str:
        """Return the exact construct revision identity."""
        return self._construct_revision_ref

    @property
    def rights_ref(self) -> str:
        """Return the rights-policy reference governing this revision."""
        return self._rights_ref

    @property
    def provenance_ref(self) -> str:
        """Return the provenance reference governing this revision."""
        return self._provenance_ref

    @property
    def criteria(self) -> tuple[CriterionRegistration, ...]:
        """Return an immutable criterion snapshot."""
        return tuple(self._criteria)

    @property
    def tasks(self) -> tuple[TaskRegistration, ...]:
        """Return an immutable task snapshot."""
        return tuple(self._tasks)

    @property
    def rater_configurations(self) -> tuple[RaterConfigurationRegistration, ...]:
        """Return an immutable rater-configuration snapshot."""
        return tuple(self._rater_configurations)

    @property
    def validation_study_refs(self) -> tuple[str, ...]:
        """Return immutable validation-study references."""
        return tuple(self._validation_study_refs)

    @property
    def successor_revision_ref(self) -> str | None:
        """Return the successor revision after supersession, when present."""
        return self._successor_revision_ref

    def to_context_bundle(self) -> dict[str, Any]:
        """Return the policy-filterable Open Host Service context bundle."""
        return {
            "definition_ref": self._definition_ref,
            "definition_revision_ref": self._definition_revision_ref,
            "construct_revision_ref": self._construct_revision_ref,
            "rights_ref": self._rights_ref,
            "provenance_ref": self._provenance_ref,
            "state": self._state.value,
            "criteria": [criterion.to_payload() for criterion in self._criteria],
            "tasks": [task.to_payload() for task in self._tasks],
            "rater_configurations": [
                configuration.to_payload()
                for configuration in self._rater_configurations
            ],
            "validation_study_refs": list(self._validation_study_refs),
            "successor_revision_ref": self._successor_revision_ref,
        }
