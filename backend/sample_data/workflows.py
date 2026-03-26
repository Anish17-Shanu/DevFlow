SAMPLE_WORKFLOWS = [
    {
        "name": "ETL Pipeline",
        "tasks": [
            {
                "name": "extract",
                "dependencies": [],
                "config": {"duration_ms": 1200, "max_retries": 1, "priority": 2},
            },
            {
                "name": "transform",
                "dependencies": ["extract"],
                "config": {"duration_ms": 1400, "fail_first_n": 1, "max_retries": 2, "backoff_seconds": 1},
            },
            {
                "name": "quality_check",
                "dependencies": ["transform"],
                "config": {"duration_ms": 900, "priority": 1},
            },
            {
                "name": "load",
                "dependencies": ["quality_check"],
                "config": {"duration_ms": 1300},
            },
        ],
    },
    {
        "name": "ML Training Pipeline",
        "tasks": [
            {"name": "prepare_dataset", "dependencies": [], "config": {"duration_ms": 1000}},
            {"name": "train_model", "dependencies": ["prepare_dataset"], "config": {"duration_ms": 2200}},
            {"name": "evaluate_model", "dependencies": ["train_model"], "config": {"duration_ms": 1100}},
            {
                "name": "deploy_shadow",
                "dependencies": ["evaluate_model"],
                "config": {"duration_ms": 800, "delay_seconds": 1},
            },
        ],
    },
]
