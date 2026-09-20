"""Client factory. JEVLANG_FAKE_JEV=1 returns a deterministic offline client."""

import json
import os
import re
from types import SimpleNamespace


class FakeClient:
    """Canned answers so tests and demos run without an API key.

    noul:   1.0 if instructions appear in the state text, else 0.0
    score:  index of the first level whose text appears in the state, else 0
    choice: first label whose label or description has a word in the state,
            else the first label
    Score probabilities/legend are keyed by str, like the real SDK.

    This is a stand-in for wiring, not for judgment: a Noul is only ever
    0.0 or 1.0 here, where the model returns a real probability.
    """

    def __init__(self):
        self.calls = 0
        self.last_state = None
        self.last_questions = None

    def system_one(self, state, questions):
        self.calls += 1
        self.last_state = state
        self.last_questions = dict(questions)
        text = (state if isinstance(state, str) else json.dumps(state)).lower()
        answers = {}
        for name, q in questions.items():
            if q.type == "noul":
                hit = str(q.instructions).lower() in text
                answers[name] = SimpleNamespace(type="noul", noul=1.0 if hit else 0.0)
            elif q.type == "score":
                levels = list(q.criteria)
                idx = next((i for i, lv in enumerate(levels) if str(lv).lower() in text), 0)
                answers[name] = SimpleNamespace(
                    type="score",
                    score=float(idx),
                    confidence=1.0,
                    probabilities={str(i): (1.0 if i == idx else 0.0) for i in range(len(levels))},
                    legend={str(i): lv for i, lv in enumerate(levels)},
                )
            elif q.type == "choice":
                labels = list(q.criteria)
                state_words = set(re.findall(r"[a-z0-9]+", text))
                pick = labels[0]
                for label in labels:
                    words = f"{label} {q.criteria[label] or ''}".lower().replace(",", " ").split()
                    if any(w in state_words for w in words):
                        pick = label
                        break
                answers[name] = SimpleNamespace(
                    type="choice",
                    choice=pick,
                    confidence=1.0,
                    probabilities={lb: (1.0 if lb == pick else 0.0) for lb in labels},
                )
            else:
                raise TypeError(f"unknown question type {q.type}")
        return SimpleNamespace(model="fake", answers=answers, usage=None)


_client = None


FAKE_ENV = "JEVLANG_FAKE_JEV"


def get_client():
    global _client
    if _client is None:
        if os.environ.get(FAKE_ENV) == "1":
            _client = FakeClient()
        else:
            from typesafe_sdk import TypeSafeClient, TypeSafeError

            try:
                _client = TypeSafeClient()
            except TypeSafeError as e:
                raise TypeSafeError(
                    f"{e}\n\n"
                    f"No key handy? Set {FAKE_ENV}=1 to run against a canned offline\n"
                    "backend that answers by substring match. It exercises the wiring,\n"
                    "not the judgment, so every Noul comes back 0.0 or 1.0."
                ) from None
    return _client
