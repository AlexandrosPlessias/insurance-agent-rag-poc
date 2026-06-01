"""Event-type constants written into audit_events.event_type.

Kept as plain string constants (not an Enum) because the column stores
text and we want the file to be greppable in DB browsers / CSV exports.
The set is intentionally closed - any new event needs to be added here
first so the export script and dashboards stay in sync.
"""
from typing import Literal

# Supervisor
SUPERVISOR_ROUTE = "supervisor.route"

# RAG
RAG_RETRIEVE = "rag.retrieve"
RAG_ANSWER = "rag.answer"

# Validator
VALIDATOR_JUDGE = "validator.judge"

# Clarifier / fallback (Phase 7)
CLARIFIER_ASK = "clarifier.ask"
YEAR_FALLBACK = "year_fallback"

# Report
REPORT_GENERATE = "report.generate"

# Decline (out_of_scope)
DECLINE = "decline.canned"


EventType = Literal[
    "supervisor.route",
    "rag.retrieve",
    "rag.answer",
    "validator.judge",
    "clarifier.ask",
    "year_fallback",
    "report.generate",
    "decline.canned",
]
