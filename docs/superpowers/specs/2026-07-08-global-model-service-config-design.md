# Global Model-Service Configuration — Design

**Date:** 2026-07-08
**Status:** Approved (design) — ready for implementation planning

## Problem

Today the LLM/ASR "model service" configuration is:

- **Per-project** — stored on each `ProjectState` (`modelConfig`), re-loaded on every
  `loadProject`, so a new project or a refresh starts from empty and the user must
  reconfigure.
- **Dropdown-driven** — a provider catalog (`domain/providers.py`, `/api/providers`)
  drives provider + model `<select>`s.
- **Indirect for secrets** — the config stores only an **env-var NAME** (`llmKeyRef` /
  `asrKeyRef`); the real key must be placed in `backend/.env` and is resolved via
  `resolve_secret`.

The user wants the opposite: a **single global** config the user fills **once**, with the
**actual** API key / base URL / model name entered as **free text** (no dropdowns, no
env-var-name indirection), used by every project and surviving new-project / refresh.

## Decisions (confirmed with user)

1. **Scope:** applies to **both** LLM and ASR.
2. **Placement:** primary entry is a **gear on the landing-page header** → a top-level
   global Settings screen. The per-project **Settings tab is kept** and renders the *same*
   global editor (with an "applies to all projects" note).
3. **No `.env` fallback:** the model key/url/model resolve **only** from the global config
   (UI-config-only). The seeded Danone demo therefore needs the key entered once before it
   runs. Operational knobs (`llm_timeout`, `llm_max_retries`, `asr_timeout`) remain in
   `Settings`/`.env`.

## Approach (chosen: single global JSON config + direct resolution)

Alternatives considered and rejected:
- **Per-project configs pointing at one shared record (write-through):** keeps
  `ProjectModelConfig`, more moving parts, violates YAGNI.
- **App writes global config into process env / `.env`:** contradicts "don't use env
  vars", and mutating `.env` at runtime is fragile.

### Backend

**Data model** (`domain/models.py`)
```python
class ServiceCreds(CamelModel):
    api_key: str = Field(default="", alias="apiKey")   # actual key, not a ref
    base_url: str = Field(default="", alias="baseUrl")
    model: str = Field(default="", alias="model")

class GlobalModelConfig(CamelModel):
    llm: ServiceCreds = Field(default_factory=ServiceCreds)
    asr: ServiceCreds = Field(default_factory=ServiceCreds)
```

**Storage** (`store/model_service.py`) — one JSON file at `data/model_service.json`
(already covered by `backend/.gitignore: data/*.json`), cached singleton:
`get_model_service() -> GlobalModelConfig` and `save_model_service(cfg)`. Global, not
per-project.

**Resolution** (`llm/volcano.py`, `asr/whisper.py`)
- `get_llm()` reads `get_model_service().llm` directly; empty `apiKey` → `LLMError`
  "LLM not configured — set it in Settings". `get_asr()` mirrors this for ASR.
- Client caching keyed on `(base_url, model, api_key, timeout, retries)` stays.
- **Removed:** `ContextVar` plumbing (`set_active_model_config` /
  `reset_active_model_config`), `_resolve_llm_params`/`_resolve_asr_params`,
  `get_llm_for(cfg)`/`get_asr_for(cfg)` per-config signatures, the provider catalog
  (`domain/providers.py`), and `resolve_secret` + `.env` key lookup for models.
- Call sites simplify: `orchestrator/engine.py` drops the per-task set/reset;
  `main.py::_require_state` drops `set_active_model_config`; `agents/business.py` calls
  `get_asr()` instead of `get_asr_for(st.model_config_data)`.

**`Settings`** (`config.py`) — drop `volcano_api_key`, `volcano_base_url`,
`volcano_model`, `asr_api_key`, `asr_base_url`, `asr_model`, `llm_key_ref_default`,
`asr_key_ref_default`, and (if now unused) `resolve_secret`/`_dotenv_values`. Keep
`llm_timeout`, `llm_max_retries`, `asr_timeout`, storage/data/reference paths.

**API routes** (`main.py`)
- Remove: `GET /api/providers`, `GET|PUT /api/projects/{id}/model-config`.
- Add: `GET /api/model-config`, `PUT /api/model-config` (global; body/response =
  `GlobalModelConfig`, camelCase via `by_alias`).

**`ProjectState`** (`store/state.py`) — remove `model_config_data`
(`alias="modelConfig"`); legacy JSON `modelConfig` keys are silently ignored (Pydantic
extra defaults to ignore). Remove any `heal_state` reference to it.

### Frontend

**Types** (`lib/types.ts`)
- Replace `ModelConfig` with `ServiceCreds { apiKey; baseUrl; model }` and
  `GlobalModelConfig { llm: ServiceCreds; asr: ServiceCreds }`.
- Remove `ProviderInfo` / `ProviderCatalog`.
- `isLlmConfigured(cfg) = !!(cfg && cfg.llm.apiKey && cfg.llm.model)`.
- Add UI placeholder constants (Volcano base URL/model, Whisper base URL/model) — hints
  only, never persisted.

**API client** (`api/client.ts`) — `getModelConfig()` / `updateModelConfig(cfg)` hitting
`/api/model-config` (no projectId); remove `listProviders`.

**Store** (`store/useSimStore.ts`) — `modelConfig: GlobalModelConfig | null` becomes
global: a `loadModelConfig()` action runs **once on app start** (not inside
`loadProject`); `updateModelConfig` PUTs the global route and optimistically sets state.
Remove per-project `modelConfig` reset in `loadProject`.

**UI** — rename/rewrite `ProjectSettingsView.tsx` into a shared **`GlobalSettingsView`**:
- Two cards: **LLM (required)**, **ASR (optional)**.
- Each card = three free-text fields: **API Key** (password `<input type="password">` +
  show/hide toggle), **Base URL**, **Model name**. No provider/model dropdowns, no
  env-var-name field.
- Defaults surface only as greyed `placeholder`s.
- A note: "These settings are global and apply to all projects."

**Routing / entry** (`main.tsx`, `ProjectsLanding.tsx`, `layout/AppShell.tsx`)
- Add top-level route `/settings` → `GlobalSettingsView` (standalone, with a back-to-home
  affordance).
- Landing-page header: add a **gear button** → `/settings`.
- Keep `/p/:projectId/settings` rendering the same `GlobalSettingsView` inside the shell;
  the per-project "Settings" nav item and the "Configure an LLM" run-gate keep pointing at
  it.

## Data flow

```
User → GlobalSettingsView → PUT /api/model-config → save_model_service()
                                                   → data/model_service.json
Any project run → get_llm()/get_asr() → get_model_service() → live client
```

## Error handling

- Empty LLM `apiKey`/`model`: `get_llm()` raises `LLMError` with a "set it in Settings"
  message; the existing `isLlmConfigured` run-gate blocks the run and links to Settings.
- Empty ASR key: audio steps surface the existing "ASR not configured" message; text
  minutes still work.
- Malformed/absent `model_service.json`: storage loader returns an empty
  `GlobalModelConfig` rather than crashing startup.

## Security

- Key stored plaintext in the gitignored `data/model_service.json`; returned to the
  browser on `GET` for editing (password field, show/hide). Acceptable for a local,
  single-user tool. No key is committed to git.

## Testing

- Backend: extend `tests/test_api_smoke.py` — `PUT` then `GET /api/model-config`
  round-trips the values; assert `get_llm()` raises when unconfigured and returns a client
  once configured. Small unit for `store/model_service.py` load/save.
- Frontend: `npm run lint` + `npm run build` green; add a Settings screenshot step to
  `scripts/visual-check.mjs`.

## Out of scope

- Encrypting the stored key, multi-user secret management, or per-project overrides
  (explicitly one global config).
- Changing `llm_timeout` / retry behavior.
