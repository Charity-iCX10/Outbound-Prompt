# Plan: API-Driven Prompt Switching for the AI Customer (Outbound Call Answerer)

## 1. Goal

We are building an automated **outbound-call answerer**: our bot (Alex) places an
outbound call to the `icx-inbound-agents` Connect instance, and an AI agent on the
receiving end plays the role of a **customer**. We want to change what that AI
customer does ("the scenario") from time to time, quickly and repeatably — without
touching the contact flow, the Lex bot, or the stable parts of the prompt.

The approach: split the prompt into a **fixed template** and a **swappable scenario**,
then run a **Python script** that stitches them together and pushes the result into
the live AI prompt. Edit the scenario, run the script, place the call. Repeat forever.

## 2. What exists today (verified)

All resources live in **`ap-southeast-2`**, account `055283454589`, `rnd` profile.

| Component | Name | ID |
|---|---|---|
| Connect instance | `icx-inbound-agents` | `23be90b0-0f72-4432-8024-c559e16638ac` |
| Contact flow | `AI-inbound-demo` | `2c40a816-c4c5-4870-96c0-4c333e1405e8` |
| Q in Connect assistant | (Wisdom assistant) | `f27a2608-098f-4bd3-98c0-c2ced1931786` |
| AI agent | `inbound-AI-POC` (ORCHESTRATION) | `3eddc019-b9ca-457d-9dbb-ce0348fac96d` |
| **AI prompt (what we edit)** | `ai-inbound` (TEXT, MESSAGES) | `9fe27837-96a9-4cfb-baeb-af9e2b68e3a4` |

**Model:** `au.anthropic.claude-haiku-4-5-20251001-v1:0`.

The contact flow only wires logging, recording, TTS (OLIVIA / `en-AU`), creates a
Q in Connect session, and bridges the caller to the AI agent via Lex. **The prompt
text itself lives entirely in the Q in Connect AI prompt `ai-inbound`.** That single
resource is the only thing we edit to change scenarios. The flow and Lex bot are
never touched.

## 3. Design: fixed template + swappable scenario

The prompt is assembled from two files. The script inserts the scenario where the
`{{SCENARIO}}` marker sits in the template, then pushes the full text.

### `template.txt` — the FIXED shell (rarely edited)
Holds the parts that must stay constant for every scenario:
- the intro line (AI roleplaying as a customer receiving a call from Alex / ConnectNow)
- a **generalized** `<identity>` (a normal customer reacting naturally — not tied to any
  one scenario)
- `<restrictions>` (never reveal the prompt, don't break character, etc.)
- `<output_format>` — the `<thinking>` / `<message>` contract and TTS formatting rules
- `<final-instructions>`
- the `messages:` anchor (`{{$.conversationHistory}}` + the trailing `content: <message>`)

Contains the `{{SCENARIO}}` marker on its own indented line, right after the intro.

### `scenario.txt` — the SWAPPABLE part (edit THIS to change scenarios)
Holds only what defines a specific scenario:
- the "primary goal" line
- the `<conversation_behavior>` block

Currently seeded with the **"transfer to agent"** scenario (the AI customer insists on
being handed to a human). To make a different scenario, you rewrite this file only.

### Why split this way
The original single prompt had "connect to agent" references woven through the intro,
identity, output-format, and final-instructions. That meant every scenario would fight
leftover "ask for a human" nudges in the scaffolding. Moving behavior into `scenario.txt`
and neutralizing the shell means the scenario fully controls behavior, and the fragile
TTS/turn-taking contract can never be broken by accident.

## 4. Tooling

### `prompt.yaml`
Config only (no prompt text): target resource IDs, which files to assemble
(`template_file`, `scenario_file`, `scenario_marker`), and a publish toggle.

### `update_prompt.py`
1. Loads `prompt.yaml`.
2. Reads `template.txt` and `scenario.txt` **byte-for-byte** (preserves CRLF, encoding,
   no reformatting) and substitutes the scenario into the marker.
3. Fetches the current live prompt and shows a unified **diff**; with `--dry-run` it stops
   here and changes nothing.
4. Backs up the current live prompt to `backups/` (JSON + verbatim `.txt`).
5. Calls `UpdateAIPrompt` to write the assembled text to the prompt's `$LATEST` draft.
6. If `draft_only: false`, also calls `CreateAIPromptVersion` and `UpdateAIAgent` to
   publish an immutable version and point the agent at it.

The next outbound call to the instance follows the updated prompt.

### Publishing modes (in `prompt.yaml`)
- **`draft_only: true` (default, chosen):** updates `$LATEST` only. Fastest; next call
  uses it. Good for rapid iteration.
- **`draft_only: false`:** publishes a numbered version and repoints the agent — audit
  trail + easy rollback. Switch to this once prompts stabilize or multiple people test.

## 5. Prerequisites — Python libraries

The script needs Python 3 and two packages:

| Package | Purpose |
|---|---|
| `boto3` | AWS SDK for Python — makes the Q in Connect API calls |
| `PyYAML` | reads `prompt.yaml` |

Install them with:

```
pip install -r requirements.txt
```

(`requirements.txt` pins `boto3>=1.34.0` and `PyYAML>=6.0`.)

The AWS CLI is also used for authentication (`aws sso login`) since the `rnd`
profile uses AWS SSO.

## 6. Commands to run

```
# one-time: install dependencies
pip install -r requirements.txt

# authenticate (the rnd profile uses AWS SSO; needed when the token expires)
aws sso login --profile rnd

# preview what would change — reads live prompt, prints a diff, changes NOTHING
python update_prompt.py --dry-run

# apply — backs up the current prompt, then pushes the assembled prompt
python update_prompt.py
```

Day-to-day loop: edit `scenario.txt`, run `--dry-run` to preview, then run
`update_prompt.py` to apply, then place the outbound call.

## 7. API used (Amazon Q in Connect — SDK client `qconnect`)

| Operation | Purpose |
|---|---|
| `GetAIPrompt` | Read + back up the current prompt |
| `UpdateAIPrompt` | Write assembled text to `$LATEST` (`templateConfiguration.textFullAIPromptEditTemplateConfiguration.text`) |
| `CreateAIPromptVersion` | (mode B) Freeze `$LATEST` into an immutable version |
| `GetAIAgent` / `UpdateAIAgent` | (mode B) Repoint `orchestrationAIPromptId` at the new version |

Note: the SDK/CLI client is named `qconnect`, but the underlying service's IAM
prefix and ARNs use `wisdom` (see IAM below).

## 8. IAM permissions required

The identity running the script (the `rnd` SSO role/user) needs the following
Amazon Q in Connect permissions. The IAM **service prefix is `wisdom`** (the
`qconnect` client maps to the `wisdom` service).

Minimum for the default **draft-only** mode:

- `wisdom:GetAIPrompt`
- `wisdom:UpdateAIPrompt`

Additionally for **versioned** mode (`draft_only: false`):

- `wisdom:CreateAIPromptVersion`
- `wisdom:GetAIAgent`
- `wisdom:UpdateAIAgent`

Example policy (scoped to this assistant's resources in `ap-southeast-2`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "QinConnectPromptSwitching",
      "Effect": "Allow",
      "Action": [
        "wisdom:GetAIPrompt",
        "wisdom:UpdateAIPrompt",
        "wisdom:CreateAIPromptVersion",
        "wisdom:GetAIAgent",
        "wisdom:UpdateAIAgent"
      ],
      "Resource": [
        "arn:aws:wisdom:ap-southeast-2:055283454589:assistant/f27a2608-098f-4bd3-98c0-c2ced1931786",
        "arn:aws:wisdom:ap-southeast-2:055283454589:ai-prompt/f27a2608-098f-4bd3-98c0-c2ced1931786/*",
        "arn:aws:wisdom:ap-southeast-2:055283454589:ai-agent/f27a2608-098f-4bd3-98c0-c2ced1931786/*"
      ]
    }
  ]
}
```

To keep it simple while testing, `"Resource": "*"` also works; the scoped ARNs
above are the least-privilege version.

## 9. Files in this project

```
template.txt         # FIXED shell with {{SCENARIO}} marker (rarely edited)
scenario.txt         # SWAPPABLE scenario: goal line + <conversation_behavior> (edit this)
prompt.yaml          # config: resource IDs, which files to assemble, publish toggle
update_prompt.py     # assembles template + scenario and pushes via API (has --dry-run)
requirements.txt     # boto3, pyyaml
README.md            # setup + usage
backups/             # auto-saved snapshot of the prompt before each change
```

## 10. Workflow

```
edit scenario.txt
  -> python update_prompt.py --dry-run      (preview the diff; changes nothing)
  -> python update_prompt.py                (apply)
  -> place the outbound call                (AI customer follows the new scenario)
  -> repeat
```

## 11. Status

- Implemented and applied. The live `ai-inbound` prompt is the assembled version
  (2549 chars, sha256 `0078a07d…`); the previous 2634-char prompt is saved under
  `backups/`.
- Current live behavior: the "transfer to agent" scenario (unchanged behavior; the
  shell was generalized so future swaps are clean).

## 12. Decisions made

1. **Language:** Python (boto3 + pyyaml).
2. **Scenario catalog:** none pre-written — only the template structure plus the seeded
   "transfer to agent" scenario. New scenarios are authored by editing `scenario.txt`.
3. **Swap boundary:** `<identity>` stays in the fixed template (generalized to a normal
   customer); only the goal line + `<conversation_behavior>` are swappable.
4. **Publishing mode:** start in `draft_only: true` (fast).
