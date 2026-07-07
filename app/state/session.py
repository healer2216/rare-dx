"""诊断会话状态 — LangGraph StateGraph 的 state schema。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EvidenceSource(str, Enum):
    PAPER_EN = "paper_en"
    PAPER_CN = "paper_cn"
    MEETING = "meeting"
    GUIDE = "guide"
    TRIAL = "trial"
    PACKAGE_INSERT = "package_insert"


class EvidenceGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


class InheritanceMode(str, Enum):
    AD = "AD"
    AR = "AR"
    XD = "XD"
    XR = "XR"
    MITOCHONDRIAL = "MITOCHONDRIAL"
    DE_NOVO = "DE_NOVO"
    UNKNOWN = "UNKNOWN"


class DiagnosticIntent(str, Enum):
    NEW_DIAGNOSIS = "new_diagnosis"
    FOLLOWUP = "followup"
    INFO_REVISE = "info_revise"
    TOPIC_DRIFT = "topic_drift"


class PresenceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class TestCategory(str, Enum):
    GENETIC = "genetic"
    BIOCHEMICAL = "biochemical"
    IMAGING = "imaging"
    FUNCTIONAL = "functional"
    HISTOPATHOLOGICAL = "histopathological"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PatientProfile(BaseModel):
    raw_input: str = ""
    age: Optional[float] = None
    sex: Optional[str] = None
    ethnicity: Optional[str] = None
    region: Optional[str] = None
    structured: dict[str, Any] = Field(default_factory=dict)
    last_updated_round: int = 0


class PhenotypeModifier(BaseModel):
    distribution: Optional[str] = None
    temporal_pattern: Optional[str] = None
    severity: Optional[str] = None
    laterality: Optional[str] = None
    progression_rate: Optional[str] = None


class PhenotypeVector(BaseModel):
    hpo_id: str
    term_name: str
    modifiers: list[PhenotypeModifier] = Field(default_factory=list)
    presence: str = "present"
    onset_age: Optional[float] = None
    onset_age_unit: Optional[str] = None
    raw_description: str = ""


class PhenotypeProfile(BaseModel):
    patient_id: str = ""
    vectors: list[PhenotypeVector] = Field(default_factory=list)
    raw_text: str = ""
    parsed_at: Optional[datetime] = None
    demographic: dict[str, Any] = Field(default_factory=dict)


class DiseaseHypothesis(BaseModel):
    disease_id: str
    disease_name: str
    orpha_number: Optional[str] = None
    bayesian_score: float = 0.0
    supporting_phenotypes: list[str] = Field(default_factory=list)
    contradicting_phenotypes: list[str] = Field(default_factory=list)
    rank: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reasoning_chain: str = ""


class TemporalMatch(BaseModel):
    disease_id: str
    onset_consistency: float = 0.0
    progression_consistency: float = 0.0
    sequence_consistency: float = 0.0
    overall_temporal_score: float = 0.0
    notes: str = ""


class InheritancePattern(BaseModel):
    mode: InheritanceMode = InheritanceMode.UNKNOWN
    confidence: float = 0.0
    supporting_evidence: list[str] = Field(default_factory=list)


class GeneticConstraint(BaseModel):
    inheritance_patterns: list[InheritancePattern] = Field(default_factory=list)
    compatible_diseases: list[str] = Field(default_factory=list)
    incompatible_diseases: list[str] = Field(default_factory=list)
    prior_modifier: float = 1.0


class PathwayStep(BaseModel):
    test_id: str
    test_name: str
    information_gain: float = 0.0
    net_evoi: float = 0.0
    rank: int = 0
    rationale: str = ""
    expected_outcomes: list[str] = Field(default_factory=list)
    alternative_tests: list[str] = Field(default_factory=list)


class DiagnosticPathway(BaseModel):
    steps: list[PathwayStep] = Field(default_factory=list)
    current_step: int = 0
    total_expected_information_gain: float = 0.0


class Evidence(BaseModel):
    id: str
    source: EvidenceSource
    title: str
    abstract: Optional[str] = None
    publish_date: Optional[str] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    study_type: Optional[str] = None
    impact_factor: Optional[float] = None
    retrieved_layer: Optional[str] = None
    relevance_score: Optional[float] = None
    grade: Optional[EvidenceGrade] = None


class EvidencePool(BaseModel):
    evidences: dict[str, Evidence] = Field(default_factory=dict)

    def add(self, ev: Evidence) -> bool:
        if ev.id in self.evidences:
            return False
        self.evidences[ev.id] = ev
        return True

    def all(self) -> list[Evidence]:
        return list(self.evidences.values())


class Turn(BaseModel):
    round: int
    user_message: str
    intent: Optional[DiagnosticIntent] = None
    layer_outputs: dict[str, Any] = Field(default_factory=dict)
    new_evidence_ids: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)


class Report(BaseModel):
    main_text: str = ""
    summary_snapshot: Optional[str] = None
    reasoning_summary: str = ""
    evidence_citations: list[str] = Field(default_factory=list)
    uncertainty_notes: str = ""
    last_updated_round: int = 0


class DiagnosticSession(BaseModel):
    session_id: str
    round: int = 0
    patient_profile: PatientProfile = Field(default_factory=PatientProfile)
    phenotype_profile: PhenotypeProfile = Field(default_factory=PhenotypeProfile)
    hypotheses: list[DiseaseHypothesis] = Field(default_factory=list)
    temporal_matches: list[TemporalMatch] = Field(default_factory=list)
    genetic_constraint: Optional[GeneticConstraint] = None
    diagnostic_pathway: Optional[DiagnosticPathway] = None
    evidence_pool: EvidencePool = Field(default_factory=EvidencePool)
    report: Report = Field(default_factory=Report)
    dialog_history: list[Turn] = Field(default_factory=list)

    current_user_message: str = ""
    current_intent: Optional[DiagnosticIntent] = None
    current_backflow_to_hypothesis: bool = False
    current_backflow_to_phenotype: bool = False
    current_backflow_iterations: int = 0
    current_error: Optional[str] = None
    safety_level: str = "strict"
