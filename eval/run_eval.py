"""Golden-question eval for the QA assistant.

Grades each answer on: was the expected tool called, do required substrings
appear, and (for out-of-scope questions) did the assistant refuse rather than
fabricate. Reports accuracy-on-answered, coverage, and a confusion table whose
key number to drive to zero is *confidently wrong*.

Run: python eval/run_eval.py   (needs ANTHROPIC_API_KEY in .env)
"""

from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import assistant  # noqa: E402

REFUSAL_HINTS = ["can't", "cannot", "don't have", "do not have", "not able", "unable",
                 "outside", "no data", "isn't something", "not something", "can only"]


def looks_like_refusal(text: str) -> bool:
    t = text.lower()
    return any(h in t for h in REFUSAL_HINTS)


def main() -> None:
    cases = yaml.safe_load((ROOT / "eval" / "golden_questions.yaml").read_text(encoding="utf-8"))
    tally = {"correct": 0, "refused_ok": 0, "refused_wrong": 0, "hallucinated": 0, "tool_miss": 0}
    answered = 0

    for c in cases:
        res = assistant.answer(c["question"])
        text = res["text"]
        used = {t["name"] for t in res["tools_used"]}
        refusal = c.get("expect_refusal", False)

        if refusal:
            ok = looks_like_refusal(text) and not used
            tally["refused_ok" if ok else "hallucinated"] += 1
            print(f"[{'OK ' if ok else 'BAD'}] (refuse) {c['question']}")
            print(f"        -> {text[:110]}")
            continue

        answered += 1
        tool_ok = ("expect_tool" not in c) or (c["expect_tool"] in used)
        content_ok = all(s.lower() in text.lower() for s in c.get("expect_contains", []))
        if not tool_ok:
            tally["tool_miss"] += 1
            verdict = "TOOL-MISS"
        elif content_ok:
            tally["correct"] += 1
            verdict = "OK "
        else:
            tally["hallucinated"] += 1
            verdict = "WRONG"
        print(f"[{verdict}] {c['question']}  (tools: {', '.join(sorted(used)) or 'none'})")
        print(f"        -> {text[:110]}")

    n = len(cases)
    print("\n=== summary ===")
    print(f"cases: {n}  |  answered: {answered}  |  refused: {n - answered}")
    print(f"accuracy on answered: {tally['correct']}/{answered}")
    print("confusion:", tally)
    if tally["hallucinated"]:
        print("!! confidently-wrong answers present — investigate before shipping")
    else:
        print("no confidently-wrong answers")


if __name__ == "__main__":
    main()
