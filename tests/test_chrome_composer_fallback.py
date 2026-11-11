"""Protect the Chrome composer fallback and forced service-worker reload."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "snapgen_modules" / "chrome_ext" / "background.js"
MANIFEST = ROOT / "snapgen_modules" / "chrome_ext" / "manifest.json"


def test_composer_fallback_in_all_five_prep_send_and_verify_paths():
    code = SOURCE.read_text(encoding="utf-8")
    assert code.count("""document.querySelector('form [contenteditable="true"]')""") == 5
    assert code.index("""document.querySelector('form [contenteditable="true"]')""") < code.index('async function pageSend(')


def test_extension_version_bumped_to_reload_previous_worker():
    assert json.loads(MANIFEST.read_text(encoding="utf-8"))["version"] == "1.0.48"


def test_open_page_accepts_contenteditable_without_legacy_prosemirror_role():
    node = shutil.which("node") or (
        r"C:\Program Files\nodejs\node.exe" if Path(r"C:\Program Files\nodejs\node.exe").exists() else None
    )
    if not node:
        pytest.skip("Node unavailable")
    source = SOURCE.read_text(encoding="utf-8")
    function = source[source.index("async function openPage("):source.index("async function inPage(")]
    script = r"""
const target = 'https://chatgpt.com/';
global.location = new URL(target);
let found = 0;
global.document = {
 title:'ChatGPT', body:{innerText:'ChatGPT ready'},
 querySelector: selector => {
   if (selector === 'form [contenteditable="true"]') {found++; return {isConnected:true};}
   return null;
 }};
global.chrome = {tabs:{get: async()=>({url:target}),update:async()=>{throw Error('Unexpected navigation');}}};
const sleep = async()=>{};
async function inPage(id, func, args) {return func(...args);}
openPage(7,target).then(id => {
 if (id !== 7 || found !== 1) throw Error('Editor fallback was not used');
 console.log('composer-ready');
}).catch(err=>{console.error(err);process.exitCode=1;});
"""
    output = subprocess.run([node, "-e", function + script], text=True, capture_output=True, check=True)
    assert output.stdout.strip() == "composer-ready"
