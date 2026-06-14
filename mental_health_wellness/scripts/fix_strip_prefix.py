"""
Patches _strip_response_metadata_prefix in optimized_response_generator.py
to also strip bare CUID tokens that leak into the response without the
SELECTED_TECHNIQUE_ID: label.
"""

path = "src/mental_health_wellness/nodes/optimized_response_generator.py"
with open(path, encoding="utf-8") as f:
    src = f.read()

OLD = '''def _strip_response_metadata_prefix(response: str) -> str:
    """Remove accidental model metadata prefixes from user-visible replies."""
    text = str(response or "")
    text = re.sub(
        r"^\\s*SELECTED_TECHNIQUE_ID\\s*:\\s*[^\\s]+\\s*(?:\\r?\\n)?",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"^\\s*(?:0|1(?:\\.0)?|0\\.\\d+)\\s*(?:\\r?\\n)+", "", text)
    text = re.sub(
        r"^\\s*(?:emotion|sub[_ -]?emotion|sentiment|intensity|confidence)\\s*[:=]\\s*[^\\n\\r]+(?:\\r?\\n)+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text'''

NEW = '''def _strip_response_metadata_prefix(response: str) -> str:
    """Remove accidental model metadata prefixes from user-visible replies."""
    text = str(response or "")
    # Strip explicit SELECTED_TECHNIQUE_ID: <id> prefix
    text = re.sub(
        r"^\\s*SELECTED_TECHNIQUE_ID\\s*:\\s*[^\\s]+\\s*(?:\\r?\\n)?",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    # Strip bare CUID/ID token the LLM sometimes emits without the label.
    # Shape: 8-32 lowercase alphanumeric chars at the very start, followed
    # by whitespace, so it won't eat real opening words like "certainly".
    text = re.sub(
        r"^\\s*[a-z0-9]{8,32}(?=\\s)",
        "",
        text,
        count=1,
    )
    text = re.sub(r"^\\s*(?:0|1(?:\\.0)?|0\\.\\d+)\\s*(?:\\r?\\n)+", "", text)
    text = re.sub(
        r"^\\s*(?:emotion|sub[_ -]?emotion|sentiment|intensity|confidence)\\s*[:=]\\s*[^\\n\\r]+(?:\\r?\\n)+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text'''

# normalise line endings for matching
src_norm = src.replace("\r\n", "\n")
old_norm = OLD.replace("\r\n", "\n")
new_norm = NEW.replace("\r\n", "\n")

if old_norm not in src_norm:
    raise RuntimeError("Target block not found — check line endings or content drift")

patched = src_norm.replace(old_norm, new_norm, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(patched)

print("Patched successfully")
