import pytest
from sqlalchemy import select

from profligator_api.config import Settings
from profligator_api.database import Database
from profligator_api.matching import MatchResult, MatchingService, Problem, candidates
from profligator_api.models import CodingRecord
from profligator_api.problem_retrieval import CandidateIndex, describe
from profligator_api.repository import Repository
from test_report_backend import seed


def problem(key, topics, title="Pair Search", statement="Find two indices whose values sum to a target.", platform="leetcode"):
    return Problem(key, platform, title, statement, topics)


@pytest.mark.parametrize("alias", ["dp", "DP", "Dynamic Programming", "DynamicProgramming", "Memoization"])
def test_provider_dp_aliases_normalize_without_changing_original_tags(alias):
    item = problem("a", [alias, "Array"])
    assert describe(item).families == {"dynamic-programming"}
    assert item.topics == [alias, "Array"]


@pytest.mark.parametrize("title,pattern", [
    ("Longest Increasing Subsequence", "sequence/lis"),
    ("Longest Common Subsequence", "sequence/lcs"),
    ("Edit Distance", "sequence/edit-distance"), ("Coin Change", "coin-change"),
    ("0/1 Knapsack", "knapsack/zero-one"), ("Unbounded Knapsack", "knapsack/unbounded"),
    ("Digit DP", "digit"), ("Bitmask DP", "bitmask"), ("Tree DP", "tree"),
    ("Matrix Chain Multiplication", "interval"),
])
def test_specific_dp_patterns_are_local_hints(title, pattern):
    item = problem("a", [], title=title)
    assert describe(item).dp_patterns == {pattern}
    assert describe(item).families == {"dynamic-programming"}


def test_same_input_words_do_not_cross_known_algorithm_families():
    opened = problem("opened", ["DP", "Array"])
    history = [problem("greedy", ["Greedy", "Array"], platform="geeksforgeeks"),
               problem("graph", ["Graphs"], platform="codeforces"),
               problem("dp", ["Dynamic Programming"], platform="geeksforgeeks")]
    assert [p.id for p in candidates(opened, history, 8)] == ["dp"]


def test_lcs_lis_and_explicit_knapsack_variants_are_separate():
    lcs = problem("opened", ["DP"], title="LCS")
    history = [problem("lis", ["DP"], title="LIS", platform="geeksforgeeks"),
               problem("lcs", ["DynamicProgramming"], title="Longest Common Subsequence", platform="geeksforgeeks")]
    assert [p.id for p in candidates(lcs, history, 8)] == ["lcs"]
    zero_one = problem("opened", ["DP"], title="0/1 Knapsack")
    history = [problem("unbounded", ["DP"], title="Unbounded Knapsack", platform="geeksforgeeks"),
               problem("general", ["DP"], title="Knapsack", platform="geeksforgeeks")]
    assert [p.id for p in candidates(zero_one, history, 8)] == ["general"]


def test_multi_label_questions_can_match_through_either_algorithm():
    opened = problem("opened", ["Dynamic Programming", "Binary Search"], title="Longest Increasing Subsequence")
    history = [problem("alternate", ["Binary Search"], title="LIS", platform="geeksforgeeks")]
    assert [p.id for p in candidates(opened, history, 8)] == ["alternate"]


def test_unknown_metadata_fallback_is_keyword_related_and_capped():
    opened = problem("opened", ["DP", "Array"])
    history = [problem(str(i), ["Array"], platform="geeksforgeeks") for i in range(20)]
    history += [problem("unrelated", [], statement="Determine whether a directed graph contains a cycle.", platform="codeforces")]
    result = candidates(opened, history, 8)
    assert len(result) == 2 and "unrelated" not in {p.id for p in result}


def test_broad_dp_label_alone_does_not_generate_comparisons():
    opened = problem("opened", ["DP"], title="Orchard", statement="Choose apples without bruises.")
    history = [problem("other", ["Dynamic Programming"], title="Robot", statement="Recharge batteries while navigating obstacles.", platform="geeksforgeeks")]
    assert candidates(opened, history, 8) == []


def test_large_unrelated_history_keeps_the_relevant_bucket_and_limit():
    opened = problem("opened", ["DP"], title="LCS")
    history = [problem(f"graph-{i}", ["Graphs"], title="Network", statement="Detect a cycle among directed edges and vertices.", platform="codeforces") for i in range(1000)]
    history += [problem(f"dp-{i}", ["Dynamic Programming"], title="Longest Common Subsequence", platform="geeksforgeeks") for i in range(20)]
    result = candidates(opened, history, 8)
    assert len(result) == 8 and all(p.id.startswith("dp-") for p in result)


def test_candidate_limit_counts_clusters_not_repeated_members():
    opened = problem("opened", ["DP"], title="LCS")
    history = [problem(f"a{i}", ["DP"], title="LCS", platform="geeksforgeeks") for i in range(5)]
    history += [problem("b", ["DP"], title="LCS", platform="geeksforgeeks")]
    result = CandidateIndex(history).candidates(opened, 2, group_key=lambda p: "a" if p.id.startswith("a") else p.id)
    assert len(result) == 2 and result[1].id == "b"


def test_exact_lookup_bypasses_topic_differences_and_ignores_same_platform():
    opened = problem("opened", ["DP"])
    history = [problem("cross", ["Greedy"], platform="geeksforgeeks"), problem("same", ["DP"])]
    assert [p.id for p in CandidateIndex(history).exact(opened)] == ["cross"]


@pytest.mark.parametrize("exact", [False, True])
async def test_algorithm_gate_prevents_provider_calls_in_application_matching(tmp_path, exact):
    config = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'filter.db'}")
    database = Database(config.database_url)
    database.initialize()
    statements = ("Find two indices with sum K.", "Find two indices with sum K." if exact else "Return two positions totaling a target.")
    user_id, _ = seed(database, statements=statements)
    with database.session() as session:
        rows = list(session.scalars(select(CodingRecord).order_by(CodingRecord.created_at)))
        rows[0].topics = ["DP", "Array"]
        rows[1].topics = ["Greedy", "Array"]
    class Provider:
        name, model = "test", "retrieval"
        async def compare(self, left, right):
            pytest.fail("Unrelated buckets and exact checks must not call Groq")
    assert await MatchingService(database, config, Provider()).match_user(user_id) == "complete"
    with database.session() as session:
        assert Repository(session).dashboard(user_id).unique_problems_solved == (1 if exact else 2)
    database.dispose()


async def test_dp_shortlist_controls_actual_extension_comparison_calls(tmp_path):
    from profligator_api.schemas import DuplicateCheckRequest
    config = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'check.db'}")
    database = Database(config.database_url)
    database.initialize()
    user_id, _ = seed(database, statements=("Longest common subsequence of two strings.", "Longest increasing subsequence of an array."))
    with database.session() as session:
        for row in session.scalars(select(CodingRecord)):
            row.topics = ["DP"]
    calls = []
    class Provider:
        name, model = "test", "retrieval"
        async def compare(self, left, right):
            calls.append(right["statement"])
            return MatchResult(duplicate=True, confidence=0.99, reason="Equivalent LCS task")
    payload = DuplicateCheckRequest(platform="codeforces", source_id="4-A", title="LCS",
        canonical_url="https://codeforces.com/problemset/problem/4/A",
        statement="Return the longest sequence present in the same order in both strings.", topics=["Dynamic Programming"])
    result = await MatchingService(database, config, Provider()).check(user_id, payload)
    assert result.status == "semantic" and calls == ["Longest common subsequence of two strings."]
    database.dispose()


@pytest.mark.parametrize("title,statement,topics", [
    ("Staircase", "Print a right-aligned staircase of hash characters.", []),
    ("Is Fibonacci", "Test Fibonacci membership using perfect squares.", ["Math"]),
    ("Bracket validator", "Do not use edit distance; check balanced brackets.", ["Stack"]),
    ("Word histogram", "Example words: longest common subsequence, edit distance, knapsack.", ["Hashing"]),
])
def test_incidental_or_ambiguous_mentions_do_not_add_dp(title, statement, topics):
    labels = describe(problem("a", topics, title, statement))
    assert "dynamic-programming" not in labels.families
    assert not labels.dp_patterns


def test_negated_output_constraint_does_not_erase_the_actual_task():
    labels = describe(problem("a", ["String"], "Shared symbols",
        "Find the longest common subsequence; symbols need not be contiguous."))
    assert labels.dp_patterns == {"sequence/lcs"}


def test_task_title_takes_priority_over_compared_knapsack_variant():
    query = problem("query", ["DP"], "Unbounded Knapsack",
        "Unlike 0/1 knapsack, each item can be used repeatedly.")
    target = problem("target", ["DP"], "Unbounded Knapsack",
        "Choose unlimited copies of items under a capacity.", "geeksforgeeks")
    assert describe(query).dp_patterns == {"knapsack/unbounded"}
    assert candidates(query, [target], 8) == [target]


def test_specific_topic_aliases_allow_matching_between_renamed_tasks():
    query = problem("query", ["DP"], "Tree DP", "Maximize the weight of nonadjacent nodes.")
    target = problem("target", ["TreeDynamicProgramming"], "Weighted independent set",
        "Choose tree nodes with no adjacent pair, maximizing weight.", "geeksforgeeks")
    assert candidates(query, [target], 8) == [target]


def test_absent_history_words_do_not_crowd_out_matching_keywords():
    query = problem("query", ["Hashing"], "Target pair",
        "Return two indices whose sum equals target. Background vocabulary: "
        "satellite orbit telemetry altitude fuel pressure velocity acceleration coolant "
        "thermodynamics compass navigation latitude longitude gyroscope payload trajectory "
        "horizon capsule atmosphere ignition thruster.")
    target = problem("target", ["Hashing"], "Find pair",
        "Find two indices with values whose sum is target.", "geeksforgeeks")
    assert candidates(query, [target], 8) == [target]


def test_subset_sum_allows_zero_one_candidates_but_excludes_unbounded():
    query = problem("query", ["DP"], "Subset Sum", "Determine whether a subset sums to a target.")
    zero_one = problem("zero-one", ["DP"], "0/1 Knapsack feasibility",
        "Determine whether choosing each item once reaches capacity exactly.", "geeksforgeeks")
    unbounded = problem("unbounded", ["DP"], "Unbounded Knapsack",
        "Choose unlimited copies of items within capacity.", "geeksforgeeks")
    assert candidates(query, [zero_one, unbounded], 8) == [zero_one]


def test_renamed_untagged_edit_task_retrieves_through_operation_synonyms():
    query = problem("query", ["DP", "String"], "Edit Distance",
        "Find the minimum number of edits to transform the source string into the target. "
        "Each character insertion, deletion or replacement costs one.")
    target = problem("target", [], "Text conversion",
        "Return the fewest unit-cost insertions removals and substitutions converting one string to another.",
        "geeksforgeeks")
    assert candidates(query, [target], 8) == [target]
