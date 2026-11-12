"""Optional deterministic consolidation proposals, never run by default.

This groups active skills with identical typed contracts and AST structure after
replacing string literals. It does not infer a general program: callers may supply
one, otherwise the shortest source body is proposed. Every source replay must
pass the library's existing admission gate. Originals remain stored, counters are
never copied, and no imagined experience is produced or counted as reliability.
"""
import ast
import copy
from dataclasses import dataclass

from .config import digest
from .library import Skill


class _Shape(ast.NodeTransformer):
    def visit_Constant(self, node):
        return ast.copy_location(ast.Constant(value='<string>'), node) if isinstance(node.value, str) else node


@dataclass
class Consolidation:
    candidate: Skill
    sources: tuple[str, ...]
    tests: list[dict]


def consolidation_candidates(library, body=None):
    """Return proposals only. body, if given, maps tuple(source_ids) -> source.

    Identical contracts mean identical parameter names/types and predicate lists;
    numeric loop bounds and control flow must match. String changes are only a
    candidate-generation heuristic and convey no behavioral equivalence claim.
    """
    groups = {}
    for skill in library.current():
        key = digest({'parameters': skill.parameters, 'preconditions': skill.preconditions,
                      'postconditions': skill.postconditions,
                      'shape': ast.dump(_Shape().visit(ast.parse(skill.body)), include_attributes=False)})
        groups.setdefault(key, []).append(skill)
    proposals = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda s: (len(s.body), s.id))
        parent = members[0]
        ids = tuple(sorted(s.id for s in members))
        source = body(ids) if body is not None else parent.body
        tests, seen = [], set()
        for member in members:
            for test in member.tests:
                fingerprint = digest(test)
                if fingerprint not in seen:
                    tests.append(copy.deepcopy(test))
                    seen.add(fingerprint)
        candidate = Skill(library.next_id(parent.name), parent.description,
                          dict(parent.parameters), list(parent.preconditions),
                          list(parent.postconditions), source, parent=parent.id)
        proposals.append(Consolidation(candidate, ids, tests))
    return proposals


def admit_consolidation(library, proposal, verify):
    """Explicitly activate only after every source's real replay passes.

    Revalidates source provenance against the current library. One distinct real
    replay is sufficient for consolidation; Dyna's stronger requirement does not
    apply here because this module never generates imagined experience.
    """
    candidate = proposal.candidate
    if len(set(proposal.sources)) < 2:
        raise ValueError('consolidation requires at least two distinct source skills')
    if candidate.parent not in proposal.sources:
        raise ValueError('consolidation parent must be a source')
    sources = []
    for sid in proposal.sources:
        skill = library.skills.get(sid)
        if skill is None or library.active.get(skill.name) != sid:
            raise ValueError('consolidation sources must still be active')
        if (skill.parameters != candidate.parameters or skill.preconditions != candidate.preconditions
                or skill.postconditions != candidate.postconditions):
            raise ValueError('consolidation must preserve every source contract')
        sources.append(skill)
    # Never trust mutable proposal.tests to remove a real regression test.
    tests = {digest(t): copy.deepcopy(t) for s in sources for t in s.tests}
    if not tests:
        raise ValueError('consolidation requires real source replay tests')
    real_tests = list(tests.values())
    outcomes = None
    def verify_union(skill, ignored_test):
        nonlocal outcomes
        if outcomes is None:
            outcomes = [bool(verify(skill, t)) for t in real_tests]
        return all(outcomes)
    admitted = library.admit(candidate, real_tests[0], verify_union)
    # Retain source tests within the same configured bound as normal admission.
    library.skills[candidate.id].tests = copy.deepcopy(real_tests[:library.cfg.test_limit])
    return admitted
