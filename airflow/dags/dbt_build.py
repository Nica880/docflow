"""dbt_build: export the Parquet lake, `dbt build` (models + tests) into gold, publish DQ report.

The data-quality report is `rpt_pipeline_health` from gold, written as JSON to the shared data
volume: `<data>/reports/pipeline_health.json` (latest) and `pipeline_health_<ds>.json`.
"""

from __future__ import annotations

from _common import DAG_KWARGS, DOCFLOW_PYTHON, RUN_ID_TEMPLATE
from airflow.decorators import dag, task


@dag(
    dag_id="dbt_build",
    schedule="@daily",
    description="export_lake -> dbt build -> publish data-quality report.",
    doc_md=__doc__,
    **DAG_KWARGS,
)
def dbt_build() -> None:
    @task.external_python(python=DOCFLOW_PYTHON, expect_airflow=False)
    def export_lake() -> dict:
        from core.config import get_settings
        from core.logging import configure_logging
        from core.telemetry import setup_tracing
        from processing.export import export_lake as export

        configure_logging(get_settings().log_level)
        setup_tracing("docflow-airflow")
        # Full overwrite of each lake table -> idempotent.
        return export()

    @task.external_python(python=DOCFLOW_PYTHON, expect_airflow=False)
    def dbt_build_gold(pipeline_run_id: str) -> dict:
        import subprocess
        import sys
        from pathlib import Path

        from core.config import get_settings
        from core.logging import configure_logging
        from core.telemetry import pipeline_run, setup_tracing

        s = get_settings()
        configure_logging(s.log_level)
        setup_tracing("docflow-airflow")
        s.warehouse_dir.mkdir(parents=True, exist_ok=True)
        dbt = Path(sys.executable).with_name("dbt")
        project = str(s.dbt_project_dir.resolve())
        args = [str(dbt), "build", "--project-dir", project, "--profiles-dir", project]
        with pipeline_run("dbt_build", pipeline_run_id):
            result = subprocess.run(args, check=False, cwd=project)  # noqa: S603
        if result.returncode:
            raise RuntimeError(f"dbt build failed with exit code {result.returncode}")
        return {"returncode": result.returncode}

    @task.external_python(python=DOCFLOW_PYTHON, expect_airflow=False)
    def publish_quality_report(logical_ds: str) -> dict:
        import json
        from datetime import UTC, datetime

        import duckdb

        from core.config import get_settings
        from core.logging import configure_logging, get_logger

        s = get_settings()
        configure_logging(s.log_level)
        log = get_logger("dags.dbt_build")
        conn = duckdb.connect(str(s.gold_db_path), read_only=True)
        try:
            cur = conn.execute("select * from rpt_pipeline_health order by dag_id")
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
        finally:
            conn.close()
        report = {
            "report": "rpt_pipeline_health",
            "logical_date": str(logical_ds),
            "generated_at": datetime.now(UTC).isoformat(),
            "gold_db": str(s.gold_db_path),
            "dags": rows,
        }
        out_dir = s.warehouse_dir.parent / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        body = json.dumps(report, indent=2, default=str)
        (out_dir / f"pipeline_health_{logical_ds}.json").write_text(body, encoding="utf-8")
        (out_dir / "pipeline_health.json").write_text(body, encoding="utf-8")
        for row in rows:
            log.info("dq.pipeline_health", **{k: str(v) for k, v in row.items()})
        return {"path": str(out_dir / "pipeline_health.json"), "dags": len(rows)}

    (
        export_lake()
        >> dbt_build_gold(pipeline_run_id=RUN_ID_TEMPLATE)
        >> publish_quality_report(logical_ds="{{ ds }}")
    )


dbt_build()
