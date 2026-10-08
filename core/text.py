def combine_messages(messages):
    cleaned = [m.strip() for m in messages if m and m.strip()]
    return "\n".join(cleaned)


def is_reset_command(text: str) -> bool:
    return text.strip().lower() in {"/reset", "reset", "/clear", "clear"}
