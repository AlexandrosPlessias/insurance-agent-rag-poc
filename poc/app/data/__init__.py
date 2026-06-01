"""Phase 8 Talk-to-Data package.

Three layers, in order of dependency:
    operations.py  -> typed Operation Pydantic schema (no I/O)
    loader.py      -> CSV/XLSX -> typed pandas DataFrame, cached per process
    executor.py    -> runs Operation against the DataFrame with guards

Public surface:
    from app.data import KpiDataset, Operation, Filters
"""
from app.data.loader import KpiDataset, get_dataset
from app.data.operations import (
    AGGREGATIONS,
    Filters,
    Operation,
    OperationViolation,
)

__all__ = [
    "KpiDataset",
    "get_dataset",
    "Operation",
    "Filters",
    "AGGREGATIONS",
    "OperationViolation",
]
