"""Tool: kpi_query — execute a typed Operation against the KPI dataset."""
from __future__ import annotations

from app.data import ExecutionResult, Operation, execute, get_dataset
from app.tools import AgentTool


def _run(operation: dict) -> ExecutionResult:
    """Execute an Operation dict against the KPI dataset.

    Args:
        operation: dict matching the Operation schema (metric, filters,
            group_by, aggregation, compare_to, sort_by, limit).

    Returns:
        ExecutionResult with result DataFrame and metadata.
    """
    op = Operation.model_validate(operation)
    return execute(op, dataset=get_dataset())


tool = AgentTool(
    name="kpi_query",
    description=(
        "Execute a structured KPI query against the insurance metrics dataset. "
        "Accepts a typed Operation (metric, filters, aggregation, group_by)."
    ),
    input_fields={
        "operation": (
            "dict – Operation schema: metric (str), filters (year/channel/"
            "product_line), aggregation (sum|mean|weighted_mean|…), "
            "group_by (list[str]), compare_to (Filters|null)"
        ),
    },
    run=_run,
)
