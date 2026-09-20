import dataclasses
import datetime

import pytest

from jevlang import runtime
from jevlang.runtime import Choice, Noul, Score, to_state


def test_noul_is_float_with_raw():
    n = Noul(0.8)
    n.raw = {"noul": 0.8}
    assert n > 0.5
    assert n.raw == {"noul": 0.8}


def test_noul_truthiness_threshold():
    assert not bool(Noul(0.0))
    assert not bool(Noul(0.49))
    assert bool(Noul(0.5))
    assert bool(Noul(1.0))


def test_score_attrs():
    s = Score(1.43)
    s.probs = {0: 0.0, 1: 0.57, 2: 0.43}
    s.confidence = 0.35
    s.legend = {0: "calm", 1: "annoyed", 2: "angry"}
    assert round(s) == 1
    assert s.legend[round(s)] == "annoyed"


def test_choice_is_str_with_probs():
    c = Choice("billing")
    c.probs = {"billing": 0.9, "sales": 0.1}
    c.confidence = 0.85
    assert c == "billing"
    assert c.probs[c] == 0.9


def test_to_state_str_passthrough():
    assert to_state("hi") == "hi"


def test_to_state_dict_passthrough():
    assert to_state({"a": 1}) == {"a": 1}


def test_to_state_list_passthrough():
    assert to_state(["a", "b"]) == ["a", "b"]


def test_to_state_dataclass():
    @dataclasses.dataclass
    class T:
        subject: str
        days: int

    assert to_state(T("x", 3)) == {"subject": "x", "days": 3}


def test_to_state_hook_wins_over_dataclass():
    @dataclasses.dataclass
    class T:
        subject: str
        secret: str

        def __jev_state__(self):
            return {"subject": self.subject}

    assert to_state(T("x", "s")) == {"subject": "x"}


def test_to_state_plain_object_strips_private():
    class O:
        def __init__(self):
            self.body = "b"
            self._cache = 1

    assert to_state(O()) == {"body": "b"}


def test_to_state_model_dump():
    class P:
        def model_dump(self, mode="python"):
            return {"m": mode}

    assert to_state(P()) == {"m": "json"}


def test_to_state_datetime_inside_dict_is_json_safe():
    d = {"when": datetime.datetime(2026, 9, 20, 12, 0)}
    out = to_state(d)
    assert out["when"] == "2026-09-20 12:00:00"


def test_to_state_fallback_str():
    assert to_state(42) == "42"


def test_noul_fake_matches_substring():
    assert runtime.noul("this is URGENT please", "urgent") == 1.0
    assert runtime.noul("all calm here", "urgent") == 0.0


def test_noul_on_dict_state_serializes():
    assert runtime.noul({"body": "refund me"}, "refund") == 1.0


def test_score_fake_picks_matching_level():
    s = runtime.score("customer is angry", ["calm", "annoyed", "angry"])
    assert s == 2.0
    assert s.probs == {0: 0.0, 1: 0.0, 2: 1.0}
    assert s.legend == {0: "calm", 1: "annoyed", 2: "angry"}
    assert s.confidence == 1.0


def test_choice_fake_matches_description_word():
    c = runtime.choice(
        "please refund my invoice",
        {"technical": "bugs, outages", "billing": "invoice, refund", "sales": None},
    )
    assert c == "billing"
    assert c.probs == {"technical": 0.0, "billing": 1.0, "sales": 0.0}
    assert c.confidence == 1.0


def test_choice_fake_defaults_to_first_label():
    c = runtime.choice("nothing relevant", {"a": None, "b": None})
    assert c == "a"


def test_ask_dispatch_str_is_noul():
    assert isinstance(runtime.ask("urgent", "urgent"), Noul)


def test_ask_dispatch_list_is_score():
    assert isinstance(runtime.ask("x", ["a", "b"]), Score)


def test_ask_dispatch_dict_is_choice():
    assert isinstance(runtime.ask("x", {"a": None}), Choice)


def test_ask_dispatch_tuple_carries_instructions():
    from jevlang.backend import get_client

    assert isinstance(runtime.ask("x", ("How bad?", ["fine", "bad"])), Score)
    q = get_client().last_questions["q"]
    assert q.type == "score" and q.instructions == "How bad?"

    assert isinstance(runtime.ask("x", ("Which?", {"a": None, "b": None})), Choice)
    q = get_client().last_questions["q"]
    assert q.type == "choice" and q.instructions == "Which?"


def test_bare_list_and_dict_use_default_instructions():
    from jevlang.backend import get_client

    runtime.ask("x", ["a", "b"])
    assert get_client().last_questions["q"].instructions == runtime.DEFAULT_SCORE_INSTRUCTIONS

    runtime.ask("x", {"a": None})
    assert get_client().last_questions["q"].instructions == runtime.DEFAULT_CHOICE_INSTRUCTIONS


def test_ask_rejects_unknown_type():
    with pytest.raises(TypeError):
        runtime.ask("x", 42)


def test_score_limits():
    with pytest.raises(ValueError):
        runtime.score("x", ["only one"])
    with pytest.raises(ValueError):
        runtime.score("x", [str(i) for i in range(11)])


def test_choice_limit():
    with pytest.raises(ValueError):
        runtime.choice("x", {str(i): None for i in range(256)})


def test_choice_fake_matches_whole_words_not_substrings():
    # "voice" sits inside "invoice" but is not a word in the state. A substring
    # matcher would pick "technical" here; whole-word matching picks "billing".
    c = runtime.choice(
        "please refund my invoice",
        {"technical": "voice", "billing": "refund"},
    )
    assert c == "billing"


def test_limit_boundaries_are_inclusive():
    assert isinstance(runtime.score("x", ["lo", "hi"]), Score)
    assert isinstance(runtime.score("x", [str(i) for i in range(10)]), Score)
    assert isinstance(runtime.choice("x", {str(i): None for i in range(255)}), Choice)


def test_to_state_of_a_result_is_its_value():
    # Noul and Score are float subclasses carrying .raw, so the plain-object
    # __dict__ fallback used to send {"raw": ...} instead of the number.
    assert to_state(runtime.noul("this is urgent", "urgent")) == "1.0"
    assert to_state(runtime.score("customer is angry", ["calm", "angry"])) == "1.0"
    assert to_state(runtime.choice("refund me", {"billing": "refund"})) == "billing"


def test_ask_all_issues_one_call_for_every_question():
    from jevlang.backend import get_client

    client = get_client()
    before = client.calls
    runtime.ask_all(
        "customer is angry about the invoice",
        urgent="invoice",
        mood=["calm", "angry"],
        team={"billing": "invoice, refund", "technical": "outage"},
    )
    assert client.calls - before == 1
    assert set(client.last_questions) == {"urgent", "mood", "team"}


def test_ask_all_results_match_the_single_question_forms():
    a = runtime.ask_all(
        "customer is angry about the invoice",
        urgent="invoice",
        mood=["calm", "angry"],
        team={"billing": "invoice, refund", "technical": "outage"},
    )
    assert isinstance(a.urgent, Noul) and a.urgent == 1.0
    assert isinstance(a.mood, Score) and a.mood == 1.0
    assert isinstance(a.team, Choice) and a.team == "billing"
    assert a.team.probs == {"billing": 1.0, "technical": 0.0}


def test_ask_all_takes_the_same_tuple_form_as_ask():
    from jevlang.backend import get_client

    a = runtime.ask_all("x", bad=("How bad?", ["fine", "bad"]))
    assert isinstance(a.bad, Score)
    assert get_client().last_questions["bad"].instructions == "How bad?"


def test_ask_all_validates_every_question_before_calling():
    from jevlang.backend import get_client

    client = get_client()
    before = client.calls
    with pytest.raises(ValueError):
        runtime.ask_all("x", ok="fine", broken=["only one"])
    assert client.calls == before  # nothing sent


def test_ask_all_rejects_unknown_question_type():
    with pytest.raises(TypeError):
        runtime.ask_all("x", bad=42)


def test_ask_all_needs_at_least_one_question():
    with pytest.raises(ValueError):
        runtime.ask_all("x")


def test_score_keys_are_ints_even_though_the_sdk_sends_strings():
    # the live SDK keys probabilities and legend by "0", "1", ...; the fake
    # mirrors that, and the wrapper must turn them into ints
    s = runtime.score("customer is angry", ["calm", "annoyed", "angry"])
    assert set(s.probs) == set(s.legend) == {0, 1, 2}
    assert s.legend[round(s)] == "angry"
