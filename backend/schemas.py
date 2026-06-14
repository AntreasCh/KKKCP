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
# Tier C transaction type (placement/movement vs reversals). Optional + defaulted so old data stays valid.
TxType = Literal["transfer", "payment", "refund", "chargeback"]


# ── core data ─────────────────────────────────────────────────────────────--
class Account(BaseModel):
    account_id: str
    owner_name: str
    account_type: AccountType
    country: str
    opened_at: str  # YYYY-MM-DD
    kyc_risk: KYCRisk
    status: AccountStatus = "active"  # enforcement state; defaulted so older data stays valid

    # ── Tier C enrichment (all optional + defaulted so pre-Tier-C data stays valid) ──
    pep: bool = False                              # C1 politically exposed person
    sanctioned: bool = False                       # C1 sanctions-list hit (near auto-flag)
    watchlist: bool = False                        # C1 internal/regulatory watchlist
    prior_sars: int = 0                            # C2 count of prior suspicious-activity reports
    occupation: Optional[str] = None               # C3 declared occupation
    business_category: Optional[str] = None        # C3 merchant/business category (MCC-style)
    expected_monthly_volume: Optional[float] = None  # C3 declared expected throughput (EUR/month)
    account_purpose: Optional[str] = None          # C3 declared account purpose
    device_id: Optional[str] = None                # C4 primary device fingerprint
    signup_ip: Optional[str] = None                # C4 signup / primary IP
    vpn_tor: bool = False                          # C4 connects via VPN / TOR / proxy
    failed_verifications: int = 0                  # C4 failed identity-verification attempts
    adverse_media: bool = False                    # C5 negative news / adverse-media hit
    nominee_owner: bool = False                    # C5 nominee director / hidden beneficial owner
    email: Optional[str] = None                    # C8 contact identifier (entity resolution / fleet linkage)
    phone: Optional[str] = None                    # C8 contact identifier (entity resolution / fleet linkage)
    chargeback_count: int = 0                      # C8 account-level dispute / chargeback history

    # ── Tier D enrichment: a full KYC/fraud-engine profile per account (all optional + defaulted).
    # Grouped into the six layers a real fintech fraud stack collects. Scored as PRECISION-SAFE
    # capped amplifiers in scoring.py (they enrich + corroborate, they don't flag alone). ──
    # Identity layer
    date_of_birth: Optional[str] = None            # D-identity YYYY-MM-DD
    address: Optional[str] = None                  # D-identity residential address
    city: Optional[str] = None                     # D-identity city
    national_id: Optional[str] = None              # D-identity government ID (masked)
    verification_level: Optional[str] = None       # D-identity unverified | basic | full
    aliases: list[str] = []                        # D-identity known previous / alternate names
    # Device layer
    device_os: Optional[str] = None                # D-device operating system
    device_type: Optional[str] = None              # D-device mobile | desktop | tablet
    device_count: int = 1                          # D-device distinct devices used by the account
    emulator: bool = False                         # D-device runs on an emulator (fraud farm)
    rooted_jailbroken: bool = False                # D-device rooted / jailbroken device
    # Network / IP layer
    ip_country: Optional[str] = None               # D-network geolocation country of the signup IP
    ip_isp: Optional[str] = None                   # D-network ISP / carrier / hosting provider
    proxy: bool = False                            # D-network proxy / datacenter-hosting IP
    ip_risk_score: float = 0.0                     # D-network IP reputation 0..1 (1 = known-bad)
    distinct_ips: int = 1                          # D-network distinct IPs seen for the account
    # Behaviour layer
    avg_session_seconds: Optional[int] = None      # D-behaviour mean session length
    logins_30d: int = 0                            # D-behaviour login count last 30d
    failed_logins_30d: int = 0                     # D-behaviour failed logins last 30d
    password_resets_30d: int = 0                   # D-behaviour password resets last 30d
    night_activity_ratio: float = 0.0              # D-behaviour share of activity at 00:00–05:00
    automation_score: float = 0.0                  # D-behaviour bot/automation likelihood 0..1
    # History layer
    prior_fraud: bool = False                      # D-history confirmed prior fraud case
    account_takeover: bool = False                 # D-history prior account-takeover incident
    disputes_count: int = 0                        # D-history lifetime dispute count
    blacklisted: bool = False                      # D-history on an internal blacklist
    linked_accounts: int = 0                       # D-history count of known linked accounts
    historical_risk_score: float = 0.0             # D-history trailing customer risk score 0..1


class Transaction(BaseModel):
    tx_id: str
    timestamp: str  # ISO-8601 UTC, e.g. 2026-06-13T14:32:00Z
    src: str
    dst: str
    amount: float
    currency: str = "EUR"
    channel: Channel
    tx_type: TxType = "transfer"                   # C7 transfer/payment vs refund/chargeback
    merchant_category: Optional[str] = None        # C7 MCC for card payments
    tx_country: Optional[str] = None               # C7 country where the transaction originated

    # ── Tier D transaction enrichment (device / network / status per payment; optional+defaulted) ──
    device_id: Optional[str] = None                # D device fingerprint the payment was made from
    ip_address: Optional[str] = None               # D originating IP of the payment
    ip_country: Optional[str] = None               # D geolocation country of that IP
    status: Optional[str] = None                   # D completed | failed | reversed | pending
    recipient_name: Optional[str] = None           # D display name of the counterparty
    reference: Optional[str] = None                # D payment reference / description
    is_international: bool = False                  # D crosses a border (origin != destination country)
    risk_score: float = 0.0                        # D per-transaction risk 0..1


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
