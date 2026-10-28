import pytest
from pydantic import ValidationError

from backend.schemas.workflow import WorkflowCreate, WorkflowTaskCreate


def test_workflow_rejects_more_than_200_tasks():
    with pytest.raises(ValidationError):
        WorkflowCreate(name="too-large", tasks=[{"name": f"task-{index}"} for index in range(201)])


def test_task_rejects_more_than_100_dependencies():
    with pytest.raises(ValidationError):
        WorkflowTaskCreate(name="task", dependencies=[f"dep-{index}" for index in range(101)])


def test_workflow_requires_at_least_one_task():
    with pytest.raises(ValidationError):
        WorkflowCreate(name="empty", tasks=[])
