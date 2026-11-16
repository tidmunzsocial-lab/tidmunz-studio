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
