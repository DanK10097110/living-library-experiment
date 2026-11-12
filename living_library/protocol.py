"""Expectations fixed from the proposal, not empirical claims about this run."""

PREREGISTRATION = {
    "hypotheses": {
        "H1": {"comparison": "E - D", "primary_metric": "task_success",
               "secondary_comparison": "E - C", "expectation": "no confident prediction against D"},
        "H2": {"comparison": "E - D", "primary_metric": "amortized_gpu_seconds_per_task",
               "expectation": "E eventually costs less including practice"},
        "H3": {"comparison": "E - E-minus", "primary_metric": "skill_invocation_success",
               "expectation": "updates help; smaller gains than adding memory"},
        "H4": {"comparison": "E - E-text", "primary_metric": "task_success",
               "expectation": "executable skills outperform the same content rendered as text"},
    },
    "exploratory": "B versus E: no prediction about the contribution of hierarchy",
    "other_expectations": {"E_vs_C": "memory helps", "C_vs_A": "hierarchy helps somewhat"},
    "success_criterion": "E-D success >=10 percentage points, OR zero within its 95% CI and >=30% lower amortized GPU cost; AND positive E-E-minus invocation effect with Holm p<=.05. H4 is reported separately.",
    "statistics": "Paired bootstrap 95% intervals clustering by task; average seeds for task success/cost; pooled invocation counts with tasks resampled as clusters; Holm correction across H1-H4.",
    "practice_allocation": "500 episodes per memory-building condition, one fixed practice seed; clone that memory into each independent evaluation seed. E-text shares E's practice charge.",
    "sanity_rule": "If E-C is near zero, inspect retrieval, execution and predicate logs before interpreting a null result.",
    "optional_extensions": "Excluded from the seven-condition core study and its success criterion.",
}
