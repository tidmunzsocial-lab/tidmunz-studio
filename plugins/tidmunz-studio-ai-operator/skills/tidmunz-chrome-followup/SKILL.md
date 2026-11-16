---
name: tidmunz-chrome-followup
description: Operate and diagnose Tidmunz ChatGPT's existing same-chat Auto follow-up extension, including safe periodic wake-ups and a permanent stop when the native sound-effect chooser opens.
---

# Tidmunz ChatGPT Chrome Extension — same-chat Auto follow-up

## Purpose and owner

The existing Tidmunz ChatGPT Chrome extension performs two different jobs inside the application's own Chrome profile.

1. Its background.js and the local snapgen_chrome_relay.py run requested ChatGPT text/image operations for the Windows app.
2. Its followup.js reopens the specifically bound existing ChatGPT conversation, reads current Auto status and sends a tagged follow-up message to that conversation, asking an available GPT to inspect and continue the authorized same job. followup_popup.html and followup_popup.js expose real Start, Stop, Check Now and diagnostic controls.

Do not conflate the extension with the computer connector (Dino Bot, Tailscale, or another user-named MyComp Bot) or with the AI Operator plugin. The connector gives GPT access to the selected device. The extension supplies a scheduled new chat turn within the same story conversation. It is NOT a permanently running GPT model.

## Correct local implementation (Chrome Extension 1.0.49 or later)

- The extension service worker imports followup.js and initializes it through tmFollowupInit. Never create a competing watcher, second extension, separate ChatGPT bridge or repeating ChatGPT automation for the same job.
- followup.js reads a read-only /monitor/status endpoint on the existing authenticated Chrome relay on this PC (the relay proxies this installation's Mobile Web /api/status). The endpoint returns only sanitized progress, not Mobile Web access credentials.
- Bind the monitor to the real current Auto project and its ChatGPT conversation when enabled. A saved conversation URL is not permission to switch machines or use another story. Re-verify device identity using tidmunz-device-routing before GPT performs remote edits or paid actions.
- Read actual Auto ready, busy, story, stage, detail, image/clip counts, and effect_review_pending. The native app sets effect_review_pending=true while the actual 'เลือกเสียงประกอบก่อนรวมวิดีโอ' window is waiting for human selection.
- Follow-up messages are tagged, serialized and verified against the conversation before sending again. Respect user drafts, active ChatGPT replies, the extension text/image queue, unknown send state and cloud provider receipts. Never blindly re-send a possibly accepted message or paid generation.
- The Chrome alarm runs only for an enabled bound project. It may be delayed when Chrome, authentication or local app is offline. An alarm only wakes the extension; it cannot guarantee a GPT reply or continuous reasoning.

## Hard human-review stop and full teardown

When effect_review_pending=true or the native UI is demonstrably at the sound-effect selection screen, STOP before any more follow-up message.

1. Set enabled=false, stopRequested=true, phase=awaiting_effect_selection, nextAt=0 in extension storage.
2. Clear the Chrome follow-up alarm, not merely skip a reply. Keep the normal tidmunz-wake alarm that serves unrelated queued text/image jobs.
3. Do NOT select green/red/grey audio items, press 'ยืนยันและรวมวิดีโอ', continue the video stage, remux or render on behalf of the user. Native Auto remains waiting for the human choice. Manual Stop also disables and clears the alarm.
4. Never resume on extension restart or on a new chat without explicit user-authorized Start for that exact job. Completed, wrong project/device or repeatedly failing monitoring similarly disables the follow-up rather than indefinitely polling.
5. If the original message may already have been sent, verify its unique marker and do not create a duplicate. No script can retract a delivered message or stop an assistant reply already in progress.

The sound-effect chooser is the default end point for the current Auto handoff, regardless of older skills that say to continue automatically to final export. Human selection and later export require separate user action.

## Verification and safety

Before claiming working follow-up, verify the installed manifest and service worker actually load followup.js, the Chrome relay serves authenticated status, the real Mobile Web Auto project exists, the conversation/device binding matches, the alarm is active only when appropriate, and the transition to awaiting_effect_selection clears it. A file on disk alone does not mean the extension loaded it.

When the local app is stopped or relay cannot be reached, report the specific unverified boundary. Diagnose without starting another Auto job, resetting GPT conversation IDs, changing providers, spawning watchers or spending credits. Do not log, paste or publish API keys, browser cookies, access URLs, message IDs or private story content. Keep machine-specific device and project identifiers out of reusable skills.
