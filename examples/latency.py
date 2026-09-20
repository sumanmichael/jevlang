"""Time one `~` against a five-question batch. Needs TYPESAFE_API_KEY; ~12 paid calls.

    uv run python examples/latency.py
"""

import statistics
import time

from jevlang import ask, ask_all

MSG = "I was charged twice for invoice A-104, please refund one of them. This is urgent."
FIVE = dict(
    refund="the customer wants a refund",
    urgent="is urgent",
    mood=["calm", "annoyed", "angry"],
    team={"billing": "refunds", "technical": "outages"},
    churn="likely to churn",
)


def ms(f):
    t = time.perf_counter()
    f()
    return (time.perf_counter() - t) * 1000


if __name__ == "__main__":
    ask(MSG, "warmup")
    single = [ms(lambda: ask(MSG, "the customer wants a refund")) for _ in range(8)]
    batch = [ms(lambda: ask_all(MSG, **FIVE)) for _ in range(3)]
    print(f"1 question:  median {statistics.median(single):.0f} ms  ({min(single):.0f} to {max(single):.0f}, {len(single)} runs)")
    print(f"5 questions: median {statistics.median(batch):.0f} ms  ({min(batch):.0f} to {max(batch):.0f}, {len(batch)} runs)")
