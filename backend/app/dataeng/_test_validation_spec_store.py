"""Run: PYTHONPATH=. .venv/bin/python app/dataeng/_test_validation_spec_store.py"""
from app.store.state import ProjectState


def main() -> None:
    st = ProjectState(project_id="t")
    assert st.validation_specs == {}, st.validation_specs

    st.validation_specs = {"specs": [{"specId": "factor::TV"}], "version": 1}
    dumped = st.model_dump()
    # No alias: the key is snake_case in the dump the frontend reads off /state.
    assert "validation_specs" in dumped, list(dumped)[:20]
    assert dumped["validation_specs"]["version"] == 1
    print("OK validation_spec_store")


if __name__ == "__main__":
    main()
