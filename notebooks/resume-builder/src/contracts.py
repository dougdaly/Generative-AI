JD_SIGNAL_FIELD_DEFINITIONS = {
    "business_industries": "Industries or business contexts where the role applies its work, such as banking, marketing, utilities, healthcare, advertising, or enterprise software.",
    "problem_spaces": "Classes of business or operational problems the role is meant to solve, such as decision support, workflow automation, risk analysis, observability, or knowledge retrieval.",
    "technology_areas": "Major technical approaches or architectural patterns involved in the role, such as LLMs, RAG, agentic AI, MLOps, graph analytics, or cloud-native AI systems.",
    "capabilities": "Reusable abilities the person is expected to apply, such as designing AI architectures, integrating systems, evaluating models, mentoring engineers, or communicating tradeoffs.",
    "technologies": "Specific tools, platforms, frameworks, languages, or infrastructure mentioned.",
    "responsibilities": "Concrete work the person is expected to perform.",
    "seniority_signals": "Signals that distinguish this as senior, staff, principal, or architect-level work.",
    "success_metrics": "Business, technical, or operational outcomes that would indicate success.",
    "role_purpose": "The function this role serves within the organization. Why does this job exist?",
    "business_problems": "Specific organizational problems the company wants this role to solve.",
    "role_outcomes": "Expected outputs or end states this role should produce.",
    "emerging_signals": "Important signals that do not fit cleanly into the other categories or were not anticipated.",
}

JD_SIGNAL_FIELDS = list(JD_SIGNAL_FIELD_DEFINITIONS.keys())

JD_SIGNAL_EXTRACTION_SCHEMA = {
    "title": "",
    "company": "",
    "source": "",
    "url": "",
    "signals": {
        field: []
        for field in JD_SIGNAL_FIELDS
    },
}

CANONICAL_MARKET_SIGNAL_SCHEMA = {
    "signal_type": "",
    "canonical_signal": "",
    "phrase_count": 0,
    "jd_coverage": 0,
    "companies": [],
    "source_phrases": [],
    "example_phrases": [],
}

TARGET_ARCHETYPE_SCHEMA = {
    "title": "",
    "archetype_summary": "",
    "market_basis": {
        "jd_count": 0,
        "primary_signal_types_used": [],
        "notes": "",
    },
    "hypothesis_assessment": {
        "confirmed": [],
        "revised": [],
        "downweighted": [],
        "added": [],
    },
    "core_market_themes": [],
    "target_capabilities": [],
    "target_problem_spaces": [],
    "target_technology_areas": [],
    "seniority_expectations": [],
    "success_patterns": [],
    "resume_implications": {
        "must_emphasize": [],
        "should_include": [],
        "use_lightly": [],
        "avoid_overemphasizing": [],
    },
    "archetype_narrative": "",
}

ARCHETYPE_HYPOTHESIS = {
    "title": "Principal AI Engineer / AI Solutions Architect",

    "business_industries": [
        "enterprise software",
        "utilities",
        "financial services",
        "media and entertainment",
        "retail",
        "telecommunications",
    ],

    "problem_spaces": [
        "business intelligence",
        "decision support",
        "operational intelligence",
        "forecasting",
        "risk analysis",
        "fraud detection",
        "observability",
        "analytics",
        "workflow automation",
        "enterprise knowledge retrieval",
    ],

    "technology_areas": [
        "LLMs",
        "RAG",
        "agentic AI",
        "graph analytics",
        "anomaly detection",
        "entity resolution",
        "cloud-native AI systems",
        "MLOps",
    ],

    "capabilities": [
        "design AI architectures",
        "integrate AI systems with enterprise data",
        "evaluate LLM performance",
        "lead technical roadmap",
        "communicate technical tradeoffs",
        "mentor engineers",
        "deliver production systems",
    ],

    "technologies": [
        "Python",
        "AWS",
        "GCP",
        "BigQuery",
        "LangGraph",
    ],

    "responsibilities": [
        "designing AI solutions",
        "leading technical teams",
        "defining architecture standards",
        "mentoring engineers",
        "collaborating with stakeholders",
    ],

    "seniority_signals": [
        "technical vision",
        "technical strategy",
        "roadmap ownership",
        "cross-functional leadership",
        "influence without authority",
        "mentorship",
        "principal-level architecture ownership",
        "enterprise-scale delivery",
        "stakeholder alignment",
        "multi-system integration",
        "governance and risk awareness",
        "ambiguous problem definition",
    ],

    "success_metrics": [
        "solution adoption",
        "operational efficiency",
        "revenue growth",
        "cost reduction",
        "system reliability",
        "stakeholder satisfaction",
    ],

    "role_purpose": [
        "Provide technical leadership for enterprise AI initiatives",
        "Translate business requirements into AI solutions",
        "Ensure AI systems operate reliably in production",
    ],

    "business_problems": [],
    "role_outcomes": [],
    "emerging_signals": [],
    "archetype_narrative": "",
}

JD_SEARCH_CONTRACT = {
    "titles": [
        "Principal AI Engineer",
        "Staff AI Engineer",
        "AI Solutions Architect",
        "AI Architect",
        "Principal Machine Learning Engineer",
        "Staff Machine Learning Engineer",
    ],

    "salary_min": 200000,

    "years_experience_min": 5,

    "exclude_titles": [
        "Research Scientist",
        "Intern",
        "Junior",
    ],
    "must_have_keywords": [
        "AI",
        "machine learning",
        "LLM",
        "GenAI",
        "artificial intelligence",
    ],

    "max_jds": 50,
}


JD_SCHEMA = {
    "title": "",
    "company": "",
    "salary_min": None,
    "salary_max": None,
    "location": "",
    "source": "",
    "url": "",
    "raw_text": "",
}