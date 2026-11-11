"""Jira's rich-text format (Atlassian Document Format) to plain text and back."""

from typing import Any

BLOCKS = ("paragraph", "heading", "blockquote", "bulletList", "orderedList")
INLINE_ATTRS = ("mention", "emoji", "inlineCard")


def _inline(kind: str, node: dict) -> str | None:
    """Text of a leaf node, or None when the node has children to walk."""
    if kind == "text":
        return str(node.get("text", ""))
    if kind == "hardBreak":
        return "\n"
    if kind in INLINE_ATTRS:
        attrs = node.get("attrs") or {}
        return str(attrs.get("text") or attrs.get("url") or attrs.get("shortName") or "")
    return None


def adf_to_text(node: Any) -> str:
    """Flatten an ADF document (or plain string) to plain text."""
    if node is None or not isinstance(node, dict | str):
        return ""
    if isinstance(node, str):
        return node

    kind = str(node.get("type", ""))
    leaf = _inline(kind, node)
    if leaf is not None:
        return leaf

    inner = "".join(adf_to_text(child) for child in node.get("content") or [])
    if kind == "listItem":
        return "- " + inner.strip() + "\n"
    if kind == "codeBlock":
        return "```\n" + inner.strip("\n") + "\n```\n\n"
    if kind in BLOCKS:
        return inner.rstrip("\n") + "\n\n"
    return inner


def text_to_adf(text: str) -> dict:
    """Wrap plain text in an ADF document: blank lines split paragraphs, newlines break lines."""
    paragraphs = [part for part in text.split("\n\n") if part.strip()] or [text]
    content = []
    for part in paragraphs:
        inline: list[dict] = []
        for index, line in enumerate(part.split("\n")):
            if index:
                inline.append({"type": "hardBreak"})
            if line:
                inline.append({"type": "text", "text": line})
        content.append({"type": "paragraph", "content": inline})
    return {"type": "doc", "version": 1, "content": content}
