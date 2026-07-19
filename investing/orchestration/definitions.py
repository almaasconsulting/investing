from __future__ import annotations

import os
import sys
import time
from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import dagster as dg
from dagster_dbt import (
    DagsterDbtTranslator,
    DbtCliResource,
    DbtProject,
    dbt_assets,
)

from investing.pipeline.config import PipelineSettings
from investing.pipeline.updates import (
    oldest_batch_partition_key,
    refresh_stock_universe,
    run_configured_analysis_batch,
    run_market_intelligence_update,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = PROJECT_ROOT / "analytics"
DBT_EXECUTABLE = os.getenv(
    "INVESTING_DBT_EXECUTABLE",
    str(Path(sys.executable).with_name("dbt.exe" if os.name == "nt" else "dbt")),
)
DBT_PROJECT = DbtProject(
    project_dir=DBT_PROJECT_DIR,
    profiles_dir=DBT_PROJECT_DIR,
)
# Under `dagster dev`, regenerate manifest.json when dbt models change.
DBT_PROJECT.prepare_if_dev()

BATCH_PARTITION_COUNT = max(
    1, int(os.getenv("INVESTING_BATCH_PARTITION_COUNT", "50"))
)
BATCH_PARTITION_KEYS = [
    f"batch_{index:03d}" for index in range(BATCH_PARTITION_COUNT)
]
STOCK_BATCH_PARTITIONS = dg.StaticPartitionsDefinition(BATCH_PARTITION_KEYS)


def _format_duration(seconds: float | None) -> str:
    """Format a duration without misleading decimal minutes."""
    if seconds is None:
        return "calculating"
    total_seconds = max(0, round(seconds))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    return f"{minutes}m {remaining_seconds:02d}s"


def _dagster_progress_callback(context, label: str):
    """Build a throttled per-stock progress logger for long ingestion assets."""
    started = time.monotonic()
    log_every = max(1, int(os.getenv("INVESTING_PROGRESS_EVERY", "10")))
    samples: deque[tuple[int, float]] = deque(maxlen=20)

    def report(event: dict[str, Any]) -> None:
        index = int(event.get("index", 0))
        total = int(event.get("total", 0))
        now = time.monotonic()
        if index:
            samples.append((index, now))
        failed = not bool(event.get("succeeded", False))
        if not (failed or index == 1 or index == total or index % log_every == 0):
            return
        elapsed = max(now - started, 0.001)
        rate = 0.0
        if len(samples) >= 2:
            completed = samples[-1][0] - samples[0][0]
            sample_seconds = samples[-1][1] - samples[0][1]
            if completed > 0 and sample_seconds > 0:
                rate = completed / sample_seconds
        remaining = max(total - index, 0)
        eta_seconds = remaining / rate if rate else None
        percent = (100.0 * index / total) if total else 100.0
        context.log.info(
            "%s progress %s/%s (%.1f%%) | %s | %s | status=%s | "
            "rows=%s | elapsed=%s | ETA=%s%s",
            label,
            index,
            total,
            percent,
            event.get("country", ""),
            event.get("symbol", ""),
            "ok" if not failed else "error",
            event.get("rows_written", 0),
            _format_duration(elapsed),
            _format_duration(eta_seconds),
            f" | {event.get('error')}" if failed and event.get("error") else "",
        )

    return report


class MedallionDagsterDbtTranslator(DagsterDbtTranslator):
    """Map dbt folders to Dagster groups and attach ingestion lineage."""

    def get_group_name(self, dbt_resource_props: Mapping[str, Any]) -> str | None:
        path_parts = Path(dbt_resource_props.get("original_file_path", "")).parts
        for layer in ("bronze", "silver", "gold"):
            if layer in path_parts:
                return layer
        return super().get_group_name(dbt_resource_props)

    def get_asset_spec(
        self,
        manifest: Mapping[str, Any],
        unique_id: str,
        project: DbtProject | None,
    ) -> dg.AssetSpec:
        spec = super().get_asset_spec(manifest, unique_id, project)
        props = self.get_resource_props(manifest, unique_id)
        path_parts = Path(props.get("original_file_path", "")).parts
        if props.get("resource_type") == "model" and "bronze" in path_parts:
            ingestion_asset = (
                "bronze_market_intelligence"
                if props.get("name") in {
                    "bronze_news_article", "bronze_financial_statement"
                }
                else "bronze_incremental_market_data"
            )
            spec = spec.merge_attributes(
                deps=[dg.AssetDep(dg.AssetKey(ingestion_asset))]
            )
        return spec


@dg.asset(group_name="bronze", compute_kind="python")
def bronze_stock_universe(context) -> dg.MaterializeResult:
    """Refresh flagship indexes, US/Canadian REITs, and dividend aristocrats."""
    result = refresh_stock_universe(PipelineSettings.from_env())
    context.log.info("Refreshed %s universe rows", result["rows"])
    return dg.MaterializeResult(metadata=result)


@dg.asset(
    deps=[bronze_stock_universe],
    group_name="bronze",
    compute_kind="python",
    partitions_def=STOCK_BATCH_PARTITIONS,
    config_schema={
        "force_update": dg.Field(
            bool,
            default_value=False,
            description="Manual override of the 24-hour per-stock update guard.",
        )
    },
)
def bronze_incremental_market_data(
    context,
) -> dg.MaterializeResult:
    """Ingest one retryable market-data partition, oldest stocks first."""
    settings = PipelineSettings.from_env()
    result = run_configured_analysis_batch(
        batch_size=settings.batch_size,
        batch_key=context.partition_key,
        partition_count=BATCH_PARTITION_COUNT,
        settings=settings,
        progress_callback=_dagster_progress_callback(context, "Price/fundamentals"),
        force_update=bool(context.op_config.get("force_update", False)),
    )
    context.log.info("Incremental ingestion result: %s", result)
    return dg.MaterializeResult(metadata=result)


@dg.asset(
    # Keep provider-intensive ingestion phases sequential within a partition.
    deps=[bronze_incremental_market_data],
    group_name="bronze",
    compute_kind="python",
    partitions_def=STOCK_BATCH_PARTITIONS,
)
def bronze_market_intelligence(context) -> dg.MaterializeResult:
    """Incrementally ingest stock news and quarterly/annual statements."""
    settings = PipelineSettings.from_env()
    result = run_market_intelligence_update(
        settings,
        limit=settings.batch_size,
        batch_key=context.partition_key,
        partition_count=BATCH_PARTITION_COUNT,
        progress_callback=_dagster_progress_callback(context, "News/statements"),
    )
    context.log.info("Market-intelligence ingestion result: %s", result)
    return dg.MaterializeResult(metadata=result)


@dbt_assets(
    manifest=DBT_PROJECT.manifest_path,
    project=DBT_PROJECT,
    dagster_dbt_translator=MedallionDagsterDbtTranslator(),
)
def medallion_dbt_assets(
    context,
    dbt: DbtCliResource,
):
    """Materialize each dbt model as a first-class Dagster asset."""
    yield from dbt.cli(["build"], context=context).stream()
    context.log.info("PostgreSQL medallion build completed.")


universe_refresh_job = dg.define_asset_job(
    "universe_refresh_job",
    selection=dg.AssetSelection.assets(bronze_stock_universe),
    description="Refresh curated flagship-index, REIT, and dividend-aristocrat membership.",
)

stock_batch_refresh_job = dg.define_asset_job(
    "stock_batch_refresh_job",
    selection=dg.AssetSelection.assets(
        bronze_incremental_market_data, bronze_market_intelligence
    ),
    description="Partitioned market data, news, and statement ingestion.",
)

medallion_refresh_job = dg.define_asset_job(
    "medallion_refresh_job",
    selection=dg.AssetSelection.assets(medallion_dbt_assets),
    description="Build and test dbt Bronze, Silver, and Gold models.",
)

daily_universe_schedule = dg.ScheduleDefinition(
    name="daily_universe_schedule",
    job=universe_refresh_job,
    cron_schedule=os.getenv("INVESTING_UNIVERSE_CRON", "0 3 * * *"),
    execution_timezone=os.getenv("INVESTING_TIMEZONE", "Europe/Oslo"),
    default_status=dg.DefaultScheduleStatus.RUNNING,
)


@dg.schedule(
    job=stock_batch_refresh_job,
    cron_schedule=os.getenv("INVESTING_BATCH_CRON", "*/15 * * * *"),
    execution_timezone=os.getenv("INVESTING_TIMEZONE", "Europe/Oslo"),
    default_status=dg.DefaultScheduleStatus.RUNNING,
)
def continuous_stock_batch_schedule(context) -> dg.RunRequest:
    partition_key = oldest_batch_partition_key(PipelineSettings.from_env())
    return dg.RunRequest(
        run_key=f"stock-batch:{context.scheduled_execution_time.isoformat()}:{partition_key}",
        partition_key=partition_key,
        tags={"investing/batch_partition": partition_key},
    )


hourly_medallion_schedule = dg.ScheduleDefinition(
    name="hourly_medallion_schedule",
    job=medallion_refresh_job,
    cron_schedule=os.getenv("INVESTING_DBT_CRON", "10 * * * *"),
    execution_timezone=os.getenv("INVESTING_TIMEZONE", "Europe/Oslo"),
    default_status=dg.DefaultScheduleStatus.RUNNING,
)

defs = dg.Definitions(
    assets=[
        bronze_stock_universe,
        bronze_incremental_market_data,
        bronze_market_intelligence,
        medallion_dbt_assets,
    ],
    jobs=[universe_refresh_job, stock_batch_refresh_job, medallion_refresh_job],
    schedules=[
        daily_universe_schedule,
        continuous_stock_batch_schedule,
        hourly_medallion_schedule,
    ],
    resources={
        "dbt": DbtCliResource(
            project_dir=DBT_PROJECT,
            dbt_executable=DBT_EXECUTABLE,
        )
    },
)
