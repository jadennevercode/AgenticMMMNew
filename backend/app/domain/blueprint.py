"""Workflow blueprint — the task DAG and artifact definitions.

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
    requiresMapping: bool  # block submit until every factor row is mapped or ignored
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
    # Optional structured input panel rendered inside this Process step (mirrors
    # how `decision`/`assignment` are declared). The frontend maps the id to a
    # component — e.g. "ols-y" | "ols-x" | "ols-params" for the 2.5 setup steps.
    panel: str


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
    # ── S2 · Data Intake & Validation — six artifacts, each a filter layer:
    #    Processing → Quality → Business → Statistical → OLS test → Master data
    {"id": "a-data-processing", "name": "Data Processing", "task_ref": "2.1", "type": "dataset", "stage": "s2", "lineage": ["a-data-request", "a-factor-tree"], "format": "sheet", "exportable": True},
    {"id": "a-quality-scorecard", "name": "Data Quality Score", "task_ref": "2.2", "type": "scorecard", "stage": "s2", "lineage": ["a-data-processing"], "format": "sheet", "exportable": True},
    {"id": "a-business-validation", "name": "Business Validation", "task_ref": "2.3", "type": "report", "stage": "s2", "lineage": ["a-data-processing", "a-quality-scorecard"], "format": "validation"},
    {"id": "a-stat-tests", "name": "Statistical Score", "task_ref": "2.4", "type": "scorecard", "stage": "s2", "lineage": ["a-data-processing", "a-business-validation"], "format": "sheet"},
    {"id": "a-ols-test", "name": "OLS Regression Test", "task_ref": "2.5", "type": "report", "stage": "s2", "lineage": ["a-stat-tests", "a-factor-tree", "a-knowledge-package"], "format": "olsTree"},
    {"id": "a-master-data", "name": "Master Data", "task_ref": "2.6", "type": "dataset", "stage": "s2", "lineage": ["a-data-processing", "a-quality-scorecard", "a-business-validation", "a-stat-tests", "a-ols-test"], "format": "masterData", "exportable": True},
    {"id": "a-prior-register", "name": "Prior Setting Rules", "task_ref": "3.1", "type": "document", "stage": "s4", "lineage": ["a-knowledge-package", "a-business-validation", "a-master-data"], "format": "sheet"},
    {"id": "a-model-candidates", "name": "Model Candidates", "task_ref": "3.2", "type": "model", "stage": "s4", "lineage": ["a-master-data", "a-prior-register"], "format": "sheet"},
    {"id": "a-tech-review", "name": "Technical Review", "task_ref": "3.3", "type": "report", "stage": "s4", "lineage": ["a-model-candidates"], "format": "sheet"},
    {"id": "a-model-diagnostics", "name": "Model Diagnostics", "task_ref": "3.3", "type": "report", "stage": "s4", "lineage": ["a-model-candidates"], "format": "review"},
    {"id": "a-decomp-results", "name": "Model Interpretation (5D)", "task_ref": "4.1a", "type": "report", "stage": "s5", "lineage": ["a-tech-review"], "format": "sheet"},
    {"id": "a-final-report", "name": "Final Report", "task_ref": "4.1b", "type": "report", "stage": "s5", "lineage": ["a-decomp-results"], "format": "slides"},
    {"id": "a-results-dashboard", "name": "Results Dashboard", "task_ref": "4.1a", "type": "report", "stage": "s5", "lineage": ["a-decomp-results"], "format": "review"},
]

STAGES = [
    {"id": "s1", "index": 1, "name": "Business Understanding", "goal": "Frame the project and lock factors, interviews and the data request.", "milestone": "Data request confirmed"},
    {"id": "s2", "index": 2, "name": "Data Intake & Validation", "goal": "Reference the prepared data assets, validate them layer by layer, and lock the master feature table.", "milestone": "Master data locked"},
    {"id": "s4", "index": 3, "name": "Modeling", "goal": "Set assumptions, train and pick the model.", "milestone": "Final model picked"},
    {"id": "s5", "index": 4, "name": "Reporting", "goal": "Decompose, narrate and deliver.", "milestone": "Report released"},
]

AGENTS = [
    {"id": "control", "name": "Project Control", "role": "Workflow choreography & gates", "capabilities": ["sequencing", "gates", "context sync"]},
    {"id": "business", "name": "Business Agent", "role": "Framing, factor tree, interviews, data request", "capabilities": ["scoping", "factor recall", "interview synthesis"]},
    {"id": "data", "name": "Data Agent", "role": "Quality, ETL, validation", "capabilities": ["scoring", "etl", "stat screening"]},
    {"id": "model", "name": "Model Agent", "role": "Priors, training, validation", "capabilities": ["priors", "ols mmm", "validation"]},
    {"id": "report", "name": "Report Agent", "role": "Decomposition, narrative, delivery", "capabilities": ["decomposition", "roi", "narrative"]},
]

# The task DAG. Decision/assignment/ai_options kept in sync with scenario.ts.
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
    # ── S2 · Data Intake & Validation (2.1 Processing → 2.2 Quality → 2.3 Business →
    #        2.4 Statistical → 2.5 OLS test → 2.6 Master data) ──
    {"id": "2.1", "name": "Data Processing", "agent": "data", "stage": "s2", "klass": "H",
     "summary": "Resolve the FactorTree↔DataAssets mapping: the AI proposes a published indicator for every unmatched factor, and you accept, remap or ignore each one.",
     "how": "In the Data Engine, each unresolved factor carries a ranked AI proposal — scored on name, factor path, unit and coverage — for you to accept, swap for another candidate, or ignore when no data exists. The gate clears once nothing is left unresolved; the mapped assets are then unioned into the modeling long table and the intake preview shows what each source actually contributed.",
     "basis_note": "Data Engine 已发布数据资产 + 确认版因子树映射。", "work_note": "Waiting for the FactorTree↔DataAssets mapping to be resolved (every indicator mapped or ignored).",
     "depends_on": ["1.7"], "duration": 2, "produces": ["a-data-processing"],
     "assignment": {"id": "in-2.1", "kind": "upload", "title": "Resolve the FactorTree↔DataAssets mapping",
                    "prompt": "In the Data Engine, review the AI's proposed indicator for each unmatched factor — accept it, pick another candidate, or mark the factor ignored. Data Intake & Validation starts once no indicator is left unresolved. (Projects using slot uploads instead clear the gate by per-L3 coverage.)",
                    "items": ["Mapped indicators", "Ignored indicators"], "submit_label": "Reference mapping",
                    "category": "data", "requiresUpload": True, "requiresManifest": True, "requiresMapping": True}},
    {"id": "2.2", "name": "Data Quality Score", "agent": "data", "stage": "s2", "klass": "A",
     "summary": "Every L1×L2×L3×L4×metric is scored on the four 2.11 dimensions (consistency / completeness / granularity / accuracy, each 0 / 0.5 / 1). A deterministic subcheck scorer computes the 10 subchecks from the real data; the AI reviews the four dimension scores and writes a note per dimension.",
     "how": "The subcheck scorer derives each dimension from the computed evidence; the AI confirms/adjusts the four dimension scores against the rubric. Total = product of the four dimensions (Excel 2.12); the verdict is reviewed by a human next.",
     "basis_note": "校验标准 + 数据资产证据。", "work_note": "AI 逐指标四维评分；Total = 最弱维度。",
     "depends_on": ["2.1"], "duration": 3, "produces": ["a-quality-scorecard"]},
    {"id": "2.2d", "name": "Review data quality verdicts", "agent": "data", "stage": "s2", "klass": "H",
     "panel": "quality-review",
     "summary": "Human reviews the AI scores; 1 = accept · 0 = unusable · 0.5 = human call (re-collect / drop / accept-with-caveat).",
     "how": "You review the scorecard right here: accept the 1s, drop the 0s (alert if a factor's only metrics all fail), and decide each 0.5. A drop is inherited by every later layer — the indicator is not re-scored at 2.4, not offered as a model variable at 2.5, and never reaches the master table.",
     "basis_note": "AI 质量评分 + 验收标准。", "work_note": "Awaiting human review of the data-quality verdicts.",
     "depends_on": ["2.2"], "duration": 1, "produces": [],
     "decision": {"id": "d-2.2", "kind": "choice", "title": "Review data-quality verdicts",
                  "question": "Some metrics scored 0.5 (borderline). Review the verdicts and decide how to handle them.",
                  "evidence": [{"artifactId": "a-quality-scorecard", "note": "Per-metric scores & verdicts"}, {"artifactId": "a-data-processing", "note": "Referenced data assets"}],
                  "options": [
                      {"id": "accept", "label": "Accept the verdicts", "detail": "Keep the 1s, drop the 0s, 0.5 enter flagged", "consequence": "Business validation starts on the accepted metrics", "recommended": True},
                      {"id": "recollect", "label": "Re-collect 0.5 data", "detail": "Re-prepare the borderline assets in the Data Engine", "consequence": "Intake reopens for the flagged assets; timeline slips"},
                      {"id": "drop", "label": "Drop the 0.5 metrics", "detail": "Exclude borderline metrics from this model", "consequence": "Leaner model; those factors enter via aggregate metrics only"}],
                  "rework_task_id": "2.1", "rework_option_id": "recollect"}},
    {"id": "2.3", "name": "Business Validation", "agent": "data", "stage": "s2", "klass": "C",
     "summary": "Visualized business review of the accepted data — each factor charted against sell-out, with its own reading.",
     "how": "AI charts every factor (L3) against the sell-out backdrop and writes its reading; you filter by source, sub-factor, indicator, time grain and model dimension to interrogate it.",
     "basis_note": "质量验收后的数据 + 因子树 + 行业基准。", "work_note": "Business-validation deck built.",
     "depends_on": ["2.2d"], "duration": 3, "produces": ["a-business-validation"]},
    {"id": "2.3a", "name": "Explain the anomalies", "agent": "data", "stage": "s2", "klass": "A",
     "panel": "anomaly-review",
     "summary": "One card per detected anomaly: the AI's causal hypothesis and a proposed handling; you accept, edit or reject each.",
     "how": "For every year-on-year move past ±40% the AI states the most likely business cause and proposes how to handle it. Your ruling reaches the model directly: a structural event becomes a dummy control over its window, capping winsorizes the response, raw leaves the data alone and carries a caveat into the report.",
     "basis_note": "计算出的 YoY 异常 + 访谈证据。", "work_note": "Anomaly hypothesis cards drafted for review.",
     "depends_on": ["2.3"], "duration": 2, "produces": []},
    {"id": "2.3s", "name": "Record client sign-off", "agent": "data", "stage": "s2", "klass": "H",
     "summary": "Per-factor client sign-off on the validated data — an unsigned factor cannot enter modeling.",
     "how": "You sign off each factor with the client on the chart page. Marking a factor not-signed-off excludes it and every one of its indicators from the model, inherited all the way to the master table.",
     "basis_note": "业务校验图表 + 异常处理裁决。", "work_note": "Awaiting client sign-off.",
     "depends_on": ["2.3a"], "duration": 1, "produces": [],
     "decision": {"id": "d-2.3", "kind": "signoff", "title": "Record client sign-off on data",
                  "question": "Did the client sign off the business validation? Any factor you mark not-signed-off is excluded from modeling, along with all of its indicators.",
                  "evidence": [{"artifactId": "a-business-validation"}],
                  "options": [
                      {"id": "approve", "label": "Signed off", "detail": "Client confirmed", "consequence": "Data is locked for statistical scoring", "recommended": True},
                      {"id": "rework", "label": "Not signed off", "detail": "Client raised blocking issues", "consequence": "Review is revisited"}],
                  "rework_task_id": "2.3", "rework_option_id": "rework"}},
    # The old `ai-2.3` set asked "how should anomalies be handled?" once, stored
    # the answer in `ai_choices` and never read it. 2.3a replaces it with a card
    # per anomaly whose handling actually reaches the fit.
    {"id": "2.4", "name": "Statistical Score", "agent": "data", "stage": "s2", "klass": "A",
     "summary": "Variability, correlation and collinearity tests per indicator (CV / Pearson / VIF); the combined score decides model entry. Indicators already rejected at 2.2 or 2.3 are not scored — that call is settled.",
     "how": "CV, Pearson and VIF are computed per indicator still in play and combined into an entry score; the AI then writes the case for or against each borderline indicator. Excluding the already-rejected ones is not bookkeeping — VIF is computed across the whole set, so dead indicators would inflate the collinearity of the live ones.",
     "basis_note": "统计筛选规则 + 上游裁决（2.2 质量 / 2.3 签核）。", "work_note": "CV / Pearson / VIF computed on the indicators still in play.",
     "depends_on": ["2.3s"], "duration": 2, "produces": ["a-stat-tests"]},
    {"id": "2.4d", "name": "Review statistical verdicts", "agent": "data", "stage": "s2", "klass": "H",
     "panel": "stat-review",
     "summary": "Human reviews the statistical scores and decides which borderline indicators enter the model.",
     "how": "You review the scorecard here: keep the Good band, decide each Acceptable, drop the Unconsiderable. What you drop is inherited — 2.5 will not offer it back as a model variable.",
     "basis_note": "统计得分 + AI 逐行入模建议。", "work_note": "Awaiting human review of the statistical verdicts.",
     "depends_on": ["2.4"], "duration": 1, "produces": [],
     "decision": {"id": "d-2.4", "kind": "choice", "title": "Borderline metrics into the model",
                  "question": "Some metrics scored Acceptable (1.5–3) — neither clearly in nor out. How should they enter the model?",
                  "evidence": [{"artifactId": "a-stat-tests", "note": "Acceptable-band (1.5–3) rows"}, {"artifactId": "a-quality-scorecard", "note": "Upstream quality dispositions"}],
                  "recommendation": "Keep the Acceptable-band metrics alongside the Good ones; the OLS regression test (2.5) then checks each against its ROI / contribution range.",
                  "options": [
                      {"id": "keep", "label": "Keep acceptable metrics", "detail": "Enter with the Good-band metrics", "consequence": "The OLS test checks their contribution range", "recommended": True},
                      {"id": "drop", "label": "Drop the weakest", "detail": "Keep only Good-band metrics", "consequence": "Leaner model; some factors lose a metric"},
                      {"id": "review", "label": "Review case-by-case", "detail": "Open the scorecard to decide per metric", "consequence": "Manual selection before the OLS test"}]}},
    # ── 2.5 OLS Regression Test — a five-step Process on one deliverable:
    #    propose → confirm Y → review X → confirm settings → fit & review.
    #    The AI proposes everything it can; the human confirms each input in turn.
    #    2.5y/2.5x/2.5p are human gates (no handler — the engine blocks on the
    #    decision, like 2.2d); the panels edit `ols_config`, which re-fits on save.
    {"id": "2.5", "name": "Propose model setup", "agent": "data", "stage": "s2", "klass": "A",
     "summary": "Propose the OLS setup from real data: a response candidate per model object, model variables scored on their 2.4 statistics, and default transform / control settings.",
     "how": "AI proposes the response (Y) for each model object, ranks the candidate model variables (X) on their 2.4 CV / Pearson / VIF, and pre-fills the transform and trend/seasonality settings — all for you to confirm in the next steps.",
     "basis_note": "2.4 统计得分 + 数据可用性（覆盖月数、单位）。", "work_note": "Model setup proposed for review.",
     "depends_on": ["2.4d"], "duration": 1, "produces": ["a-ols-test"]},
    {"id": "2.5y", "name": "Confirm response variable", "agent": "data", "stage": "s2", "klass": "H",
     "panel": "ols-y",
     "summary": "Pick the response (Y) each model object is fitted against — the KPI volume metric is recommended.",
     "how": "You pick the response for each model object. The KPI volume metric is recommended; choosing a money metric (or setting a unit price later) makes ROI a true incremental-revenue / spend ratio.",
     "basis_note": "各模型对象的 KPI 候选（单位 + 覆盖月数）。", "work_note": "Awaiting the response-variable confirmation.",
     "depends_on": ["2.5"], "duration": 1, "produces": [],
     "decision": {"id": "d-2.5y", "kind": "approval", "title": "Confirm the response variable",
                  "question": "The KPI volume metric is proposed as the response for each model object. Confirm it, or pick a different response above.",
                  "evidence": [{"artifactId": "a-ols-test", "note": "Response candidates per model object"}],
                  "recommendation": "The KPI volume response keeps coefficients in sales units — confirm to continue.",
                  "options": [
                      {"id": "confirm", "label": "Confirm response", "detail": "Fit against the selected response", "consequence": "Model variables are reviewed next", "recommended": True}]}},
    {"id": "2.5x", "name": "Review model variables", "agent": "data", "stage": "s2", "klass": "H",
     "panel": "ols-x",
     "summary": "Review the AI-proposed model variables (X) — each with its correlation, collinearity and 2.4 verdict — and tick the ones that enter the regression.",
     "how": "You tick the variables that enter the regression. Each carries its Pearson r vs the KPI, its VIF, its CV and its 2.4 verdict, plus the remaining degrees of freedom — this is where you drive the screening.",
     "basis_note": "2.4 统计得分 + 共线性/自由度约束。", "work_note": "Awaiting the model-variable selection.",
     "depends_on": ["2.5y"], "duration": 1, "produces": [],
     "decision": {"id": "d-2.5x", "kind": "approval", "title": "Confirm the model variables",
                  "question": "These variables will enter the regression. Confirm the selection, or tick / untick above.",
                  "evidence": [{"artifactId": "a-ols-test", "note": "Candidate variables with their 2.4 statistics"}, {"artifactId": "a-stat-tests", "note": "Statistical score"}],
                  "recommendation": "The pre-ticked variables clear the correlation and collinearity gates — confirm to continue.",
                  "options": [
                      {"id": "confirm", "label": "Confirm variables", "detail": "These variables enter the regression", "consequence": "Model settings are confirmed next", "recommended": True}]}},
    {"id": "2.5p", "name": "Confirm model settings", "agent": "data", "stage": "s2", "klass": "H",
     "panel": "ols-params",
     "summary": "Confirm the carryover / saturation transforms and the trend + seasonality controls that keep the paid coefficients honest.",
     "how": "You set the adstock carryover, the saturation curve, and the trend / seasonality controls. The controls absorb the trend and seasonal swing so the paid variables do not — this is what keeps the baseline positive and the coefficients correctly signed.",
     "basis_note": "变换与控制项设置（默认：adstock 0.5 · Hill · 线性趋势 · Fourier 季节性）。", "work_note": "Awaiting the model settings.",
     "depends_on": ["2.5x"], "duration": 1, "produces": [],
     "decision": {"id": "d-2.5p", "kind": "approval", "title": "Confirm the model settings",
                  "question": "These transforms and controls will be used for the fit. Confirm them, or adjust above.",
                  "evidence": [{"artifactId": "a-ols-test", "note": "Transform + control settings"}],
                  "recommendation": "A linear trend plus Fourier seasonality is the cheapest control that keeps the paid coefficients honest — confirm to fit.",
                  "options": [
                      {"id": "confirm", "label": "Confirm settings", "detail": "Fit with these transforms and controls", "consequence": "The regression runs", "recommended": True}]}},
    {"id": "2.5r", "name": "Run OLS & review fit", "agent": "data", "stage": "s2", "klass": "M",
     "summary": "Fit the OLS on the confirmed setup and check each variable's ROI and contribution against the knowledge-base industry ranges — far-out variables are flagged for review.",
     "how": "The regression runs on the setup you confirmed. Each variable's coefficient, t / p, ROI and contribution land on the factor tree; results outside the knowledge-base industry ranges are flagged for you to drop.",
     "basis_note": "行业经验 ROI / 贡献区间（知识库维护）+ 业务校验假设。", "work_note": "OLS fitted; ranges checked.",
     "depends_on": ["2.5p"], "duration": 2, "produces": ["a-ols-test"],
     "decision": {"id": "d-2.5", "kind": "choice", "title": "Confirm indicator selection",
                  "question": "The OLS test checked each factor's ROI / contribution against its knowledge-base range. Confirm the selection, drop the flagged indicators, or revisit the business hypotheses?",
                  "evidence": [{"artifactId": "a-ols-test", "note": "Per-factor ROI / contribution vs knowledge ranges"}, {"artifactId": "a-business-validation", "note": "Business hypotheses"}],
                  "recommendation": "Selected indicators fall within their expected ranges — confirm and assemble the master table.",
                  "options": [
                      {"id": "confirm", "label": "Confirm selection", "detail": "Selected indicators enter the master table", "consequence": "Master data is assembled for modeling", "recommended": True},
                      {"id": "drop", "label": "Drop flagged indicators", "detail": "Remove the out-of-range indicators", "consequence": "Master data is assembled without them"},
                      {"id": "rework", "label": "Revisit hypotheses", "detail": "Out-of-range factors need rethinking", "consequence": "Business validation is revisited"}],
                  "rework_task_id": "2.3", "rework_option_id": "rework"}},
    {"id": "2.6", "name": "Assemble master data", "agent": "data", "stage": "s2", "klass": "M",
     "summary": "Assemble the indicators that survived every filter layer into the master feature wide table modeling consumes — sliceable by product × channel × region.",
     "how": "The pipeline pivots the adopted indicators — the response you confirmed at 2.5y, the variables you ticked at 2.5x — into one feature wide table per model object. Every rejected indicator keeps the chain of verdicts that removed it, so the funnel is auditable end to end.",
     "basis_note": "指标生命周期账本：映射/质量/业务签核/统计/选择/区间六层裁决。", "work_note": "Master feature table assembled from the adopted indicators.",
     "depends_on": ["2.5r"], "duration": 2, "produces": ["a-master-data"]},
    {"id": "2.6d", "name": "Lock master data", "agent": "data", "stage": "s2", "klass": "H",
     "summary": "Review the assembled feature table and the filter funnel behind it, then lock it as the modeling input.",
     "how": "You slice the table by product × channel × region, check the funnel accounts for every dropped indicator, and lock it. Locking is a human act — modeling should never start on a table nobody looked at.",
     "basis_note": "Master feature 宽表 + 六层过滤漏斗。", "work_note": "Awaiting the master-data lock.",
     "depends_on": ["2.6"], "duration": 1, "produces": [],
     "decision": {"id": "d-2.6", "kind": "approval", "title": "Lock the master data",
                  "question": "Review the assembled feature table and lock it as the modeling input?",
                  "evidence": [{"artifactId": "a-master-data", "note": "Feature table + filter funnel"},
                               {"artifactId": "a-ols-test", "note": "The fit it was assembled from"}],
                  "recommendation": "The table carries only indicators that survived every filter layer — lock it to start modeling.",
                  "options": [
                      {"id": "lock", "label": "Lock master data", "detail": "Modeling trains on this table", "consequence": "Model assumptions are registered next", "recommended": True},
                      {"id": "rework", "label": "Revisit the variables", "detail": "The selection needs another pass", "consequence": "The OLS setup is revisited"}],
                  "rework_task_id": "2.5", "rework_option_id": "rework"}},
    # ── S4 ──
    {"id": "3.1", "name": "Register model assumptions", "agent": "model", "stage": "s4", "klass": "C",
     "summary": "Turn confirmed business judgments into bounded model constraints, each traced to its source.",
     "how": "AI turns each client-confirmed business judgment into a bounded model constraint, traced to source.",
     "basis_note": "知识包 + 业务校验假设。", "work_note": "Constraints registered.",
     "depends_on": ["2.6d"], "duration": 2, "produces": ["a-prior-register"],
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
