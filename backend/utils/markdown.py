# backend/utils/markdown.py
"""
Markdown 处理工具
"""

import markdown2


def convert_markdown_to_html(markdown_text: str) -> str:
    """
    将 Markdown 文本转换为 HTML
    
    Args:
        markdown_text: Markdown 格式文本
    
    Returns:
        str: HTML 格式文本
    """
    converter = markdown2.Markdown(extras=["tables", "fenced-code-blocks"])
    return converter.convert(markdown_text)
