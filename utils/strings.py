import re


def split_preserving_whitespace(text: str) -> tuple[list[str], list[str]]:
    """Split a string into parts, preserving whitespace. The result will
    be a tuple of two lists: the parts and the whitespaces. The whitespaces
    will be strings of whitespace characters (spaces, tabs, newlines, etc.).
    The original string can be reconstructed by joining the parts and the
    whitespaces, as follows:
        ''.join([w + p for p, w in zip(parts, whitespaces)]) + whitespaces[-1]

    In other words, the first whitespace is assumed to come before the first
    part, and the last whitespace is assumed to come after the last part. If needed,
    the first and/or last whitespace element can be an empty string.

    Each part is guaranteed to be non-empty.

    Returns:
        A tuple of two lists: the parts and the whitespaces.
    """
    parts = []
    whitespaces = []
    start = 0
    for match in re.finditer(r"\S+", text):
        end = match.start()
        parts.append(match.group())
        whitespaces.append(text[start:end])
        start = match.end()
    whitespaces.append(text[start:])
    return parts, whitespaces


def remove_consecutive_blank_lines(
    lines: list[str], max_consecutive_blank_lines=1
) -> list[str]:
    """Remove consecutive blank lines from a list of lines."""
    new_lines = []
    num_consecutive_blank_lines = 0
    for line in lines:
        if line:
            # Non-blank line
            num_consecutive_blank_lines = 0
            new_lines.append(line)
        else:
            # Blank line
            num_consecutive_blank_lines += 1
            if num_consecutive_blank_lines <= max_consecutive_blank_lines:
                new_lines.append(line)
    return new_lines


def limit_number_of_words(text: str, max_words: int) -> tuple[str, int]:
    """
    Limit the number of words in a text to a given number.
    Return the text and the number of words in it. Strip leading and trailing
    whitespace from the text.
    """
    parts, whitespaces = split_preserving_whitespace(text)
    num_words = min(max_words, len(parts))
    if num_words == 0:
        return "", 0
    text = (
        "".join(p + w for p, w in zip(parts[: num_words - 1], whitespaces[1:num_words]))
        + parts[num_words - 1]
    )
    return text, num_words


def limit_number_of_characters(text: str, max_characters: int) -> str:
    """
    Limit the number of characters in a string to a given number. If the string
    is longer than the given number of characters, truncate it and append an
    ellipsis
    """
    if len(text) <= max_characters:
        return text
    if max_characters > 0:
        return text[: max_characters - 1] + "…"
    return ""
