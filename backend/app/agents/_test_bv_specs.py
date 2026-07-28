"""Run: PYTHONPATH=. .venv/bin/python app/agents/_test_bv_specs.py
Invokes the 2.3 handler with a fake engine and asserts the produced artifact body carries `specs`."""
import asyncio
import pandas as pd
from app.store.state import ProjectState


def _fake_df() -> pd.DataFrame:
    return pd.DataFrame({
        "l1": ["KPI", "MARKETING"], "l2": ["Sales", "Media"], "l3": ["Sell-out", "TV"],
        "l4": ["", "TV spend"], "metric": ["销量", "花费"], "metric_type": ["Y", "spending"],
        "value": [1000.0, 200.0], "year": [2025, 2025], "month": [202501, 202501],
        "source": ["d", "d"], "brand": ["M", "M"], "channel_type": ["TV", "TV"],
        "province_group": ["E", "E"],
    })


class _Eng:
    def __init__(self): self.body = None
    def set_analysis(self, st, key, val): pass
    def produce(self, st, aid, body=None, state=None, agent=None): self.body = body
    def add_findings(self, st, tid, findings): pass
    def add_insight(self, st, insight): pass


def main() -> None:
    import app.agents.data as data
    import app.agents.dataset_cache as dataset_cache
    fake = lambda st=None: _fake_df()
    data.model_df = fake                                  # handler calls its own module global
    dataset_cache.model_df = fake                          # default_specs() looks this up dynamically
    def _boom(): raise data.LLMError("no llm")              # make _bv_narrate a no-op
    data.get_llm = _boom

    eng = _Eng()
    asyncio.run(data.business_validation(eng, ProjectState(project_id="t"), {"id": "2.3"}))
    assert eng.body is not None, "handler never produced an artifact"
    assert "specs" in eng.body, list(eng.body)
    assert any(s["l3"] == "TV" for s in eng.body["specs"]), eng.body["specs"]
    assert "groups" in eng.body                          # groups kept for the Sign-off tab
    print("OK bv specs wired:", [s["specId"] for s in eng.body["specs"]])


if __name__ == "__main__":
    main()
