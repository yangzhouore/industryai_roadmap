"""Internal generation/review contracts; public Issue remains unchanged."""
from typing import Annotated, Literal
from pydantic import Field, StrictBool, StrictInt, StrictStr
from ..verification.schema import Record, Text, Short, Long

Category = Literal["Manufacturing AI", "Robotics & Physical AI", "Digital Twins & Simulation",
                   "Energy & Infrastructure AI", "Industrial Agents & Copilots", "Industrial Edge AI",
                   "Industrial AI Business & Policy", "out_of_scope"]
Maturity = Literal["research", "prototype", "pilot", "deployed", "scaling", "commercial", "unknown"]
Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Dimensions(Record):
    industrial_relevance: Unit
    real_deployment: Unit
    significance: Unit


class Entity(Record):
    name: Short
    type: Literal["organization", "facility", "technology", "project"]


class Classification(Record):
    articleId: Short
    include: StrictBool
    category: Category
    maturity: Maturity
    company: Annotated[StrictStr, Field(max_length=500)]
    eventKey: Annotated[StrictStr, Field(max_length=500)]
    entities: Annotated[list[Entity], Field(max_length=12)]
    dimensions: Dimensions
    evidenceQuote: Annotated[StrictStr, Field(max_length=4000)]
    reason: Short


class Classified(Record):
    classifications: Annotated[list[Classification], Field(min_length=1, max_length=30)]


class Pointer(Record):
    articleId: Short
    start: Annotated[StrictInt, Field(ge=0)]
    end: Annotated[StrictInt, Field(gt=0)]
    quote: Long


class Claim(Record):
    field: Literal["title", "summary", "why", "limitation"]
    text: Text
    evidence: Annotated[list[Pointer], Field(max_length=8)]


class SourceTranslation(Record):
    articleId: Short
    excerpt: Text


class GeneratedStory(Record):
    articleId: Short
    title: Text
    summary: Text
    why: Text
    limitation: Text
    claims: Annotated[list[Claim], Field(min_length=4, max_length=4)]


class Generated(Record):
    translations: Annotated[list[SourceTranslation], Field(min_length=1, max_length=9)]
    stories: Annotated[list[GeneratedStory], Field(min_length=1, max_length=9)]


class ClaimCheck(Record):
    claimId: Short
    supported: StrictBool
    translationEquivalent: StrictBool
    numbersMatch: StrictBool
    entitiesMatch: StrictBool
    rationale: Short


class SourceCheck(Record):
    articleId: Short
    translationEquivalent: StrictBool
    numbersMatch: StrictBool
    entitiesMatch: StrictBool
    rationale: Short


class ClassificationCheck(Record):
    articleId: Short
    categorySupported: StrictBool
    maturitySupported: StrictBool
    companySupported: StrictBool
    scoresJustified: StrictBool
    rationale: Short


class FactCheck(Record):
    claims: Annotated[list[ClaimCheck], Field(min_length=4, max_length=36)]
    sources: Annotated[list[SourceCheck], Field(min_length=1, max_length=9)]
    classifications: Annotated[list[ClassificationCheck], Field(min_length=1, max_length=9)]


def strict_output_schema(model):
    """Strip validation-only constraints unsupported by some structured models.

    Pydantic still enforces every constraint locally after decoding the response.
    """
    schema = model.model_json_schema()
    unsupported = {"title", "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "minItems", "maxItems"}
    def clean(node, preserve_keys=False):
        if isinstance(node, dict):
            return {key: clean(value, key in {"properties", "$defs"}) for key, value in node.items()
                    if preserve_keys or key not in unsupported}
        if isinstance(node, list):
            return [clean(value) for value in node]
        return node
    return clean(schema)
