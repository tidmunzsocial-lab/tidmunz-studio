---
name: tidmunz-remote-operator
description: Operate, monitor, troubleshoot, or continue Tidmunz Studio on an authorized Windows PC using Remote Desktop Commander or a verified local web controller. Distinguish เล่าภาพ from วิดีโอออโต้ and protect paid media.
---

# Tidmunz Studio — remote operator

## Purpose
Use this skill when a person asks ChatGPT or another AI assistant to control **ติดมันส์ สตูดิโอ (Tidmunz Studio)**, open a saved story, read progress/logs, recover GPT/Bridge errors, or operate Auto/เล่าภาพ. Read [references/operations.md](references/operations.md) for commands and version boundaries.

## Connection and discovery
1. Ask the user to connect and authorize their own Remote Desktop Commander (or another supported local tool). Never assume access to a workstation merely from a plugin name.
2. Discover **the currently authorized device** from the tool's device list. Do not hard-code a personal computer ID, Windows username, private host, or auth token into the skill.
3. The installed app root is typically `%LOCALAPPDATA%\Tidmunz Studio`; honor `TIDMUNZ_HOME` if configured. The source repository is a different directory; do not edit installed code to publish a fix.
4. Prefer commands and native APIs over simulated mouse clicks. If a UI click is necessary, locate the right window, verify it is in front, and confirm success from actual app status, not merely from an input event.

## Two different workflows — do not confuse them
- **วิดีโอออโต้ (Auto):** `snapgen_modules/snapgen_ai_operator.py` and the existing Mobile Web `auto` status/actions support read-only `projects`, `status`, `diagnose`, opening a saved Auto project, and guarded stop/resume.
- **เล่าภาพ (Narration):** separate projects under `export/เล่าภาพ/`. A similarly named project does not make Auto's `auto_start` equivalent to Narration's `start_pipeline()`. GitHub source now includes a separate `mobile_narrate` controller and Mobile Web tab; check that the *installed app* actually returns `narrate` in `/api/status` before using it. Supported actions on that build are `narrate_open`, `narrate_stop`, and guarded `narrate_start` requiring explicit credit consent; details and tested limits are in `references/operations.md`. Never fall back to Auto actions when Narration support is absent.
- The local Mobile Web at `127.0.0.1:8765` has `GET /api/status`, `POST /api/command`, and `GET /api/receipt/<id>`. Read the credential from the local `snapgen_data/mobile_web_url.txt` **inside the authorized machine only**, and keep it out of shell output, chat, documentation, Git and other hosts.

## Safety and verification
- First inspect project name, mode, busy flag, stage, missing media, provider receipts, and error log. Use actual files to corroborate UI percentages.
- Read-only operations and source inspection are safe defaults. Do **not** click `▶ ทำต่อ`, re-submit images or video, spend credits, alter providers, clear media, reset GPT histories, or change account credentials without the relevant current-job authorization and duplicate-submission checks.
- A `429` is a rate-limit indication, not proof of deletion; a `404 conversation_not_found` does not by itself prove a chat was deleted. Diagnose tab/session/Conversation ID changes and the Bridge separately.
- If a POST returns `202 pending`, poll `/api/receipt/<same-id>`. Never retry a possibly paid action with a *new* request id.
- If app or network access is unavailable, report it truthfully. The installed Desktop Auto engine can work on its own; a skill file is not a 24/7 autonomous agent.
- Never reveal private credentials, `access=` URLs, local config or session secrets in output.
- Report exact observed result, last action, and remaining blocker. A command being accepted is not proof a video completed.

## Distribution
This skill is currently available in GitHub source for testing; it is not yet included in the installer or release patch. `references/distribution.md` explains how a different GPT can import it. Shipping files onto a PC **does not** auto-install a ChatGPT plugin or grant remote permissions to another account.
