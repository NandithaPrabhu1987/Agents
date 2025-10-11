def truncate_list(items, max_items):
    return items[-max_items:] if max_items and len(items) > max_items else items

def truncate_text(text: str, max_len: int) -> str:
    if not text or len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
