"""`docflow` command line: every pipeline step is runnable by hand, by Airflow and by CI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from core.config import get_settings
from core.logging import configure_logging, get_logger
from core.telemetry import setup_tracing

app = typer.Typer(no_args_is_help=True, add_completion=False, help="DocFlow pipeline CLI")
log = get_logger("docflow.cli")


@app.callback()
def _init() -> None:
    s = get_settings()
    configure_logging(s.log_level)
    setup_tracing("docflow-cli")


def _echo(obj: object) -> None:
    typer.echo(json.dumps(obj, indent=2, default=str))


@app.command("init-db")
def init_db(with_queue: bool = True) -> None:
    """Run Alembic migrations, create buckets and (optionally) the SQS queue."""
    from alembic import command
    from alembic.config import Config

    from core import storage

    command.upgrade(Config(str(Path(__file__).resolve().parent.parent / "alembic.ini")), "head")
    storage.ensure_buckets()
    if with_queue:
        from core import queue

        queue.queue_url()
    typer.echo("database migrated, buckets ready")


@app.command()
def ingest(
    tickers: Annotated[list[str] | None, typer.Option("--ticker", "-t")] = None,
    watchlist: bool = False,
    demo: bool = False,
    forms: str = "10-K",
    years: int = 10,
    since: str | None = None,
    max_per_company: int | None = None,
    max_filings: int | None = None,
    workers: int = 4,
    dag_id: str = "edgar_ingest",
) -> None:
    """Download filings into bronze (idempotent)."""
    from ingestion.bronze import ingest_tickers
    from ingestion.watchlist import DEMO, WATCHLIST

    chosen = list(tickers or []) + (WATCHLIST if watchlist else []) + (DEMO if demo else [])
    if not chosen:
        raise typer.BadParameter("pass --ticker, --watchlist or --demo")
    start = date.fromisoformat(since) if since else date(date.today().year - years, 1, 1)
    res = ingest_tickers(
        chosen, tuple(forms.split(",")), start, None, max_per_company, max_filings, workers, dag_id
    )
    _echo(res.__dict__ | {"accessions": len(res.accessions)})


@app.command()
def parse(limit: int | None = None, reparse: bool = False) -> None:
    """Bronze -> silver sections."""
    from processing.silver import parse_pending

    _echo(parse_pending(limit, reparse))


@app.command("ground-truth")
def ground_truth() -> None:
    """Seed ground truth from XBRL company facts."""
    from processing.ground_truth import seed_ground_truth

    _echo({"rows": seed_ground_truth()})


@app.command()
def enqueue(
    limit: int | None = None, latest_per_company: int | None = None, model: str | None = None
) -> None:
    """Queue parsed filings for LLM extraction (SQS)."""
    from processing.worker import enqueue_pending

    _echo({"enqueued": enqueue_pending(limit, latest_per_company, model)})


@app.command()
def worker(
    max_messages: int | None = None, idle_exit: float | None = None, serve: bool = False
) -> None:
    """Consume extraction jobs from SQS."""
    from processing.worker import run_worker, worker_main

    if serve:
        worker_main()
    else:
        _echo(run_worker(max_messages, idle_exit))


@app.command()
def extract(
    limit: int | None = None, latest_per_company: int | None = None, model: str | None = None
) -> None:
    """Extract facts in-process (no queue)."""
    from processing.worker import extract_inline

    _echo(extract_inline(limit, latest_per_company, model))


@app.command()
def invoices(n: int = 6, model: str | None = None) -> None:
    """Generate synthetic invoices and extract them (human-review demo)."""
    from processing.invoices import generate_and_extract

    out = generate_and_extract(n, model)
    _echo({"invoices": len(out), "review_tasks": sum(o.review_tasks for o in out)})


@app.command()
def embed(all_filings: bool = False) -> None:
    """Embed sections into pgvector."""
    from processing.embed import embed_sections

    _echo({"chunks": embed_sections(latest_only=not all_filings)})


@app.command()
def export() -> None:
    """Export Postgres + extraction facts to the Parquet lake read by dbt."""
    from processing.export import export_lake

    _echo(export_lake())


@app.command()
def dbt(command: str = "build") -> None:
    """Run dbt (build by default) against the gold DuckDB warehouse."""
    from core.telemetry import pipeline_run

    s = get_settings()
    s.warehouse_dir.mkdir(parents=True, exist_ok=True)
    exe = Path(sys.executable).with_name("dbt.exe" if sys.platform == "win32" else "dbt")
    args = [str(exe) if exe.exists() else "dbt", command, "--project-dir", str(s.dbt_project_dir),
            "--profiles-dir", str(s.dbt_project_dir)]  # fmt: skip
    with pipeline_run("dbt_build"):
        env = os.environ | {
            "DOCFLOW_LAKE_DIR": str(s.lake_dir.resolve()),
            "DOCFLOW_GOLD_DB": str(s.gold_db_path.resolve()),
        }
        result = subprocess.run(args, check=False, env=env)  # noqa: S603 - fixed argv
    if result.returncode:
        raise typer.Exit(result.returncode)


@app.command("eval")
def evaluate(
    models: Annotated[list[str] | None, typer.Option("--model", "-m")] = None,
    prompts: Annotated[list[str] | None, typer.Option("--prompt", "-p")] = None,
    limit: int | None = None,
) -> None:
    """Run the eval harness on the ground-truth set and write docs/eval/<date>.md."""
    from processing.evaluation import run_eval
    from processing.llm import RULES_MODEL

    s = get_settings()
    default = (
        [RULES_MODEL]
        if s.llm_provider == "fake"
        else [s.llm_model, s.llm_compare_model, RULES_MODEL]
    )
    results = run_eval(list(models or default), list(prompts) if prompts else None, limit)
    _echo([{"model": r["model"], "prompt": r["prompt_version"], "docs": r["n_docs"],
            "mean_field_accuracy": r["metrics"].get("mean_field_accuracy")} for r in results])  # fmt: skip


@app.command()
def ask(question: str) -> None:
    """Ask the Q&A agent from the terminal."""
    from api.agent.agent import Agent

    typer.echo(Agent().ask(question).model_dump_json(indent=2))


@app.command()
def mcp() -> None:
    """Run the MCP server on stdio."""
    from api.mcp_server import main

    main()


@app.command()
def api(host: str = "0.0.0.0", port: int = 8000, reload: bool = False) -> None:  # noqa: S104
    """Serve the HTTP API."""
    import uvicorn

    uvicorn.run("api.main:app", host=host, port=port, reload=reload)


@app.command()
def demo(
    max_filings: int | None = None,
    extract_filings: int | None = None,
    use_queue: bool = False,
    skip_ingest: bool = False,
) -> None:
    """Small-mode end-to-end run: ingest -> parse -> extract -> embed -> export -> dbt -> eval."""
    from ingestion.bronze import ingest_tickers
    from ingestion.watchlist import DEMO, WATCHLIST
    from processing.embed import embed_sections
    from processing.evaluation import run_eval
    from processing.export import export_lake
    from processing.ground_truth import seed_ground_truth
    from processing.invoices import generate_and_extract
    from processing.llm import RULES_MODEL
    from processing.silver import parse_pending
    from processing.worker import enqueue_pending, extract_inline, run_worker

    s = get_settings()
    n_filings = max_filings or s.demo_max_filings
    n_extract = extract_filings or s.demo_extract_filings
    if not skip_ingest:
        tickers = DEMO if s.edgar_fixtures_dir else WATCHLIST
        start = date(date.today().year - s.demo_years, 1, 1)
        typer.echo(f"[1/8] ingest {len(tickers)} companies, <= {n_filings} filings")
        ingest_tickers(tickers, ("10-K",), start, None, None, n_filings, 4, "edgar_backfill")
    typer.echo("[2/8] parse + section")
    parse_pending()
    typer.echo("[3/8] ground truth (XBRL)")
    seed_ground_truth()
    model = RULES_MODEL if s.llm_provider == "fake" else s.llm_model
    typer.echo(f"[4/8] extract {n_extract} filings with {model}")
    if use_queue:
        enqueue_pending(limit=n_extract, latest_per_company=2)
        run_worker(max_messages=n_extract, idle_exit_s=30)
    else:
        extract_inline(limit=n_extract, latest_per_company=2)
    generate_and_extract(6)
    typer.echo("[5/8] embed")
    embed_sections()
    typer.echo("[6/8] eval")
    models = [RULES_MODEL] if s.llm_provider == "fake" else [s.llm_model, RULES_MODEL]
    run_eval(models, limit=n_extract)
    typer.echo("[7/8] export lake")
    export_lake()
    typer.echo("[8/8] dbt build")
    dbt("build")
    typer.echo("demo ready: API http://localhost:8000/docs, UI http://localhost:8080")


if __name__ == "__main__":
    app()
