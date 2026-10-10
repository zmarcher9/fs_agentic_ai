"""Reply formatting shared by the agent and the live guide.

Every client (guide sidebar, chat.ps1, the demo) shows replies as plain
text. The prompt asks the model not to use markdown, but it still does
sometimes, so run_agent strips it before the reply is checked and returned.
"""

import re

# Whole fence-marker lines (```, ```json) only — the content inside a fence
# is kept (it's usually the steps the model formatted as a block). Inline
# ```text``` is left to the backtick removal below, so its text survives.
_FENCE_RE = re.compile(r"^[ \t]*```[\w+-]*[ \t]*(?:\n|$)", re.MULTILINE)
_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.MULTILINE)
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\([^)\s]+\)")
# The inner text can't contain '*' or a newline: keeps matching linear
# (unbounded `.+?` was quadratic on replies full of asterisks).
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
# Italics only when the asterisks hug a word, so "30 m * 50 cells" survives.
_ITALIC_RE = re.compile(r"(?<![\w*])\*(?=[^\s*])([^*\n]*[^\s*])\*(?![\w*])")


def strip_markdown(text: str) -> str:
    """Drop fence markers and strip bold, italics, headings, and links."""
    text = _FENCE_RE.sub("", text)
    text = text.replace("`", "")
    text = _HEADING_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _BOLD_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub(r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
