"""MuleNet shared data contracts — see REQUIREMENTS.md §7.  **FROZEN.**

Do NOT change field names/types without posting in CLAUDE.md → Team Sync first —
every module depends on these shapes. Detectors/pipeline pass plain dicts that
match these models; the API uses them for validation/serialization.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ── constants ───────────────────────────────────────────────────────────────
REPORTING_THRESHOLD: float = 10_000.0  # EUR; structuring sits just under this
CHANNELS = ("wire", "sepa", "card", "crypto", "cash_deposit")

AccountType = Literal["personal", "business"]
KYCRisk = Literal["low", "medium", "high"]
# Enforcement lifecycle (REQUIREMENTS/TASKS §6). Baseline data is always "active"; freeze/review
# transitions are runtime state set by the API. Optional + defaulted so existing data stays valid.
AccountStatus = Literal["active", "frozen", "blocked", "banned"]
Channel = Literal["wire", "sepa", "card", "crypto", "cash_deposit"]
SubjectType = Literal["account", "edge", "subgraph"]
PatternType = Literal["structuring", "layering", "mule_fanin", "mule_fanout", "circular"]


# ── core data ─────────────────────────────────────────────────────────────--
class Account(BaseModel):
    account_id: str
    owner_name: str
    account_type: AccountType
    country: str
    opened_at: str  # YYYY-MM-DD
    kyc_risk: KYCRisk
    status: AccountStatus = "active"  # enforcement state; defaulted so older data stays valid


class Transaction(BaseModel):
    tx_id: str
    timestamp: str  # ISO-8601 UTC, e.g. 2026-06-13T14:32:00Z
    src: str
    dst: str
    amount: float
    currency: str = "EUR"
    channel: Channel


class Dataset(BaseModel):
    accounts: list[Account]
    transactions: list[Transaction]


# ── ground truth (eval only — detectors never see this) ──────────────────────
class TrueRing(BaseModel):
    ring_id: str
    account_ids: list[str]
    tx_ids: list[str]
    patterns: list[PatternType]


class Labels(BaseModel):
    mule_accounts: list[str]
    rings: list[TrueRing]


# ── detection outputs ─────────────────────────────────────────────────────--
class Window(BaseModel):
    start: str
    end: str


class Finding(BaseModel):
    """What every detector returns (a list[Finding])."""
    detector: str
    subject_type: SubjectType
    subject_ids: list[str]
    score: float = Field(ge=0.0, le=1.0)
    evidence: dict[str, Any] = {}
    window: Optional[Window] = None


class SignalRef(BaseModel):
    detector: str
    score: float


class AccountRisk(BaseModel):
    account_id: str
    risk: float = Field(ge=0.0, le=1.0)
    top_signals: list[SignalRef] = []


class Ring(BaseModel):
    ring_id: str
    account_ids: list[str]
    tx_ids: list[str]
    score: float = Field(ge=0.0, le=1.0)
    patterns: list[str] = []
    key_accounts: list[str] = []
    narrative: Optional[str] = None  # filled by the SAR step


class PipelineResult(BaseModel):
    findings: list[Finding]
    account_risk: list[AccountRisk]
    rings: list[Ring]
