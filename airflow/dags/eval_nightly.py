"""eval_nightly: run the eval harness on the ground-truth set for both LLMs + rules baseline.

The Markdown report is written to `<data>/eval/<date>.md` on the shared data volume; per-model
metrics are also stored in the `eval_runs` table (served by the API's eval dashboard).
"""

from __future__ import annotations

from _common import DAG_KWARGS, DOCFLOW_PYTHON
from airflow.decorators import dag, task
from airflow.models.param import Param


@dag(
    dag_id="eval_nightly",
    schedule="0 2 * * *",
    description="Two-model (+ rules baseline) evaluation against ground truth.",
    doc_md=__doc__,
    params={"limit": Param(None, type=["null", "integer"], description="Max ground-truth docs")},
    **DAG_KWARGS,
)
def eval_nightly() -> None:
    @task.external_python(python=DOCFLOW_PYTHON, expect_airflow=False)
    def run_eval(limit: int | None) -> list:
        from core.config import get_settings
        from core.logging import configure_logging
        from core.telemetry import setup_tracing
        from processing.evaluation import run_eval as evaluate
        from processing.llm import RULES_MODEL

        s = get_settings()
        configure_logging(s.log_level)
        setup_tracing("docflow-airflow")
        models = [s.llm_model, s.llm_compare_model, RULES_MODEL]
        results = evaluate(
            models,
            limit=int(limit) if limit else None,
            report_dir=s.warehouse_dir.parent / "eval",
        )
        return [
            {
                "model": r["model"],
                "prompt_version": r["prompt_version"],
                "docs": r["n_docs"],
                "mean_field_accuracy": r["metrics"].get("mean_field_accuracy"),
            }
            for r in results
        ]

    run_eval(limit="{{ params.limit }}")


eval_nightly()
