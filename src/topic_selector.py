"""Simple topic selector using epsilon-greedy exploration.
"""
import random
from src.utils import setup_logger, PROJECT_ROOT
from pathlib import Path
import json

logger = setup_logger("topic_selector")

SCORES_PATH = PROJECT_ROOT / "output" / "autonomous" / "topic_scores.json"


def _load_scores():
    if not SCORES_PATH.exists():
        return {}
    try:
        return json.loads(SCORES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_scores(scores: dict):
    SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCORES_PATH.write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")


def select_topic(candidates: list[dict], epsilon: float = 0.2) -> dict:
    """Choose a topic: with probability epsilon explore (random), else exploit best-scoring candidate.

    Returns chosen candidate dict augmented with `reason` field.
    """
    scores = _load_scores()
    # attach historical score
    for c in candidates:
        c_topic = c["topic"]
        c["hist_score"] = scores.get(c_topic, 0.0)

    if random.random() < epsilon:
        choice = random.choice(candidates)
        choice["reason_detail"] = "explore (epsilon)"
    else:
        choice = max(candidates, key=lambda x: (x.get("hist_score", 0), x.get("score", 0)))
        choice["reason_detail"] = "exploit (best historical/score)"

    # update scores lightly
    scores[choice["topic"]] = scores.get(choice["topic"], 0) + 0.1
    _save_scores(scores)
    logger.info(f"Selected topic: {choice['topic']} ({choice.get('reason_detail')})")
    return choice
