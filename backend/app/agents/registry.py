"""Wire every producing task to its handler."""
from __future__ import annotations

from app.agents import business, data, model, report, uploads
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
    # S2/S3 — data (artifact-driven: 2.1 Validation · 2.2 Process · 2.3 Cross-Validation)
    eng.register("2.0a", uploads.provide_data_files)
    eng.register("2.11", data.validation_standard)   # Input: validation standard
    eng.register("2.12", data.score_data)            # Output: quality score
    eng.register("2.21", data.wide_schema)           # Input: wide-table schema
    eng.register("2.22", data.processing_logic)      # Input: processing logic (TaskLog)
    eng.register("2.23", data.data_dictionary)       # I/O: data dictionary
    eng.register("2.24", data.integrate_dataset)     # Output: master dataset
    eng.register("2.31", data.business_rules)        # Input: business validation rules + drill
    eng.register("2.32", data.data_review)           # Output: data review deck + client Q&A
    eng.register("2.33", data.stat_screening)        # Input: technical validation
    eng.register("2.34", data.pre_fit)               # I/O: indicator selection
    # S4 — model
    eng.register("3.1", model.register_priors)
    eng.register("3.2", model.train_models)
    eng.register("3.3", model.technical_review)
    # S5 — report
    eng.register("4.1a", report.build_tables)
    eng.register("4.1b", report.write_narrative)
    return eng
