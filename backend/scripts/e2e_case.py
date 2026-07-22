"""Drive a full MMM case end to end on the restored model-input_2.32 data.

Run from backend/ with the server up:
    .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 &
    PYTHONPATH=. .venv/bin/python -m scripts.e2e_case

Everything here is a real HTTP call against the real backend — no mocks, no
seeded state. Stages are idempotent-ish: re-running creates a fresh project.

Findings (breaks in continuity, fabricated data, dead ends) are appended to
`restored/model-input-2.32/qa/e2e-findings.md` as they are hit, so the log is
evidence collected during the run rather than a recollection after it.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib import error, request

from scripts.restore import paths

BASE = "http://127.0.0.1:8010"
REPO = paths.REPO
FINDINGS: list[dict] = []


# ── tiny HTTP client (stdlib only, so the script has no new deps) ──

def _call(method: str, path: str, body: object = None, timeout: int = 600):
    url = f"{BASE}{path}"
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["content-type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:2000]
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from None


def get(p, **kw):
    return _call("GET", p, **kw)


def post(p, body=None, **kw):
    return _call("POST", p, body, **kw)


def put(p, body=None, **kw):
    return _call("PUT", p, body, **kw)


def upload(project_id: str, category: str, file_path: Path, slot: str = "") -> dict:
    """Multipart upload to POST /files, hand-rolled to stay stdlib-only."""
    boundary = "----mmme2e7f3a9c1"
    content = file_path.read_bytes()
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"category\"\r\n\r\n"
        f"{category}\r\n".encode(),
    ]
    if slot:
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"slot\"\r\n\r\n"
            f"{slot}\r\n".encode())
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{file_path.name}\"\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n".encode()
        + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = request.Request(
        f"{BASE}/api/projects/{project_id}/files", data=b"".join(parts),
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
        method="POST")
    with request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())


# ── findings log ──

def finding(stage: str, severity: str, title: str, detail: str,
            evidence: str = "") -> None:
    rec = {"stage": stage, "severity": severity, "title": title,
           "detail": detail, "evidence": evidence}
    FINDINGS.append(rec)
    print(f"  [{severity}] {stage}: {title}")


def write_findings() -> None:
    paths.mkdirs()
    order = {"BLOCKER": 0, "BREAK": 1, "FAKE-DATA": 2, "GAP": 3, "NOTE": 4}
    rows = sorted(FINDINGS, key=lambda r: (order.get(r["severity"], 9), r["stage"]))
    lines = [
        "# E2E 案例贯通记录",
        "",
        "由 `backend/scripts/e2e_case.py` 在真实跑一遍 S1→S2 的过程中记录，",
        "每条都是当场撞到的，不是事后回忆。",
        "",
        "| 级别 | 阶段 | 问题 |",
        "|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['severity']} | {r['stage']} | {r['title']} |")
    lines += ["", "---", ""]
    for r in rows:
        lines += [
            f"## [{r['severity']}] {r['stage']} — {r['title']}",
            "",
            r["detail"],
            "",
        ]
        if r["evidence"]:
            lines += ["```", r["evidence"], "```", ""]
    (paths.QA_DIR / "e2e-findings.md").write_text("\n".join(lines),
                                                  encoding="utf-8")
    print(f"\nfindings -> {paths.QA_DIR / 'e2e-findings.md'} ({len(FINDINGS)} records)")


# ── stage helpers ──

def wait_for_run(project_id: str, timeout_s: int = 1800) -> dict:
    """Poll /run/status until the run loop stops."""
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        st = get(f"/api/projects/{project_id}/run/status")
        if st != last:
            print(f"    run: {st}")
            last = st
        if not st.get("running"):
            return st
        time.sleep(3)
    raise TimeoutError(f"run did not settle within {timeout_s}s; last={last}")


def state(project_id: str) -> dict:
    return get(f"/api/projects/{project_id}/state")


def pending_gates(st: dict) -> tuple[list, list]:
    """(open upload assignments, open decisions). Both are dicts keyed by id."""
    ups = [a for a in st.get("assignments", {}).values() if a.get("status") == "open"]
    decs = [d for d in st.get("decisions", {}).values() if d.get("status") == "open"]
    return ups, decs


def task_summary(st: dict) -> dict:
    counts: dict[str, int] = {}
    for t in st.get("tasks", {}).values():
        counts[t.get("status", "?")] = counts.get(t.get("status", "?"), 0) + 1
    return counts


def recommended_option(dec: dict) -> str:
    """The option the product marks recommended, else the first."""
    opts = dec.get("options") or []
    for o in opts:
        if o.get("recommended"):
            return o["id"]
    return opts[0]["id"] if opts else "approve"


def drive(project_id: str, max_rounds: int = 60,
          decide=None, on_assignment=None) -> dict:
    """Run → clear whichever gate opened → run again, until nothing moves.

    `decide(dec) -> option_id | None` and `on_assignment(a) -> bool` let a stage
    override gate handling; returning None/False falls back to the default
    (recommended option / plain submit).
    """
    for rnd in range(1, max_rounds + 1):
        post(f"/api/projects/{project_id}/run", {"autopilot": False})
        wait_for_run(project_id)
        st = state(project_id)
        ups, decs = pending_gates(st)
        counts = task_summary(st)
        print(f"  round {rnd:2d} tasks={counts} open_uploads={[a['id'] for a in ups]} "
              f"open_decisions={[d['id'] for d in decs]}")
        if not ups and not decs:
            return st
        moved = False
        for a in ups:
            if on_assignment and on_assignment(a):
                moved = True
                continue
            body = {}
            if a.get("choiceOptions"):
                body["chosenSource"] = a["choiceOptions"][0]["id"]
            try:
                post(f"/api/projects/{project_id}/assignments/{a['id']}/submit", body)
                print(f"    submitted {a['id']} {body or ''}")
                moved = True
            except RuntimeError as exc:
                print(f"    BLOCKED  {a['id']}: {exc}")
        for d in decs:
            opt = (decide(d) if decide else None) or recommended_option(d)
            try:
                post(f"/api/projects/{project_id}/decisions/{d['id']}/resolve",
                     {"optionId": opt})
                print(f"    resolved {d['id']} -> {opt}")
                moved = True
            except RuntimeError as exc:
                print(f"    BLOCKED  {d['id']}: {exc}")
        if not moved:
            print("  no gate could be cleared — stopping")
            return st
    return state(project_id)


S1_DOC_SETS = (
    ("project_background", ("Scope",)),
    ("industry_reference", ("行业知识", "factor&data_request")),
)


def new_project(name: str) -> str:
    p = post("/api/projects", {
        "name": name, "brand": "MIZONE",
        "industry": {"l1": "food-bev", "l2": "beverage", "l3": "sports-functional"}})
    print(f"  project: {p['id']}")
    return p["id"]


def upload_s1_docs(project_id: str) -> int:
    ref = REPO / "reference" / "01.商业智能体"
    n = 0
    for category, needles in S1_DOC_SETS:
        for needle in needles:
            for f in sorted(ref.glob("*.xlsx")):
                if needle in f.name:
                    upload(project_id, category, f)
                    n += 1
    minutes = sorted((ref / "【MMM AI】商业智能提-访谈框架及纪要_1.32" / "纪要").glob("*.docx"))
    for f in minutes:
        upload(project_id, "interview_minutes", f)
        n += 1
    print(f"  uploaded {n} documents ({len(minutes)} interview transcripts)")
    return n


def register_curated_asset(project_id: str) -> str:
    """Upload the restored curated long table and publish it as a data asset.

    The curated table already lands on the target schema, so the transform is
    near-identity. That is the point: it isolates whether the *rest* of the S2
    chain (publish → indicators → factor map → scoring → OLS) is continuous,
    without the AI codegen step's failures masking a break further down.
    """
    src = paths.CURATED_DIR / "long_table.xlsx"
    if not src.exists():
        raise FileNotFoundError(
            f"{src} missing — run scripts.restore_model_input first")
    rec = upload(project_id, "data", src)
    print(f"  uploaded {src.name} ({rec['size']} bytes) file_id={rec['id']}")
    asset = post(f"/api/projects/{project_id}/data-assets", {
        "name": "Mizone model input 2.32 (restored long table)",
        "description": "23,813-row canonical long table restored from "
                       "model input_2.32.xlsx; already on the 19-column target schema.",
        "sourceFileIds": [rec["id"]]})
    aid = asset["id"]
    print(f"  asset {aid} status={asset['status']}")
    return aid


def publish_asset(project_id: str, asset_id: str, instruction: str = "") -> dict:
    """review → AI pipeline → dbt build → publish, reporting each step's outcome."""
    steps = {}
    for label, call in (
        ("review", lambda: post(f"/api/projects/{project_id}/data-assets/{asset_id}/review")),
        ("generate", lambda: post(f"/api/projects/{project_id}/data-assets/{asset_id}/dbt/generate",
                                  {"instruction": instruction})),
        ("build", lambda: post(f"/api/projects/{project_id}/data-assets/{asset_id}/dbt/build")),
        ("publish", lambda: post(f"/api/projects/{project_id}/data-assets/{asset_id}/dbt/publish")),
    ):
        try:
            call()
            steps[label] = "ok"
            print(f"    {label:9s} ok")
        except RuntimeError as exc:
            steps[label] = str(exc)[:400]
            print(f"    {label:9s} FAILED {str(exc)[:300]}")
            break
    return steps


def resolve_factor_map(project_id: str) -> dict:
    """Clear the 2.1 gate: accept every AI suggestion, ignore the rest.

    This is the human step at 2.1, executed honestly — a row is only *bound* when
    the resolver actually proposed an indicator for it. Rows with no candidate are
    *ignored* with the reason recorded, never bound to a lookalike, because an
    invented binding would put someone else's series under a factor name and no
    later gate would ever catch it.
    """
    fm = get(f"/api/projects/{project_id}/factor-map")
    bound = ignored = 0
    for row in fm.get("rows", []):
        if row["status"] != "pending":
            continue
        cand = row.get("suggestions") or []
        if cand:
            top = cand[0]
            put(f"/api/projects/{project_id}/factor-map/bind",
                {"rowId": row["rowId"],
                 "indicatorId": top.get("indicatorId") or top.get("id")})
            bound += 1
        else:
            put(f"/api/projects/{project_id}/factor-map/ignore", {
                "rowId": row["rowId"], "ignored": True,
                "note": "No published indicator covers this factor in the restored "
                        "2.32 dataset (planned-only factor)."})
            ignored += 1
    fm = get(f"/api/projects/{project_id}/factor-map")
    print(f"  factor map: bound={bound} ignored={ignored} -> "
          f"mapped={fm['mapped']} ignored={fm['ignored']} pending={fm['pending']} "
          f"complete={fm['complete']}")
    return fm


def ols_report(project_id: str) -> None:
    st = state(project_id)
    cfg = st.get("ols_config") or {}
    print(f"  ols_config: y={cfg.get('yMetric')!r} object={cfg.get('modelObject')!r} "
          f"include={len(cfg.get('include') or [])} exclude={len(cfg.get('exclude') or [])}")
    led = get(f"/api/projects/{project_id}/indicator-ledger")
    rows = led if isinstance(led, list) else led.get("rows", [])
    print(f"  ledger rows: {len(rows)}")


def main() -> int:
    print("== health")
    print(" ", get("/api/health"))
    write_findings()
    return 0


if __name__ == "__main__":
    sys.exit(main())
