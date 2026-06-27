# Self-host quickstart

Run Mail Intelligence Router on your own hardware with Docker. The public tree ships runtime-resolved configuration stubs — operator credentials and local paths are configured on your machine only.

---

## Prerequisites

- Docker & Docker Compose  
- 16 GB+ RAM recommended  
- Node.js 18+ (to build the web UI once)  

---

## 1. Clone and configure from examples

Copy the example env files and edit placeholders locally (these files are gitignored once created):

```bash
cp docker/.env.mail-intel.example docker/.env.mail-intel
cp config/mail_intel.env.example config/mail_intel.env
```

In `docker/.env.mail-intel`, set generic values such as:

- `DOC_ENGINE=infinity` (already in the example)  
- `SVR_WEB_HTTP_PORT=80`  
- `OBSIDIAN_VAULT_PATH` — **your** host path to a notes vault (or leave unset if unused)  
- `MAIL_INTEL_AGENT_ID` — filled in after first deploy  

See also `config/mail_intel.env.example` for agent and connector placeholders.

> Stack env files carry infrastructure labels, not secrets. Export deploy identity in your shell for the one-shot init job only (see step 4).

---

## 2. Build the web UI

```bash
cd web
npm install
npm run build
cd ..
```

---

## 3. Start the stack

```bash
cd docker
docker compose -f docker-compose-mail-intel.yml \
  --env-file .env \
  --env-file .env.mail-intel \
  --profile infinity \
  up -d --build
```

**Services:** RAGFlow (nginx **port 80**), MySQL, Redis, MinIO, Infinity.

---

## 4. One-shot agent deploy

Export login credentials in your shell (not in env files), then run the init job:

```bash
export RAGFLOW_API_EMAIL='you@example.com'
export RAGFLOW_API_PASSWORD='your-ragflow-password'

docker compose -f docker-compose-mail-intel.yml \
  --env-file .env \
  --env-file .env.mail-intel \
  --profile infinity \
  --profile init \
  run --rm mail-intel-deploy
```

Open the agent explore UI at `http://localhost/agent/<your-agent-id>/explore` (use the id from your env or deploy output).

---

## 5. Connect mail

Configure an IMAP or supported mail connector in the RAGFlow UI. Connector credentials live in RAGFlow’s store or your operator-managed secrets — not in the public repo.

---

## Templates in the repo

Example env files and compose definitions ship with placeholder values. Copy them to gitignored local names and edit on the host. The Docker operator README (same repository, not linked from this site) covers live-code mounts and credential philosophy.

---

## Troubleshooting

| Issue | Check |
|-------|-------|
| Port 80 in use | Change `SVR_WEB_HTTP_PORT` in `.env.mail-intel` |
| Infinity not starting | Ensure `--profile infinity` is set |
| Agent missing in UI | Re-run `mail-intel-deploy` with shell exports |
| Obsidian not writing | Confirm vault path env points to a writable directory on the host |

---

## Next steps

- [Product overview](index.md)  
- [Architecture](architecture-overview.md)  

For deeper operator documentation (live-code mounts, volume resets), see `docker/README-mail-intel.md` in the repository.
