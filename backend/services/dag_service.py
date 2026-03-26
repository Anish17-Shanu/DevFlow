from collections import defaultdict, deque


class DagValidationError(ValueError):
    """Raised when workflow dependencies do not form a valid DAG."""


class DagService:
    @staticmethod
    def validate(tasks: list[dict]) -> None:
        names = {task["name"] for task in tasks}
        if len(names) != len(tasks):
            raise DagValidationError("Task names must be unique within a workflow.")

        adjacency: dict[str, list[str]] = defaultdict(list)
        indegree = {task["name"]: 0 for task in tasks}

        for task in tasks:
            for dependency in task.get("dependencies", []):
                if dependency not in names:
                    raise DagValidationError(f"Dependency '{dependency}' does not exist.")
                adjacency[dependency].append(task["name"])
                indegree[task["name"]] += 1

        queue = deque([name for name, degree in indegree.items() if degree == 0])
        visited = 0

        while queue:
            current = queue.popleft()
            visited += 1
            for neighbor in adjacency[current]:
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(tasks):
            raise DagValidationError("Workflow dependencies contain a cycle.")
