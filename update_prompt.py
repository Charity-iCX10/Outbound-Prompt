#!/usr/bin/env python3
"""
update_prompt.py
----------------
Pushes the prompt text in `prompt.txt` into the Amazon Q in Connect AI prompt
used by the icx-inbound-agents instance, so the next outbound call to that
instance follows it.

The prompt is assembled from two files, read BYTE-FOR-BYTE:
  template_file (template.txt) - fixed shell with a {{SCENARIO}} marker
  scenario_file (scenario.txt) - the swappable scenario text
The scenario text is substituted into the marker. Nothing is reformatted.

(Backward compatible: if the YAML has `prompt_file` instead, that single file
is pushed as-is.)

Usage:
    python update_prompt.py                 # assemble + push
    python update_prompt.py --dry-run       # compare only; change NOTHING
    python update_prompt.py other.yaml      # use a different config file
    python update_prompt.py other.yaml --dry-run

Requires: boto3, pyyaml   ->   pip install -r requirements.txt
"""

import difflib
import hashlib
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import boto3
import yaml

HERE = Path(__file__).resolve().parent
BACKUP_DIR = HERE / "backups"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_args(argv):
    dry_run = False
    yaml_path = None
    for arg in argv[1:]:
        if arg in ("--dry-run", "-n"):
            dry_run = True
        elif not arg.startswith("-"):
            yaml_path = Path(arg).resolve()
    if yaml_path is None:
        yaml_path = HERE / "prompt.yaml"
    return yaml_path, dry_run


def load_config(yaml_path: Path) -> dict:
    if not yaml_path.exists():
        sys.exit(f"ERROR: config file not found: {yaml_path}")
    with yaml_path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    if "aws" not in cfg:
        sys.exit(f"ERROR: 'aws' section missing from {yaml_path.name}")
    aws = cfg["aws"]
    for field in ("profile", "region", "assistant_id", "ai_prompt_id", "ai_agent_id"):
        if not aws.get(field):
            sys.exit(f"ERROR: aws.{field} is missing or empty in {yaml_path.name}")

    base = yaml_path.parent
    # Mode 1 (preferred): template + scenario assembly
    if cfg.get("template_file"):
        cfg["_mode"] = "assemble"
        cfg["_template_path"] = (base / cfg["template_file"]).resolve()
        cfg["_scenario_path"] = (base / cfg.get("scenario_file", "scenario.txt")).resolve()
        cfg["_marker"] = cfg.get("scenario_marker", "{{SCENARIO}}")
    else:
        # Mode 2 (legacy): single prompt file pushed as-is
        cfg["_mode"] = "single"
        cfg["_prompt_path"] = (base / cfg.get("prompt_file", "prompt.txt")).resolve()
    return cfg


def _read_verbatim(path: Path) -> str:
    """Read a file VERBATIM (preserve CRLF, no trailing-newline, etc.)."""
    if not path.exists():
        sys.exit(f"ERROR: file not found: {path}")
    with io.open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def read_prompt_text(cfg: dict) -> str:
    """Return the full prompt text to push."""
    if cfg["_mode"] == "single":
        text = _read_verbatim(cfg["_prompt_path"])
        if not text.strip():
            sys.exit(f"ERROR: prompt file is empty: {cfg['_prompt_path']}")
        return text

    # assemble mode
    template = _read_verbatim(cfg["_template_path"])
    scenario = _read_verbatim(cfg["_scenario_path"])
    marker = cfg["_marker"]
    if marker not in template:
        sys.exit(f"ERROR: marker {marker!r} not found in {cfg['_template_path'].name}")
    if not scenario.strip():
        sys.exit(f"ERROR: scenario file is empty: {cfg['_scenario_path']}")
    return template.replace(marker, scenario)


def make_client(cfg: dict):
    session = boto3.Session(
        profile_name=cfg["aws"]["profile"],
        region_name=cfg["aws"]["region"],
    )
    return session.client("qconnect")


def get_live_prompt(client, cfg: dict) -> dict:
    return client.get_ai_prompt(
        assistantId=cfg["aws"]["assistant_id"],
        aiPromptId=cfg["aws"]["ai_prompt_id"],
    )["aiPrompt"]


def live_text(ai_prompt: dict) -> str:
    return (
        ai_prompt.get("templateConfiguration", {})
        .get("textFullAIPromptEditTemplateConfiguration", {})
        .get("text", "")
    )


def show_diff(current: str, new: str) -> bool:
    """Return True if different; print a unified diff."""
    if current == new:
        return False
    diff = difflib.unified_diff(
        current.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile="live (current)",
        tofile="prompt.txt (new)",
    )
    sys.stdout.writelines(diff)
    if not current.endswith("\n") or not new.endswith("\n"):
        print()  # keep terminal tidy
    return True


def backup_current(ai_prompt: dict) -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = BACKUP_DIR / f"ai-prompt-{stamp}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(ai_prompt, fh, indent=2, default=str)
    # also keep the exact prior text next to it, verbatim
    tpath = BACKUP_DIR / f"ai-prompt-{stamp}.txt"
    with io.open(tpath, "w", encoding="utf-8", newline="") as fh:
        fh.write(live_text(ai_prompt))
    return path


def update_draft(client, cfg: dict, new_text: str) -> None:
    client.update_ai_prompt(
        assistantId=cfg["aws"]["assistant_id"],
        aiPromptId=cfg["aws"]["ai_prompt_id"],
        visibilityStatus="PUBLISHED",
        templateConfiguration={
            "textFullAIPromptEditTemplateConfiguration": {"text": new_text}
        },
    )


def publish_version(client, cfg: dict) -> str:
    resp = client.create_ai_prompt_version(
        assistantId=cfg["aws"]["assistant_id"],
        aiPromptId=cfg["aws"]["ai_prompt_id"],
    )
    version_number = resp["aiPrompt"]["versionNumber"]
    return f"{cfg['aws']['ai_prompt_id']}:{version_number}"


def repoint_agent(client, cfg: dict, versioned_prompt_id: str) -> str:
    agent = client.get_ai_agent(
        assistantId=cfg["aws"]["assistant_id"],
        aiAgentId=cfg["aws"]["ai_agent_id"],
    )["aiAgent"]
    orch = agent["configuration"]["orchestrationAIAgentConfiguration"]
    orch["orchestrationAIPromptId"] = versioned_prompt_id
    client.update_ai_agent(
        assistantId=cfg["aws"]["assistant_id"],
        aiAgentId=cfg["aws"]["ai_agent_id"],
        visibilityStatus="PUBLISHED",
        configuration={"orchestrationAIAgentConfiguration": orch},
    )
    return agent.get("name", "")


def main() -> None:
    yaml_path, dry_run = parse_args(sys.argv)
    cfg = load_config(yaml_path)
    draft_only = bool(cfg.get("publish", {}).get("draft_only", True))

    new_text = read_prompt_text(cfg)

    if cfg["_mode"] == "assemble":
        src = f"{cfg['_template_path'].name} + {cfg['_scenario_path'].name}"
    else:
        src = cfg["_prompt_path"].name
    print(f"Config: {yaml_path.name}   Source: {src}")
    print(f"Region: {cfg['aws']['region']}   Profile: {cfg['aws']['profile']}")
    print(f"Mode:   {'DRY RUN (no changes)' if dry_run else ('draft only' if draft_only else 'publish version + repoint agent')}")
    print(f"New prompt: {len(new_text)} chars, sha256 {sha(new_text)[:16]}...")
    print("-" * 64)

    client = make_client(cfg)
    ai_prompt = get_live_prompt(client, cfg)
    current = live_text(ai_prompt)
    print(f"Live prompt: {len(current)} chars, sha256 {sha(current)[:16]}...")
    print("-" * 64)

    changed = show_diff(current, new_text)

    if not changed:
        print("No difference between prompt.txt and the live prompt. Nothing to do.")
        if dry_run:
            print("(dry run)")
        return

    if dry_run:
        print("-" * 64)
        print("DRY RUN: the above changes would be applied. Nothing was changed.")
        return

    print("-" * 64)
    bpath = backup_current(ai_prompt)
    print(f"Backed up current prompt -> {bpath.relative_to(HERE)}")

    update_draft(client, cfg, new_text)
    print("Updated $LATEST draft of the AI prompt.")

    if not draft_only:
        time.sleep(2)
        versioned_id = publish_version(client, cfg)
        print(f"Published version -> {versioned_id}")
        name = repoint_agent(client, cfg, versioned_id)
        print(f"Repointed agent '{name}' at {versioned_id}")

    print("-" * 64)
    print("Done. The next outbound call to this instance uses the new prompt.")


if __name__ == "__main__":
    main()
