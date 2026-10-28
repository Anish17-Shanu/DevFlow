TEMPLATE_WORKFLOWS = [
    {
        "name": "Service health probe",
        "description": "Calls three public endpoints over HTTP and records their status.",
        "tasks": [
            {
                "name": "probe_example",
                "dependencies": [],
                "config": {
                    "type": "http",
                    "method": "GET",
                    "url": "https://example.com",
                    "expected_status": 200,
                    "max_retries": 2,
                    "backoff_seconds": 2,
                    "timeout_seconds": 15,
                },
            },
            {
                "name": "record_result",
                "dependencies": ["probe_example"],
                "config": {"type": "echo", "message": "Health probe finished.", "duration_ms": 100},
            },
        ],
    },
    {
        "name": "Fan-out / fan-in",
        "description": "Runs three parallel branches and joins them before publishing.",
        "tasks": [
            {"name": "start", "dependencies": [], "config": {"duration_ms": 300}},
            {"name": "branch_a", "dependencies": ["start"], "config": {"duration_ms": 800}},
            {"name": "branch_b", "dependencies": ["start"], "config": {"duration_ms": 1200}},
            {"name": "branch_c", "dependencies": ["start"], "config": {"duration_ms": 600}},
            {
                "name": "join",
                "dependencies": ["branch_a", "branch_b", "branch_c"],
                "config": {"duration_ms": 400},
            },
            {"name": "publish", "dependencies": ["join"], "config": {"type": "echo", "duration_ms": 200}},
        ],
    },
    {
        "name": "Resilient ingestion",
        "description": "Demonstrates retries with exponential backoff and idempotent output.",
        "tasks": [
            {
                "name": "fetch",
                "dependencies": [],
                "config": {"fail_first_n": 2, "max_retries": 3, "backoff_seconds": 1, "duration_ms": 500},
            },
            {"name": "normalize", "dependencies": ["fetch"], "config": {"duration_ms": 700}},
            {
                "name": "write",
                "dependencies": ["normalize"],
                "config": {"type": "echo", "message": "Rows written.", "duration_ms": 400},
            },
        ],
    },
]
