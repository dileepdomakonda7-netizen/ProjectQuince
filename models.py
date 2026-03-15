"""
Pydantic models for structured validation of products, hooks, and grading results.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional


class Product(BaseModel):
    id: str
    name: str
    category: str
    material: str
    price: float = Field(gt=0)
    comparable_retail_price: float = Field(gt=0)
    target_persona: str
    sustainability: str
    fit: str
    sizes: List[str]
    colors: List[str]
    key_features: List[str]

    @model_validator(mode="after")
    def price_must_be_less_than_comparable(self):
        if self.price >= self.comparable_retail_price:
            raise ValueError("Quince price must be less than comparable retail price")
        return self


class HookSet(BaseModel):
    educational: str
    value_driven: str
    lifestyle: str


class GeneratedHookSet(BaseModel):
    product_id: str
    product_name: str
    channel: str
    hooks: HookSet


class RubricScore(BaseModel):
    quality_premium: int = Field(ge=0, le=1)
    value_proposition: int = Field(ge=0, le=1)
    sustainability: int = Field(ge=0, le=1)
    accuracy: int = Field(ge=0, le=1)
    justification: str

    @property
    def total(self) -> int:
        return (
            self.quality_premium
            + self.value_proposition
            + self.sustainability
            + self.accuracy
        )

    @property
    def passed(self) -> bool:
        return self.total == 4


class ValidationResult(BaseModel):
    rule: str
    passed: bool
    detail: str


class HookValidationReport(BaseModel):
    product: str
    channel: str
    hook_type: str
    hook_text: str
    violations: List[ValidationResult]


class FullReport(BaseModel):
    total_hooks: int = 0
    passed: int = 0
    failed: int = 0
    failures: List[HookValidationReport] = []

    @property
    def pass_rate(self) -> float:
        return (self.passed / self.total_hooks * 100) if self.total_hooks > 0 else 0.0


# --- Quality Judge Models ---

class SpecificityResult(BaseModel):
    """Result from the product-specificity LLM judge."""
    specificity_score: int = Field(ge=1, le=5)
    unique_attributes_used: List[str] = []
    reasoning: str = ""
    product: str = ""
    channel: str = ""
    hook_type: str = ""
    hook_text: str = ""


class ChannelFitResult(BaseModel):
    """Result from the channel-appropriateness LLM judge."""
    channel_fit_score: int = Field(ge=1, le=5)
    reasoning: str = ""
    product: str = ""
    channel: str = ""
    hook_type: str = ""
    hook_text: str = ""


class NearDuplicate(BaseModel):
    """A pair of hooks flagged as near-duplicates across products."""
    channel: str
    hook_type: str
    product_a: str
    product_b: str
    similarity: float = Field(ge=0.0, le=1.0)
    text_a: str
    text_b: str


class DeduplicationReport(BaseModel):
    """Cross-product deduplication analysis results."""
    corpus_uniqueness: float = Field(ge=0.0, le=1.0)
    total_pairs_checked: int = 0
    duplicate_pairs_found: int = 0
    near_duplicates: List[NearDuplicate] = []


class CompositeScoreDimension(BaseModel):
    """A single dimension in the composite quality score."""
    raw: str
    normalized: Optional[float] = None


class CompositeScore(BaseModel):
    """Weighted composite quality score combining all eval signals."""
    composite_score: float = Field(ge=0.0, le=1.0)
    dimensions: dict
    weights: dict
    dimensions_evaluated: int = 0
    dimensions_total: int = 5
