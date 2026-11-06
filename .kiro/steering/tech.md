# Tech Stack

- Language: Python 3
- Dependencies (`requirements.txt`): `boto3`, `PyYAML`
- AWS service: Amazon Q in Connect, boto3 client name `qconnect`, IAM prefix `wisdom`
- Region: `ap-southeast-2`
- Auth: AWS SSO via the `rnd` profile (`aws sso login --profile rnd`)
- Model used by the prompt: Claude Haiku 4.5 (`au.anthropic.claude-haiku-4-5-20251001-v1:0`)

## Common commands

```bash
pip install -r requirements.txt
aws sso login --profile rnd
python update_prompt.py --dry-run   # preview diff, changes nothing
python update_prompt.py             # back up, then push
```

## API calls used

- `GetAIPrompt`: read and back up the live prompt
- `UpdateAIPrompt`: write to the `$LATEST` draft
- `CreateAIPromptVersion`, `GetAIAgent`, `UpdateAIAgent`: only when `publish.draft_only` is `false`

## Conventions

- Read and write prompt files byte-for-byte (`newline=""`). Do not reformat, normalize line endings, or strip trailing newlines.
- Always run `--dry-run` before a real push.
- Never run the real push without the user asking for it, since it changes a live AI prompt.
- Do not hardcode credentials. Use the AWS profile in `prompt.yaml`.
- Resource IDs belong in `prompt.yaml`, not in code.
