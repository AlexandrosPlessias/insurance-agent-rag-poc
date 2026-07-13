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

# Clarifier / fallback
CLARIFIER_ASK = "clarifier.ask"
YEAR_FALLBACK = "year_fallback"

# Report
REPORT_GENERATE = "report.generate"

# Decline (out_of_scope)
DECLINE = "decline.canned"

# Talk-to-Data
DATA_PLAN = "data.plan"
DATA_EXECUTE = "data.execute"

# Planner / Orchestrator / Feedback
PLANNER_PLAN = "planner.plan"
ORCHESTRATOR_STEP = "orchestrator.step"
FEEDBACK_RECEIVED = "feedback.received"

# Voice I/O
VOICE_TRANSCRIBE = "voice.transcribe"
VOICE_SYNTHESIZE = "voice.synthesize"

# HITL approval gates
APPROVAL_SUSPENDED = "approval.suspended"
APPROVAL_GRANTED = "approval.granted"
APPROVAL_REJECTED = "approval.rejected"
APPROVAL_EXPIRED = "approval.expired"
APPROVAL_RESUMED = "approval.resumed"


EventType = Literal[
    "supervisor.route",
    "rag.retrieve",
    "rag.answer",
    "validator.judge",
    "clarifier.ask",
    "year_fallback",
    "report.generate",
    "decline.canned",
    "data.plan",
    "data.execute",
    "planner.plan",
    "orchestrator.step",
    "feedback.received",
    "approval.suspended",
    "approval.granted",
    "approval.rejected",
    "approval.expired",
    "approval.resumed",
    "voice.transcribe",
    "voice.synthesize",
]
