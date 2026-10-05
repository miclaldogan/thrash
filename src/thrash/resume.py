"""Canonical restored context. The model supplies semantics; disk changes remain code."""
from .tracing import traced
from pydantic import BaseModel, Field

from .drift import DriftReport, StaleAssumption
from .process_image import CompletedWork, Decision, ProcessImage


class ChangesSinceSnapshot(BaseModel):
    new_commits: int = 0
    files: list[str] = Field(default_factory=list)
    commit_subjects: list[str] = Field(default_factory=list)
    history_rewritten: bool = False


class ResumeReport(BaseModel):
    project: str
    snapshot_timestamp: float | None = None
    what_happened: str = ""
    completed: list[CompletedWork] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    decision_reasons: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    last_execution_point: str = ""
    relevant_files: list[str] = Field(default_factory=list)
    changes_since_snapshot: ChangesSinceSnapshot = Field(default_factory=ChangesSinceSnapshot)
    possible_drift: list[StaleAssumption] = Field(default_factory=list)
    drift_level: str = "NONE"
    next_action: str = ""
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)
    registers: dict[str, str] = Field(default_factory=dict)
    stack: list[str] = Field(default_factory=list)
    last_useful_state: str = ""
    purpose: str = ""
    failures: list[str] = Field(default_factory=list)
    resurrection_hint: str = ""
    legacy_image: bool = False
    available: bool = False


@traced("thrash.restore.render")
def build_resume_report(alias: str, image: ProcessImage | None,
                        drift: DriftReport | None = None) -> ResumeReport:
    drift = drift or DriftReport()
    report = ResumeReport(
        project=alias,
        changes_since_snapshot=ChangesSinceSnapshot(new_commits=drift.new_commits,
            files=drift.changed_files, commit_subjects=drift.commit_subjects,
            history_rewritten=drift.history_rewritten),
        possible_drift=drift.stale, drift_level=drift.level,
    )
    if image is None:
        return report
    report.snapshot_timestamp = image.meta.created_at
    report.available = True
    report.what_happened = image.summary or image.last_useful_state
    report.completed = image.completed
    report.decisions = image.decisions
    report.decision_reasons = [d.reason for d in image.decisions]
    report.unresolved, report.blockers = image.unresolved, image.blockers
    report.last_execution_point = image.program_counter.task
    report.relevant_files = image.open_handles
    report.next_action = image.next_action or image.program_counter.task
    report.confidence = image.program_counter.confidence
    report.evidence = list(dict.fromkeys([*image.evidence,
        *(d.source for d in image.decisions if d.source), *(c.source for c in image.completed if c.source)]))
    report.registers, report.stack = image.registers, image.stack
    report.last_useful_state = image.last_useful_state
    report.purpose, report.failures = image.purpose, image.failures
    report.resurrection_hint = image.resurrection_hint
    report.legacy_image = image.meta.context_version < 2
    return report
