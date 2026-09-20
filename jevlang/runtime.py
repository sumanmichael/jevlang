"""Result types, state coercion, and the ask/noul/score/choice functions."""

import dataclasses
import json
from types import SimpleNamespace

from typesafe_sdk import Choice as _ChoiceQ
from typesafe_sdk import Noul as _NoulQ
from typesafe_sdk import Score as _ScoreQ

from jevlang.backend import get_client

DEFAULT_SCORE_INSTRUCTIONS = "Which level best describes the state?"
DEFAULT_CHOICE_INSTRUCTIONS = "Which option best describes the state?"


class Noul(float):
    """0 to 1 probability that the statement is true. Truthy at >= 0.5."""

    raw = None

    def __bool__(self):
        return float(self) >= 0.5


class Score(float):
    """Probability-weighted level index; may be fractional."""

    raw = None
    probs = None
    confidence = None
    legend = None


class Choice(str):
    """The chosen label, with the full distribution attached."""

    raw = None
    probs = None
    confidence = None


def _jsonable(x):
    # round-trip so datetime/Decimal/UUID become strings and nested objects flatten
    return json.loads(json.dumps(x, default=str))


def to_state(x):
    if isinstance(x, str):
        return x
    if hasattr(x, "__jev_state__"):
        return to_state(x.__jev_state__())
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return _jsonable(dataclasses.asdict(x))
    if hasattr(x, "model_dump"):
        return _jsonable(x.model_dump(mode="json"))
    if isinstance(x, (dict, list, tuple)):
        return _jsonable(x)
    if isinstance(x, (int, float)):
        # Noul and Score are float subclasses carrying .raw, so without this they
        # would reach the __dict__ fallback below and be sent as {"raw": ...}.
        return str(x)
    if hasattr(x, "__dict__") and vars(x):
        return _jsonable({k: v for k, v in vars(x).items() if not k.startswith("_")})
    return str(x)


def _call(state, question):
    resp = get_client().system_one(state=to_state(state), questions={"q": question})
    return resp.answers["q"]


def _wrap_noul(ans):
    out = Noul(ans.noul)
    out.raw = ans
    return out


def _wrap_score(ans):
    out = Score(ans.score)
    out.raw = ans
    # the live SDK keys these by the level index as a string; int keys let
    # s.legend[round(s)] work
    out.probs = {int(k): v for k, v in ans.probabilities.items()}
    out.confidence = ans.confidence
    out.legend = {int(k): v for k, v in ans.legend.items()}
    return out


def _wrap_choice(ans):
    out = Choice(ans.choice)
    out.raw = ans
    out.probs = dict(ans.probabilities)
    out.confidence = ans.confidence
    return out


def _noul_q(instructions):
    return _NoulQ(instructions=instructions), _wrap_noul


def _score_q(criteria, instructions):
    criteria = list(criteria)
    if not 2 <= len(criteria) <= 10:
        raise ValueError(f"score needs 2 to 10 levels, got {len(criteria)}")
    return _ScoreQ(instructions=instructions, criteria=criteria), _wrap_score


def _choice_q(criteria, instructions):
    criteria = dict(criteria)
    if not 1 <= len(criteria) <= 255:
        raise ValueError(f"choice needs 1 to 255 options, got {len(criteria)}")
    return _ChoiceQ(instructions=instructions, criteria=criteria), _wrap_choice


def _build(q):
    """Map a `~` right-hand side to an SDK question plus its result wrapper."""
    if isinstance(q, tuple) and len(q) == 2 and isinstance(q[0], str):
        instructions, criteria = q
        if isinstance(criteria, dict):
            return _choice_q(criteria, instructions)
        if isinstance(criteria, (list, tuple)):
            return _score_q(criteria, instructions)
    if isinstance(q, str):
        return _noul_q(q)
    if isinstance(q, dict):
        return _choice_q(q, DEFAULT_CHOICE_INSTRUCTIONS)
    if isinstance(q, (list, tuple)):
        return _score_q(q, DEFAULT_SCORE_INSTRUCTIONS)
    raise TypeError(f"cannot ask a {type(q).__name__}; expected str, list, dict, or (instructions, criteria)")


def noul(state, instructions):
    question, wrap = _noul_q(instructions)
    return wrap(_call(state, question))


def score(state, criteria, instructions=DEFAULT_SCORE_INSTRUCTIONS):
    question, wrap = _score_q(criteria, instructions)
    return wrap(_call(state, question))


def choice(state, criteria, instructions=DEFAULT_CHOICE_INSTRUCTIONS):
    question, wrap = _choice_q(criteria, instructions)
    return wrap(_call(state, question))


def ask(state, q):
    """Dispatch for `state ~ q`. See the spec's syntax table."""
    question, wrap = _build(q)
    return wrap(_call(state, question))


def ask_all(state, **questions):
    """Ask several questions about one state in a single API call.

    Each keyword takes any right-hand side `~` accepts, and comes back as an
    attribute of the result:

        a = ask_all(ticket, urgent="is it urgent", mood=["calm", "angry"])
        if a.urgent and a.mood >= 1: ...

    Every question is built (and validated) before anything is sent, so a bad
    question raises instead of half-spending a call.
    """
    if not questions:
        raise ValueError("ask_all needs at least one question")
    # no cap on question count. Choice and Score have documented
    # limits, a batch does not; if the API has one, add the check here.
    built = {name: _build(q) for name, q in questions.items()}
    resp = get_client().system_one(
        state=to_state(state),
        questions={name: question for name, (question, _) in built.items()},
    )
    return SimpleNamespace(**{name: wrap(resp.answers[name]) for name, (_, wrap) in built.items()})
