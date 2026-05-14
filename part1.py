messages = [
    {"user_id": "u1", "channel": "email",    "message": "Hello, I want info about grants for education."},
    {"user_id": "u2", "channel": "whatsapp", "message": " "},
    {"user_id": "",   "channel": "email",    "message": "What is the deadline?"},
    {"user_id": "u3", "channel": "email",    "message": "Please send the report again."},
    {"user_id": "u1", "channel": "whatsapp", "message": " Can you help me find funding? "},
    {"user_id": "u4", "channel": "telegram", "message": "Good morning!"},
    {"user_id": "u5", "channel": "email",    "message": "Can you send me the scholarship document?"},
    {"user_id": "u6", "channel": "whatsapp", "message": ""},
]


def clean_and_classify(messages):
    # Priority order: grant_search > report_request > general_question > unknown
    # Rationale: more specific/actionable categories take precedence over general ones.
    # e.g. "Can you send me the scholarship document?" matches both report_request and
    # general_question — we assign report_request because it's more specific and useful
    # for routing the message to the right handler.

    RULES = [
        ("grant_search",     ["grant", "funding", "deadline", "scholarship"]),
        ("report_request",   ["report", "file", "send again", "document"]),
        ("general_question", ["how", "what", "can you", "where", "why"]),
    ]

    result = []

    for msg in messages:
        # Drop messages with empty/missing user_id
        if not msg.get("user_id", "").strip():
            continue

        # Drop messages that are empty or whitespace-only
        raw_text = msg.get("message", "")
        trimmed = raw_text.strip()
        if not trimmed:
            continue

        # Classify using priority order
        text_lower = trimmed.lower()
        category = "unknown"
        for cat_name, keywords in RULES:
            if any(kw in text_lower for kw in keywords):
                category = cat_name
                break

        result.append({
            "user_id":  msg["user_id"],
            "channel":  msg["channel"],
            "message":  trimmed,
            "category": category,
        })

    return result


if __name__ == "__main__":
    cleaned = clean_and_classify(messages)
    for item in cleaned:
        print(item)