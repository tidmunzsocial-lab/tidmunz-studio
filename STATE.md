- 2026-11-18 updater: Patch and Restore use the normal Studio shutdown
  cleanup on the GUI thread before handing off. Windows process waiting
  checks whether the process actually exited, even if a handle is held.
  Regression checks cover both running and exited child processes.
  Installed update/relaunch verification remains pending.
- 2026-11-18 Chrome 1.0.57: Select tabs inside Studio's dedicated
  Chrome without requesting Windows foreground. The extension never
  opens a browser window. Reuse the assigned worker or restored idle
  worker tab, and reuse an open exact monitor conversation. Do not choose
  a window arbitrarily when the profile has multiple normal windows.
  Windows focus and embedded ChatGPT submission need live verification.
- 2026-11-18 Chrome follow-up 1.0.56: Recheck the original message
  marker after delayed confirmation or service-worker interruption.
  Recover the receipt and check tool evidence without resending. Report
  recovery only after the bound Auto project advances. Back off relay
  errors, preserve manual Stop, and clear the alarm at sound selection.
  Mock Chrome tests cover delayed confirmation and terminal cleanup.
  Live ChatGPT and Tidmunz verification remains pending.
- 2026-11-17 v2.0.40: Repair Auto economy ("ประหยัด สโลว์ 2x")
  being silently defeated by the old hard-coded 10-second clip_choice,
  including defaults in new projects and restoring old projects. GPT
  still plans narration/shot boundaries, then an auto-duration clip
  selector chooses the shortest supported paid 6/10/15s for each
  Grok shot; every economy shot without spoken dialogue uses Slow 2x
  (6s->12s, 10s->20s), while lip-synced dialogue stays normal speed.
  The selected explicit Grok model remains fixed (no switch to Muse).
  Previously completed clips and accepted paid UUIDs are never reassigned
  or resubmitted; no storyboard/image/clip re-generation merely because
  the old plan recorded fixed 10s. Migration of legacy hidden default
  is one-time and preserves every existing asset and completed flag.
  New explicit fixed-length choice turns off economy visibly instead
  of silently nullifying Slow 2x. Tested provider 6 vs 10 choices, scene
  timing, spoken dialogue, old 114-scene/72-clip preservation, and
  pending paid UUID protection.
- 2026-11-17 v2.0.39 urgent fix: packaging v2.0.38 overwrote a 1.0.54
  Chrome extension hotfix with old 1.0.53 source on app restart.
  snapgen_chrome_relay._write_extension now never downgrades an already
  newer installed extension, but still upgrades whenever the bundled
  extension is newer. Both shipped folders contain Chrome extension
  1.0.55, including real @app mentions and reusable one-owned-tab logic.
  Auto bootstrap now distinguishes an uncertain OLD scheduled follow-up
  from a separately reserved UNSENT first project chat. The reserved
  unsent SAME project tab may safely send once; prior uncertain marker is
  archived intact, never replayed. An attempted send or navigated pending
  tab is never resent. Python and JS regressions cover downgrade,
  same-version replacement, upgrade and uncertain-safe bootstrap.
- 2026-11-17 Chrome monitor tab & real app mention fix: ChatGPT no longer
  exposes the Tidmunz app in the old Plus-menu button list. The Tidmunz
  Chrome extension uses native @tidmunz and @dino autocomplete in the actual
  ChatGPT composer, validates the two exact app-mention-path chips and
  refuses to send if either is unavailable. Project monitoring now reuses
  exactly one extension-owned chat tab across stories, never repurposes the
  user's active/manual tab, and refuses to navigate away from drafts or a
  responding assistant. The two image worker tabs remain separately owned
  for parallel image generation. Extension manifest bumped 1.0.53 -> 1.0.54.
  Tests cover real DOM chip paths, no fake text, tab reuse, draft protection,
  and the follow-up send/stop behavior. Existing conversations/receipts stay
  intact and no automated duplicate retry is introduced.
- 2026-11-17: Retroactive Auto monitoring for existing partial films: if the
  per-story monitor binding is missing or incomplete, run only the monitor
  bootstrap once BEFORE resuming the currently requested stage; preserve every
  already-completed stage and all saved images, clips, and paid receipts.
  Do not rebind a confirmed monitor on every start. The existing Chrome
  extension monitor_bootstrap arms its own scheduled Alarm; no extra watcher.
  Existing legacy skip for partially-produced films was removed; scoped tests
  were updated to cover old paid clips, targeted resumes, absent bindings,
  valid bindings, non-video mode, and duplicate prevention.
  Version footer now distinguishes intentional post-install code edits from
  truly missing files. Source-only until a safe app restart following Release.
- 2026-11-17: Follow-up routing: authenticated Chrome relay reads **this** PC's
  \`snapgen_data/followup_device_bot.json\` ({host,bot}) and current
  \`mobile_web_url.txt\`, validates exact host and access-token match, and includes
  the bot name and full Tailscale URL in the extension follow-up prompt. The
  access key is never committed or hardcoded. Unconfigured/mismatched targets
  fail closed (no prompt sent), no other-machine bot fallback. Prompt no longer
  requires reading chat history. The sound-effect review stop is unchanged.
  Source extension is v1.0.52, incorporating the installed 1.0.51 composer fixes.
  Installed source files staged; activation requires a safe reload/restart
  **after active image/text jobs**, not during GPT processing.
- 2026-11-17: Footer status UI now uses one compact row: "ติดตาม: อีก N นาที" before Chrome/GPT/Tailscale. No new watcher; live program files were patched, but restart deferred while Auto was busy. Added layout/label regression checks.
# 2026-11-16 — Chrome Extension Follow-up footer (source-only)

- Adds a separate bottom-right footer status for the existing Tidmunz ChatGPT `followup.js`. It is independent of GPT image/video/SnapGen job indicators.
- The installed Chrome extension reports its own Alarm, active phase, next check and configured minutes to the authenticated local Chrome relay. The existing `tidmunz-wake` Alarm handles heartbeat. No duplicate watcher or Windows Scheduled Task is created.
- Display: "เฝ้าติดตาม · นัด GPT ตรวจอีก N นาที (รอบ M นาที)" with dynamic times. Absent/stale Alarm, disabled follow-up, ongoing check and human audio-effect selection are distinguished.
- Chrome Extension version 1.0.50 is the next source version. No Release or running-app restart was authorized; live Auto was still processing refs, so installed GUI/service-worker verification remains pending until a safe restart.
- Tests: Python formatting/relay endpoint, Node Chrome-alarm mock and main regression suite (see command outputs).
- This feature does not guarantee GPT remains actively reasoning between turns; it accurately shows the extension's scheduled attempt to send a same-chat follow-up.
