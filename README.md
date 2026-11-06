# AI Customer Prompt Switcher

Edit one YAML file, run one script, and the next outbound call to the
`icx-inbound-agents` Connect instance follows the new prompt.

## How it works

The AI "customer" persona lives in an Amazon Q in Connect **AI prompt**
(not in the contact flow). This tool reads `prompt.yaml` and pushes its
`prompt` text into that AI prompt via the `qconnect` API.

- Contact flow and Lex bot are never touched.
- You just keep editing `prompt.yaml` and re-running the script.

## Setup

```bash
pip install -r requirements.txt
```

Make sure the `rnd` AWS profile is configured (the YAML references it).

## Use

1. Edit the `prompt:` block in `prompt.yaml`.
2. Run:

   ```bash
   python update_prompt.py
   ```

3. Place/trigger the outbound call. It uses the updated prompt.

Repeat whenever you want a different scenario.

## Publishing modes (in `prompt.yaml`)

```yaml
publish:
  draft_only: true    # fast: just updates $LATEST, next call picks it up
# draft_only: false   # also publishes an immutable version + repoints the agent
```

Use `draft_only: true` for quick iteration. Switch to `false` when you want
versioned, rollback-friendly changes.

## Backups

Every run saves the previous prompt to `backups/ai-prompt-<timestamp>.json`
before overwriting, so you can always restore an earlier prompt.

## Target resources (ap-southeast-2)

| Thing | ID |
|---|---|
| Connect instance `icx-inbound-agents` | `23be90b0-0f72-4432-8024-c559e16638ac` |
| Q in Connect assistant | `f27a2608-098f-4bd3-98c0-c2ced1931786` |
| AI prompt `ai-inbound` | `9fe27837-96a9-4cfb-baeb-af9e2b68e3a4` |
| AI agent `inbound-AI-POC` | `3eddc019-b9ca-457d-9dbb-ce0348fac96d` |
