"""Transparent, conservative industrial ranking. Unknown evidence scores zero."""
from math import isfinite

VERSION = "industrial-v1"
WEIGHTS = {"industrial_relevance": 25, "real_deployment": 20, "authority": 15,
           "corroboration": 15, "recency": 10, "significance": 10, "attention": 5}
CATEGORIES = {"Manufacturing AI", "Robotics & Physical AI", "Digital Twins & Simulation",
              "Energy & Infrastructure AI", "Industrial Agents & Copilots", "Industrial Edge AI",
              "Industrial AI Business & Policy"}
MATURITY = {"research": .1, "prototype": .2, "pilot": .4, "deployed": .7,
            "scaling": .9, "commercial": 1.0}


def score_story(story: dict, weights: dict | None = None) -> dict:
    """Optional scoringDimensions must be supplied by the evidence review stage."""
    weights = dict(WEIGHTS if weights is None else weights)
    if set(weights) != set(WEIGHTS) or any(not isinstance(v, (int, float)) or
            not isfinite(v) or v < 0 for v in weights.values()) or sum(weights.values()) == 0:
        raise ValueError("Weights must contain every dimension and be finite, nonnegative")
    dimensions = dict.fromkeys(WEIGHTS, 0.0)
    dimensions["industrial_relevance"] = float(story.get("category") in CATEGORIES)
    dimensions["real_deployment"] = MATURITY.get(story.get("maturity"), 0)
    for key, value in story.get("scoringDimensions", {}).items():
        if key not in dimensions or isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Scoring dimensions must be known finite values from 0 to 1")
        dimensions[key] = float(value)
    return {"version": VERSION, "dimensions": dimensions, "weights": weights,
            "finalScore": round(sum(weights[k] * dimensions[k] for k in weights) * 100 / sum(weights.values()), 2)}


def select_stories(stories: list[dict], maximum: int = 3) -> list[dict]:
    """A company and category each get one lead slot; never force filler."""
    selected, companies, categories = [], set(), set()
    for story in sorted(stories, key=lambda s: (-score_story(s)["finalScore"], s["id"])):
        item = dict(story)
        eligible = (len(companies) < maximum and story.get("category") in CATEGORIES and
                    story.get("company") not in companies and story.get("category") not in categories and
                    bool(story.get("sourceIds")) and story.get("evidenceStatus") in {"verified", "synthetic"})
        item["kind"] = "feature" if eligible else "quick_bite"
        item["score"] = score_story(story)["finalScore"]
        if eligible:
            companies.add(story["company"])
            categories.add(story["category"])
        selected.append(item)
    return selected
