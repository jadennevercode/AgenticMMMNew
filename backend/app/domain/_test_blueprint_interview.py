"""Structural assertions for the interview blueprint after 1.3b removal."""
from app.domain.blueprint import TASKS

def _by_id():
    return {t["id"]: t for t in TASKS}

def main():
    tasks = _by_id()
    assert "1.3b" not in tasks, "1.3b (pre-answer) must be removed"
    assert "1.4a" in tasks, "1.4a upload gate must remain"
    assert tasks["1.4a"]["depends_on"] == ["1.3"], \
        f'1.4a must depend on 1.3, got {tasks["1.4a"]["depends_on"]}'
    print("OK blueprint interview structure")

if __name__ == "__main__":
    main()
