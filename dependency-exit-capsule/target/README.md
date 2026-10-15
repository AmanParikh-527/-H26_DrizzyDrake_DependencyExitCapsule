# Target Repositories

Place the target GitHub repositories you wish to analyze in this directory.

Example:
```
dependency-exit-capsule/target/
└── LinkWatch/
    ├── linkwatch/
    ├── tests/
    ├── pyproject.toml
    └── requirements.txt
```

To run the pipeline against a target repository:
```bash
python dependency-exit-capsule/scripts/run_pipeline.py --repo dependency-exit-capsule/target/LinkWatch --dependency Jinja2
```
Outputs will be written to `capsule_output/` next to `dependency-exit-capsule`.
