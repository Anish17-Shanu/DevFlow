import pytest

from backend.services.dag_service import DagService, DagValidationError


def test_dag_validation_rejects_missing_dependencies():
    with pytest.raises(DagValidationError):
        DagService.validate(
            [
                {"name": "extract", "dependencies": []},
                {"name": "transform", "dependencies": ["missing-task"]},
            ]
        )


def test_dag_validation_rejects_cycles():
    with pytest.raises(DagValidationError):
        DagService.validate(
            [
                {"name": "extract", "dependencies": ["load"]},
                {"name": "load", "dependencies": ["extract"]},
            ]
        )


def test_dag_validation_accepts_valid_graph():
    DagService.validate(
        [
            {"name": "extract", "dependencies": []},
            {"name": "transform", "dependencies": ["extract"]},
            {"name": "load", "dependencies": ["transform"]},
        ]
    )
