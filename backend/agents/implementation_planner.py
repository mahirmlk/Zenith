"""Evidence-backed, non-executing paper-to-code planning (update.md §11)."""

import re
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from security.prompt_injection import scan_untrusted

FactCategory = Literal[
    "architecture",
    "dependency",
    "dataset",
    "metric",
    "training",
    "evaluation",
    "compute",
    "limitation",
]


class EvidenceSpan(BaseModel):
    paper_id: str
    paper_url: str = ""
    start: int = Field(ge=0, description="Inclusive abstract character offset")
    end: int = Field(gt=0, description="Exclusive abstract character offset")
    quote: str


class PlanFact(BaseModel):
    category: FactCategory
    text: str
    evidence: EvidenceSpan


class ModelDataCard(BaseModel):
    model_or_method: str | None = None
    datasets: list[str] = Field(default_factory=list)
    dataset_license: str | None = None
    intended_use: str | None = None
    limitations: list[str] = Field(default_factory=list)
    status: Literal["partial", "not available"] = "partial"


class ImplementationPlan(BaseModel):
    paper_id: str
    title: str = ""
    architecture: str = "Not stated in the abstract."
    dependencies: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    training_steps: list[str] = Field(default_factory=list)
    evaluation_steps: list[str] = Field(default_factory=list)
    compute_requirements: list[str] = Field(default_factory=list)
    facts: list[PlanFact] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    suggested_structure: list[str] = Field(default_factory=list)
    compatibility_notes: list[str] = Field(default_factory=list)
    model_data_card: ModelDataCard = Field(default_factory=ModelDataCard)
    candidate_repos: list[dict[str, Any]] = Field(default_factory=list)
    repository_lookup_status: Literal["available", "no_results", "unavailable"] = "no_results"
    reproducibility_gaps: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    status: Literal["plan generated"] = "plan generated"


_CATEGORY_PATTERNS: dict[FactCategory, re.Pattern[str]] = {
    "architecture": re.compile(
        r"\b(architecture|framework|model|method|system|approach|algorithm|network)\b",
        re.IGNORECASE,
    ),
    "dependency": re.compile(
        r"\b(implement(?:ed|ation)?|pytorch|tensorflow|jax|cuda|python|library|libraries)\b",
        re.IGNORECASE,
    ),
    "dataset": re.compile(
        r"\b(dataset|data set|benchmark|corpus|mnist|imagenet|cifar|glue|squad|wikitext)\b",
        re.IGNORECASE,
    ),
    "metric": re.compile(
        r"\b(accuracy|precision|recall|f1|auc|bleu|rouge|perplexity|metric|score)\b",
        re.IGNORECASE,
    ),
    "training": re.compile(
        r"\b(train(?:ed|ing)?|fine[ -]?tun(?:e|ed|ing)|pretrain(?:ed|ing)?|optimizer|epoch|batch)\b",
        re.IGNORECASE,
    ),
    "evaluation": re.compile(
        r"\b(evaluat(?:e|ed|ion)|experiment(?:s|al)?|baseline|ablation|test set)\b",
        re.IGNORECASE,
    ),
    "compute": re.compile(
        r"\b(gpu|tpu|cuda|a100|v100|h100|compute|memory|parameters?|hours?)\b",
        re.IGNORECASE,
    ),
    "limitation": re.compile(
        r"\b(limitations?|future work|drawback|constraint|does not|failed to|remain unsolved)\b",
        re.IGNORECASE,
    ),
}
_SENTENCE = re.compile(r"[^.!?]+(?:[.!?]+|$)")
_REPO_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]+$")


def _abstract_sentences(abstract: str) -> list[tuple[str, int, int]]:
    sentences: list[tuple[str, int, int]] = []
    for match in _SENTENCE.finditer(abstract):
        raw = match.group(0)
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        start = match.start() + leading
        end = match.start() + trailing
        sentence = abstract[start:end]
        if len(sentence) >= 20 and not scan_untrusted(sentence):
            sentences.append((sentence, start, end))
    return sentences


def _safe_repository_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or len(parts) < 2
        or any(part in {".", ".."} for part in parts[:2])
        or not all(_REPO_SEGMENT.fullmatch(part) for part in parts[:2])
    ):
        return None
    repo = parts[1].removesuffix(".git")
    if not repo:
        return None
    return f"https://github.com/{parts[0]}/{repo}"


def _candidate_repositories(
    repos: list[dict[str, Any]], source: str = "GitHub repository search"
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for repo in repos[:10]:
        url = _safe_repository_url(repo.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        raw_stars = repo.get("stars", 0)
        stars = raw_stars if isinstance(raw_stars, int) and raw_stars >= 0 else 0
        candidates.append(
            {
                "url": url,
                "stars": stars,
                "verified": False,
                "verification_status": "unverified paper association",
                "source": source,
            }
        )
    return candidates


def _string_field(value: Any) -> str:
    return value if isinstance(value, str) else ""


def make_plan(
    paper: dict[str, Any],
    repos: list[dict[str, Any]] | None = None,
    *,
    repository_lookup_status: Literal["available", "no_results", "unavailable"] | None = None,
    repository_source: str = "GitHub repository search",
) -> ImplementationPlan:
    """Extract reproducibility facts only from exact abstract sentences.

    Summary-model text is deliberately not treated as source evidence. Missing
    details remain explicit gaps and every extracted fact includes a verifiable
    half-open offset into the source abstract.
    """
    paper_id = _string_field(paper.get("id"))
    title = _string_field(paper.get("title"))
    abstract = _string_field(paper.get("abstract"))
    paper_url = _string_field(paper.get("url"))
    grouped: dict[FactCategory, list[str]] = {key: [] for key in _CATEGORY_PATTERNS}
    facts: list[PlanFact] = []
    seen_facts: set[tuple[str, str]] = set()

    for sentence, start, end in _abstract_sentences(abstract):
        for category, pattern in _CATEGORY_PATTERNS.items():
            key = (category, sentence.casefold())
            if pattern.search(sentence) and key not in seen_facts and len(grouped[category]) < 5:
                seen_facts.add(key)
                grouped[category].append(sentence)
                facts.append(
                    PlanFact(
                        category=category,
                        text=sentence,
                        evidence=EvidenceSpan(
                            paper_id=paper_id,
                            paper_url=paper_url,
                            start=start,
                            end=end,
                            quote=sentence,
                        ),
                    )
                )

    repos = repos or []
    candidates = _candidate_repositories(repos, repository_source)
    if repository_lookup_status is None:
        lookup_status: Literal["available", "no_results", "unavailable"] = (
            "available" if candidates else "no_results"
        )
    else:
        lookup_status = repository_lookup_status

    missing: list[str] = []
    category_gaps: dict[FactCategory, str] = {
        "architecture": "A supported architecture or method sentence was not found in the abstract.",
        "dependency": "Frameworks, package versions, and environment dependencies were not identified in the abstract.",
        "dataset": "Dataset names, versions, and licenses need verification from the full paper or dataset source.",
        "metric": "Evaluation metrics were not identified in the abstract.",
        "training": "Training procedure and hyperparameters need verification from the full paper.",
        "evaluation": "Evaluation protocol and baseline details need verification from the full paper.",
        "compute": "Hardware and compute requirements were not identified in the abstract.",
        "limitation": "Limitations and failure cases need verification from the full paper.",
    }
    for category, gap in category_gaps.items():
        if not grouped[category]:
            missing.append(gap)
    if lookup_status == "unavailable":
        missing.append("Repository lookup was unavailable; no repository candidates could be checked.")
    elif not candidates:
        missing.append("No candidate repository was returned; this does not establish that no implementation exists.")
    if candidates:
        missing.append("Candidate repositories are unverified and may not be official implementations of this paper.")
    if grouped["dataset"]:
        missing.append("Dataset licenses and access terms have not been verified.")
    missing.append("Intended use has not been assessed from the available abstract.")
    if not paper_id:
        missing.append("The source paper has no stable identifier; extracted evidence cannot be cited safely.")

    architecture = grouped["architecture"][0] if grouped["architecture"] else "Not stated in the abstract."
    checklist = [
        "Inspect the cited paper and verify each extracted statement against the full text.",
        "Create a locked environment after confirming framework and package versions.",
        "Record dataset versions, licenses, preprocessing, and access requirements before use.",
        "Implement training and evaluation steps only from verified full-text evidence.",
        "Reproduce reported baselines and preserve command, environment, and result artifacts.",
    ]
    if candidates:
        checklist.insert(0, "Review candidate repositories and verify authorship or official paper links manually.")

    return ImplementationPlan(
        paper_id=paper_id,
        title=title,
        architecture=architecture,
        dependencies=grouped["dependency"],
        datasets=grouped["dataset"],
        metrics=grouped["metric"],
        training_steps=grouped["training"],
        evaluation_steps=grouped["evaluation"],
        compute_requirements=grouped["compute"],
        facts=facts,
        checklist=checklist,
        suggested_structure=[
            "configs/",
            "data/README.md",
            "src/model.py",
            "src/train.py",
            "src/evaluate.py",
            "tests/",
            "environment.lock",
        ],
        compatibility_notes=[
            "Python, framework, and hardware compatibility are not inferred from the abstract; verify them against the paper and any official repository."
        ],
        model_data_card=ModelDataCard(
            model_or_method=architecture if architecture != "Not stated in the abstract." else None,
            datasets=grouped["dataset"],
            limitations=grouped["limitation"],
            status="partial" if facts else "not available",
        ),
        candidate_repos=candidates,
        repository_lookup_status=lookup_status,
        reproducibility_gaps=missing,
        citations=[paper_id] if paper_id and facts else [],
    )
