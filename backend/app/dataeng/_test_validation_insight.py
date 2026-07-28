"""Run: PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_insight.py"""
import asyncio


def main() -> None:
    import app.dataeng.validation_insight as vi

    class _LLM:
        async def json(self, system, user):
            assert "aggregated" in user.lower() or "rows" in user.lower()
            return {"insight": "TV spend leads sell-out with a one-month lag."}

    vi.get_llm = lambda: _LLM()
    out = asyncio.run(vi.generate_insight(
        {"title": "TV", "encoding": {"x": "period", "yOverlay": ["花费"]}},
        [{"period": "2025-01", "花费": 200, "value_yoy": 30.0}],
    ))
    assert "TV spend" in out, out

    # LLM failure → empty string, never raises.
    def _boom():
        raise vi.LLMError("no key")
    vi.get_llm = _boom
    assert asyncio.run(vi.generate_insight({"title": "x"}, [])) == ""
    print("OK validation_insight")


if __name__ == "__main__":
    main()
