// Native ChatGPT app mentions for Tidmunz's existing Chrome-profile extension.
// This function is serialized by chrome.scripting.executeScript into chatgpt.com.
// It MUST use the real composer/menu, never inject plain Markdown @bot names.
// Any ambiguous send remains unverified; the caller must not retry blindly.
self.tmMonitorComposeWithApps = async function (payload) {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const editor = () => [...document.querySelectorAll('form [contenteditable="true"]')]
    .find(e => e.closest("form") && visible(e));
  const expected = [
    ["Tidmunz Studio AI Operator", "app://plugins_6aebd38bc5588191808c3cbd710ded69"],
    ["Dino Bot Tunnel", "app://asdk_app_6afac8c38ba88191afe3e6f5a07f43eb"],
  ];
  const visible = node => {
    if (!node || typeof node.getBoundingClientRect !== "function") return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  if (location.hostname !== "chatgpt.com")
    return {attempted:false,error:"Not chatgpt.com"};
  if (payload.cid && !location.pathname.endsWith("/c/" + payload.cid))
    return {attempted:false,error:"Wrong conversation"};
  if (!payload.cid && location.pathname !== "/")
    return {attempted:false,error:"Not a blank ChatGPT chat"};
  for (let attempt=0; attempt<30 && !editor(); attempt++) await sleep(400);
  const input=editor();
  if (!input) return {attempted:false,error:"ChatGPT composer not available"};
  if ((input.innerText || "").trim())
    return {attempted:false,error:"ChatGPT composer contains a draft"};
  // ChatGPT's Plus menu may show only "Search plugins"; the real plugin
  // mention chooser is opened by typing @name in the actual composer.
  // Use the UI's real suggestions, verify the exact chip path, never insert
  // a plain-text fake bot name or send on a failed selection.
  const choices = [
    ["Tidmunz Studio AI Operator", "app://plugins_6aebd38bc5588191808c3cbd710ded69", "@tidmunz"],
    ["Dino Bot Tunnel", "app://asdk_app_6afac8c38ba88191afe3e6f5a07f43eb", " @dino"],
  ];
  function resetOwnedDraft() {
    // Called only after the composer was confirmed empty on entry. A failed
    // mention selection must not poison the dedicated pending tab for retry.
    const text=(input.innerText||"").trim();
    if (/Tidmunz Studio \|/.test(text)) return;
    const known=/^(?:(?:Tidmunz Studio AI Operator|Dino Bot Tunnel|@tidmunz|@dino)\s*)+$/;
    if (!known.test(text)) return;
    const sel=window.getSelection(),range=document.createRange();
    range.selectNodeContents(input);
    sel.removeAllRanges();sel.addRange(range);
    input.focus();
    document.execCommand("delete",false);
  }
  function moveCaretToEnd() {
    const paragraph=input.querySelector("p:last-child") || input;
    const selection=window.getSelection(),range=document.createRange();
    range.selectNodeContents(paragraph);range.collapse(false);
    selection.removeAllRanges();selection.addRange(range);
    input.focus();
  }
  async function selectActualApp(name,path,query) {
    moveCaretToEnd();
    if (!document.execCommand("insertText",false,query)) return false;
    let button=null;
    for (let attempt=0; attempt<16; attempt++) {
      await sleep(250);
      button=[...document.querySelectorAll("button")].find(el => {
        const label=(el.innerText||"").trim();
        return visible(el) && label.startsWith(name) &&
          label.length < name.length*3+40;
      });
      if (button) break;
    }
    if (!button) return false;
    button.click();
    await sleep(250);
    return [...input.querySelectorAll("[app-mention-path]")]
      .some(el => el.getAttribute("app-mention-path")===path);
  }
  for (const [name,path,query] of choices) {
    if (!await selectActualApp(name,path,query)) {
      resetOwnedDraft();
      return {attempted:false,error:"Real ChatGPT app unavailable in @ menu: "+name};
    }
  }
  const apps=[...input.querySelectorAll("[app-mention-path]")].map(el => el.getAttribute("app-mention-path"));
  if (!expected.every(([,path])=>apps.includes(path)) || apps.length !== 2)
    return {attempted:false,error:"Required two-app binding not verified"};
  const last=input.querySelector("p:last-child") || input;
  const selection=window.getSelection(), range=document.createRange();
  range.selectNodeContents(last);range.collapse(false);
  selection.removeAllRanges();selection.addRange(range);
  input.focus();
  if (!document.execCommand("insertText",false," "+String(payload.prompt||"")))
    return {attempted:false,error:"Cannot enter monitor instructions"};
  if (!(input.innerText||"").includes(String(payload.marker||"")))
    return {attempted:false,error:"Monitor marker missing after editing"};
  const form=input.closest("form");
  const send=[...(form ? form.querySelectorAll("button") : [])].find(el =>
    !el.disabled && visible(el) && (
      ["ส่ง","send","send message"].includes(String(el.getAttribute("aria-label")||"").toLowerCase()) ||
      el.getAttribute("data-testid") === "send-button"
    ));
  if (!send) return {attempted:false,error:"ChatGPT Send control not available"};
  send.click();
  return {attempted:true,appMentionsVerified:true,appCount:apps.length};
};
