"""Locale consistency checks; mock mode never fabricates a translation."""
import re
from collections import Counter


def parity_errors(text: dict, path: str = "text") -> list[str]:
    errors = []
    if not re.search(r"[\u3400-\u9fff]", text["zh"]):
        errors.append(f"{path}: Chinese text missing")
    if Counter(re.findall(r"\d+(?:\.\d+)?", text["en"])) != Counter(re.findall(r"\d+(?:\.\d+)?", text["zh"])):
        errors.append(f"{path}: EN/ZH numerical mismatch")
    # Retained Latin technical names must agree; translated entities require human review.
    entities = lambda value: set(re.findall(r"(?<![A-Za-z0-9_])[A-Z][A-Z0-9]+(?![A-Za-z0-9_])", value))
    english, chinese = entities(text["en"]), entities(text["zh"])
    if "AI" in english and "人工智能" in text["zh"]:
        chinese.add("AI")
    if english != chinese:
        errors.append(f"{path}: EN/ZH technical entity mismatch")
    return errors


def translate_fixture(text: dict) -> dict:
    errors = parity_errors(text)
    if errors:
        raise ValueError("; ".join(errors))
    return dict(text)
