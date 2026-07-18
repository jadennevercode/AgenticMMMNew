"""Wire every producing task to its handler."""
from __future__ import annotations

from app.agents import business, data, ledger, model, report, uploads
from app.orchestrator.engine import Engine


def build_engine() -> Engine:
    eng = Engine()
    # S1 — uploads + business
    eng.register("1.0a", uploads.provide_sow)
    eng.register("1.0", business.frame_profile)
    eng.register("1.1a", uploads.provide_materials)
    eng.register("1.1", business.assemble_knowledge)
    eng.register("1.21", business.derive_factor_tree)
    eng.register("1.3", business.draft_interview)
    eng.register("1.3b", business.pre_answer)
    eng.register("1.4b", business.transcribe_audio)
    eng.register("1.4", business.writeback_minutes)
    eng.register("1.5", business.gen_data_request)
    eng.register("1.7", business.bu_summary)
    # S2 — Data Intake & Validation (six artifacts, each a filter layer)
    eng.register("2.1", data.data_processing)        # Data Processing: assets + factor-tree mapping
    eng.register("2.2", data.score_data)             # Data Quality Score
    eng.register("2.3", data.business_validation)    # Business Validation deck
    eng.register("2.3a", data.review_anomalies)      # Anomaly hypothesis cards
    # 2.3s is a human sign-off gate — no handler (cf. 2.2d).
    eng.register("2.4", data.stat_screening)         # Statistical Score
    eng.register("2.5", data.propose_ols_setup)      # OLS setup proposal (Y / X / params)
    # 2.5y / 2.5x / 2.5p are human gates — no handler; the engine blocks on their
    # decision and the step's panel edits `ols_config` (cf. 2.2d).
    eng.register("2.5r", data.ols_regression_test)   # OLS fit vs knowledge ranges
    eng.register("2.6", data.assemble_master_data)   # Master Data feature wide table
    # d-2.5 freezes its dropped indicators onto the resolution, so a later re-fit
    # (which no longer flags them, having excluded them) cannot revive them.
    eng.register_decision("d-2.5", ledger.freeze_range_drops)
    # S4 — model
    eng.register("3.1", model.register_priors)
    eng.register("3.2", model.train_models)
    eng.register("3.3", model.technical_review)
    # S5 — report
    eng.register("4.1a", report.build_tables)
    eng.register("4.1b", report.write_narrative)
    return eng
