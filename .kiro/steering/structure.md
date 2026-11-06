# Project Structure

```
template.txt         Fixed prompt shell with a {{SCENARIO}} marker (rarely edited)
scenario.txt         Swappable scenario: goal line + <conversation_behavior> (edit this)
prompt.yaml          Config: AWS resource IDs, files to assemble, publish toggle
update_prompt.py     Assembles template + scenario and pushes via API (supports --dry-run)
prompt.txt           Legacy single-file prompt (kept for reference)
requirements.txt     Python dependencies
README.md            Setup and usage
PROPOSAL-ai-scenario-switching.md   Design doc
backups/             Auto-saved snapshots of the live prompt before each push
```

## Rules for editing

- To change what the AI customer does, edit only `scenario.txt`.
- `template.txt` holds the intro, a generalized `<identity>`, `<restrictions>`, `<output_format>`, `<final-instructions>` and the `messages:` anchor. Keep scenario-specific behavior out of it.
- Keep the `{{SCENARIO}}` marker in `template.txt`. The script exits with an error if it is missing.
- Do not edit files in `backups/`. They are generated.
- Keep `scenario.txt` indentation consistent with the `system: |` block (4 spaces) so the YAML stays valid.

## Writing a new scenario

Replace the contents of `scenario.txt` with a goal line and a `<conversation_behavior>` block. Do not repeat identity, restrictions or output-format rules there, because the template already covers them.
