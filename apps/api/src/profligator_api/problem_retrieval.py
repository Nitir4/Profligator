"""Local, multi-label topic filtering before bounded semantic comparisons.

These heuristics select candidates; they do not prove equivalence or modify
provider tags. Unknown classifications use a small keyword-based fallback.
"""

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import math
import re


_FAMILY_ALIASES = {
    "dynamic-programming": ("dp", "dynamic programming", "dynamic programing", "memoization", "tabulation"),
    "graph": ("graph", "graphs", "graph theory", "bfs", "breadth first search", "dfs", "depth first search", "dfs and similar", "shortest path", "shortest paths", "topological sort"),
    "greedy": ("greedy", "greedy algorithm"),
    "backtracking": ("backtracking",),
    "binary-search": ("binary search", "binary search on answer", "bisection"),
    "two-pointers": ("two pointers", "two pointer", "two-pointer"),
    "sliding-window": ("sliding window",),
    "hashing": ("hashing", "hash table", "hash map", "hashmap"),
    "stack": ("stack", "monotonic stack"),
    "heap": ("heap", "priority queue", "heaps"),
    "disjoint-set": ("dsu", "disjoint set", "disjoint set union", "union find"),
    "trie": ("trie", "tries"),
    "bit-operations": ("bit manipulation", "bitmasks", "bit operations"),
    "math": ("math", "mathematics", "number theory", "combinatorics"),
}
_DOMAIN_ALIASES = {
    "array": ("array", "arrays", "sorting", "prefix sum"),
    "string": ("string", "strings", "string matching"),
    "graph": ("graph", "graphs", "graph theory"),
    "tree": ("tree", "trees", "binary tree", "binary search tree"),
    "grid": ("matrix", "matrices", "grid", "grids"),
    "linked-list": ("linked list", "linked lists"),
}


def _tag(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


_FAMILIES = {_tag(alias): bucket for bucket, aliases in _FAMILY_ALIASES.items() for alias in aliases}
_DOMAINS = {_tag(alias): bucket for bucket, aliases in _DOMAIN_ALIASES.items() for alias in aliases}
_PATTERNS = {
    "sequence/lcs": r"\blongest common subsequence\b|\blcs\b",
    "sequence/lis": r"\blongest (?:strictly )?increasing subsequence\b|\blis\b",
    "sequence/edit-distance": r"\bedit distance\b|\blevenshtein\b",
    "knapsack": r"\bknapsack\b",
    "knapsack/subset-sum": r"\bsubset sum\b|\bpartition equal subset\b",
    "coin-change": r"\bcoin change\b",
    "grid-paths": r"\bunique paths\b|\bgrid paths\b",
    "interval": r"\binterval (?:dp|dynamic programming)\b|\bmatrix chain\b|\bburst balloons\b",
    "tree": r"\btree dp\b|\bdp on trees\b|\bdynamic programming on trees\b",
    "digit": r"\bdigit (?:dp|dynamic programming)\b",
    "bitmask": r"\bbitmask (?:dp|dynamic programming)\b|\b(?:dp|dynamic programming) with bitmasks\b",
    "linear/nonadjacent": r"\bhouse robber\b|\bmaximum sum of non adjacent\b",
    "linear/recurrence": r"\bclimbing stairs\b",
    "sequence/palindrome": r"\blongest palindromic subsequence\b",
    "linear/decoding": r"\bdecode ways\b|\bways to decode\b",
    "linear/jumps": r"\b(?:minimum|min|fewest) jumps\b",
    "grid/min-cost": r"\bminimum path sum\b",
}
_PATTERN_TAGS = {
    "treedp": "tree", "digitdp": "digit", "bitmaskdp": "bitmask",
    "intervaldp": "interval", "dpontrees": "tree",
    "treedynamicprogramming": "tree", "digitdynamicprogramming": "digit",
    "bitmaskdynamicprogramming": "bitmask", "intervaldynamicprogramming": "interval",
}
# A mention in a rejected approach, example or comparison is not task evidence.
# This remains an English heuristic, so unfamiliar prose can still be unknown.
_INCIDENTAL = re.compile(
    r"\b(?:not|never|unlike|instead|rather than|do not|don't|avoid|example|"
    r"e\.g|labels? include|called|named|similar to|compared to)\b"
)


def _task_mentions(pattern, text):
    """Ignore nearby preceding rejection/example markers, not later constraints."""
    for match in re.finditer(pattern, text):
        prefix = re.split(r"[.!?;\n]", text[:match.start()])[-1]
        markers = list(_INCIDENTAL.finditer(prefix))
        if not markers or len(prefix[markers[-1].end():].split()) > 6:
            yield match
_STOP = set("""
    a an the and or of to in on at for from with by is are be as that this it its
    given find return output input determine compute calculate print you your we
    have has each any some all there exactly must can should will need do does
    example examples explanation constraint constraints test case cases per
    integer integers int n m k value values element elements item items
    array arrays list lists string strings graph graphs tree trees matrix grid
    minimum maximum min max number numbers length size valid distinct different
    dynamic programming dynamicprogramming dp memoization tabulation greedy
""".split())
_WORDS = {
    "indices": "index", "indexes": "index", "positions": "index", "position": "index",
    "total": "sum", "totals": "sum", "totaling": "sum", "totalling": "sum", "adding": "sum", "summing": "sum", "sums": "sum",
    "vertices": "node", "vertex": "node", "nodes": "node", "edges": "edge",
    "subarrays": "subarray", "subsequences": "subsequence", "substrings": "substring",
    "paths": "path", "cycles": "cycle", "coins": "coin", "targets": "target",
    "choosing": "choose", "chosen": "choose", "selecting": "select",
    "selected": "select", "selects": "select", "maximizing": "maximize",
    "minimizing": "minimize",
    "insertion": "insert", "insertions": "insert", "inserting": "insert",
    "deletion": "delete", "deletions": "delete", "deleting": "delete",
    "removal": "delete", "removals": "delete", "removing": "delete",
    "replacement": "replace", "replacements": "replace", "replacing": "replace",
    "substitution": "replace", "substitutions": "replace", "substituting": "replace",
}


@dataclass(frozen=True)
class Features:
    families: frozenset[str]
    domains: frozenset[str]
    dp_patterns: frozenset[str]
    terms: frozenset[str]


@lru_cache(maxsize=1024)
def features(title: str, statement: str | None, topics: tuple[str, ...]) -> Features:
    tags = {_tag(topic) for topic in topics}
    families = {_FAMILIES[tag] for tag in tags if tag in _FAMILIES}
    domains = {_DOMAINS[tag] for tag in tags if tag in _DOMAINS}
    text = " ".join((title, " ".join(topics), statement or "")).lower()
    def extract(value, *, body=False):
        normal = re.sub(r"[-_/]+", " ", value.lower())
        found = set()
        for name, pattern in _PATTERNS.items():
            # Bare abbreviations in prose may be identifiers or example labels.
            if body and name in {"sequence/lcs", "sequence/lis"}:
                pattern = pattern.split("|")[0]
            if next(_task_mentions(pattern, normal), None) is not None:
                found.add(name)
        # Fibonacci membership and staircase printing do not imply recurrence DP.
        if "dynamic-programming" in families and next(_task_mentions(r"\bfibonacci\b|\bstaircase\b", normal), None):
            found.add("linear/recurrence")
        if "knapsack" in found:
            variants = set()
            if next(_task_mentions(r"\b(?:0 1|zero one) knapsack\b", normal), None):
                variants.add("knapsack/zero-one")
            if next(_task_mentions(r"\bunbounded knapsack\b", normal), None):
                variants.add("knapsack/unbounded")
            if variants:
                found.remove("knapsack")
                found.update(variants)
        return found

    patterns = {_PATTERN_TAGS[tag] for tag in tags if tag in _PATTERN_TAGS}
    patterns.update(extract(title))
    for topic in topics:
        patterns.update(extract(topic))
    # Prefer explicit title/tag hints over incidental patterns elsewhere in text.
    if not patterns:
        for sentence in re.split(r"[.!?\n]+", statement or ""):
            patterns.update(extract(sentence, body=True))
    if patterns:
        families.add("dynamic-programming")
    if "tree" in domains:
        domains.add("graph")
    terms = {_WORDS.get(token, token) for token in re.findall(r"[a-z][a-z0-9]+", text)
             if token not in _STOP}
    return Features(frozenset(families), frozenset(domains), frozenset(patterns), frozenset(terms))


def describe(problem) -> Features:
    return features(problem.title, problem.statement, tuple(problem.topics))


def _patterns_overlap(left, right) -> bool:
    def related(a, b):
        return (a == b or a.startswith(b + "/") or b.startswith(a + "/")
                or {a, b} == {"knapsack/subset-sum", "knapsack/zero-one"})
    return any(related(a, b) for a in left for b in right)


def compatible(left: Features, right: Features) -> bool:
    if left.families and right.families and not left.families & right.families:
        return False
    if left.dp_patterns and right.dp_patterns:
        # Subset sum and 0/1 feasibility share a selection pattern. Explicit 0/1
        # and unbounded variants remain separate; eligibility is not equivalence.
        if not _patterns_overlap(left.dp_patterns, right.dp_patterns):
            return False
    if not left.families & right.families and left.domains and right.domains and not left.domains & right.domains:
        return False
    return True


def _statement_key(statement: str | None) -> bytes | None:
    normalized = " ".join((statement or "").split())
    return hashlib.sha256(normalized.encode()).digest() if normalized else None


class CandidateIndex:
    def __init__(self, history=()):
        self.problems = {}
        self.features = {}
        self.order = {}
        self.family = defaultdict(set)
        self.domain = defaultdict(set)
        self.term = defaultdict(set)
        self.pattern = defaultdict(set)
        self.statement = defaultdict(set)
        self.unknown = set()
        for problem in history:
            self.add(problem)

    def add(self, problem):
        if problem.id in self.problems:
            return
        self.order[problem.id] = len(self.problems)
        self.problems[problem.id] = problem
        labels = self.features[problem.id] = describe(problem)
        if not labels.families:
            self.unknown.add(problem.id)
        for key in labels.families:
            self.family[key].add(problem.id)
        for key in labels.domains:
            self.domain[key].add(problem.id)
        for key in labels.terms:
            self.term[key].add(problem.id)
        for key in labels.dp_patterns:
            self.pattern[key].add(problem.id)
        statement = _statement_key(problem.statement)
        if statement is not None:
            self.statement[statement].add(problem.id)

    def exact(self, problem):
        ids = self.statement.get(_statement_key(problem.statement), ())
        normalized = " ".join((problem.statement or "").split())
        return [self.problems[key] for key in sorted(ids, key=self.order.get)
                if self.problems[key].platform != problem.platform
                and " ".join((self.problems[key].statement or "").split()) == normalized]

    def candidates(self, problem, limit: int, *, group_key=None):
        if limit <= 0:
            return []
        labels = describe(problem)
        count = len(self.problems)
        def weight(term):
            return 1 + math.log((count + 1) / (len(self.term.get(term, ())) + 1))

        # Missing algorithm tags fall back to shared informative words, never all history.
        # Words absent from all history have no postings. They must not crowd
        # real task keywords out of the twelve slots or dilute their score.
        query_terms = {term for term in labels.terms if self.term.get(term)}
        keywords = sorted(query_terms, key=lambda term: (-weight(term), term))[:12]
        lexical = set().union(*(self.term.get(term, set()) for term in keywords)) if keywords else set()
        if labels.families:
            bucket = set().union(*(self.family.get(family, set()) for family in labels.families))
            pattern = set().union(*(ids for key, ids in self.pattern.items()
                if _patterns_overlap((key,), labels.dp_patterns))) if labels.dp_patterns else set()
            pool = (bucket & lexical) | pattern | (lexical & self.unknown)
        else:
            pool = lexical
        ranked = []
        for key in pool:
            candidate = self.problems[key]
            other = self.features[key]
            if candidate.platform == problem.platform or not candidate.statement or not compatible(labels, other):
                continue
            shared = labels.terms & other.terms
            known = bool(labels.families & other.families)
            same_pattern = _patterns_overlap(labels.dp_patterns, other.dp_patterns)
            if not same_pattern and len(shared) < (1 if known else 2):
                continue
            union = query_terms | other.terms
            score = sum(weight(term) for term in shared) / max(1, sum(weight(term) for term in union))
            if not same_pattern and score < 0.08:
                continue
            ranked.append((not known, -score, key, candidate))
        ranked.sort(key=lambda item: item[:3])
        result, fallback, groups = [], 0, set()
        for unknown, _, _, candidate in ranked:
            group = group_key(candidate) if group_key else candidate.id
            if group in groups:
                continue
            if unknown:
                if fallback >= 2:
                    continue
                fallback += 1
            result.append(candidate)
            groups.add(group)
            if len(result) == limit:
                break
        return result
