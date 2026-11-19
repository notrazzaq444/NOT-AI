SHORT_TERM_MESSAGE_LIMIT = 30

def select_context(messages: list[dict], limit: int = SHORT_TERM_MESSAGE_LIMIT):
    """Keep the most recent messages as short-term context."""
    return messages[-limit:]
