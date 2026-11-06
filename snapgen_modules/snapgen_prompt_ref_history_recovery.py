"""Conservative recovery policy for a missing ChatGPT Prompt-Ref history.

Only an unsaved Context stage may rebuild its own story chat. Image/video
requests and established official Context histories must not be replayed.
"""


def safe_to_rebuild_context_history(*, http_status, error_message,
                                    retry_allowed, require_history,
                                    context_ready, conversation_id,
                                    expected_story_hash, current_story_hash):
    error = str(error_message or "").lower()
    return bool(
        retry_allowed
        and require_history
        and int(http_status or 0) == 404
        and ("conversation_not_found" in error or "cannot load this chat" in error)
        and not context_ready
        and conversation_id
        and expected_story_hash
        and expected_story_hash == current_story_hash
    )
