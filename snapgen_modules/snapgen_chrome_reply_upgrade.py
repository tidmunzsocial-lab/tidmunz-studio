"""Portable, narrowly scoped upgrade of the older optional SnapGen Web worker."""

CURRENT_MARKER = "chatgpt_page_current_complete"

def _replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Unexpected Chrome worker layout")
    return text.replace(old, new, 1)

def upgrade_worker(text, bundled):
    """Migrate shared polling logic without replacing optional provider handlers."""
    start = bundled.index("  // Current ChatGPT renderer:")
    end = bundled.index("  let domUnsure = false;", start)
    block = bundled[start:end]
    if CURRENT_MARKER in text:
        # Already has the renderer fix, including locally hotfixed installs.
        return text
    text = _replace_once(text, '      if (tab.status !== "complete") continue;  // reloading: look again when it is back',
                         '      if (tab.discarded) continue;  // a live ChatGPT document may keep loading in the background')
    text = _replace_once(text, 'user_message_id: started.user_message_id || null};',
                         'user_message_id: started.user_message_id || null, existing_chat: Boolean(job.conversation_id)};')
    pos = text.index("async function pagePoll(kind, state) {")
    prefix, tail = text[:pos], text[pos:]
    old_match = '  const match = location.pathname.match(/\\/c\\/([0-9a-f-]{20,})/);'
    new_match_start = bundled.index('  const match = location.pathname.match', bundled.index('async function pagePoll('))
    new_match_end = bundled.index('\n', new_match_start)
    tail = _replace_once(tail, old_match, bundled[new_match_start:new_match_end])
    old_cid = '  const cid = state.cid || (match ? match[1] : null);'
    new_cid_start = bundled.index('  const cid = match ? match[1] : null;', bundled.index("async function pagePoll("))
    new_cid_end = bundled.index('  const idle =', new_cid_start)
    tail = _replace_once(tail, old_cid, bundled[new_cid_start:new_cid_end].rstrip())
    anchor = '  // ChatGPT can render a finished reply' if '  // ChatGPT can render a finished reply' in tail else '  let domUnsure = false;'
    tail = _replace_once(tail, anchor, block + anchor)
    old_fetch_start = tail.index('  const token = (await (await fetch("/api/auth/session")).json()).accessToken;')
    old_fetch_end = tail.index('  if (!response.ok)', old_fetch_start)
    new_fetch_start = bundled.index('  let token, auth, response;', bundled.index("async function pagePoll("))
    new_fetch_end = bundled.index('  if (!response.ok)', new_fetch_start)
    tail = tail[:old_fetch_start] + bundled[new_fetch_start:new_fetch_end] + tail[old_fetch_end:]
    tail = _replace_once(tail, '!state.before.includes(id)', '!(state.before || []).includes(id)')
    return prefix + tail
