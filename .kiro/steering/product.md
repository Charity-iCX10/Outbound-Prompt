# Product Overview

This project switches the behavior of an AI "customer" used to test outbound calls.

- Our bot, Alex (ConnectNow, a utility connections service), places an outbound call to an Amazon Connect instance.
- An AI agent on the receiving end roleplays a customer.
- The customer's behavior (the "scenario") is defined by an Amazon Q in Connect AI prompt.
- A Python script assembles the prompt from a fixed template plus a swappable scenario and pushes it to AWS.

## Core workflow

1. Edit `scenario.txt`.
2. Preview with `python update_prompt.py --dry-run`.
3. Apply with `python update_prompt.py`.
4. Place the outbound call.

## Principles

- The contact flow and Lex bot are never modified. Only the AI prompt changes.
- Scenario changes go in `scenario.txt`. Treat `template.txt` as fixed.
- The `<output_format>` and TTS rules in `template.txt` must not be altered, because they control turn-taking and what is spoken aloud.
- The only scenario seeded today is "customer insists on a human agent".
