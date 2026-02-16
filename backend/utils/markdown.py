# backend/utils/markdown.py
"""
Markdown 处理工具
"""

from html import escape

try:
    import markdown2
except Exception:  # pragma: no cover
    markdown2 = None


def convert_markdown_to_html(markdown_text: str) -> str:
    """
    将 Markdown 文本转换为 HTML

    Args:
        markdown_text: Markdown 格式文本

    Returns:
        str: HTML 格式文本
    """
    if not markdown_text:
        return ""

    if markdown2 is None:
        return f"<pre>{escape(markdown_text)}</pre>"

    converter = markdown2.Markdown(
        extras=["tables", "fenced-code-blocks", "strike", "target-blank-links"]
    )
    return converter.convert(markdown_text)
