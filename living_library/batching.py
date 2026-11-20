"""Batched practice: k games run at once from the same memory, then merge in a fixed order.

Each game of a batch is still its own episode (own trace, own record). It runs on a private copy
of the memory as it was at the start of the batch. Afterwards the main process applies each
game's changes, in position order, to the live memory:

  D trajectories   successful traces are appended
  rule manual      the game's applied manual operations are replayed onto the live rules
                   (manual.replay; a rule's text changes at most once per batch)

With k = 1 the merge returns exactly the game's own final memory, i.e. sequential practice.
"""
import copy


def merge_memory(live, base, end, log, rule_operations=()):
    """Memory = {'trajectories', 'rules'}: D appends successful practice traces; the rule manual replays the
    game's applied operations onto the live rules (judged against the batch's starting rules `base['rules']`)."""
    from .manual import replay
    trajectories = copy.deepcopy(live['trajectories']) + copy.deepcopy(end['trajectories'][len(base['trajectories']):])
    return {'trajectories': trajectories,
            'rules': replay(live['rules'], list(rule_operations), log, base['rules'])}
