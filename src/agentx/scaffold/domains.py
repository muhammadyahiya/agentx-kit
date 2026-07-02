"""Domain inference for project seeding.

When a project name or problem statement clearly implies a domain (legal,
medical, finance, …), the generator can seed a tailored expert system prompt
(with the right guardrails/disclaimers) and a starter knowledge-base document,
so the generated agent behaves as that domain expert out of the box.

Inference is keyword-based and conservative: ``infer_domain`` returns ``None``
when there's no confident match, leaving the generic behavior unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Domain:
    key: str
    label: str
    keywords: tuple[str, ...]
    system_prompt: str
    knowledge_seed: str
    suggested_skills: tuple[str, ...] = field(default_factory=tuple)


LEGAL = Domain(
    key="legal",
    label="Legal Research Assistant",
    keywords=("legal", "law", "lawyer", "attorney", "contract", "compliance",
              "nda", "litigation", "paralegal", "counsel", "regulation"),
    system_prompt=(
        "You are a legal research assistant. You provide legal information, not legal "
        "advice — always recommend consulting a licensed attorney before any decision. "
        "Cite the specific document or section you rely on. If a fact is not in your "
        "knowledge base or search results, say so plainly rather than guessing."
    ),
    knowledge_seed=(
        "# Legal knowledge base\n\n"
        "Add source documents here (statutes, contracts, policies, case summaries) as "
        "PDF/DOCX/TXT/MD. The agent cites what it retrieves.\n\n"
        "## Disclaimer\n"
        "This assistant provides general legal information, not legal advice. Consult a "
        "licensed attorney for your specific situation.\n"
    ),
    suggested_skills=("citation",),
)

MEDICAL = Domain(
    key="medical",
    label="Clinical Information Assistant",
    keywords=("medical", "clinical", "health", "patient", "diagnosis", "triage",
              "symptom", "healthcare", "nurse", "doctor", "physician", "pharma"),
    system_prompt=(
        "You are a clinical information assistant. You provide general, educational "
        "health information only — this is NOT a substitute for professional medical "
        "advice, diagnosis, or treatment. Always advise consulting a qualified "
        "healthcare provider, and urge emergency services for urgent symptoms. Ground "
        "every statement in your knowledge base or cited sources; never fabricate "
        "dosages, guidelines, or study results."
    ),
    knowledge_seed=(
        "# Clinical knowledge base\n\n"
        "Add clinical references here (guidelines, formularies, protocols) as "
        "PDF/DOCX/TXT/MD.\n\n"
        "## Disclaimer\n"
        "Educational information only — not a substitute for professional medical advice. "
        "Seek emergency care for urgent symptoms.\n"
    ),
    suggested_skills=("citation",),
)

FINANCE = Domain(
    key="finance",
    label="Financial Analysis Assistant",
    keywords=("finance", "financial", "investment", "trading", "portfolio", "banking",
              "accounting", "tax", "audit", "fintech", "valuation", "budget"),
    system_prompt=(
        "You are a financial analysis assistant. You provide information and analysis, "
        "not personalized financial advice — recommend consulting a licensed financial "
        "advisor for decisions. Show your calculations and cite data sources. State "
        "assumptions explicitly and flag when figures are estimates or out of date."
    ),
    knowledge_seed=(
        "# Financial knowledge base\n\n"
        "Add filings, reports, and market data here (PDF/XLSX/CSV/MD).\n\n"
        "## Disclaimer\n"
        "Informational analysis only — not personalized financial advice. Consult a "
        "licensed advisor before investing.\n"
    ),
)

SUPPORT = Domain(
    key="support",
    label="Customer Support Assistant",
    keywords=("support", "helpdesk", "customer", "ticket", "faq", "service desk",
              "troubleshoot", "onboarding"),
    system_prompt=(
        "You are a customer support assistant. Answer using the product knowledge base "
        "first; be concise, friendly, and step-by-step. If the knowledge base doesn't "
        "cover the question, say so and offer to escalate rather than inventing an answer."
    ),
    knowledge_seed=(
        "# Support knowledge base\n\n"
        "Add product docs, FAQs, and troubleshooting guides here (PDF/DOCX/TXT/MD).\n"
    ),
)

DEVOPS = Domain(
    key="devops",
    label="DevOps / SRE Assistant",
    keywords=("devops", "sre", "infrastructure", "kubernetes", "terraform", "ci/cd",
              "observability", "incident", "deployment", "cloud"),
    system_prompt=(
        "You are a DevOps/SRE assistant. Prefer safe, reversible actions; explain the "
        "blast radius of any command before suggesting it. Reference the team's runbooks "
        "and docs from the knowledge base, and never invent config values — ask or say "
        "you don't know."
    ),
    knowledge_seed=(
        "# DevOps knowledge base\n\n"
        "Add runbooks, architecture docs, and postmortems here (PDF/DOCX/TXT/MD).\n"
    ),
)

RESEARCH = Domain(
    key="research",
    label="Research Assistant",
    keywords=("research", "academic", "paper", "literature", "scientific", "study",
              "survey", "citation", "scholar"),
    system_prompt=(
        "You are a research assistant. Synthesize information rigorously, distinguish "
        "established findings from speculation, and cite every source. When sources "
        "conflict, surface the disagreement rather than picking one silently."
    ),
    knowledge_seed=(
        "# Research knowledge base\n\n"
        "Add papers, datasets, and notes here (PDF/DOCX/TXT/MD).\n"
    ),
    suggested_skills=("citation",),
)

DOMAINS: list[Domain] = [LEGAL, MEDICAL, FINANCE, SUPPORT, DEVOPS, RESEARCH]

_BY_KEY = {d.key: d for d in DOMAINS}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9/]+", (text or "").lower()))


def infer_domain(*text: str) -> Domain | None:
    """Return the best-matching ``Domain`` for the given text, or ``None``.

    Scores each domain by keyword hits across all provided strings (project
    name + problem statement). Requires at least one hit; ties break by the
    order in ``DOMAINS``.
    """
    haystack = " ".join(t for t in text if t)
    toks = _tokens(haystack)
    lowered = haystack.lower()

    best: Domain | None = None
    best_score = 0
    for dom in DOMAINS:
        # Count both whole-token matches and substring matches (for "legaltech").
        score = sum(1 for kw in dom.keywords if kw in toks or kw in lowered)
        if score > best_score:
            best, best_score = dom, score
    return best if best_score > 0 else None


def get_domain(key: str) -> Domain | None:
    return _BY_KEY.get((key or "").strip().lower())
