"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const src = fs.readFileSync(path.join(__dirname, "..", "snapgen_modules",
  "chrome_ext", "followup.js"), "utf8");
const anchor = "  async function inPage(";
assert.equal(src.split(anchor).length, 2);
const self = {};
const sandbox = { self, chrome: {}, URL, Date, Promise, console };
vm.runInNewContext(src.replace(anchor,
  "  self.__testFollowupMessage = message;\n" + anchor), sandbox,
  {filename: "followup.js"});

const testUrl = "https://desktop-f1pjt4s.tailtest.ts.net/?access=DUMMY_TEST_KEY";
const text = self.__testFollowupMessage({
  host: "DESKTOP-F1PJT4S", story: "บท - มฆมานพ",
  monitor_bot: "Dino Bot Tunnel", tailscale_url: testUrl,
  checked_at: "2026-11-17 03:00", images: 0, clips: 0, total: 114,
  busy: true, stage: "วางแผน", detail: "กำลังตรวจ"
}, "TMF-1794858254895-4", 10);
assert.ok(text.includes("@Dino Bot Tunnel"), "Correct bot must be named");
assert.ok(text.includes(testUrl), "Machine URL must be included");
assert.ok(text.includes("DESKTOP-F1PJT4S"), "Correct PC must be named");
assert.ok(text.includes("ไม่จำเป็นต้องอ่านแชทเดิม"), "History not required");
assert.ok(text.includes("เลือกเสียงประกอบก่อนรวมวิดีโอ"), "Keep terminal stop");
assert.ok(src.includes("if(!live.monitor_bot || !live.tailscale_url)"),
  "No fallback to an unconfigured cross-machine bot");
console.log("PASS followup prompt routes to matching bot + Tailscale URL; no history requirement");
