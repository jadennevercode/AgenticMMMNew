"""Workflow blueprint — the 27-task DAG and 21 artifact definitions.

This is the PRODUCT DESIGN (the fixed MMM workflow), ported from
frontend/src/lib/scenario.ts + artifacts-data.ts. It is configuration, not
mock data: task structure, dependencies, human gates and option sets. The
artifact *content* and decision *recommendations* are produced at runtime by
real computation + the LLM, never hardcoded.
"""
from __future__ import annotations

from typing import Optional, TypedDict


class OptionDef(TypedDict, total=False):
    id: str
    label: str
    detail: str
    consequence: str
    recommended: bool


class DecisionDef(TypedDict, total=False):
    id: str
    kind: str
    title: str
    question: str
    evidence: list[dict]
    recommendation: str  # design-seed; LLM regenerates grounded in real artifacts
    options: list[OptionDef]
    rework_task_id: Optional[str]
    rework_option_id: Optional[str]


class AssignmentDef(TypedDict, total=False):
    id: str
    kind: str
    title: str
    prompt: str
    items: list[str]
    submit_label: str
    category: str          # Project-Folder category this upload feeds
    requiresUpload: bool   # block submit until real parsed files exist
    requiresManifest: bool # block submit until the data-request manifest validates
    choicePrompt: str      # optional source-choice gate prompt (e.g. factor-tree origin)
    choiceOptions: list[dict]      # [{id,label,detail,recommended}] the user picks from
    choiceUploadCategory: str      # category required only when the upload-option is chosen


class AiOptionSetDef(TypedDict, total=False):
    id: str
    prompt: str
    options: list[dict]


class TaskDef(TypedDict, total=False):
    id: str
    name: str
    agent: str
    stage: str
    klass: str
    summary: str
    how: str
    basis_note: str
    work_note: str
    depends_on: list[str]
    duration: int
    produces: list[str]
    decision: DecisionDef
    assignment: AssignmentDef
    ai_options: AiOptionSetDef


class ArtifactDef(TypedDict, total=False):
    id: str
    name: str
    task_ref: str
    type: str
    stage: str
    lineage: list[str]
    format: str
    internal: bool
    exportable: bool


def _approve_rework(rework_task: str) -> list[OptionDef]:
    return [
        {"id": "approve", "label": "Approve", "detail": "Confirm and continue",
         "consequence": "Next step starts", "recommended": True},
        {"id": "rework", "label": "Send back", "detail": "Needs changes",
         "consequence": "Step is redone"},
    ]


ARTIFACTS: list[ArtifactDef] = [
    {"id": "a-sow", "name": "SOW & Brief (provided)", "task_ref": "1.0a", "type": "document", "stage": "s1", "lineage": [], "format": "doc", "internal": True},
    {"id": "a-scope", "name": "Project Profile", "task_ref": "1.0", "type": "document", "stage": "s1", "lineage": ["a-sow"], "format": "sheet", "exportable": True},
    {"id": "a-source-materials", "name": "Reports & Materials (provided)", "task_ref": "1.1a", "type": "document", "stage": "s1", "lineage": ["a-scope"], "format": "doc", "internal": True},
    {"id": "a-knowledge-package", "name": "Industry Knowledge", "task_ref": "1.1", "type": "master-data", "stage": "s1", "lineage": ["a-source-materials", "a-scope"], "format": "sheet", "internal": True},
    {"id": "a-factor-tree", "name": "Factor Tree", "task_ref": "1.21", "type": "master-data", "stage": "s1", "lineage": ["a-knowledge-package", "a-source-materials"], "format": "sheet", "exportable": True},
    {"id": "a-interview", "name": "Interview", "task_ref": "1.3", "type": "document", "stage": "s1", "lineage": ["a-factor-tree", "a-scope", "a-source-materials", "a-knowledge-package"], "format": "sheet", "exportable": True},
    {"id": "a-data-request", "name": "Data Request", "task_ref": "1.5", "type": "document", "stage": "s1", "lineage": ["a-factor-tree"], "format": "sheet", "exportable": True},
    {"id": "a-bu-summary", "name": "Business Understanding Summary", "task_ref": "1.7", "type": "report", "stage": "s1", "lineage": ["a-scope", "a-factor-tree", "a-interview", "a-data-request"], "format": "doc", "exportable": True},
    {"id": "a-data-files", "name": "Collected Client Data (provided)", "task_ref": "2.0a", "type": "dataset", "stage": "s2", "lineage": ["a-data-request"], "format": "sheet", "internal": True},
    # 2.1 Data Validation — Input standard (2.11) → Output score (2.12)
    {"id": "a-validation-standard", "name": "Data Validation Standard", "task_ref": "2.11", "type": "document", "stage": "s2", "lineage": ["a-data-files"], "format": "sheet", "internal": True},
    {"id": "a-quality-scorecard", "name": "Data Quality Score", "task_ref": "2.12", "type": "scorecard", "stage": "s2", "lineage": ["a-validation-standard", "a-data-files"], "format": "sheet", "exportable": True},
    # 2.2 Data Process — schema (2.21) → processing (2.22) → dictionary (2.23) → dataset (2.24)
    {"id": "a-schema", "name": "Wide-table Schema", "task_ref": "2.21", "type": "master-data", "stage": "s2", "lineage": ["a-factor-tree", "a-quality-scorecard"], "format": "sheet", "internal": True},
    {"id": "a-data-dictionary", "name": "Data Processing (TaskLog)", "task_ref": "2.22", "type": "document", "stage": "s2", "lineage": ["a-schema", "a-quality-scorecard"], "format": "sheet"},
    {"id": "a-data-warehouse", "name": "Data Dictionary", "task_ref": "2.23", "type": "master-data", "stage": "s2", "lineage": ["a-data-dictionary"], "format": "sheet", "internal": True},
    {"id": "a-dataset", "name": "Master Dataset", "task_ref": "2.24", "type": "dataset", "stage": "s2", "lineage": ["a-data-warehouse", "a-schema"], "format": "sheet"},
    # 2.3 Data Cross-Validation — biz rules (2.31) → display+signoff (2.32) → tech (2.33) → selection (2.34)
    {"id": "a-drill-framework", "name": "Business Validation Rules & Drill-down Framework", "task_ref": "2.31", "type": "document", "stage": "s3", "lineage": ["a-dataset"], "format": "sheet", "internal": True},
    {"id": "a-trend-review", "name": "Data Review Deck", "task_ref": "2.32", "type": "report", "stage": "s3", "lineage": ["a-dataset", "a-drill-framework"], "format": "review"},
    {"id": "a-client-qa", "name": "Client Q&A Tracker", "task_ref": "2.32", "type": "workflow", "stage": "s3", "lineage": ["a-factor-tree", "a-drill-framework"], "format": "sheet"},
    {"id": "a-stat-tests", "name": "Statistical Screening Results", "task_ref": "2.33", "type": "scorecard", "stage": "s3", "lineage": ["a-dataset", "a-trend-review"], "format": "sheet"},
    {"id": "a-model-input", "name": "Model Input", "task_ref": "2.34", "type": "dataset", "stage": "s3", "lineage": ["a-dataset", "a-stat-tests"], "format": "sheet"},
    {"id": "a-prior-register", "name": "Prior Setting Rules", "task_ref": "3.1", "type": "document", "stage": "s4", "lineage": ["a-knowledge-package", "a-trend-review", "a-model-input"], "format": "sheet"},
    {"id": "a-model-candidates", "name": "Model Candidates", "task_ref": "3.2", "type": "model", "stage": "s4", "lineage": ["a-model-input", "a-prior-register"], "format": "sheet"},
    {"id": "a-tech-review", "name": "Technical Review", "task_ref": "3.3", "type": "report", "stage": "s4", "lineage": ["a-model-candidates"], "format": "sheet"},
    {"id": "a-model-diagnostics", "name": "Model Diagnostics", "task_ref": "3.3", "type": "report", "stage": "s4", "lineage": ["a-model-candidates"], "format": "review"},
    {"id": "a-decomp-results", "name": "Model Interpretation (5D)", "task_ref": "4.1a", "type": "report", "stage": "s5", "lineage": ["a-tech-review"], "format": "sheet"},
    {"id": "a-final-report", "name": "Final Report", "task_ref": "4.1b", "type": "report", "stage": "s5", "lineage": ["a-decomp-results"], "format": "slides"},
    {"id": "a-results-dashboard", "name": "Results Dashboard", "task_ref": "4.1a", "type": "report", "stage": "s5", "lineage": ["a-decomp-results"], "format": "review"},
]

STAGES = [
    {"id": "s1", "index": 1, "name": "Business Understanding", "goal": "Frame the project and lock factors, interviews and the data request.", "milestone": "Data request confirmed"},
    {"id": "s2", "index": 2, "name": "Data Intake & Quality", "goal": "Collect, score and integrate the master dataset.", "milestone": "Master dataset integrated"},
    {"id": "s3", "index": 3, "name": "Validation & Hypotheses", "goal": "Sense-check, screen and pre-fit the data.", "milestone": "Model input confirmed"},
    {"id": "s4", "index": 4, "name": "Modeling", "goal": "Set assumptions, train and pick the model.", "milestone": "Final model picked"},
    {"id": "s5", "index": 5, "name": "Reporting", "goal": "Decompose, narrate and deliver.", "milestone": "Report released"},
]

AGENTS = [
    {"id": "control", "name": "Project Control", "role": "Workflow choreography & gates", "capabilities": ["sequencing", "gates", "context sync"]},
    {"id": "business", "name": "Business Agent", "role": "Framing, factor tree, interviews, data request", "capabilities": ["scoping", "factor recall", "interview synthesis"]},
    {"id": "data", "name": "Data Agent", "role": "Quality, ETL, validation", "capabilities": ["scoring", "etl", "stat screening"]},
    {"id": "model", "name": "Model Agent", "role": "Priors, training, validation", "capabilities": ["priors", "ols mmm", "validation"]},
    {"id": "report", "name": "Report Agent", "role": "Decomposition, narrative, delivery", "capabilities": ["decomposition", "roi", "narrative"]},
]

# The 27-task DAG. Decision/assignment/ai_options ported from scenario.ts.
TASKS: list[TaskDef] = [
    # ── S1 ──
    {"id": "1.0a", "name": "Provide SOW & brief", "agent": "business", "stage": "s1", "klass": "H",
     "summary": "Upload the signed SOW and kickoff brief so the AI can frame the project profile.",
     "how": "You attach the SOW & brief; the AI reads them to extract the project profile.",
     "basis_note": "客户签署的 SOW 与立项简报。", "work_note": "Waiting for the SOW.",
     "depends_on": [], "duration": 1, "produces": ["a-sow"],
     "assignment": {"id": "in-1.0a", "kind": "upload", "title": "Provide the SOW & brief",
                    "prompt": "Upload the signed SOW and kickoff brief to the Project Folder (Project Background). The AI parses them to frame the project profile.",
                    "items": ["Mizone_MMM_SOW_signed.pdf", "Kickoff_brief.pptx"], "submit_label": "Submit SOW",
                    "category": "project_background", "requiresUpload": True}},
    {"id": "1.0", "name": "Frame project profile", "agent": "business", "stage": "s1", "klass": "C",
     "summary": "Extract brand / category / market / time window / objective from the SOW into a locked project profile.",
     "how": "AI reads the SOW and fills the profile against the hard limits; you confirm to lock.",
     "basis_note": "SOW + 立项简报。", "work_note": "Profile drafted from SOW.",
     "depends_on": ["1.0a"], "duration": 2, "produces": ["a-scope"],
     "decision": {"id": "d-1.0", "kind": "approval", "title": "Confirm & lock the project profile",
                  "question": "Does the profile match the SOW? Locking it sets the analysis granularity.",
                  "evidence": [{"artifactId": "a-scope"}, {"artifactId": "a-sow", "note": "Source SOW"}],
                  "options": [
                      {"id": "approve", "label": "Lock profile", "detail": "Lock granularity and continue", "consequence": "Factor-tree work starts", "recommended": True},
                      {"id": "rework", "label": "Send back for changes", "detail": "Adjust channels, grouping or window", "consequence": "Profile is re-framed"}],
                  "rework_task_id": "1.0", "rework_option_id": "rework"}},
    {"id": "1.1a", "name": "Upload reports & materials", "agent": "business", "stage": "s1", "klass": "H",
     "summary": "Provide brand/competitor reports and internal materials, and choose how the factor-tree baseline is built.",
     "how": "You upload reports; AI mines them. You also choose: start from the industry template, or upload your own factor tree for AI to supplement.",
     "basis_note": "品牌财报、竞品研究、内部资料。", "work_note": "Waiting for materials.",
     "depends_on": ["1.0"], "duration": 1, "produces": ["a-source-materials"],
     "assignment": {"id": "in-1.1a", "kind": "upload", "title": "Upload reports & materials",
                    "prompt": "Upload brand & competitor reports and internal materials to the Project Folder (Industry Reference). The AI mines them into the factor tree.",
                    "items": ["202408_Competitor_Benchmark.pdf", "Mizone_brand_review.pptx"], "submit_label": "Submit materials",
                    "category": "industry_reference", "requiresUpload": True,
                    "choicePrompt": "How should the factor-tree baseline be built?",
                    "choiceOptions": [
                        {"id": "template", "label": "Start from industry template",
                         "detail": "AI derives L3/L4 on the standard industry factor-tree skeleton.", "recommended": True},
                        {"id": "upload", "label": "Upload my own factor tree",
                         "detail": "AI supplements your uploaded tree from the industry template + your materials."}],
                    "choiceUploadCategory": "factor_tree"}},
    {"id": "1.1", "name": "Assemble industry knowledge", "agent": "business", "stage": "s1", "klass": "C",
     "summary": "Recall the applicable industry knowledge (L1/L2 skeleton + brand analysis framework) for the beverage category.",
     "how": "AI assembles the industry-knowledge package the factor tree is derived on.",
     "basis_note": "行业知识库（饮料 / 功能饮料包）。", "work_note": "知识包成形：L1/L2 行业骨架 + 品牌生意分析框架。",
     "depends_on": ["1.1a"], "duration": 2, "produces": ["a-knowledge-package"]},
    {"id": "1.21", "name": "Derive factor tree & indicators", "agent": "business", "stage": "s1", "klass": "C",
     "summary": "Derive L3/L4 on the locked L1/L2 skeleton and map each L4 to candidate indicators with 3-axis scores.",
     "how": "AI derives L3/L4 from the knowledge package + reports, then proposes indicators per L4.",
     "basis_note": "知识包 + 上传报告 + L1/L2 骨架（锁定）。", "work_note": "L3/L4 + 候选指标 + 三轴打分。",
     "depends_on": ["1.1"], "duration": 3, "produces": ["a-factor-tree"],
     "ai_options": {"id": "ai-1.21", "prompt": "指标选型的整体取向", "options": [
         {"id": "conservative", "label": "Conservative 谨慎", "rationale": "只用高质量、已验证、口径稳定的指标", "tradeoff": "覆盖收窄"},
         {"id": "balanced", "label": "Balanced 平衡", "rationale": "质量与覆盖兼顾", "tradeoff": "少量指标可解释性中等", "recommended": True},
         {"id": "aggressive", "label": "Aggressive 激进", "rationale": "尽量广覆盖", "tradeoff": "噪声与共线性风险上升"}]}},
    {"id": "1.21d", "name": "Confirm factor tree", "agent": "business", "stage": "s1", "klass": "H",
     "summary": "Accept/adjust the derived L3/L4 and pick the primary indicator per L4; L1/L2 locked.",
     "how": "You accept/adjust L3/L4 and the primary indicator per L4, then lock the baseline.",
     "work_note": "Awaiting confirmation of the L3/L4 + indicator selection.",
     "depends_on": ["1.21"], "duration": 1, "produces": [],
     "decision": {"id": "d-1.21", "kind": "approval", "title": "Confirm the factor tree",
                  "question": "Confirm the derived L3/L4 and the primary indicator per L4? L1/L2 stay locked.",
                  "evidence": [{"artifactId": "a-factor-tree"}, {"artifactId": "a-knowledge-package", "note": "Derivation basis"}],
                  "options": [
                      {"id": "approve", "label": "Confirm factor tree", "detail": "Baseline L1–L4 + indicators", "consequence": "Interview outline is drafted next", "recommended": True},
                      {"id": "rework", "label": "Re-derive", "detail": "The tree missed something", "consequence": "AI re-derives"}],
                  "rework_task_id": "1.21", "rework_option_id": "rework"}},
    {"id": "1.3", "name": "Draft interview outline", "agent": "business", "stage": "s1", "klass": "A",
     "summary": "Generate a structured interview outline by interviewee layer (GM / Mgmt / Operation) from the confirmed factor tree.",
     "how": "AI drafts one question set per role; each question is tagged to the factor it probes.",
     "basis_note": "确认版因子树 + 访谈框架。", "work_note": "分层提纲已生成。",
     "depends_on": ["1.21d"], "duration": 2, "produces": ["a-interview"]},
    {"id": "1.3b", "name": "AI pre-answers the outline", "agent": "business", "stage": "s1", "klass": "C",
     "summary": "Before the interviews, AI drafts a preliminary answer to each question from what it already knows.",
     "how": "AI answers each outline question up front with a confidence and source, so interviews focus on gaps.",
     "basis_note": "项目档案 + 竞品/品牌报告 + 行业知识 + 因子树。", "work_note": "AI 预答已生成。",
     "depends_on": ["1.3"], "duration": 2, "produces": []},
    {"id": "1.4a", "name": "Upload interview recordings", "agent": "business", "stage": "s1", "klass": "H",
     "summary": "Upload the interview recordings (audio) — or text minutes — for the AI to digest.",
     "how": "You upload audio recordings (or text minutes); AI transcribes audio, then digests against its pre-answers.",
     "basis_note": "分层访谈录音 / 纪要。", "work_note": "Waiting for the recordings.",
     "depends_on": ["1.3b"], "duration": 1, "produces": [],
     "assignment": {"id": "in-1.4a", "kind": "upload", "title": "Upload interview recordings",
                    "prompt": "After the interviews, upload the recordings (.mp3 / .wav / .m4a) — or text minutes (.docx / .md / .txt) — to the Project Folder (Interview Minutes). Audio is transcribed automatically by the ASR step before the AI digests it.",
                    "items": ["Layer1_GM.m4a", "Layer3_Media.mp3", "Layer3_SIA.wav", "+9 more"], "submit_label": "Submit recordings",
                    "category": "interview_minutes", "requiresUpload": True}},
    {"id": "1.4b", "name": "Transcribe interview audio (ASR)", "agent": "business", "stage": "s1", "klass": "M",
     "summary": "Transcribe uploaded interview audio to text via the project's ASR model.",
     "how": "The ASR model transcribes each audio recording into a text transcript the AI can digest. Text uploads pass straight through.",
     "basis_note": "访谈录音 → ASR。", "work_note": "录音转写为文字。",
     "depends_on": ["1.4a"], "duration": 1, "produces": []},
    {"id": "1.4", "name": "AI writeback from minutes", "agent": "business", "stage": "s1", "klass": "C",
     "summary": "Digest the minutes into business insights and proposed Factor-Tree changes, each traced to a quote.",
     "how": "AI structures the minutes into insight items and derives factor-tree change suggestions with their source quote.",
     "basis_note": "访谈纪要 + AI 预答 + 确认版因子树。", "work_note": "业务洞察 + Factor 回写建议。",
     "depends_on": ["1.4b"], "duration": 2, "produces": []},
    {"id": "1.4d", "name": "Confirm interview-driven factor changes", "agent": "business", "stage": "s1", "klass": "H",
     "summary": "Review the AI's proposed Factor-Tree changes from the interviews; accepted ones write back.",
     "how": "You confirm each interview-driven change; accepting writes it back into the Factor Tree.",
     "work_note": "Awaiting confirmation of interview-driven changes.",
     "depends_on": ["1.4"], "duration": 1, "produces": [],
     "decision": {"id": "d-1.4", "kind": "approval", "title": "Confirm interview-driven factor-tree changes",
                  "question": "The interviews suggest factor-tree changes. Accept them into the tree?",
                  "evidence": [{"artifactId": "a-interview", "note": "AI 回写建议"}, {"artifactId": "a-factor-tree", "note": "Target tree"}],
                  "options": [
                      {"id": "approve", "label": "Accept changes", "detail": "Write back into the factor tree", "consequence": "Data request is generated next", "recommended": True},
                      {"id": "rework", "label": "Re-digest", "detail": "Missed or misread the minutes", "consequence": "AI re-digests"}],
                  "rework_task_id": "1.4", "rework_option_id": "rework"}},
    {"id": "1.5", "name": "Data request", "agent": "business", "stage": "s1", "klass": "A",
     "summary": "Lay out the data-request collection templates: one Excel workbook per L3, one sheet per L4.",
     "how": "AI lays out the data-request workbook (granularity columns, definitions, example rows) per L3/L4 from the confirmed factor tree.",
     "basis_note": "入选指标 + 数据源标准。", "work_note": "L3 模板生成（每个 L3 一个工作簿，每个 L4 一个 sheet）。",
     "depends_on": ["1.4d"], "duration": 2, "produces": ["a-data-request"]},
    {"id": "1.5d", "name": "Confirm data request", "agent": "business", "stage": "s1", "klass": "H",
     "summary": "Review the data request and confirm fields, granularity and owners — this closes Business Understanding.",
     "how": "You review the request workbook, then sign off so data intake can begin.",
     "work_note": "Awaiting data-request sign-off.",
     "depends_on": ["1.5"], "duration": 1, "produces": [],
     "decision": {"id": "d-1.5", "kind": "signoff", "title": "Confirm the data request",
                  "question": "Did the client sign off the data request (fields, granularity, owners)?",
                  "evidence": [{"artifactId": "a-data-request"}, {"artifactId": "a-factor-tree", "note": "Coverage"}],
                  "options": [
                      {"id": "approve", "label": "Signed off", "detail": "Client confirmed the request", "consequence": "Close Business Understanding; data intake begins", "recommended": True},
                      {"id": "rework", "label": "Needs changes", "detail": "Client flagged gaps", "consequence": "Data request is revised"}],
                  "rework_task_id": "1.5", "rework_option_id": "rework"}},
    {"id": "1.7", "name": "Business Understanding summary", "agent": "business", "stage": "s1", "klass": "C",
     "summary": "Synthesize the profile, factor tree, interview outcomes and the data request into one recap that closes Business Understanding.",
     "how": "AI assembles the BU summary from the confirmed S1 deliverables.",
     "basis_note": "All confirmed S1 deliverables.", "work_note": "BU summary assembled.",
     "depends_on": ["1.5d"], "duration": 1, "produces": ["a-bu-summary"]},
    # ── S2 · Data Intake & Quality (2.1 Validation + 2.2 Process) ──
    {"id": "2.0a", "name": "Collect client data", "agent": "data", "stage": "s2", "klass": "H",
     "summary": "Provide the filled data-request workbooks returned by the client teams — one workbook per L3 slot.",
     "how": "You upload each L3 workbook to the Project Folder (Data); the gate clears once every required L3 slot validates against the factor tree.",
     "basis_note": "客户回填的数据需求工作簿（按 L3 slot）。", "work_note": "Waiting for the data files. Per-L3 coverage is validated before intake closes.",
     "depends_on": ["1.7"], "duration": 1, "produces": ["a-data-files"],
     "assignment": {"id": "in-2.0a", "kind": "upload", "title": "Collect client data (per-L3 slot)",
                    "prompt": "按数据需求清单逐个 L3 上传客户回填工作簿到 Project Folder (Data)。系统按因子树校验每个 L3 的 L4/指标覆盖度，全部覆盖后方可进入数据校验。",
                    "items": ["Media_spend.xlsx", "Nielsen_offtake.xlsx", "+35 more"], "submit_label": "Submit data files",
                    "category": "data", "requiresUpload": True, "requiresManifest": True}},
    # 2.1 Data Validation — standard (loaded) → AI score → human review
    {"id": "2.11", "name": "Data validation standard", "agent": "data", "stage": "s2", "klass": "M",
     "summary": "Load the EXISTING general validation standard: the four-rule compliance principles and the 0 / 0.5 / 1 scoring rubric (not AI-authored).",
     "how": "The standard is loaded verbatim from the reference rule library (the two 2.11 sheets); it grounds the AI scoring that follows.",
     "basis_note": "数据通用校验标准 + 打分规则（reference 2.11 sheets）。", "work_note": "四大校验规则 + 0/0.5/1 打分细则已载入。",
     "depends_on": ["2.0a"], "duration": 1, "produces": ["a-validation-standard"]},
    {"id": "2.12", "name": "AI scores data quality", "agent": "data", "stage": "s2", "klass": "A",
     "summary": "The AI scores every L1×L2×L3×L4×metric on the four dimensions (一致性/完整性/颗粒度/真实性, each 0 / 0.5 / 1) with a 情况 note, grounded in the rubric + computed evidence.",
     "how": "AI applies the loaded rubric to the computed data evidence, assigning each dimension 0 / 0.5 / 1 and writing the 情况; the verdict (weakest dimension) is reviewed by a human next.",
     "basis_note": "校验标准 + 回填数据证据。", "work_note": "AI 逐指标四维评分 + 情况；Total = 最弱维度。",
     "depends_on": ["2.11"], "duration": 3, "produces": ["a-quality-scorecard"]},
    {"id": "2.13", "name": "Review data quality verdicts", "agent": "data", "stage": "s2", "klass": "H",
     "summary": "Human reviews the AI scores; Final = 完整性+颗粒度+真实性+一致性 → 1 验收 · 0 不可用 · 0.5 人决策 (re-collect / drop / accept-with-caveat).",
     "how": "You review the scorecard: accept the 1s, drop the 0s (alert if a factor's only metrics all fail), and decide each 0.5.",
     "basis_note": "AI 质量评分 + 验收标准。", "work_note": "Awaiting human review of the data-quality verdicts.",
     "depends_on": ["2.12"], "duration": 1, "produces": [],
     "decision": {"id": "d-2.13", "kind": "choice", "title": "Review data-quality verdicts",
                  "question": "Some metrics scored 0.5 (borderline). Review the verdicts and decide how to handle them.",
                  "evidence": [{"artifactId": "a-quality-scorecard", "note": "Per-metric scores & verdicts"}, {"artifactId": "a-validation-standard", "note": "Acceptance standard"}],
                  "options": [
                      {"id": "accept", "label": "Accept the verdicts", "detail": "Keep the 1s, drop the 0s, 0.5 enter flagged", "consequence": "Schema & processing start on the accepted metrics", "recommended": True},
                      {"id": "recollect", "label": "Re-collect 0.5 data", "detail": "Ask the client to re-upload the borderline metrics", "consequence": "Intake reopens for the flagged L3s; timeline slips"},
                      {"id": "drop", "label": "Drop the 0.5 metrics", "detail": "Exclude borderline metrics from this model", "consequence": "Leaner model; those factors enter via aggregate metrics only"}],
                  "rework_task_id": "2.0a", "rework_option_id": "recollect"}},
    # 2.2 Data Process
    {"id": "2.21", "name": "Define wide-table schema", "agent": "data", "stage": "s2", "klass": "C",
     "summary": "Define the unified long-table schema from the factor tree: model + time granularity, factor L1–L4, deep-dive L5–L8, metric type / unit.",
     "how": "AI derives the long-table column contract from the confirmed factor tree (因子树即数据 Schema); every data task outputs to this shape.",
     "basis_note": "因子树 L1–L8 + 模型/时间颗粒度 + 指标类型。", "work_note": "统一长表 Schema 成形（L1–L8 → 列）。",
     "depends_on": ["2.13"], "duration": 2, "produces": ["a-schema"]},
    {"id": "2.22", "name": "Confirm processing logic per source", "agent": "data", "stage": "s2", "klass": "A",
     "summary": "AI drafts mapping/transform logic for each data task (TaskLog); owners check before the pipeline runs.",
     "how": "AI drafts the column-level mapping/transform logic for each source task; two owners cross-check.",
     "basis_note": "宽表 Schema + 回填数据。", "work_note": "Processing logic drafted; two-person cross-check logged.",
     "depends_on": ["2.21"], "duration": 3, "produces": ["a-data-dictionary"],
     "decision": {"id": "d-2.22", "kind": "approval", "title": "Confirm processing logic",
                  "question": "AI drafted the column-level mapping/transform logic per source and two owners cross-checked. Confirm before the integration pipeline runs?",
                  "evidence": [{"artifactId": "a-data-dictionary", "note": "Per-source processing logic"}, {"artifactId": "a-schema", "note": "Target schema"}],
                  "recommendation": "Two-person cross-check logged with no open issues — safe to confirm and run the pipeline.",
                  "options": [
                      {"id": "approve", "label": "Confirm logic", "detail": "Owners signed off", "consequence": "Data dictionary is registered, then the pipeline integrates", "recommended": True},
                      {"id": "rework", "label": "Request changes", "detail": "A source's mapping/transform needs fixing", "consequence": "Processing logic is redrafted"}],
                  "rework_task_id": "2.22", "rework_option_id": "rework"}},
    {"id": "2.23", "name": "Register data dictionary", "agent": "data", "stage": "s2", "klass": "C",
     "summary": "Register the ODS→DW metadata: per source table, column-level ETL (Hardcode / Mapping / Transform / Calculation), and the master-data mappings.",
     "how": "AI registers the confirmed processing logic into the data dictionary that the integration pipeline reads.",
     "basis_note": "确认版处理逻辑 + 主数据 mapping。", "work_note": "数据字典登记完成（列级 ETL 四类）。",
     "depends_on": ["2.22"], "duration": 2, "produces": ["a-data-warehouse"]},
    {"id": "2.24", "name": "Integrate the master dataset", "agent": "data", "stage": "s2", "klass": "M",
     "summary": "Run the pipeline: one long table on the 2.21 schema, keyed by brand × region × channel × month × factor levels.",
     "how": "The pipeline cleans master data and integrates everything into one long table on the unified schema.",
     "basis_note": "数据字典 + 宽表 Schema。", "work_note": "Rows integrated on the unified schema; master-data cleaning applied.",
     "depends_on": ["2.23"], "duration": 3, "produces": ["a-dataset"]},
    # ── S3 · Validation & Hypotheses (2.3 Data Cross-Validation) ──
    {"id": "2.31", "name": "Business validation rules & drill-down", "agent": "data", "stage": "s3", "klass": "C",
     "summary": "Lay out the six-step business-validation rules and the L5–L8 drill-down map that anomaly localization runs on.",
     "how": "AI assembles the business-validation rules (六步法) and the per-L4 drill-down configuration grounded in the factor tree.",
     "basis_note": "宽表数据集 + 行业基准 + 因子下钻维度。", "work_note": "业务校验规则 + L5–L8 下钻框架成形。",
     "depends_on": ["2.24"], "duration": 2, "produces": ["a-drill-framework"],
     "ai_options": {"id": "ai-2.31", "prompt": "异常怎么处理？", "options": [
         {"id": "event", "label": "Structural-event marker", "rationale": "与访谈一致，避免误归因到营销", "tradeoff": "需客户确认事件时段", "recommended": True},
         {"id": "cap", "label": "Outlier capping", "rationale": "快速稳健", "tradeoff": "可能抹掉真实业务增长"},
         {"id": "raw", "label": "Leave raw + caveat", "rationale": "保留真实数据", "tradeoff": "模型可能高估线上营销 ROI"}]}},
    {"id": "2.32", "name": "Data review & client sign-off", "agent": "data", "stage": "s3", "klass": "C",
     "summary": "Charting + trend interpretation deck (per-page Y/N sign-off) plus the data & metric Q&A tracker; every chart needs sign-off before modeling.",
     "how": "AI runs the six-step review into a deck and a client Q&A tracker; you walk the client through it and record their sign-off.",
     "basis_note": "业务校验规则 + 宽表数据集。", "work_note": "Review deck + Q&A built. Awaiting client sign-off.",
     "depends_on": ["2.31"], "duration": 3, "produces": ["a-trend-review", "a-client-qa"],
     "decision": {"id": "d-2.32", "kind": "signoff", "title": "Record client sign-off on data",
                  "question": "Did the client sign off the data review? Unsigned charts cannot enter modeling.",
                  "evidence": [{"artifactId": "a-trend-review"}, {"artifactId": "a-client-qa", "note": "Open questions"}],
                  "options": [
                      {"id": "approve", "label": "Signed off", "detail": "Client confirmed", "consequence": "Data is locked for modeling", "recommended": True},
                      {"id": "rework", "label": "Not signed off", "detail": "Client raised blocking issues", "consequence": "Review is revisited"}],
                  "rework_task_id": "2.32", "rework_option_id": "rework"}},
    {"id": "2.33", "name": "Statistical screening", "agent": "data", "stage": "s3", "klass": "M",
     "summary": "Variability, correlation and collinearity tests per metric; combined score decides model entry.",
     "how": "CV, Pearson and VIF are computed per metric and combined into an entry score.",
     "basis_note": "统计筛选规则。", "work_note": "CV / Pearson / VIF computed.",
     "depends_on": ["2.32"], "duration": 2, "produces": ["a-stat-tests"],
     "decision": {"id": "d-2.33", "kind": "choice", "title": "Borderline metrics into the model",
                  "question": "Some metrics scored Acceptable (1.5–3) — neither clearly in nor out. How should they enter the model?",
                  "evidence": [{"artifactId": "a-stat-tests", "note": "Acceptable-band (1.5–3) rows"}, {"artifactId": "a-quality-scorecard", "note": "Upstream quality dispositions"}],
                  "recommendation": "Keep the Acceptable-band metrics alongside the Good ones; the pre-fit (2.34) then checks each against its contribution/ROI range.",
                  "options": [
                      {"id": "keep", "label": "Keep acceptable metrics", "detail": "Enter with the Good-band metrics", "consequence": "Pre-fit checks their contribution range", "recommended": True},
                      {"id": "drop", "label": "Drop the weakest", "detail": "Keep only Good-band metrics", "consequence": "Leaner model; some factors lose a metric"},
                      {"id": "review", "label": "Review case-by-case", "detail": "Open the scorecard to decide per metric", "consequence": "Manual selection before pre-fit"}]}},
    {"id": "2.34", "name": "Quick pre-fit check", "agent": "data", "stage": "s3", "klass": "C",
     "summary": "Fast linear fit to verify each factor lands in a believable contribution and ROI range before full modeling.",
     "how": "A fast OLS fit checks each factor lands in a believable range before the full model is built.",
     "basis_note": "行业弹性范围 + 业务校验假设。", "work_note": "Pre-fit run; ranges checked.",
     "depends_on": ["2.33"], "duration": 2, "produces": ["a-model-input"],
     "decision": {"id": "d-2.34", "kind": "choice", "title": "Confirm metric selection",
                  "question": "Pre-fit checked each L4 factor's selected metric against its contribution / ROI range. Confirm the selection, or revisit the business hypotheses?",
                  "evidence": [{"artifactId": "a-model-input", "note": "指标筛选 sheet"}, {"artifactId": "a-trend-review", "note": "Business hypotheses"}],
                  "recommendation": "Selected metrics fall within their expected ranges — confirm and proceed to modeling.",
                  "options": [
                      {"id": "confirm", "label": "Confirm selection", "detail": "Selected metrics enter the model", "consequence": "Model Input is locked for training", "recommended": True},
                      {"id": "rework", "label": "Revisit hypotheses", "detail": "Out-of-range factors need rethinking", "consequence": "Business sense-check is revisited"}],
                  "rework_task_id": "2.31", "rework_option_id": "rework"},
     "ai_options": {"id": "ai-2.34", "prompt": "预拟合里季节性怎么建模？", "options": [
         {"id": "prophet", "label": "Prophet seasonality", "rationale": "自动捕捉年节与旺季", "tradeoff": "可解释性略低", "recommended": True},
         {"id": "dummies", "label": "Monthly dummies", "rationale": "透明可控", "tradeoff": "自由度消耗多"},
         {"id": "none", "label": "None", "rationale": "最简", "tradeoff": "旺季信号会漏入媒体项"}]}},
    # ── S4 ──
    {"id": "3.1", "name": "Register model assumptions", "agent": "model", "stage": "s4", "klass": "C",
     "summary": "Turn confirmed business judgments into bounded model constraints, each traced to its source.",
     "how": "AI turns each client-confirmed business judgment into a bounded model constraint, traced to source.",
     "basis_note": "知识包 + 业务校验假设。", "work_note": "Constraints registered.",
     "depends_on": ["2.34"], "duration": 2, "produces": ["a-prior-register"],
     "decision": {"id": "d-3.1", "kind": "approval", "title": "Confirm model assumptions",
                  "question": "Each constraint traces to a client-confirmed judgment. Confirm the set before training?",
                  "evidence": [{"artifactId": "a-prior-register"}, {"artifactId": "a-knowledge-package", "note": "Source judgments"}],
                  "options": [
                      {"id": "approve", "label": "Confirm assumptions", "detail": "Training uses these bounds", "consequence": "Results checked against this register", "recommended": True},
                      {"id": "rework", "label": "Revise first", "detail": "A constraint needs rewording", "consequence": "Register is redrafted"}],
                  "rework_task_id": "3.1", "rework_option_id": "rework"}},
    {"id": "3.2", "name": "Train & tune models", "agent": "model", "stage": "s4", "klass": "M",
     "summary": "Training per model object (channel × region group); convergence checked every round.",
     "how": "Models train per model object; 3 candidates are kept per object.",
     "work_note": "Model objects trained; candidates kept per object.",
     "depends_on": ["3.1"], "duration": 5, "produces": ["a-model-candidates"]},
    {"id": "3.3", "name": "Technical review", "agent": "model", "stage": "s4", "klass": "C",
     "summary": "Cross-check R² / error rate / residual health per candidate; any negative baseline stops the line.",
     "how": "Each candidate is cross-checked on R² / error / residual health; a negative baseline is a hard stop.",
     "basis_note": "技术检验基准（R² 85–95% · MAPE 5–15% · DW 1.5–2.5）。", "work_note": "Candidates cross-checked.",
     "depends_on": ["3.2"], "duration": 2, "produces": ["a-tech-review", "a-model-diagnostics"]},
    {"id": "3.4", "name": "Business review & model pick", "agent": "business", "stage": "s4", "klass": "H",
     "summary": "Check results against the assumption register; a person picks the final model.",
     "how": "You compare the technically-passing candidates against the confirmed assumptions and pick the model.",
     "work_note": "Candidates compared against the register. Awaiting the final pick.",
     "depends_on": ["3.3"], "duration": 1, "produces": [],
     "decision": {"id": "d-3.4", "kind": "choice", "title": "Pick the final model",
                  "question": "Candidates passed the technical review. Pick the one to deliver — priority: ① fits business judgments ② plausible decomposition ③ statistical fit.",
                  "evidence": [{"artifactId": "a-tech-review"}, {"artifactId": "a-model-candidates"}, {"artifactId": "a-prior-register", "note": "Confirmed bounds"}],
                  "options": [
                      {"id": "cand-a", "label": "Candidate A", "detail": "Best raw fit", "consequence": "May need a baseline exception"},
                      {"id": "cand-b", "label": "Candidate B", "detail": "Bounds respected", "consequence": "Proceeds straight to reporting", "recommended": True},
                      {"id": "cand-c", "label": "Candidate C", "detail": "Media share looks inflated", "consequence": "Media ROI claims need caveats"}]}},
    # ── S5 ──
    {"id": "4.1a", "name": "Build report tables & charts", "agent": "report", "stage": "s5", "klass": "M",
     "summary": "Decomposition, contribution, growth attribution and ROI views per channel from the picked model.",
     "how": "AI builds the decomposition, contribution and ROI views per channel from the picked model.",
     "work_note": "Chart books built from the picked model.",
     "depends_on": ["3.4"], "duration": 3, "produces": ["a-decomp-results", "a-results-dashboard"]},
    {"id": "4.1b", "name": "Write the narrative", "agent": "report", "stage": "s5", "klass": "A",
     "summary": "AI drafts the reading for every chart following the house style; reviewers polish.",
     "how": "AI drafts the reading for each chart in the house style; reviewers polish the wording.",
     "basis_note": "报告解读话术模板。", "work_note": "Narrative drafted per template.",
     "depends_on": ["4.1a"], "duration": 2, "produces": ["a-final-report"],
     "ai_options": {"id": "ai-4.1b", "prompt": "报告叙述风格？", "options": [
         {"id": "exec", "label": "Executive concise", "rationale": "决策者友好，结论先行", "tradeoff": "细节需放附录", "recommended": True},
         {"id": "detailed", "label": "Detailed", "rationale": "完整论证链", "tradeoff": "篇幅长"},
         {"id": "data", "label": "Data-heavy", "rationale": "图表与数字驱动", "tradeoff": "可读性下降"}]}},
    {"id": "4.1c", "name": "Review & deliver", "agent": "report", "stage": "s5", "klass": "H",
     "summary": "Final read-through, then deliver to the client.",
     "how": "You do a final read-through and release the report to the client.",
     "work_note": "Awaiting release decision.",
     "depends_on": ["4.1b"], "duration": 1, "produces": [],
     "decision": {"id": "d-4.1", "kind": "approval", "title": "Release the final report",
                  "question": "Release the report to the client? Every factor-tree question should map to at least one chart.",
                  "evidence": [{"artifactId": "a-final-report"}, {"artifactId": "a-factor-tree", "note": "Coverage check"}],
                  "options": [
                      {"id": "approve", "label": "Release", "detail": "Deliver to the client", "consequence": "Project moves to wrap-up", "recommended": True},
                      {"id": "rework", "label": "Hold for edits", "detail": "Narrative needs changes", "consequence": "Report goes back for rewriting"}]}},
]

TASK_MAP: dict[str, TaskDef] = {t["id"]: t for t in TASKS}
ARTIFACT_MAP: dict[str, ArtifactDef] = {a["id"]: a for a in ARTIFACTS}


def downstream_of(task_id: str) -> set[str]:
    result: set[str] = set()

    def visit(tid: str) -> None:
        for t in TASKS:
            if tid in t.get("depends_on", []) and t["id"] not in result:
                result.add(t["id"])
                visit(t["id"])

    visit(task_id)
    return result
