# Operations and diagnostics

## Read-only device workflow
- In Remote Desktop Commander, call `list_devices`; proceed only if the authorized Windows device is online.
- From that device inspect `%LOCALAPPDATA%\Tidmunz Studio`, running app processes and saved projects. Use PowerShell or the actual installed Python (often `.venv312\Scripts\python.exe`).
- On a workstation with the CLI available, run its `status`, `diagnose`, and `projects` commands. For example, from the app root: `.venv312\Scripts\python.exe snapgen_modules\snapgen_ai_operator.py status`. Results refer to **Auto** unless the installed version explicitly documents otherwise.
- Inspect `export\เล่าภาพ\<existing-title>\project.json`, `story_analysis.json`, `context.json` and `snapgen_data\logs\console.log` for Narration. Read-only access is sufficient to diagnose progress. Preserve original files.
- Open Mobile Web via the user's existing authenticated session when available; never paste its `access=` token in the chat. Request status from loopback on the authorized machine. Check whether the status actually includes a narration-specific state and commands before using them.

## Action gating
1. Confirm the exact existing story and workflow (Auto vs เล่าภาพ).
2. Check whether work is already busy and whether an accepted remote provider job could still be running.
3. Inspect the first incomplete shot plus provider receipt/request ID. If receipt state is unknown, do not resubmit.
4. Verify the installed version supports the requested native action. Only invoke an action whose handler and main-thread semantics are established.
5. For potentially credit-consuming work obtain specific authorization and verify the result, including actual saved media.
6. A user-controlled graceful stop is safer than killing the desktop process.

## Engineering changes
The authoritative source repository (not the installed app) owns code and skills. Read its `AGENTS.md` and `STATE.md` before changing source. Preserve unrelated worktree edits. The Mobile Web frontend is `snapgen_modules/mobile/`, HTTP routing in `snapgen_modules/snapgen_mobile_web.py`, and Tk-owned execution in `snapgen_modules/snapgen_mobile_controller.py`. The Narration page implementation is `snapgen_modules/snapgen_page_narrate.py`.
For Narration remote support, add an explicitly named `narrate` status/actions registration from the real Tk page, process operations on Tk's main thread, preserve existing project data, and use request receipts/idempotency. Never reuse Auto's controller for Narration by name alone. Test the exact running version before claiming action support.
