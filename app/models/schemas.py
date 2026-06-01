"""Pydantic schemas for API request/response validation."""
from pydantic import BaseModel, Field


# ── Patient ───────────────────────────────────────────────────────────
class PatientInfo(BaseModel):
    name: str = "Unknown"
    age: str = ""
    date: str = ""


# ── Metrics (top row of the report) ──────────────────────────────────
class Metrics(BaseModel):
    weight: float = 0.0
    bmi: float = 0.0
    bodyFat: float = Field(0.0, alias="bodyFat")
    heartRate: int = Field(0, alias="heartRate")
    bioEnergy: float = Field(0.0, alias="bioEnergy")
    energyReserve: int = Field(0, alias="energyReserve")
    lfhfRatio: float = Field(0.0, alias="lfhfRatio")
    nadiPulse: int = Field(0, alias="nadiPulse")

    model_config = {"populate_by_name": True}


# ── Dimensions (Physical / Emotional / Psychological / Spiritual) ────
class Dimension(BaseModel):
    score: int = Field(0, ge=0, le=100)
    description: str = ""


class Dimensions(BaseModel):
    physical: Dimension = Field(default_factory=Dimension)
    emotional: Dimension = Field(default_factory=Dimension)
    psychological: Dimension = Field(default_factory=Dimension)
    spiritual: Dimension = Field(default_factory=Dimension)


# ── Body Systems (10 systems) ────────────────────────────────────────
class SystemStatus(BaseModel):
    score: int = Field(0, ge=0, le=100)
    status: str = "Need Attention"  # "Normal" or "Need Attention"


class Systems(BaseModel):
    nervous: SystemStatus = Field(default_factory=SystemStatus)
    cardiovascular: SystemStatus = Field(default_factory=SystemStatus)
    respiratory: SystemStatus = Field(default_factory=SystemStatus)
    musculoskeletal: SystemStatus = Field(default_factory=SystemStatus)
    digestive: SystemStatus = Field(default_factory=SystemStatus)
    integumentary: SystemStatus = Field(default_factory=SystemStatus)
    endocrine: SystemStatus = Field(default_factory=SystemStatus)
    urogenital: SystemStatus = Field(default_factory=SystemStatus)
    reproductive: SystemStatus = Field(default_factory=SystemStatus)
    immune: SystemStatus = Field(default_factory=SystemStatus)


# ── Wellness Offerings ───────────────────────────────────────────────
class WellnessOfferings(BaseModel):
    diet: str = ""
    yoga: str = ""
    physicalActivity: str = Field("", alias="physicalActivity")
    sleep: str = ""
    stress: str = ""
    supplements: str = ""
    medicine: str = ""

    model_config = {"populate_by_name": True}


# ── Full Report ──────────────────────────────────────────────────────
class WellnessReport(BaseModel):
    """Complete wellness report — the main output schema."""
    patient: PatientInfo = Field(default_factory=PatientInfo)
    metrics: Metrics = Field(default_factory=Metrics)
    dimensions: Dimensions = Field(default_factory=Dimensions)
    systems: Systems = Field(default_factory=Systems)
    wellness: WellnessOfferings = Field(default_factory=WellnessOfferings)


# ── API Response wrappers ────────────────────────────────────────────
class GenerateResponse(BaseModel):
    """Response from POST /api/generate."""
    report_id: str
    report: WellnessReport
    extraction_summary: dict = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Response from GET /api/health."""
    service: str = "Nanocare Wellness Report Engine"
    ollama: str = "unknown"
    configured_model: str = ""
    available_models: list[str] = Field(default_factory=list)
    model_loaded: bool = False
