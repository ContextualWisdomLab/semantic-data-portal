"""Tests for the governed measurement-context registry."""

from __future__ import annotations

from copy import deepcopy

import pytest

from sdp_core.measurement_registry import (
    MAX_MEASUREMENT_CRITERIA,
    MAX_MEASUREMENT_REFERENCE_LENGTH,
    MAX_MEASUREMENT_TASKS,
    MAX_RATER_CONFIGURATIONS,
    MAX_VALIDATION_STUDIES,
    CriterionRegistration,
    MeasurementDefinition,
    MeasurementDefinitionState,
    MeasurementRegistryError,
    RaterConfigurationRegistration,
    TaskRegistration,
)


def _criterion(
    criterion_ref: str = "criterion_argument_quality",
    revision_ref: str = "criterion_argument_quality_v1",
) -> dict[str, str]:
    return {
        "criterion_ref": criterion_ref,
        "criterion_revision_ref": revision_ref,
        "rubric_revision_ref": f"rubric_{criterion_ref}_v1",
    }


def _task(
    task_ref: str = "task_argument_essay",
    revision_ref: str = "task_argument_essay_v1",
    criterion_refs: list[str] | None = None,
) -> dict[str, object]:
    return {
        "task_ref": task_ref,
        "task_revision_ref": revision_ref,
        "criterion_refs": criterion_refs or ["criterion_argument_quality"],
    }


def _configuration(
    configuration_ref: str = "rater_configuration_model_alpha_v1",
) -> dict[str, str]:
    return {
        "configuration_ref": configuration_ref,
        "rater_family_ref": "rater_family_model_alpha",
        "provider_authority_ref": "provider_authority_alpha",
        "implementation_revision_ref": "implementation_model_alpha_v1",
        "instruction_revision_ref": "instruction_analytic_rubric_v1",
        "response_schema_revision_ref": "response_schema_observation_v1",
        "workflow_mode_ref": "workflow_blind_independent",
        "modality_channel_ref": "modality_text",
    }


def _draft() -> MeasurementDefinition:
    return MeasurementDefinition(
        definition_ref="measurement_definition_argument_writing",
        definition_revision_ref="measurement_definition_argument_writing_v1",
        construct_revision_ref="construct_argument_writing_v1",
        rights_ref="rights_internal_measurement_v1",
        provenance_ref="provenance_measurement_design_v1",
    )


def _complete_draft() -> MeasurementDefinition:
    definition = _draft()
    definition.add_criterion(CriterionRegistration.from_mapping(_criterion()))
    definition.add_task(TaskRegistration.from_mapping(_task()))
    definition.add_rater_configuration(
        RaterConfigurationRegistration.from_mapping(_configuration())
    )
    definition.add_validation_study("validation_study_recovery_v1")
    return definition


def _payload(state: str = "draft") -> dict[str, object]:
    payload = {
        "definition_ref": "measurement_definition_argument_writing",
        "definition_revision_ref": "measurement_definition_argument_writing_v1",
        "construct_revision_ref": "construct_argument_writing_v1",
        "rights_ref": "rights_internal_measurement_v1",
        "provenance_ref": "provenance_measurement_design_v1",
        "state": state,
        "criteria": [_criterion()],
        "tasks": [_task()],
        "rater_configurations": [_configuration()],
        "validation_study_refs": ["validation_study_recovery_v1"],
        "successor_revision_ref": None,
    }
    if state == "superseded":
        payload["successor_revision_ref"] = (
            "measurement_definition_argument_writing_v2"
        )
    return payload


def _error_code(callable_object) -> str:
    with pytest.raises(MeasurementRegistryError) as exc_info:
        callable_object()
    return exc_info.value.code


def test_registry_round_trip_preserves_reference_metadata_only() -> None:
    definition = MeasurementDefinition.from_mapping(_payload("published"))
    bundle = definition.to_context_bundle()

    assert bundle == _payload("published")
    assert definition.state is MeasurementDefinitionState.PUBLISHED
    assert definition.definition_ref == "measurement_definition_argument_writing"
    assert definition.definition_revision_ref.endswith("_v1")
    assert definition.construct_revision_ref == "construct_argument_writing_v1"
    assert definition.rights_ref == "rights_internal_measurement_v1"
    assert definition.provenance_ref == "provenance_measurement_design_v1"
    assert definition.criteria[0].rubric_revision_ref.startswith("rubric_")
    assert definition.tasks[0].criterion_refs == ("criterion_argument_quality",)
    assert definition.rater_configurations[0].configuration_ref.startswith(
        "rater_configuration_"
    )
    assert definition.validation_study_refs == ("validation_study_recovery_v1",)
    assert definition.successor_revision_ref is None
    assert not {
        "raw_response",
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
    }.intersection(bundle)


def test_authority_leakage_and_unknown_fields_fail_closed_at_every_boundary() -> None:
    for field_name in ("raw_response", "score", "adjudication_state"):
        payload = _payload()
        payload[field_name] = "forbidden"
        assert _error_code(
            lambda payload=payload: MeasurementDefinition.from_mapping(payload)
        ) == "authority_leakage"

    unknown = _payload()
    unknown["display_label"] = "not-yet-contracted"
    assert _error_code(lambda: MeasurementDefinition.from_mapping(unknown)) == (
        "unknown_field"
    )

    criterion = _criterion()
    criterion["criterion_observation"] = "forbidden"
    assert _error_code(lambda: CriterionRegistration.from_mapping(criterion)) == (
        "authority_leakage"
    )

    task = _task()
    task["provider_payload"] = {}
    assert _error_code(lambda: TaskRegistration.from_mapping(task)) == (
        "authority_leakage"
    )

    configuration = _configuration()
    configuration["final_score"] = 3
    assert _error_code(
        lambda: RaterConfigurationRegistration.from_mapping(configuration)
    ) == "authority_leakage"


def test_mapping_boundaries_reject_non_objects_non_string_keys_and_missing_fields() -> None:
    assert _error_code(lambda: MeasurementDefinition.from_mapping([])) == (
        "invalid_object"
    )
    assert _error_code(lambda: CriterionRegistration.from_mapping({1: "value"})) == (
        "invalid_object_key"
    )

    payload = _payload()
    del payload["rights_ref"]
    assert _error_code(lambda: MeasurementDefinition.from_mapping(payload)) == (
        "missing_field"
    )

    criterion = _criterion()
    del criterion["rubric_revision_ref"]
    assert _error_code(lambda: CriterionRegistration.from_mapping(criterion)) == (
        "missing_field"
    )

    task = _task()
    del task["criterion_refs"]
    assert _error_code(lambda: TaskRegistration.from_mapping(task)) == "missing_field"

    configuration = _configuration()
    del configuration["workflow_mode_ref"]
    assert _error_code(
        lambda: RaterConfigurationRegistration.from_mapping(configuration)
    ) == "missing_field"


def test_references_are_exact_bounded_non_numeric_and_control_free() -> None:
    for invalid in (
        "",
        " reference ",
        "123.4",
        "bad\nreference",
        "x" * (MAX_MEASUREMENT_REFERENCE_LENGTH + 1),
    ):
        assert _error_code(
            lambda invalid=invalid: MeasurementDefinition(
                definition_ref=invalid,
                definition_revision_ref="definition_revision_v1",
                construct_revision_ref="construct_revision_v1",
                rights_ref="rights_revision_v1",
                provenance_ref="provenance_revision_v1",
            )
        ) == "invalid_reference"

    assert _error_code(
        lambda: MeasurementDefinition(
            definition_ref=object(),  # type: ignore[arg-type]
            definition_revision_ref="definition_revision_v1",
            construct_revision_ref="construct_revision_v1",
            rights_ref="rights_revision_v1",
            provenance_ref="provenance_revision_v1",
        )
    ) == "invalid_reference"


def test_entity_round_trips_are_exact_and_collections_are_immutable() -> None:
    criterion_payload = _criterion()
    criterion = CriterionRegistration.from_mapping(criterion_payload)
    assert criterion.to_payload() == criterion_payload

    task_payload = _task()
    task = TaskRegistration.from_mapping(task_payload)
    assert task.to_payload() == task_payload

    configuration_payload = _configuration()
    configuration = RaterConfigurationRegistration.from_mapping(configuration_payload)
    assert configuration.to_payload() == configuration_payload

    definition = _complete_draft()
    criterion_snapshot = definition.criteria
    task_snapshot = definition.tasks
    configuration_snapshot = definition.rater_configurations
    validation_snapshot = definition.validation_study_refs

    assert isinstance(criterion_snapshot, tuple)
    assert isinstance(task_snapshot, tuple)
    assert isinstance(configuration_snapshot, tuple)
    assert isinstance(validation_snapshot, tuple)


def test_task_criterion_reference_set_is_non_empty_unique_and_bounded() -> None:
    empty = _task(criterion_refs=[])
    empty["criterion_refs"] = []
    assert _error_code(lambda: TaskRegistration.from_mapping(empty)) == (
        "invalid_reference_set"
    )

    duplicate = _task(criterion_refs=["criterion_a", "criterion_a"])
    assert _error_code(lambda: TaskRegistration.from_mapping(duplicate)) == (
        "duplicate_reference"
    )

    wrong_type = _task()
    wrong_type["criterion_refs"] = "criterion_a"
    assert _error_code(lambda: TaskRegistration.from_mapping(wrong_type)) == (
        "invalid_reference_set"
    )

    oversized = _task(
        criterion_refs=[
            f"criterion_{index}" for index in range(MAX_MEASUREMENT_CRITERIA + 1)
        ]
    )
    assert _error_code(lambda: TaskRegistration.from_mapping(oversized)) == (
        "invalid_reference_set"
    )


def test_draft_aggregate_rejects_wrong_types_duplicates_and_limits() -> None:
    definition = _draft()
    assert _error_code(lambda: definition.add_criterion("wrong")) == "invalid_entity"
    assert _error_code(lambda: definition.add_task("wrong")) == "invalid_entity"
    assert _error_code(lambda: definition.add_rater_configuration("wrong")) == (
        "invalid_entity"
    )

    criterion = CriterionRegistration.from_mapping(_criterion())
    definition.add_criterion(criterion)
    assert _error_code(lambda: definition.add_criterion(criterion)) == (
        "duplicate_criterion"
    )
    same_revision = CriterionRegistration.from_mapping(
        _criterion("criterion_other", criterion.criterion_revision_ref)
    )
    assert _error_code(lambda: definition.add_criterion(same_revision)) == (
        "duplicate_criterion"
    )

    task = TaskRegistration.from_mapping(_task())
    definition.add_task(task)
    assert _error_code(lambda: definition.add_task(task)) == "duplicate_task"
    same_revision_task = TaskRegistration.from_mapping(
        _task("task_other", task.task_revision_ref)
    )
    assert _error_code(lambda: definition.add_task(same_revision_task)) == (
        "duplicate_task"
    )

    configuration = RaterConfigurationRegistration.from_mapping(_configuration())
    definition.add_rater_configuration(configuration)
    assert _error_code(
        lambda: definition.add_rater_configuration(configuration)
    ) == "duplicate_rater_configuration"

    definition.add_validation_study("validation_study_v1")
    assert _error_code(
        lambda: definition.add_validation_study("validation_study_v1")
    ) == "duplicate_validation_study"


def test_collection_limits_are_enforced_without_silent_truncation() -> None:
    criteria = _draft()
    for index in range(MAX_MEASUREMENT_CRITERIA):
        criteria.add_criterion(
            CriterionRegistration.from_mapping(
                _criterion(f"criterion_{index}", f"criterion_revision_{index}")
            )
        )
    assert _error_code(
        lambda: criteria.add_criterion(
            CriterionRegistration.from_mapping(
                _criterion("criterion_overflow", "criterion_revision_overflow")
            )
        )
    ) == "collection_limit"

    tasks = _draft()
    for index in range(MAX_MEASUREMENT_TASKS):
        tasks.add_task(
            TaskRegistration.from_mapping(
                _task(
                    f"task_{index}",
                    f"task_revision_{index}",
                    ["criterion_reference"],
                )
            )
        )
    assert _error_code(
        lambda: tasks.add_task(
            TaskRegistration.from_mapping(
                _task(
                    "task_overflow",
                    "task_revision_overflow",
                    ["criterion_reference"],
                )
            )
        )
    ) == "collection_limit"

    configurations = _draft()
    for index in range(MAX_RATER_CONFIGURATIONS):
        configurations.add_rater_configuration(
            RaterConfigurationRegistration.from_mapping(
                _configuration(f"rater_configuration_{index}")
            )
        )
    assert _error_code(
        lambda: configurations.add_rater_configuration(
            RaterConfigurationRegistration.from_mapping(
                _configuration("rater_configuration_overflow")
            )
        )
    ) == "collection_limit"

    studies = _draft()
    for index in range(MAX_VALIDATION_STUDIES):
        studies.add_validation_study(f"validation_study_{index}")
    assert _error_code(
        lambda: studies.add_validation_study("validation_study_overflow")
    ) == "collection_limit"


def test_publication_requires_complete_referentially_closed_definition() -> None:
    definition = _draft()
    assert _error_code(definition.publish) == "empty_criterion_set"

    definition.add_criterion(CriterionRegistration.from_mapping(_criterion()))
    assert _error_code(definition.publish) == "empty_task_set"

    definition.add_task(TaskRegistration.from_mapping(_task()))
    assert _error_code(definition.publish) == "empty_rater_configuration_set"

    definition.add_rater_configuration(
        RaterConfigurationRegistration.from_mapping(_configuration())
    )
    definition.publish()
    assert definition.state is MeasurementDefinitionState.PUBLISHED

    outside = _draft()
    outside.add_criterion(CriterionRegistration.from_mapping(_criterion()))
    outside.add_task(
        TaskRegistration.from_mapping(
            _task(criterion_refs=["criterion_not_registered"])
        )
    )
    outside.add_rater_configuration(
        RaterConfigurationRegistration.from_mapping(_configuration())
    )
    assert _error_code(outside.publish) == "task_criterion_outside_definition"


def test_publication_freezes_aggregate_and_supersession_is_explicit() -> None:
    definition = _complete_draft()
    definition.publish()

    assert _error_code(
        lambda: definition.add_criterion(
            CriterionRegistration.from_mapping(
                _criterion("criterion_new", "criterion_new_v1")
            )
        )
    ) == "definition_not_draft"
    assert _error_code(
        lambda: definition.add_task(
            TaskRegistration.from_mapping(
                _task("task_new", "task_new_v1", ["criterion_argument_quality"])
            )
        )
    ) == "definition_not_draft"
    assert _error_code(
        lambda: definition.add_rater_configuration(
            RaterConfigurationRegistration.from_mapping(
                _configuration("rater_configuration_new")
            )
        )
    ) == "definition_not_draft"
    assert _error_code(
        lambda: definition.add_validation_study("validation_study_new")
    ) == "definition_not_draft"
    assert _error_code(definition.publish) == "definition_not_draft"

    definition.supersede("measurement_definition_argument_writing_v2")
    assert definition.state is MeasurementDefinitionState.SUPERSEDED
    assert (
        definition.successor_revision_ref
        == "measurement_definition_argument_writing_v2"
    )
    assert _error_code(
        lambda: definition.supersede("measurement_definition_argument_writing_v3")
    ) == "invalid_transition"

    draft = _draft()
    assert _error_code(
        lambda: draft.supersede("measurement_definition_argument_writing_v2")
    ) == "invalid_transition"


def test_rehydration_validates_state_and_successor_contract() -> None:
    superseded = MeasurementDefinition.from_mapping(_payload("superseded"))
    assert superseded.state is MeasurementDefinitionState.SUPERSEDED
    assert superseded.successor_revision_ref is not None

    invalid_state = _payload()
    invalid_state["state"] = "retired"
    assert _error_code(lambda: MeasurementDefinition.from_mapping(invalid_state)) == (
        "invalid_state"
    )

    published_successor = _payload("published")
    published_successor["successor_revision_ref"] = "unexpected_successor"
    assert _error_code(
        lambda: MeasurementDefinition.from_mapping(published_successor)
    ) == "invalid_state"

    draft_successor = _payload("draft")
    draft_successor["successor_revision_ref"] = "unexpected_successor"
    assert _error_code(lambda: MeasurementDefinition.from_mapping(draft_successor)) == (
        "invalid_state"
    )

    superseded_without_successor = _payload("superseded")
    superseded_without_successor["successor_revision_ref"] = None
    assert _error_code(
        lambda: MeasurementDefinition.from_mapping(superseded_without_successor)
    ) == "invalid_reference"


def test_rehydration_collections_are_arrays_and_caller_mutation_isolated() -> None:
    for field_name in ("criteria", "tasks", "rater_configurations"):
        payload = _payload()
        payload[field_name] = "not-an-array"
        assert _error_code(
            lambda payload=payload: MeasurementDefinition.from_mapping(payload)
        ) == "invalid_collection"

    validation = _payload()
    validation["validation_study_refs"] = "not-an-array"
    assert _error_code(lambda: MeasurementDefinition.from_mapping(validation)) == (
        "invalid_reference_set"
    )

    payload = _payload()
    original = deepcopy(payload)
    definition = MeasurementDefinition.from_mapping(payload)
    payload["criteria"][0]["criterion_ref"] = "mutated"  # type: ignore[index]
    payload["tasks"][0]["criterion_refs"].append("mutated")  # type: ignore[index,union-attr]
    payload["rater_configurations"][0]["configuration_ref"] = "mutated"  # type: ignore[index]
    payload["validation_study_refs"].append("mutated")  # type: ignore[union-attr]

    assert definition.to_context_bundle() == original


def test_registry_errors_expose_stable_machine_codes_and_messages() -> None:
    error = MeasurementRegistryError("test_code", "test message")
    assert error.code == "test_code"
    assert str(error) == "test message"
