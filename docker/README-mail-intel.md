# Mail Intelligence — Docker runtime

Operator notes for the live-code Mail Intelligence stack. This document describes **design intent and credential philosophy**; step-by-step wiring lives in your local environment, not in the public tree.

---

## Design principles

### Separation of compute and storage (存算分离)

The engine runs online: routing, LLM calls, and agent execution stay inside the container boundary. **Knowledge artifacts and operator secrets stay off-repo** — note vaults, encrypted local stores, and HSM-gated unlock material bind at runtime through environment and volume mounts, not baked into images or git history.

### Pipeline: gate → mine → decide → synthesize

The v2 Mail Intelligence Router is a multi-sector agent graph:

| Stage | Role |
|-------|------|
| **InboxIndexer** | Builds a structured manifest from recent mail — the shared context layer for downstream agents |
| **CyberSecGate** | First-pass security triage; elevates threat signals before sector routing |
| **Route (×5)** | Categorize dispatches to **security**, **career**, **commerce**, **platform**, or **briefing** |
| **Miners** | Sector specialists extract structured facts (auctions, subscriptions, finance, notifications, etc.) |
| **Verifiers** | External corroboration where claims matter (e.g. career postings via search tools) |
| **Synth** | Briefing synthesis merges sector outputs into one actionable response |

Prompt bodies and API credentials for these components are **runtime-resolved configuration**: the public repo does not ship prompt text (see `agent/prompts/mail_intel/README.md`). Full operator prompts live locally or inject from an encrypted vault after HSM unlock; the router build defaults to skeleton stubs unless you opt into vault inject or local `--full-prompts`.

### Multi-layer authentication

Credentials are not a single secret — they are **layered by blast radius**:

1. **Deploy identity** — short-lived shell export for one-shot agent registration; never persisted in compose env files or images.
2. **Application store** — connector and model keys configured in the RAGFlow UI (MySQL-backed), appropriate for service-scoped secrets.
3. **Local secrets vault** — AES-GCM encrypted store for prompts, tool keys, and connector references; unlocked via TOTP + **HSM** (hardware security module, e.g. YubiKey Bio touch).
4. **Ephemeral hardware session** — after HSM verification, a bounded JWT backs API calls until browser refresh; Obsidian write paths can require a separate vault gate.

Think in terms of **what must exist where**: images carry code, volumes carry state, vaults carry intent — not the reverse.

---

## Live-code vs image

| Change | Effect |
|--------|--------|
| Agent graph / prompts in UI | Persisted to MySQL — no image rebuild |
| Python backend or agent components | Edit bind-mounted source → restart application container |
| Frontend (HSM unlock overlay, explore UI) | Rebuild web assets → restart application container |
| Dependency manifest changes | Reset the Python venv volume once, then restart |

The runtime image is intentionally slim. Application source is bind-mounted so fork-specific logic survives upstream pulls. Python dependencies hydrate into a named volume on first boot.

---

## Credential handling (advisory)

**Stack env files** hold non-secret configuration: doc engine choice, ports, agent identifiers, optional note-vault mount points. Treat them as infrastructure labels, not secret carriers.

**Deploy credentials** belong in process environment for the duration of a single init job only. Compose forwards host exports into the init container; they are not written to disk by the stack.

**Third-party keys** (search APIs, mail connectors) should live in the RAGFlow credential store or in the encrypted local vault — not in tracked templates. Vault-unlocked deploy can inject tool keys and connector IDs into the agent DSL at registration time.

**HSM enrollment** binds physical presence to vault unlock. Relying party origin must match the browser URL you actually use (local nginx vs dev proxy). Hardware credential encryption material stays on the operator host — never in images or the public tree.

If a credential ever touched a tracked or shared file: rotate it, remove the artifact, and confirm ignore rules before pushing.

---

## Quick start (outline)

1. Copy example env templates to operator-local config; fill placeholders (ports, optional note vault, agent id).
2. Build the web UI once (`npm run build` in the web package).
3. Start the compose stack with the Infinity profile.
4. Export deploy identity in your shell; run the one-shot init profile to register the agent graph.
5. Open the agent explore URL for your configured agent id.
6. Configure mail connectors in the UI.

Exact compose flags and file names are in the example templates shipped with this directory — follow those comments locally.

---

## Runtime topology (conceptual)

- **Edge network** — nginx terminates HTTP for the browser
- **Application network** — RAGFlow API, workers, internal services
- **Data network** — MySQL, Redis, MinIO, Infinity (no Elasticsearch / TEI in this profile)
- **Optional host bind** — personal note vault mounted read/write for briefing capture; gated by vault policy when 2FA-for-Obsidian is enabled

Five long-running services plus a one-shot deploy job. Pre-built static frontend; no Vite dev server in production compose.

---

## After code changes

Restart the application service after Python edits. Rebuild web assets before restart when frontend or HSM overlay logic changes. Use the compose env files you already configured — no credential re-export needed for ordinary restarts.
