import json
from functools import lru_cache
from pathlib import Path


_KNOWLEDGE_FILE = Path(__file__).resolve().parents[1] / "data" / "assistant_knowledge_v1.json"


@lru_cache(maxsize=1)
def get_assistant_knowledge() -> dict:
    with _KNOWLEDGE_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def assistant_reply(scope: str, key: str) -> str:
    knowledge = get_assistant_knowledge()
    return str(knowledge.get(scope, {}).get(key, ""))


def assistant_knowledge_version() -> str:
    knowledge = get_assistant_knowledge()
    return str(knowledge.get("version", "unknown"))
