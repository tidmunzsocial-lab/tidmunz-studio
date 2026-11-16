"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const js = fs.readFileSync(path.join(__dirname, "..", "snapgen_modules", "chrome_ext", "followup.js"), "utf8");
const calls = { created: [], cleared: [], sent: 0 };
let config = {
  enabled: true, cid: "12345678-1234-1234-1234-123456789012",
  host: "TEST-WORKSTATION", story: "Test Auto",
  phase: "idle", nextAt: Date.now() + 3600000, stopRequested: false
};
let terminal = true;
let onMessage = null;
global.self = global;
global.chrome = {
  storage: { local: {
    get: async key => ({ [key]: { ...config } }),
    set: async obj => { config = { ...obj.tmProjectFollowup }; }
  } },
  alarms: {
    create: (name, opt) => calls.created.push(name),
    clear: async name => { calls.cleared.push(name); return true; },
    onAlarm: { addListener: () => {} }
  },
  runtime: { onMessage: { addListener: fn => { onMessage = fn; } } }
};
global.fetch = async url => {
  assert.match(String(url), /^http:\/\/127\.0\.0\.1:8766\/monitor\/status\?token=/);
  return {
    ok: true, json: async () => ({
      ready: true, story: "Test Auto", host: "TEST-WORKSTATION",
      checked_at: "test", stage: "ตัดต่อ", detail: "กำลังรอคนเลือกเสียง",
      busy: true, images: 2, clips: 2, total: 2,
      effect_review_pending: terminal, complete: false
    })
  };
};
vm.runInThisContext(js, { filename: "followup.js" });
assert.equal(typeof self.tmFollowupInit, "function");
self.tmFollowupInit({
  inPage: () => { calls.sent++; throw new Error("should never send"); },
  pageSend: () => { calls.sent++; throw new Error("should never send"); },
  getLink: async () => ({ port: 8766, token: "mock-only" })
});
function command(type, extra = {}) {
  return new Promise(resolve => onMessage({ type: "tm_followup_" + type, ...extra }, {}, resolve));
}
(async () => {
  await new Promise(resolve => setTimeout(resolve, 80));
  assert.equal(config.enabled, false, "must disable when native sound chooser appears");
  assert.equal(config.phase, "awaiting_effect_selection");
  assert.equal(config.nextAt, 0);
  assert.equal(config.stopRequested, true);
  assert.ok(calls.cleared.includes("tm-project-followup"), "must clear the alarm");
  assert.equal(calls.sent, 0, "must not send any new follow-up after selector");
  terminal = false;
  config = { ...config, enabled: true, stopRequested: false, phase: "idle" };
  const stopped = await command("stop");
  assert.equal(stopped.ok, true);
  assert.equal(config.enabled, false);
  assert.equal(config.phase, "stopped");
  assert.equal(config.nextAt, 0);
  assert.ok(calls.cleared.length >= 2, "manual stop must also clear alarm");
  const start = await command("start", {
    url: "https://chatgpt.com/c/12345678-1234-1234-1234-123456789012"
  });
  assert.equal(start.ok, true, "a later explicit start may re-enable");
  assert.equal(config.enabled, true);
  assert.equal(config.host, "TEST-WORKSTATION");
  assert.equal(config.story, "Test Auto");
  assert.ok(calls.created.includes("tm-project-followup"));
  assert.equal(calls.sent, 0);
  console.log("PASS: selector stops follow-up, manual stop clears alarm, explicit restart binds project");
})().catch(err => { console.error(err); process.exitCode = 1; });
