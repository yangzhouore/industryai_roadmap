"""Strict bilingual public record schema; validation never alters input."""
from datetime import date, datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator

Short = Annotated[StrictStr, Field(min_length=1, max_length=500)]
Long = Annotated[StrictStr, Field(min_length=1, max_length=4000)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Text(Record):
    en: Long
    zh: Long

    @field_validator("en", "zh")
    @classmethod
    def meaningful(cls, value):
        if not value.strip():
            raise ValueError("Text must not be blank")
        return value


class Source(Record):
    id: Short
    name: Short
    url: Short
    publishedAt: Short
    eventAt: Short | None
    timezone: Short
    synthetic: StrictBool
    excerpt: Text

    @field_validator("publishedAt", "eventAt")
    @classmethod
    def timestamp(cls, value):
        if value is not None:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("Timestamp requires timezone")
        return value


class Story(Record):
    id: Short
    category: Short
    maturity: Short
    company: Short
    kind: Literal["feature", "quick_bite"]
    title: Text
    summary: Text
    why: Text
    limitation: Text
    sourceIds: Annotated[list[Short], Field(min_length=1, max_length=30)]
    evidenceStatus: Literal["verified", "synthetic"]
    score: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class Issue(Record):
    id: Short
    slug: Annotated[StrictStr, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)]
    date: Short
    state: Literal["draft", "validated", "published"]
    validated: StrictBool
    synthetic: StrictBool
    title: Text
    introduction: Text
    sources: Annotated[list[Source], Field(min_length=1, max_length=300)]
    stories: Annotated[list[Story], Field(min_length=1, max_length=30)]

    @field_validator("date")
    @classmethod
    def iso_date(cls, value):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("Date must be YYYY-MM-DD")
        return value
