"""Deterministic text syntax inspection and bounded repair.

Consumes content and extension only; never reads, writes, promotes or schedules.
Callers retain exact saved-target binding and acceptance authority.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional, Sequence


_CSS_BACKGROUND_DECLARATION_RE = re.compile(
    r'(?P<property>\bbackground(?:-image)?\b)\s*:\s*(?P<value>[^;{}]+)',
    re.IGNORECASE,
)


_CSS_DECLARATION_VALUE_RE = re.compile(
    r'(?m)(?P<prefix>[{;]\s*)(?P<property>-{0,2}[a-z_][a-z0-9_-]*)\s*:\s*(?P<value>[^;{}]+)',
    re.IGNORECASE,
)


_CSS_HTML_ENTITY_FRAGMENT_IN_FUNCTION_RE = re.compile(
    r'\b(?:rgb|rgba|hsl|hsla|linear-gradient|radial-gradient|color-mix)\s*\([^;{}]*&#',
    re.IGNORECASE,
)


_CSS_INVALID_BACKGROUND_SHORTHAND_TOKEN_RE = re.compile(
    r'(?<![A-Za-z0-9_-])(?P<token>no-(?:scale|format|array))(?![A-Za-z0-9_-])',
    re.IGNORECASE,
)


_CSS_INVALID_BACKGROUND_SHORTHAND_TOKENS = {
    'no-scale': 'no-repeat',
    'no-format': 'no-repeat',
    'no-array': 'no-repeat',
}


_CSS_KNOWN_INVALID_PROPERTY_VALUES = {
    ('box-sizing', 'border-width'): 'border-box',
}


_HTML_CLASS_ATTR_RE = re.compile(
    r'\bclass\s*=\s*(?P<quote>["\'])(?P<value>.*?)(?P=quote)',
    re.IGNORECASE | re.DOTALL,
)


_HTML_ATTRIBUTE_VALUE_RE = re.compile(
    r'\b(?P<name>[a-z_:][a-z0-9_:.:-]*)\s*=\s*(?P<quote>["\'])(?P<value>.*?)(?P=quote)',
    re.IGNORECASE | re.DOTALL,
)


_HTML_BARE_DUPLICATE_ATTRIBUTE_RE = re.compile(
    r'(?<![A-Za-z0-9_:-])(?P<name>class|id|href|src|rel|alt|title|type|name|role|aria-[a-z0-9_-]+|data-[a-z0-9_-]+)\b'
    r'\s+(?P=name)\s*=',
    re.IGNORECASE,
)


_HTML_MALFORMED_STYLESHEET_LINK_ATTR_RE = re.compile(
    r'<link\b(?P<prefix>[^>]*?)\brel\s*=\s*(?P<quote>["\'])'
    r'stylesheet\s*=\s*(?P=quote)\s*(?P<href>href\s*=\s*(?P<hquote>["\'])(?P<value>[^"\']*)(?P=hquote))'
    r'(?P<suffix>[^>]*)>',
    re.IGNORECASE | re.DOTALL,
)


_HTML_SYNTAX_VOID_TAGS = {
    'area',
    'base',
    'br',
    'col',
    'embed',
    'hr',
    'img',
    'input',
    'link',
    'meta',
    'param',
    'source',
    'track',
    'wbr',
}


_HTML_SYNTAX_REPAIR_CLOSING_TAGS = _HTML_SYNTAX_VOID_TAGS | {
    'a',
    'article',
    'aside',
    'body',
    'button',
    'canvas',
    'code',
    'dd',
    'details',
    'dialog',
    'div',
    'dl',
    'dt',
    'figcaption',
    'figure',
    'footer',
    'form',
    'h1',
    'h2',
    'h3',
    'h4',
    'h5',
    'h6',
    'head',
    'header',
    'html',
    'label',
    'li',
    'main',
    'menu',
    'nav',
    'ol',
    'option',
    'p',
    'picture',
    'pre',
    'script',
    'section',
    'select',
    'small',
    'span',
    'strong',
    'style',
    'summary',
    'table',
    'tbody',
    'td',
    'template',
    'textarea',
    'tfoot',
    'th',
    'thead',
    'tr',
    'ul',
    'video',
}


_HTML_STRAY_KNOWN_CLOSING_TAG_REMOVABLE_TAGS = {
    'a',
    'article',
    'aside',
    'button',
    'code',
    'dd',
    'details',
    'dialog',
    'div',
    'dl',
    'dt',
    'figcaption',
    'figure',
    'footer',
    'form',
    'h1',
    'h2',
    'h3',
    'h4',
    'h5',
    'h6',
    'header',
    'label',
    'li',
    'main',
    'menu',
    'nav',
    'ol',
    'p',
    'pre',
    'section',
    'small',
    'span',
    'strong',
    'summary',
    'ul',
}


_HTML_SYNTAX_REPAIR_TAG_ALT = '|'.join(
    re.escape(tag)
    for tag in sorted(_HTML_SYNTAX_REPAIR_CLOSING_TAGS, key=len, reverse=True)
)


_HTML_MALFORMED_CLOSE_EMBEDDED_TAG_RE = re.compile(
    rf'</<[^>\n]{{1,80}}>(?P<tag>{_HTML_SYNTAX_REPAIR_TAG_ALT})\s*>',
    re.IGNORECASE,
)


_HTML_MALFORMED_CLOSE_PREFIX_RE = re.compile(
    rf'</(?P<prefix>[^a-z0-9\s<>/:-]+)(?P<tag>{_HTML_SYNTAX_REPAIR_TAG_ALT})\s*>',
    re.IGNORECASE,
)


_HTML_MALFORMED_CLOSE_KNOWN_SUFFIX_RE = re.compile(
    rf'</\s*(?!(?:{_HTML_SYNTAX_REPAIR_TAG_ALT})\s*>)'
    rf'(?P<prefix>[a-z0-9]{{1,12}})(?P<tag>{_HTML_SYNTAX_REPAIR_TAG_ALT})\s*>',
    re.IGNORECASE,
)


_HTML_STRAY_NESTED_CLOSE_RE = re.compile(
    rf'</\s*</\s*(?P<tag>{_HTML_SYNTAX_REPAIR_TAG_ALT})\s*>',
    re.IGNORECASE,
)


_HTML_STRAY_FORMATTING_CLOSE_TAG_ALT = r'strong|em|b|i'


_HTML_STRAY_FORMATTING_CLOSE_IN_OPEN_TAG_RE = re.compile(
    rf'<\s*</\s*(?P<format_tag>{_HTML_STRAY_FORMATTING_CLOSE_TAG_ALT})\s*>\s*'
    rf'(?P<tag>{_HTML_SYNTAX_REPAIR_TAG_ALT})(?P<boundary>[\s>/])',
    re.IGNORECASE,
)


_HTML_PARTIAL_OPEN_TAG_WITH_STRAY_FORMATTING_CLOSE_RE = re.compile(
    rf'<(?P<tag>{_HTML_SYNTAX_REPAIR_TAG_ALT})(?P<attrs>[^<>\n]{{0,80}}?)'
    rf'</\s*(?P<format_tag>{_HTML_STRAY_FORMATTING_CLOSE_TAG_ALT})\s*>\s*'
    rf'(?=<(?P=tag)(?:[\s>/]))',
    re.IGNORECASE,
)


_HTML_MALFORMED_OPEN_PREFIX_KNOWN_TAG_RE = re.compile(
    rf'<(?P<prefix>[^a-z0-9\s<>/:-]{{1,12}})(?P<tag>{_HTML_SYNTAX_REPAIR_TAG_ALT})(?P<boundary>[\s>/])',
    re.IGNORECASE,
)


_HTML_DUPLICATE_OPEN_ANGLE_KNOWN_TAG_RE = re.compile(
    rf'<<(?P<tag>{_HTML_SYNTAX_REPAIR_TAG_ALT})(?P<boundary>[\s>/])',
    re.IGNORECASE,
)


_HTML_STRAY_PUNCTUATION_PSEUDO_TAG_BEFORE_KNOWN_TAG_RE = re.compile(
    rf'(?P<prefix>^|[\s>])(?P<fragment><[)\]}}]+)\s*'
    rf'(?=<\s*(?P<tag>{_HTML_SYNTAX_REPAIR_TAG_ALT})(?P<boundary>[\s>/]))',
    re.IGNORECASE | re.MULTILINE,
)


_HTML_QUOTED_KNOWN_OPEN_TAG_RE = re.compile(
    rf'(?P<prefix>^|[\s>])(?P<quote>["\'])(?P<tag>{_HTML_SYNTAX_REPAIR_TAG_ALT})(?P=quote)'
    r'(?P<attrs>\s+[^<>\n]*?)>',
    re.IGNORECASE | re.MULTILINE,
)


_HTML_REPEATED_SIBLING_CLASS_HINT_RE = re.compile(
    r'(?:^|[-_])(card|item|panel|tile|feature|story|gallery|slide|entry)(?:$|[-_])',
    re.IGNORECASE,
)


_HTML_SYNTAX_TAG_RE = re.compile(
    r'<!--[\s\S]*?-->|<![a-z][^>]*>|<(?P<close>/)?(?P<tag>[a-z][a-z0-9:-]*)(?P<attrs>[^<>]*?)(?P<self>/)?>',
    re.IGNORECASE,
)


_HTML_UNTERMINATED_KNOWN_OPEN_TAG_RE = re.compile(
    rf'<(?P<tag>{_HTML_SYNTAX_REPAIR_TAG_ALT})\b'
    r'(?P<attrs>[^<>\r\n]*[^\s<>\r\n][^<>\r\n]*)'
    r'(?=\r?\n[ \t]*<)',
    re.IGNORECASE,
)


_HTML_RAW_TEXT_BLOCK_RE = re.compile(
    r'<(?P<tag>script|style)\b[^>]*>[\s\S]*?</\s*(?P=tag)\s*>',
    re.IGNORECASE,
)


_HTML_HERO_ATTR_VALUE_RE = re.compile(r'(^|[\s_-])hero($|[\s_-])', re.IGNORECASE)


_HTML_HERO_LANDMARK_TAGS = {'footer', 'main'}


_HTML_MARKUP_IN_ATTRIBUTE_RE = re.compile(
    r'=\s*"[^"]*</[a-z][^"]*"|=\s*\'[^\']*</[a-z][^\']*\'',
    re.IGNORECASE,
)


_HTML_MALFORMED_CLASS_ATTR_COLON_RE = re.compile(
    r'(?<!["\'=A-Za-z0-9_-])\bclass\s*:\s*(?P<value>[^\s"\'<>/][^"\'<>]*?)(?P<quote>["\'])',
    re.IGNORECASE,
)


_HTML_MALFORMED_ANCHOR_OPEN_TAG_RE = re.compile(
    rf'<(?P<tag>(?!(?:{_HTML_SYNTAX_REPAIR_TAG_ALT})\b)a[a-z0-9]{{1,15}})'
    r'(?P<attrs>[^<>\n]*\bhref\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s<>]+)[^<>\n]*)>'
    r'(?P<body>[\s\S]{0,2000}?)</a>'
    r'(?P<obsolete_close>\s*</\s*(?P=tag)\s*>)?',
    re.IGNORECASE,
)


_HTML_MALFORMED_FORMATTED_ANCHOR_FRAGMENT_RE = re.compile(
    r'<<(?P<wrapper>em|strong|b|i)>\s*a\s+'
    r'(?P<attrs>[^<>\n]{0,400}\bhref\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s<>]+)[^<>\n]*)>'
    r'(?P<body>[\s\S]{0,1200}?)</\s*(?P=wrapper)\s*>',
    re.IGNORECASE,
)


_HTML_HREF_ALLOWED_TAGS = {'a', 'area', 'base', 'link'}


_HTML_HREF_ALLOWED_TAG_ALT = '|'.join(
    re.escape(tag)
    for tag in sorted(_HTML_HREF_ALLOWED_TAGS, key=len, reverse=True)
)


_HTML_HREF_ATTR_RE = re.compile(r'\bhref\s*=', re.IGNORECASE)


_HTML_STYLESHEET_REL_TOKENS = {'stylesheet', 'preload'}


_HTML_UNSUPPORTED_HREF_ELEMENT_RE = re.compile(
    rf'<(?P<tag>(?!(?:{_HTML_HREF_ALLOWED_TAG_ALT})\b)[a-z][a-z0-9:-]{{0,30}})'
    r'(?P<attrs>[^<>\n]*\bhref\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s<>]+)[^<>\n]*)>'
    r'(?P<body>[\s\S]{0,2000}?)</\s*(?P=tag)\s*>',
    re.IGNORECASE,
)


_HTML_UNSUPPORTED_NAV_ANCHOR_WRAPPER_RE = re.compile(
    rf'<(?P<tag>(?!(?:{_HTML_SYNTAX_REPAIR_TAG_ALT})\b)[a-z][a-z0-9:-]{{0,30}})'
    r'(?P<attrs>[^<>\n]*)>\s*'
    r'(?P<anchor><a\b[^>]*>[\s\S]{0,2000}?</a>)\s*'
    r'</\s*(?P=tag)\s*>',
    re.IGNORECASE,
)


_HTML_LITERAL_UNSUPPORTED_TAG_RE = re.compile(
    r'<(?P<tag>unsupported)(?P<attrs>[^<>\n]*)>'
    r'(?P<body>[\s\S]{0,2000}?)</\s*(?P=tag)\s*>',
    re.IGNORECASE,
)


_HTML_HREF_REPAIR_EXCLUDED_TAGS = _HTML_SYNTAX_REPAIR_CLOSING_TAGS | {
    'animate',
    'animatemotion',
    'animatetransform',
    'feimage',
    'image',
    'mpath',
    'textpath',
    'use',
}


_HTML_MALFORMED_CLASS_ONLY_OPEN_TAG_RE = re.compile(
    rf'<\s+(?P<class>[_A-Za-z][A-Za-z0-9_-]{{1,80}})(?P<quote>["\'])\s*>'
    rf'(?P<body>[\s\S]{{0,1200}}?)</\s*(?P<close>{_HTML_SYNTAX_REPAIR_TAG_ALT})\s*>',
    re.IGNORECASE,
)


_HTML_UNKNOWN_CLASS_WRAPPER_TAG_RE = re.compile(
    rf'<(?P<tag>(?!(?:{_HTML_SYNTAX_REPAIR_TAG_ALT})\b)[a-z][a-z0-9]{{1,30}})'
    r'(?P<attrs>[^<>\n]*\b(?:class|id)\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s<>]+)[^<>\n]*)>'
    r'(?P<body>[\s\S]{0,4000}?)</\s*(?P=tag)\s*>',
    re.IGNORECASE,
)


_CSS_KNOWN_PROPERTY_TYPOS = {
    'align-s_items': 'align-items',
    'background-transparent': 'background',
    'font-mask': 'font-family',
    'font-scale': 'font-size',
    'font-width': 'font-weight',
    'letter-lag': 'letter-spacing',
    'letter-length': 'letter-spacing',
    'margin-blop': 'margin-bottom',
    'scroll-template': 'scroll-behavior',
    'text-allign': 'text-align',
}


_CSS_AMBIGUOUS_PROPERTY_TYPOS = {
    'margin-length': 'margin, margin-left, or another margin-side property',
}


_CSS_DECLARATION_NAME_RE = re.compile(
    r'(?m)(?P<prefix>[{;]\s*)(?P<property>[^{};:\n][^{};:]*?)\s*:',
)


_CSS_DECLARATION_NAME_FORMATTING_TAG_RE = re.compile(
    r'</?\s*(?:strong|b|em|i)\s*/?>',
    re.IGNORECASE,
)


_CSS_PROPERTY_IDENTIFIER_RE = re.compile(
    r'^(?:--[A-Za-z0-9_-]+|-?[A-Za-z_][A-Za-z0-9_-]*)$',
)


_CSS_CUSTOM_PROPERTY_DEFINITION_RE = re.compile(
    r'(?m)(?<![A-Za-z0-9_-])(?P<name>--[A-Za-z0-9_-]+)\s*:',
)


_CSS_VAR_REFERENCE_RE = re.compile(
    r'\bvar\(\s*(?P<name>---[A-Za-z0-9_-]+)(?P<suffix>\s*(?:,[^)]*)?\))',
    re.IGNORECASE,
)


_CSS_ANY_VAR_REFERENCE_RE = re.compile(
    r'\bvar\(\s*(?P<name>--[A-Za-z0-9_-]+)(?P<suffix>\s*(?:,[^)]*)?\))',
    re.IGNORECASE,
)


_CSS_INVALID_FUNCTION_TOKENS = (
    (
        re.compile(r'\bvar\s+var\s*\(', re.IGNORECASE),
        'var(',
        'css_invalid_duplicated_var_function_token',
    ),
    (
        re.compile(r'\bvarint\s*\(', re.IGNORECASE),
        'var(',
        'css_invalid_varint_function_token',
    ),
    (
        re.compile(r'\bvar\s*/\s*\(', re.IGNORECASE),
        'var(',
        'css_invalid_var_function_token',
    ),
)


_CSS_INVALID_VAR_SLASH_REFERENCE_RE = re.compile(
    r'\bvar\s*/\s*(?P<name>-{0,2}[A-Za-z0-9_-]+)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_EXTENSION_ALIASES = {
    'htm': 'html',
    'markdown': 'md',
    'plain': 'txt',
    'text': 'txt',
    'xhtml': 'html',
}


def _normalize_text_artifact_extension(value: Any) -> str:
    token = str(value or '').strip().lower().lstrip('.')
    return _TEXT_ARTIFACT_EXTENSION_ALIASES.get(token, token)


def _strip_fenced_json_boundary(text: str) -> str:
    stripped = str(text or '').strip()
    match = re.fullmatch(r'```[a-z0-9_-]*\s*\n(?P<body>[\s\S]*?)\n?```', stripped, flags=re.IGNORECASE)
    if match:
        return match.group('body').strip()
    return stripped


def _line_number_for_offset(text: str, offset: int) -> int:
    try:
        bounded = max(0, min(int(offset), len(text)))
    except (TypeError, ValueError):
        bounded = 0
    return str(text or '').count('\n', 0, bounded) + 1


def _html_open_tag_stack_before_offset(content: str, offset: int) -> list[str]:
    text = str(content or '')
    try:
        bounded = max(0, min(int(offset), len(text)))
    except (TypeError, ValueError):
        bounded = 0
    stack: list[str] = []
    for match in _HTML_SYNTAX_TAG_RE.finditer(text[:bounded]):
        token = match.group(0)
        if token.startswith('<!--') or token.startswith('<!'):
            continue
        tag = str(match.group('tag') or '').strip().lower()
        if not tag:
            continue
        if match.group('close'):
            if tag in stack:
                while stack:
                    current = stack.pop()
                    if current == tag:
                        break
            continue
        if tag not in _HTML_SYNTAX_VOID_TAGS and not match.group('self'):
            stack.append(tag)
    return stack


def _html_attrs_have_hero_marker(attrs: str) -> bool:
    for match in _HTML_CLASS_ATTR_RE.finditer(str(attrs or '')):
        value = str(match.group('value') or '').strip()
        if value and _HTML_HERO_ATTR_VALUE_RE.search(value):
            return True
    return False


def _html_hero_header_landmark_containment_defects(
    content: str,
) -> list[dict[str, Any]]:
    text = str(content or '')
    if not text.strip():
        return []
    stack: list[dict[str, Any]] = []
    defects: list[dict[str, Any]] = []
    for match in _HTML_SYNTAX_TAG_RE.finditer(text):
        token = match.group(0)
        if token.startswith('<!--') or token.startswith('<!'):
            continue
        tag = str(match.group('tag') or '').strip().lower()
        if not tag:
            continue
        if match.group('close'):
            for index in range(len(stack) - 1, -1, -1):
                if str(stack[index].get('tag') or '') == tag:
                    del stack[index:]
                    break
            continue

        if tag in _HTML_HERO_LANDMARK_TAGS:
            hero_header = next(
                (
                    item
                    for item in reversed(stack)
                    if str(item.get('tag') or '') == 'header'
                    and item.get('hero_header') is True
                ),
                None,
            )
            if hero_header:
                defects.append(
                    {
                        'landmark_tag': tag,
                        'landmark_line': _line_number_for_offset(text, match.start()),
                        'landmark_start': match.start(),
                        'header_line': hero_header.get('line'),
                        'header_start': hero_header.get('start'),
                    }
                )

        if tag in _HTML_SYNTAX_VOID_TAGS or match.group('self'):
            continue
        attrs = str(match.group('attrs') or '')
        stack.append(
            {
                'tag': tag,
                'line': _line_number_for_offset(text, match.start()),
                'start': match.start(),
                'hero_header': tag == 'header' and _html_attrs_have_hero_marker(attrs),
            }
        )
    return defects


def _html_unsupported_nav_anchor_wrapper_issue(
    content: str,
    match: re.Match[str],
) -> Optional[str]:
    tag = str(match.group('tag') or '').strip().lower()
    attrs = str(match.group('attrs') or '').strip()
    if (
        not tag
        or tag in _HTML_SYNTAX_REPAIR_CLOSING_TAGS
        or '-' in tag
        or ':' in tag
        or attrs
    ):
        return None
    stack = _html_open_tag_stack_before_offset(content, match.start())
    in_navigation_context = (
        'nav' in stack
        or (stack and stack[-1] == 'li' and any(parent in {'ul', 'ol', 'menu'} for parent in stack[:-1]))
    )
    if not in_navigation_context:
        return None
    return (
        f'HTML has unsupported navigation anchor wrapper <{tag}> at line '
        f'{_line_number_for_offset(content, match.start())}; unwrap it and keep the <a> element'
    )


def _html_attribute_values(attrs: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for match in _HTML_ATTRIBUTE_VALUE_RE.finditer(str(attrs or '')):
        name = str(match.group('name') or '').strip().lower()
        if name:
            values.setdefault(name, []).append(str(match.group('value') or ''))
    return values


def _html_href_targets_stylesheet(value: str) -> bool:
    lowered = str(value or '').strip().lower()
    if not lowered:
        return False
    without_fragment = lowered.split('#', 1)[0]
    without_query = without_fragment.split('?', 1)[0]
    return (
        without_query.endswith('.css')
        or 'fonts.googleapis.com/css' in lowered
        or '/css2' in lowered
        or '/css?' in lowered
    )


def _html_link_stylesheet_rel_is_invalid(attrs: str) -> bool:
    values = _html_attribute_values(attrs)
    href = next((item for item in values.get('href', []) if item.strip()), '')
    if not _html_href_targets_stylesheet(href):
        return False
    rel = next((item for item in values.get('rel', []) if item.strip()), '')
    if not rel:
        return True
    rel_tokens = {
        token.strip().lower()
        for token in re.split(r'\s+', rel)
        if token.strip()
    }
    return not bool(rel_tokens & _HTML_STYLESHEET_REL_TOKENS)


def _html_attrs_have_unbalanced_quote(attrs: str) -> bool:
    quote: Optional[str] = None
    for char in str(attrs or ''):
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
    return quote is not None


def _offset_is_inside_spans(offset: int, spans: Sequence[tuple[int, int]]) -> bool:
    return any(start <= offset < end for start, end in spans)


def _html_stray_open_angle_offsets(content: str) -> list[int]:
    text = str(content or '')
    valid_spans = [match.span() for match in _HTML_SYNTAX_TAG_RE.finditer(text)]
    raw_text_spans = [match.span() for match in _HTML_RAW_TEXT_BLOCK_RE.finditer(text)]
    offsets: list[int] = []
    for match in re.finditer(r'<', text):
        offset = match.start()
        if _offset_is_inside_spans(offset, valid_spans):
            continue
        if _offset_is_inside_spans(offset, raw_text_spans):
            continue
        offsets.append(offset)
        if len(offsets) >= 6:
            break
    return offsets


def _html_syntax_sanity_issues(content: str) -> list[str]:
    text = str(content or '')
    if not text.strip():
        return []
    issues: list[str] = []
    raw_text_spans = [match.span() for match in _HTML_RAW_TEXT_BLOCK_RE.finditer(text)]
    for match in _HTML_MALFORMED_CLASS_ONLY_OPEN_TAG_RE.finditer(text):
        issues.append(
            f'HTML has malformed class-only opening tag at line {_line_number_for_offset(text, match.start())}'
        )
        if len(issues) >= 6:
            return issues
    for match in _HTML_MARKUP_IN_ATTRIBUTE_RE.finditer(text):
        if _offset_is_inside_spans(match.start(), raw_text_spans):
            continue
        issues.append(
            f'HTML attribute contains markup-like closing tag at line {_line_number_for_offset(text, match.start())}'
        )
        if len(issues) >= 6:
            return issues
    for match in _HTML_UNTERMINATED_KNOWN_OPEN_TAG_RE.finditer(text):
        tag = str(match.group('tag') or '').strip().lower()
        issues.append(
            f'HTML has unterminated opening tag <{tag}> at line {_line_number_for_offset(text, match.start())}'
        )
        if len(issues) >= 6:
            return issues
    for match in _HTML_DUPLICATE_OPEN_ANGLE_KNOWN_TAG_RE.finditer(text):
        tag = str(match.group('tag') or '').strip().lower()
        issues.append(
            f'HTML opening tag <{tag}> has duplicate opening angle bracket at line {_line_number_for_offset(text, match.start())}'
        )
        if len(issues) >= 6:
            return issues
    for match in _HTML_STRAY_PUNCTUATION_PSEUDO_TAG_BEFORE_KNOWN_TAG_RE.finditer(text):
        tag = str(match.group('tag') or '').strip().lower()
        fragment = str(match.group('fragment') or '').strip()
        issues.append(
            f'HTML has stray punctuation pseudo-tag `{fragment}` before <{tag}> at line {_line_number_for_offset(text, match.start("fragment"))}'
        )
        if len(issues) >= 6:
            return issues
    for match in _HTML_MALFORMED_OPEN_PREFIX_KNOWN_TAG_RE.finditer(text):
        tag = str(match.group('tag') or '').strip().lower()
        prefix = str(match.group('prefix') or '').strip()
        issues.append(
            f'HTML opening tag <{tag}> has stray prefix `{prefix}` at line {_line_number_for_offset(text, match.start())}'
        )
        if len(issues) >= 6:
            return issues
    for match in _HTML_QUOTED_KNOWN_OPEN_TAG_RE.finditer(text):
        tag = str(match.group('tag') or '').strip().lower()
        issues.append(
            f'HTML opening tag <{tag}> is quoted instead of angle-bracketed at line {_line_number_for_offset(text, match.start())}'
        )
        if len(issues) >= 6:
            return issues
    for match in _HTML_MALFORMED_STYLESHEET_LINK_ATTR_RE.finditer(text):
        issues.append(
            'HTML stylesheet link tag has malformed rel/href attributes at line '
            f'{_line_number_for_offset(text, match.start())}; use rel="stylesheet" href="..."'
        )
        if len(issues) >= 6:
            return issues
    for match in _HTML_MALFORMED_FORMATTED_ANCHOR_FRAGMENT_RE.finditer(text):
        issues.append(
            'HTML has malformed formatted anchor fragment at line '
            f'{_line_number_for_offset(text, match.start())}; use a normal <a href="..."> link'
        )
        if len(issues) >= 6:
            return issues
    for match in _HTML_UNSUPPORTED_NAV_ANCHOR_WRAPPER_RE.finditer(text):
        issue = _html_unsupported_nav_anchor_wrapper_issue(text, match)
        if issue:
            issues.append(issue)
            if len(issues) >= 6:
                return issues
    for match in _HTML_LITERAL_UNSUPPORTED_TAG_RE.finditer(text):
        issues.append(
            'HTML has literal unsupported placeholder tag <unsupported> at line '
            f'{_line_number_for_offset(text, match.start())}; unwrap it or replace it with a standard element'
        )
        if len(issues) >= 6:
            return issues
    for match in _HTML_UNKNOWN_CLASS_WRAPPER_TAG_RE.finditer(text):
        tag = str(match.group('tag') or '').strip().lower()
        if '-' in tag or ':' in tag:
            continue
        issues.append(
            f'HTML has unknown class/id wrapper tag <{tag}> at line '
            f'{_line_number_for_offset(text, match.start())}; use a standard wrapper such as <div>'
        )
        if len(issues) >= 6:
            return issues

    for defect in _html_hero_header_landmark_containment_defects(text):
        landmark = str(defect.get('landmark_tag') or '').strip().lower()
        landmark_line = defect.get('landmark_line')
        header_line = defect.get('header_line')
        issues.append(
            f'HTML <{landmark}> landmark is nested inside hero/header opened at line {header_line}; '
            f'close the header before line {landmark_line}'
        )
        if len(issues) >= 6:
            return issues

    href_context_stack: list[str] = []
    for match in _HTML_SYNTAX_TAG_RE.finditer(text):
        token = match.group(0)
        if token.startswith('<!--') or token.startswith('<!'):
            continue
        tag = str(match.group('tag') or '').strip().lower()
        if not tag:
            continue
        if match.group('close'):
            if tag in href_context_stack:
                while href_context_stack:
                    current = href_context_stack.pop()
                    if current == tag:
                        break
            continue
        attrs = str(match.group('attrs') or '')
        attrs_offset = match.start('attrs') if match.start('attrs') >= 0 else match.start()
        for attr_match in _HTML_MALFORMED_CLASS_ATTR_COLON_RE.finditer(attrs):
            issues.append(
                f'HTML class attribute uses `:` instead of `=` at line {_line_number_for_offset(text, attrs_offset + attr_match.start())}'
            )
            if len(issues) >= 6:
                return issues
        for attr_match in _HTML_BARE_DUPLICATE_ATTRIBUTE_RE.finditer(attrs):
            attr_name = str(attr_match.group('name') or '').strip().lower()
            issues.append(
                f'HTML attribute `{attr_name}` has a bare duplicate token before its value at line {_line_number_for_offset(text, attrs_offset + attr_match.start())}'
            )
            if len(issues) >= 6:
                return issues
        if _html_attrs_have_unbalanced_quote(attrs):
            issues.append(
                f'HTML opening tag <{tag}> has an unbalanced quote in attributes at line {_line_number_for_offset(text, attrs_offset)}'
            )
            if len(issues) >= 6:
                return issues
        if tag == 'link' and _html_link_stylesheet_rel_is_invalid(attrs):
            issues.append(
                f'HTML stylesheet link tag has invalid or missing rel attribute at line {_line_number_for_offset(text, match.start())}; use rel="stylesheet" for CSS links'
            )
            if len(issues) >= 6:
                return issues
        if (
            'svg' not in href_context_stack
            and tag not in _HTML_HREF_ALLOWED_TAGS
            and _HTML_HREF_ATTR_RE.search(attrs)
        ):
            issues.append(
                f'HTML has unsupported href element <{tag}> at line {_line_number_for_offset(text, match.start())}; use <a> for navigation links'
            )
            if len(issues) >= 6:
                return issues
        if tag not in _HTML_SYNTAX_VOID_TAGS and not match.group('self'):
            href_context_stack.append(tag)

    for offset in _html_stray_open_angle_offsets(text):
        issues.append(
            f'HTML has stray opening angle bracket at line {_line_number_for_offset(text, offset)}; escape text as `&lt;` or complete the intended tag'
        )
        if len(issues) >= 6:
            return issues

    stack: list[tuple[str, int]] = []
    for match in _HTML_SYNTAX_TAG_RE.finditer(text):
        token = match.group(0)
        if token.startswith('<!--') or token.startswith('<!'):
            continue
        tag = str(match.group('tag') or '').strip().lower()
        if not tag:
            continue
        line = _line_number_for_offset(text, match.start())
        if match.group('close'):
            if not stack:
                issues.append(f'HTML has stray closing tag </{tag}> at line {line}')
            elif stack[-1][0] == tag:
                stack.pop()
            else:
                open_tags = [item[0] for item in stack]
                if tag in open_tags:
                    expected_tag, expected_line = stack[-1]
                    issues.append(
                        f'HTML closes </{tag}> at line {line} before closing <{expected_tag}> opened at line {expected_line}'
                    )
                    while stack and stack[-1][0] != tag:
                        stack.pop()
                    if stack and stack[-1][0] == tag:
                        stack.pop()
                else:
                    issues.append(f'HTML has stray closing tag </{tag}> at line {line}')
        elif tag not in _HTML_SYNTAX_VOID_TAGS and not match.group('self'):
            stack.append((tag, line))
        if len(issues) >= 6:
            return issues
    for tag, line in reversed(stack[-6:]):
        issues.append(f'HTML tag <{tag}> opened at line {line} is not closed')
        if len(issues) >= 6:
            break
    return issues


def _css_custom_property_names(content: str) -> set[str]:
    text = re.sub(r'/\*[\s\S]*?\*/', '', str(content or ''))
    return {
        str(match.group('name') or '').strip()
        for match in _CSS_CUSTOM_PROPERTY_DEFINITION_RE.finditer(text)
        if str(match.group('name') or '').strip()
    }


def _css_custom_property_var_reference_suggestion(
    defined_properties: set[str],
    reference_name: str,
) -> Optional[str]:
    name = str(reference_name or '').strip()
    if not name.startswith('---'):
        return None
    suggestion = f'--{name[3:]}'
    if suggestion in defined_properties and name not in defined_properties:
        return suggestion
    return None


def _bounded_edit_distance(left: str, right: str, max_distance: int) -> int:
    if abs(len(left) - len(right)) > max_distance:
        return max_distance + 1
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        row_min = current[0]
        for right_index, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            value = min(
                previous[right_index] + 1,
                current[right_index - 1] + 1,
                previous[right_index - 1] + cost,
            )
            current.append(value)
            row_min = min(row_min, value)
        if row_min > max_distance:
            return max_distance + 1
        previous = current
    return previous[-1]


def _css_custom_property_var_reference_near_miss_suggestion(
    defined_properties: set[str],
    reference_name: str,
) -> Optional[str]:
    name = str(reference_name or '').strip()
    if not name.startswith('--') or name.startswith('---') or name in defined_properties:
        return None
    stem = name[2:].lower()
    if len(stem) < 5:
        return None
    best: tuple[int, int, str] | None = None
    for candidate in defined_properties:
        candidate_name = str(candidate or '').strip()
        if not candidate_name.startswith('--') or candidate_name.startswith('---'):
            continue
        candidate_stem = candidate_name[2:].lower()
        if len(candidate_stem) < 5:
            continue
        shared_prefix = 0
        for left_char, right_char in zip(stem, candidate_stem):
            if left_char != right_char:
                break
            shared_prefix += 1
        if shared_prefix < min(4, len(stem), len(candidate_stem)):
            continue
        max_distance = 3 if max(len(stem), len(candidate_stem)) >= 7 else 2
        distance = _bounded_edit_distance(stem, candidate_stem, max_distance)
        if distance > max_distance:
            continue
        rank = (distance, -shared_prefix, candidate_name)
        if best is None or rank < best:
            best = rank
    if best is None:
        return None
    return best[2]


def _css_custom_property_var_reference_typos(
    content: str,
) -> list[tuple[re.Match[str], str, str]]:
    text = re.sub(r'/\*[\s\S]*?\*/', '', str(content or ''))
    defined_properties = _css_custom_property_names(text)
    typos: list[tuple[re.Match[str], str, str]] = []
    for match in _CSS_VAR_REFERENCE_RE.finditer(text):
        name = str(match.group('name') or '').strip()
        suggestion = _css_custom_property_var_reference_suggestion(
            defined_properties,
            name,
        )
        if suggestion:
            typos.append((match, name, suggestion))
    return typos


def _css_custom_property_var_reference_near_misses(
    content: str,
) -> list[tuple[re.Match[str], str, str]]:
    text = re.sub(r'/\*[\s\S]*?\*/', '', str(content or ''))
    defined_properties = _css_custom_property_names(text)
    near_misses: list[tuple[re.Match[str], str, str]] = []
    for match in _CSS_ANY_VAR_REFERENCE_RE.finditer(text):
        name = str(match.group('name') or '').strip()
        suggestion = _css_custom_property_var_reference_near_miss_suggestion(
            defined_properties,
            name,
        )
        if suggestion:
            near_misses.append((match, name, suggestion))
    return near_misses


def _css_property_identifier_is_valid(value: str) -> bool:
    return bool(_CSS_PROPERTY_IDENTIFIER_RE.fullmatch(str(value or '').strip()))


def _css_invalid_property_value_suggestion(property_name: str, value: str) -> Optional[str]:
    property_key = str(property_name or '').strip().lower()
    raw_value = re.sub(r'\s+', ' ', str(value or '').strip())
    important = ''
    important_match = re.search(r'\s*!important\s*$', raw_value, flags=re.IGNORECASE)
    if important_match:
        important = raw_value[important_match.start():]
        raw_value = raw_value[:important_match.start()].strip()
    value_key = raw_value.lower()
    suggestion = _CSS_KNOWN_INVALID_PROPERTY_VALUES.get((property_key, value_key))
    if not suggestion:
        return None
    return f'{suggestion}{important}'


def _css_malformed_declaration_name_suggestion(property_name: str) -> Optional[str]:
    raw = re.sub(r'\s+', ' ', str(property_name or '').strip())
    if not raw:
        return None
    if '/*' in raw or '*/' in raw:
        return None
    normalized = raw.lower()
    if _css_property_identifier_is_valid(normalized):
        return None
    tokens = [token.strip() for token in re.split(r'\s+', raw) if token.strip()]
    if len(tokens) < 2:
        return None
    candidate = tokens[-1].lower()
    prefix = ''.join(tokens[:-1])
    if not _css_property_identifier_is_valid(candidate):
        return None
    if not re.search(r'[^A-Za-z0-9_-]', prefix):
        return None
    return candidate


def _css_declaration_name_formatting_tag_suggestion(property_name: str) -> Optional[str]:
    raw = str(property_name or '').strip()
    if not raw or not _CSS_DECLARATION_NAME_FORMATTING_TAG_RE.search(raw):
        return None
    candidate = _CSS_DECLARATION_NAME_FORMATTING_TAG_RE.sub('', raw).strip().lower()
    if candidate == raw.lower():
        return None
    if not _css_property_identifier_is_valid(candidate):
        return None
    return candidate


def _css_offset_inside_string_or_parentheses(content: str, offset: int) -> bool:
    text = str(content or '')
    try:
        bounded = max(0, min(int(offset), len(text)))
    except (TypeError, ValueError):
        bounded = 0
    quote: Optional[str] = None
    escaped = False
    in_comment = False
    paren_depth = 0
    index = 0
    while index < bounded:
        char = text[index]
        next_char = text[index + 1] if index + 1 < bounded else ''
        if in_comment:
            if char == '*' and next_char == '/':
                in_comment = False
                index += 2
                continue
            index += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char == '/' and next_char == '*':
            in_comment = True
            index += 2
            continue
        if char in {'"', "'"}:
            quote = char
            index += 1
            continue
        if char == '(':
            paren_depth += 1
        elif char == ')' and paren_depth > 0:
            paren_depth -= 1
        index += 1
    return bool(quote or in_comment or paren_depth > 0)


def _css_syntax_sanity_issues(content: str) -> list[str]:
    text = re.sub(r'/\*[\s\S]*?\*/', '', str(content or ''))
    if not text.strip():
        return []
    issues: list[str] = []
    stack: list[int] = []
    for index, char in enumerate(text):
        if char == '{':
            stack.append(_line_number_for_offset(text, index))
        elif char == '}':
            if stack:
                stack.pop()
            else:
                issues.append(f'CSS has closing brace without matching opening brace at line {_line_number_for_offset(text, index)}')
        if len(issues) >= 6:
            return issues
    for line in reversed(stack[-6:]):
        issues.append(f'CSS block opened at line {line} is not closed')
        if len(issues) >= 6:
            return issues

    for match in _CSS_DECLARATION_NAME_RE.finditer(text):
        if _css_offset_inside_string_or_parentheses(text, match.start()):
            continue
        property_name = re.sub(r'\s+', ' ', str(match.group('property') or '').strip()).lower()
        if not property_name or _css_property_identifier_is_valid(property_name):
            continue
        suggestion = _css_malformed_declaration_name_suggestion(property_name)
        if suggestion:
            issues.append(
                f'CSS declaration name `{property_name}` at line {_line_number_for_offset(text, match.start("property"))} is invalid; use `{suggestion}`'
            )
        else:
            issues.append(
                f'CSS declaration name `{property_name}` at line {_line_number_for_offset(text, match.start("property"))} is invalid'
            )
        if len(issues) >= 6:
            return issues
    for match in re.finditer(r'(?m)(?P<property>-{0,2}[a-z_][a-z0-9_-]*)\s*:', text, flags=re.IGNORECASE):
        property_name = str(match.group('property') or '').strip().lower()
        suggestion = _CSS_KNOWN_PROPERTY_TYPOS.get(property_name)
        if suggestion:
            issues.append(
                f'CSS property `{property_name}` at line {_line_number_for_offset(text, match.start())} is likely invalid; use `{suggestion}`'
            )
        ambiguous = _CSS_AMBIGUOUS_PROPERTY_TYPOS.get(property_name)
        if ambiguous:
            issues.append(
                f'CSS property `{property_name}` at line {_line_number_for_offset(text, match.start())} is invalid and ambiguous; choose one of {ambiguous}'
            )
        if len(issues) >= 6:
            return issues
    for match in _CSS_DECLARATION_VALUE_RE.finditer(text):
        if _css_offset_inside_string_or_parentheses(text, match.start('property')):
            continue
        property_name = str(match.group('property') or '').strip().lower()
        value = str(match.group('value') or '').strip()
        suggestion = _css_invalid_property_value_suggestion(property_name, value)
        if suggestion:
            normalized_value = re.sub(r'\s+', ' ', value)
            issues.append(
                f'CSS property `{property_name}` value `{normalized_value}` at line {_line_number_for_offset(text, match.start("value"))} is invalid; use `{suggestion}`'
            )
            if len(issues) >= 6:
                return issues
        if _CSS_HTML_ENTITY_FRAGMENT_IN_FUNCTION_RE.search(value):
            issues.append(
                f'CSS declaration value for `{property_name}` at line {_line_number_for_offset(text, match.start("value"))} contains an HTML entity fragment inside a CSS function'
            )
            if len(issues) >= 6:
                return issues
    for pattern, replacement, _kind in _CSS_INVALID_FUNCTION_TOKENS:
        for match in pattern.finditer(text):
            issues.append(
                f'CSS token `{match.group(0)}` at line {_line_number_for_offset(text, match.start())} is likely invalid; use `{replacement}`'
            )
            if len(issues) >= 6:
                return issues
    for match in _CSS_INVALID_VAR_SLASH_REFERENCE_RE.finditer(text):
        name = str(match.group('name') or '').strip()
        suggestion_name = name if name.startswith('--') else f'--{name}'
        issues.append(
            f'CSS token `{match.group(0)}` at line {_line_number_for_offset(text, match.start())} is likely invalid; use `var({suggestion_name})`'
        )
        if len(issues) >= 6:
            return issues
    for declaration_match in _CSS_BACKGROUND_DECLARATION_RE.finditer(text):
        value = str(declaration_match.group('value') or '')
        value_offset = declaration_match.start('value')
        for token_match in _CSS_INVALID_BACKGROUND_SHORTHAND_TOKEN_RE.finditer(value):
            token = str(token_match.group('token') or '').strip().lower()
            suggestion = _CSS_INVALID_BACKGROUND_SHORTHAND_TOKENS.get(token)
            if not suggestion:
                continue
            issues.append(
                f'CSS background token `{token}` at line {_line_number_for_offset(text, value_offset + token_match.start())} is likely invalid; use `{suggestion}`'
            )
            if len(issues) >= 6:
                return issues
    for match, name, suggestion in _css_custom_property_var_reference_typos(text):
        issues.append(
            f'CSS variable reference `{name}` at line {_line_number_for_offset(text, match.start())} is likely invalid; use `{suggestion}`'
        )
        if len(issues) >= 6:
            return issues
    for match, name, suggestion in _css_custom_property_var_reference_near_misses(text):
        issues.append(
            f'CSS variable reference `{name}` at line {_line_number_for_offset(text, match.start())} is likely undefined; use `{suggestion}`'
        )
        if len(issues) >= 6:
            return issues
    return issues


def _json_syntax_sanity_issues(content: str) -> list[str]:
    text = str(content or '').strip()
    if not text:
        return []
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return [f'JSON syntax error at line {exc.lineno} column {exc.colno}: {exc.msg}']
    return []


def text_artifact_syntax_sanity_issues_for_extension(
    extension: str,
    content: str,
) -> list[str]:
    normalized = _normalize_text_artifact_extension(extension)
    if normalized in {'html', 'htm'}:
        return _html_syntax_sanity_issues(content)
    if normalized == 'css':
        return _css_syntax_sanity_issues(content)
    if normalized == 'json':
        return _json_syntax_sanity_issues(content)
    return []


def _repair_html_syntax_sanity_content(content: str) -> tuple[str, list[dict[str, Any]]]:
    original = str(content or '')
    before_issues = _html_syntax_sanity_issues(original)
    if not before_issues:
        return original, []

    repairs: list[dict[str, Any]] = []

    def normalize_embedded_close(match: re.Match[str]) -> str:
        tag = str(match.group('tag') or '').strip().lower()
        replacement = f'</{tag}>'
        repairs.append(
            {
                'kind': 'html_malformed_closing_tag',
                'from': match.group(0),
                'to': replacement,
            }
        )
        return replacement

    def normalize_prefixed_close(match: re.Match[str]) -> str:
        tag = str(match.group('tag') or '').strip().lower()
        replacement = f'</{tag}>'
        repairs.append(
            {
                'kind': 'html_malformed_closing_tag',
                'from': match.group(0),
                'to': replacement,
            }
        )
        return replacement

    def normalize_known_suffix_close(match: re.Match[str]) -> str:
        tag = str(match.group('tag') or '').strip().lower()
        prefix = str(match.group('prefix') or '').strip().lower()
        replacement = f'</{tag}>'
        repairs.append(
            {
                'kind': 'html_malformed_closing_tag_known_suffix',
                'from': match.group(0),
                'to': replacement,
                'prefix': prefix,
            }
        )
        return replacement

    def remove_stray_nested_close(match: re.Match[str]) -> str:
        repairs.append(
            {
                'kind': 'html_stray_nested_closing_tag_fragment',
                'from': match.group(0),
                'to': '',
            }
        )
        return ''

    def remove_stray_formatting_close_in_open_tag(match: re.Match[str]) -> str:
        tag = str(match.group('tag') or '').strip().lower()
        boundary = str(match.group('boundary') or '')
        replacement = f'<{tag}{boundary}'
        repairs.append(
            {
                'kind': 'html_stray_formatting_close_in_open_tag',
                'from': match.group(0),
                'to': replacement,
            }
        )
        return replacement

    def remove_partial_open_tag_with_stray_formatting_close(match: re.Match[str]) -> str:
        repairs.append(
            {
                'kind': 'html_partial_open_tag_with_stray_formatting_close',
                'from': match.group(0),
                'to': '',
            }
        )
        return ''

    def normalize_malformed_open_prefix_known_tag(match: re.Match[str]) -> str:
        tag = str(match.group('tag') or '').strip().lower()
        boundary = str(match.group('boundary') or '')
        replacement = f'<{tag}{boundary}'
        repairs.append(
            {
                'kind': 'html_malformed_opening_tag_prefix',
                'from': match.group(0),
                'to': replacement,
                'prefix': str(match.group('prefix') or ''),
                'tag': tag,
                'line': _line_number_for_offset(original, match.start()),
            }
        )
        return replacement

    def normalize_duplicate_open_angle_known_tag(match: re.Match[str]) -> str:
        tag = str(match.group('tag') or '').strip().lower()
        boundary = str(match.group('boundary') or '')
        replacement = f'<{tag}{boundary}'
        repairs.append(
            {
                'kind': 'html_duplicate_opening_angle_known_tag',
                'from': match.group(0),
                'to': replacement,
                'tag': tag,
                'line': _line_number_for_offset(original, match.start()),
            }
        )
        return replacement

    def remove_stray_punctuation_pseudo_tag_before_known_tag(match: re.Match[str]) -> str:
        fragment = str(match.group('fragment') or '')
        tag = str(match.group('tag') or '').strip().lower()
        prefix = str(match.group('prefix') or '')
        repairs.append(
            {
                'kind': 'html_stray_punctuation_pseudotag_removed',
                'from': fragment,
                'to': '',
                'before_tag': tag,
                'line': _line_number_for_offset(original, match.start('fragment')),
            }
        )
        return prefix

    def normalize_quoted_known_open_tag(match: re.Match[str]) -> str:
        prefix = str(match.group('prefix') or '')
        tag = str(match.group('tag') or '').strip().lower()
        attrs = str(match.group('attrs') or '')
        replacement = f'{prefix}<{tag}{attrs}>'
        repairs.append(
            {
                'kind': 'html_quoted_known_opening_tag',
                'from': match.group(0),
                'to': replacement,
                'tag': tag,
                'line': _line_number_for_offset(original, match.start()),
            }
        )
        return replacement

    def normalize_malformed_stylesheet_link_attrs(match: re.Match[str]) -> str:
        prefix = str(match.group('prefix') or '')
        href = str(match.group('href') or '').strip()
        suffix = str(match.group('suffix') or '')
        replacement = f'<link{prefix}rel="stylesheet" {href}{suffix}>'
        repairs.append(
            {
                'kind': 'html_malformed_stylesheet_link_attributes',
                'from': match.group(0),
                'to': replacement,
                'line': _line_number_for_offset(original, match.start()),
            }
        )
        return replacement

    def normalize_invalid_stylesheet_link_rel_in_tag(match: re.Match[str]) -> str:
        token = match.group(0)
        if token.startswith('<!--') or token.startswith('<!') or match.group('close'):
            return token
        tag = str(match.group('tag') or '').strip().lower()
        attrs = str(match.group('attrs') or '')
        if tag != 'link' or not _html_link_stylesheet_rel_is_invalid(attrs):
            return token
        values = _html_attribute_values(attrs)
        rel = next((item for item in values.get('rel', []) if item.strip()), '')
        line = _line_number_for_offset(original, min(match.start(), len(original)))

        def replace_rel_attr(rel_match: re.Match[str]) -> str:
            quote = str(rel_match.group('quote') or '"')
            repairs.append(
                {
                    'kind': 'html_invalid_stylesheet_link_rel',
                    'from': rel,
                    'to': 'stylesheet',
                    'line': line,
                }
            )
            return f'rel={quote}stylesheet{quote}'

        replaced = re.sub(
            r'\brel\s*=\s*(?P<quote>["\'])(?P<value>.*?)(?P=quote)',
            replace_rel_attr,
            token,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if replaced != token:
            return replaced
        repairs.append(
            {
                'kind': 'html_missing_stylesheet_link_rel',
                'from': '',
                'to': 'stylesheet',
                'line': line,
            }
        )
        if token.endswith('/>'):
            return f'{token[:-2].rstrip()} rel="stylesheet" />'
        return f'{token[:-1].rstrip()} rel="stylesheet">'

    def normalize_malformed_class_attr_in_tag(match: re.Match[str]) -> str:
        token = match.group(0)
        if token.startswith('<!--') or token.startswith('<!') or match.group('close'):
            return token

        def replace_class_attr(attr_match: re.Match[str]) -> str:
            value = re.sub(r'\s+', ' ', str(attr_match.group('value') or '')).strip()
            quote = str(attr_match.group('quote') or '"')
            if not value:
                return attr_match.group(0)
            replacement = f'class={quote}{value}{quote}'
            repairs.append(
                {
                    'kind': 'html_malformed_class_attribute_assignment',
                    'from': attr_match.group(0),
                    'to': replacement,
                }
            )
            return replacement

        return _HTML_MALFORMED_CLASS_ATTR_COLON_RE.sub(replace_class_attr, token)

    def normalize_bare_duplicate_attr_in_tag(match: re.Match[str]) -> str:
        token = match.group(0)
        if token.startswith('<!--') or token.startswith('<!') or match.group('close'):
            return token
        line = _line_number_for_offset(original, min(match.start(), len(original)))

        def replace_bare_duplicate_attr(attr_match: re.Match[str]) -> str:
            attr_name = str(attr_match.group('name') or '').strip()
            if not attr_name:
                return attr_match.group(0)
            replacement = f'{attr_name}='
            repairs.append(
                {
                    'kind': 'html_bare_duplicate_attribute_token',
                    'from': attr_match.group(0),
                    'to': replacement,
                    'attribute': attr_name.lower(),
                    'line': line,
                }
            )
            return replacement

        return _HTML_BARE_DUPLICATE_ATTRIBUTE_RE.sub(
            replace_bare_duplicate_attr,
            token,
        )

    def normalize_malformed_anchor_opening_tag(match: re.Match[str]) -> str:
        tag = str(match.group('tag') or '').strip()
        attrs = str(match.group('attrs') or '')
        body = str(match.group('body') or '')
        replacement = f'<a{attrs}>{body}</a>'
        repairs.append(
            {
                'kind': 'html_malformed_anchor_opening_tag',
                'from_tag': tag,
                'to_tag': 'a',
                'removed_obsolete_close': bool(match.group('obsolete_close')),
                'line': _line_number_for_offset(original, match.start()),
            }
        )
        return replacement

    def normalize_malformed_formatted_anchor_fragment(match: re.Match[str]) -> str:
        attrs = re.sub(r'\s+', ' ', str(match.group('attrs') or '').strip())
        body = str(match.group('body') or '').strip()
        replacement = f'<a {attrs}>{body}</a>'
        repairs.append(
            {
                'kind': 'html_malformed_formatted_anchor_fragment',
                'from': match.group(0),
                'to': replacement,
                'line': _line_number_for_offset(original, match.start()),
            }
        )
        return replacement

    def normalize_unsupported_href_element(match: re.Match[str]) -> str:
        tag = str(match.group('tag') or '').strip()
        normalized_tag = tag.lower()
        attrs = str(match.group('attrs') or '')
        if (
            not normalized_tag
            or normalized_tag in _HTML_HREF_ALLOWED_TAGS
            or normalized_tag in _HTML_HREF_REPAIR_EXCLUDED_TAGS
            or ':' in normalized_tag
            or not _HTML_HREF_ATTR_RE.search(attrs)
        ):
            return match.group(0)
        body = str(match.group('body') or '')
        replacement = f'<a{attrs}>{body}</a>'
        repairs.append(
            {
                'kind': 'html_unsupported_href_element_rewritten_to_anchor',
                'from_tag': tag,
                'to_tag': 'a',
                'line': _line_number_for_offset(original, match.start()),
            }
        )
        return replacement

    def normalize_unsupported_navigation_anchor_wrapper(match: re.Match[str]) -> str:
        issue = _html_unsupported_nav_anchor_wrapper_issue(repaired, match)
        if not issue:
            return match.group(0)
        tag = str(match.group('tag') or '').strip()
        anchor = str(match.group('anchor') or '')
        if not anchor:
            return match.group(0)
        repairs.append(
            {
                'kind': 'html_unsupported_navigation_anchor_wrapper_unwrapped',
                'from_tag': tag,
                'to': 'anchor_only',
                'line': _line_number_for_offset(original, match.start()),
            }
        )
        return anchor

    def normalize_literal_unsupported_tag(match: re.Match[str]) -> str:
        tag = str(match.group('tag') or '').strip()
        body = str(match.group('body') or '')
        repairs.append(
            {
                'kind': 'html_literal_unsupported_tag_unwrapped',
                'from_tag': tag,
                'to': 'inner_content',
                'line': _line_number_for_offset(original, match.start()),
            }
        )
        return body

    def normalize_malformed_class_only_opening_tag(match: re.Match[str]) -> str:
        class_token = str(match.group('class') or '').strip()
        close_tag = str(match.group('close') or '').strip().lower()
        if not class_token or close_tag in _HTML_SYNTAX_VOID_TAGS:
            return match.group(0)
        body = str(match.group('body') or '')
        replacement = f'<{close_tag} class="{class_token}">{body}</{close_tag}>'
        repairs.append(
            {
                'kind': 'html_malformed_class_only_opening_tag',
                'from': match.group(0),
                'to': replacement,
                'class': class_token,
                'tag': close_tag,
                'line': _line_number_for_offset(original, match.start()),
            }
        )
        return replacement

    def normalize_unknown_class_wrapper_tag(match: re.Match[str]) -> str:
        tag = str(match.group('tag') or '').strip().lower()
        if not tag or '-' in tag or ':' in tag:
            return match.group(0)
        attrs = str(match.group('attrs') or '')
        body = str(match.group('body') or '')
        replacement = f'<div{attrs}>{body}</div>'
        repairs.append(
            {
                'kind': 'html_unknown_class_wrapper_tag_rewritten_to_div',
                'from_tag': tag,
                'to_tag': 'div',
                'line': _line_number_for_offset(original, match.start()),
            }
        )
        return replacement

    def class_tokens_for_attrs(attrs: str) -> set[str]:
        match = re.search(
            r'\bclass\s*=\s*(?P<quote>["\'])(?P<value>.*?)(?P=quote)',
            str(attrs or ''),
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return set()
        return {
            token.strip().lower()
            for token in re.split(r'\s+', str(match.group('value') or ''))
            if token.strip()
        }

    def has_repeated_sibling_hint(tokens: set[str]) -> bool:
        return any(_HTML_REPEATED_SIBLING_CLASS_HINT_RE.search(token) for token in tokens)

    def close_repeated_same_class_div_siblings(value: str) -> tuple[str, list[dict[str, Any]]]:
        insertions: list[tuple[int, str]] = []
        sibling_repairs: list[dict[str, Any]] = []
        stack: list[dict[str, Any]] = []
        for match in _HTML_SYNTAX_TAG_RE.finditer(value):
            token = match.group(0)
            if token.startswith('<!--') or token.startswith('<!'):
                continue
            tag = str(match.group('tag') or '').strip().lower()
            if not tag:
                continue
            line = _line_number_for_offset(value, match.start())
            if match.group('close'):
                if stack and str(stack[-1].get('tag') or '') == tag:
                    stack.pop()
                else:
                    for index in range(len(stack) - 1, -1, -1):
                        if str(stack[index].get('tag') or '') == tag:
                            del stack[index:]
                            break
                continue
            if tag in _HTML_SYNTAX_VOID_TAGS or match.group('self'):
                continue
            tokens = class_tokens_for_attrs(match.group('attrs') or '')
            if tag == 'div' and stack and str(stack[-1].get('tag') or '') == 'div':
                previous_tokens = set(stack[-1].get('class_tokens') or set())
                shared_tokens = tokens & previous_tokens
                if (
                    shared_tokens
                    and has_repeated_sibling_hint(shared_tokens | tokens | previous_tokens)
                ):
                    insertions.append((match.start(), '</div>\n'))
                    sibling_repairs.append(
                        {
                            'kind': 'html_missing_repeated_sibling_div_close',
                            'inserted': '</div>',
                            'before_line': line,
                            'class_tokens': sorted(shared_tokens),
                        }
                    )
                    stack.pop()
            stack.append(
                {
                    'tag': tag,
                    'line': line,
                    'class_tokens': tokens,
                }
            )
        if not insertions:
            return value, []
        repaired_value = value
        for index, insertion in reversed(insertions):
            repaired_value = f'{repaired_value[:index]}{insertion}{repaired_value[index:]}'
        return repaired_value, sibling_repairs

    def close_hero_header_before_landmarks(value: str) -> tuple[str, list[dict[str, Any]]]:
        insertions: list[tuple[int, str]] = []
        containment_repairs: list[dict[str, Any]] = []
        seen_header_starts: set[int] = set()
        for defect in _html_hero_header_landmark_containment_defects(value):
            try:
                header_start = int(defect.get('header_start'))
                landmark_start = int(defect.get('landmark_start'))
            except (TypeError, ValueError):
                continue
            if header_start in seen_header_starts:
                continue
            seen_header_starts.add(header_start)
            landmark = str(defect.get('landmark_tag') or '').strip().lower()
            insertions.append((landmark_start, '</header>\n'))
            containment_repairs.append(
                {
                    'kind': 'html_hero_header_landmark_containment_closed',
                    'inserted': '</header>',
                    'before_tag': f'<{landmark}>',
                    'header_line': defect.get('header_line'),
                    'before_line': defect.get('landmark_line'),
                }
            )
        if not insertions:
            return value, []
        repaired_value = value
        for index, insertion in reversed(insertions):
            repaired_value = f'{repaired_value[:index]}{insertion}{repaired_value[index:]}'
        return repaired_value, containment_repairs

    def close_intervening_tags_before_parent_close(value: str) -> tuple[str, list[dict[str, Any]]]:
        insertions: list[tuple[int, str]] = []
        parent_repairs: list[dict[str, Any]] = []
        stack: list[dict[str, Any]] = []
        for match in _HTML_SYNTAX_TAG_RE.finditer(value):
            token = match.group(0)
            if token.startswith('<!--') or token.startswith('<!'):
                continue
            tag = str(match.group('tag') or '').strip().lower()
            if not tag:
                continue
            line = _line_number_for_offset(value, match.start())
            if match.group('close'):
                if stack and str(stack[-1].get('tag') or '') == tag:
                    stack.pop()
                    continue
                ancestor_index = -1
                for index in range(len(stack) - 1, -1, -1):
                    if str(stack[index].get('tag') or '') == tag:
                        ancestor_index = index
                        break
                if ancestor_index < 0:
                    continue
                missing = stack[ancestor_index + 1:]
                repairable_missing = [
                    item
                    for item in missing
                    if str(item.get('tag') or '') not in {'html', 'head', 'body'}
                ]
                if repairable_missing:
                    closing_tags = [
                        str(item.get('tag') or '').strip().lower()
                        for item in reversed(repairable_missing)
                        if str(item.get('tag') or '').strip()
                    ]
                    inserted = ''.join(f'</{missing_tag}>' for missing_tag in closing_tags)
                    if inserted:
                        insertion = f'{inserted}\n'
                        insertions.append((match.start(), insertion))
                        parent_repairs.append(
                            {
                                'kind': 'html_missing_intervening_close_before_parent',
                                'inserted': inserted,
                                'closed_tags': closing_tags,
                                'before_parent_close': f'</{tag}>',
                                'before_line': line,
                            }
                        )
                del stack[ancestor_index:]
                continue
            if tag in _HTML_SYNTAX_VOID_TAGS or match.group('self'):
                continue
            stack.append({'tag': tag, 'line': line})
        if not insertions:
            return value, []
        repaired_value = value
        for index, insertion in reversed(insertions):
            repaired_value = f'{repaired_value[:index]}{insertion}{repaired_value[index:]}'
        return repaired_value, parent_repairs

    def remove_stray_unknown_closing_tags(value: str) -> tuple[str, list[dict[str, Any]]]:
        removals: list[tuple[int, int]] = []
        unknown_close_repairs: list[dict[str, Any]] = []
        stack: list[dict[str, Any]] = []
        for match in _HTML_SYNTAX_TAG_RE.finditer(value):
            token = match.group(0)
            if token.startswith('<!--') or token.startswith('<!'):
                continue
            tag = str(match.group('tag') or '').strip().lower()
            if not tag:
                continue
            line = _line_number_for_offset(value, match.start())
            if match.group('close'):
                if stack and str(stack[-1].get('tag') or '') == tag:
                    stack.pop()
                    continue
                open_tags = [str(item.get('tag') or '') for item in stack]
                if tag in open_tags:
                    while stack and str(stack[-1].get('tag') or '') != tag:
                        stack.pop()
                    if stack:
                        stack.pop()
                    continue
                if tag not in _HTML_SYNTAX_REPAIR_CLOSING_TAGS:
                    removals.append((match.start(), match.end()))
                    unknown_close_repairs.append(
                        {
                            'kind': 'html_stray_unknown_closing_tag_removed',
                            'from': token,
                            'line': line,
                        }
                    )
                continue
            if tag in _HTML_SYNTAX_VOID_TAGS or match.group('self'):
                continue
            stack.append({'tag': tag, 'line': line})
        if not removals:
            return value, []
        repaired_value = value
        for start, end in reversed(removals):
            repaired_value = f'{repaired_value[:start]}{repaired_value[end:]}'
        return repaired_value, unknown_close_repairs

    def remove_stray_known_closing_tags(value: str) -> tuple[str, list[dict[str, Any]]]:
        removals: list[tuple[int, int]] = []
        known_close_repairs: list[dict[str, Any]] = []
        stack: list[dict[str, Any]] = []
        for match in _HTML_SYNTAX_TAG_RE.finditer(value):
            token = match.group(0)
            if token.startswith('<!--') or token.startswith('<!'):
                continue
            tag = str(match.group('tag') or '').strip().lower()
            if not tag:
                continue
            line = _line_number_for_offset(value, match.start())
            if match.group('close'):
                if stack and str(stack[-1].get('tag') or '') == tag:
                    stack.pop()
                    continue
                open_tags = [str(item.get('tag') or '') for item in stack]
                if tag in open_tags:
                    while stack and str(stack[-1].get('tag') or '') != tag:
                        stack.pop()
                    if stack:
                        stack.pop()
                    continue
                if tag in _HTML_STRAY_KNOWN_CLOSING_TAG_REMOVABLE_TAGS:
                    removals.append((match.start(), match.end()))
                    known_close_repairs.append(
                        {
                            'kind': 'html_stray_known_closing_tag_removed',
                            'from': token,
                            'line': line,
                        }
                    )
                continue
            if tag in _HTML_SYNTAX_VOID_TAGS or match.group('self'):
                continue
            stack.append({'tag': tag, 'line': line})
        if not removals:
            return value, []
        repaired_value = value
        for start, end in reversed(removals):
            repaired_value = f'{repaired_value[:start]}{repaired_value[end:]}'
        return repaired_value, known_close_repairs

    repaired = _HTML_QUOTED_KNOWN_OPEN_TAG_RE.sub(
        normalize_quoted_known_open_tag,
        original,
    )
    repaired = _HTML_DUPLICATE_OPEN_ANGLE_KNOWN_TAG_RE.sub(
        normalize_duplicate_open_angle_known_tag,
        repaired,
    )
    repaired = _HTML_STRAY_PUNCTUATION_PSEUDO_TAG_BEFORE_KNOWN_TAG_RE.sub(
        remove_stray_punctuation_pseudo_tag_before_known_tag,
        repaired,
    )
    repaired = _HTML_MALFORMED_STYLESHEET_LINK_ATTR_RE.sub(
        normalize_malformed_stylesheet_link_attrs,
        repaired,
    )
    repaired = _HTML_SYNTAX_TAG_RE.sub(normalize_invalid_stylesheet_link_rel_in_tag, repaired)
    repaired = _HTML_SYNTAX_TAG_RE.sub(normalize_malformed_class_attr_in_tag, repaired)
    repaired = _HTML_SYNTAX_TAG_RE.sub(normalize_bare_duplicate_attr_in_tag, repaired)
    repaired = _HTML_MALFORMED_ANCHOR_OPEN_TAG_RE.sub(
        normalize_malformed_anchor_opening_tag,
        repaired,
    )
    repaired = _HTML_MALFORMED_FORMATTED_ANCHOR_FRAGMENT_RE.sub(
        normalize_malformed_formatted_anchor_fragment,
        repaired,
    )
    repaired = _HTML_UNSUPPORTED_HREF_ELEMENT_RE.sub(
        normalize_unsupported_href_element,
        repaired,
    )
    repaired = _HTML_UNSUPPORTED_NAV_ANCHOR_WRAPPER_RE.sub(
        normalize_unsupported_navigation_anchor_wrapper,
        repaired,
    )
    repaired = _HTML_LITERAL_UNSUPPORTED_TAG_RE.sub(
        normalize_literal_unsupported_tag,
        repaired,
    )
    repaired = _HTML_MALFORMED_CLASS_ONLY_OPEN_TAG_RE.sub(
        normalize_malformed_class_only_opening_tag,
        repaired,
    )
    repaired = _HTML_UNKNOWN_CLASS_WRAPPER_TAG_RE.sub(
        normalize_unknown_class_wrapper_tag,
        repaired,
    )
    repaired = _HTML_MALFORMED_CLOSE_EMBEDDED_TAG_RE.sub(normalize_embedded_close, repaired)
    repaired = _HTML_MALFORMED_CLOSE_PREFIX_RE.sub(normalize_prefixed_close, repaired)
    repaired = _HTML_MALFORMED_CLOSE_KNOWN_SUFFIX_RE.sub(
        normalize_known_suffix_close,
        repaired,
    )
    repaired = _HTML_STRAY_NESTED_CLOSE_RE.sub(remove_stray_nested_close, repaired)
    repaired = _HTML_PARTIAL_OPEN_TAG_WITH_STRAY_FORMATTING_CLOSE_RE.sub(
        remove_partial_open_tag_with_stray_formatting_close,
        repaired,
    )
    repaired = _HTML_MALFORMED_OPEN_PREFIX_KNOWN_TAG_RE.sub(
        normalize_malformed_open_prefix_known_tag,
        repaired,
    )
    repaired = _HTML_STRAY_FORMATTING_CLOSE_IN_OPEN_TAG_RE.sub(
        remove_stray_formatting_close_in_open_tag,
        repaired,
    )
    sibling_repaired, sibling_repairs = close_repeated_same_class_div_siblings(repaired)
    if sibling_repairs:
        repaired = sibling_repaired
        repairs.extend(sibling_repairs)
    containment_repaired, containment_repairs = close_hero_header_before_landmarks(repaired)
    if containment_repairs:
        repaired = containment_repaired
        repairs.extend(containment_repairs)
    parent_repaired, parent_repairs = close_intervening_tags_before_parent_close(repaired)
    if parent_repairs:
        repaired = parent_repaired
        repairs.extend(parent_repairs)
    unknown_close_repaired, unknown_close_repairs = remove_stray_unknown_closing_tags(repaired)
    if unknown_close_repairs:
        repaired = unknown_close_repaired
        repairs.extend(unknown_close_repairs)
    known_close_repaired, known_close_repairs = remove_stray_known_closing_tags(repaired)
    if known_close_repairs:
        repaired = known_close_repaired
        repairs.extend(known_close_repairs)
    if repaired == original or not repairs:
        return original, []
    after_issues = _html_syntax_sanity_issues(repaired)
    if len(after_issues) < len(before_issues):
        return repaired, repairs
    return original, []


def _repair_css_syntax_sanity_content(content: str) -> tuple[str, list[dict[str, Any]]]:
    original = str(content or '')
    before_issues = _css_syntax_sanity_issues(original)
    if not before_issues:
        return original, []

    repairs: list[dict[str, Any]] = []
    repaired = original
    def replace_malformed_declaration_name(match: re.Match[str]) -> str:
        if _css_offset_inside_string_or_parentheses(repaired, match.start()):
            return match.group(0)
        property_name = re.sub(r'\s+', ' ', str(match.group('property') or '').strip()).lower()
        formatting_tag_suggestion = _css_declaration_name_formatting_tag_suggestion(property_name)
        if formatting_tag_suggestion:
            repairs.append(
                {
                    'kind': 'css_formatting_tag_in_declaration_name',
                    'from': property_name,
                    'to': formatting_tag_suggestion,
                    'line': _line_number_for_offset(original, match.start('property')),
                }
            )
            return f"{match.group('prefix')}{formatting_tag_suggestion}:"
        suggestion = _css_malformed_declaration_name_suggestion(property_name)
        if not suggestion:
            return match.group(0)
        repairs.append(
            {
                'kind': 'css_malformed_declaration_name',
                'from': property_name,
                'to': suggestion,
                'line': _line_number_for_offset(original, match.start('property')),
            }
        )
        return f"{match.group('prefix')}{suggestion}:"

    repaired = _CSS_DECLARATION_NAME_RE.sub(replace_malformed_declaration_name, repaired)

    def replace_invalid_property_value(match: re.Match[str]) -> str:
        if _css_offset_inside_string_or_parentheses(repaired, match.start('property')):
            return match.group(0)
        property_name = str(match.group('property') or '').strip()
        value = str(match.group('value') or '').strip()
        suggestion = _css_invalid_property_value_suggestion(property_name, value)
        if not suggestion:
            return match.group(0)
        repairs.append(
            {
                'kind': 'css_invalid_property_value',
                'property': property_name.lower(),
                'from': re.sub(r'\s+', ' ', value),
                'to': suggestion,
                'line': _line_number_for_offset(original, match.start('value')),
            }
        )
        return f"{match.group('prefix')}{property_name}: {suggestion}"

    repaired = _CSS_DECLARATION_VALUE_RE.sub(replace_invalid_property_value, repaired)
    for pattern, replacement, kind in _CSS_INVALID_FUNCTION_TOKENS:
        def replace_token(
            match: re.Match[str],
            *,
            replacement: str = replacement,
            kind: str = kind,
        ) -> str:
            repairs.append(
                {
                    'kind': kind,
                    'from': match.group(0),
                    'to': replacement,
                }
            )
            return replacement

        repaired = pattern.sub(replace_token, repaired)

    def replace_invalid_var_slash_reference(match: re.Match[str]) -> str:
        name = str(match.group('name') or '').strip()
        if not name:
            return match.group(0)
        suggestion_name = name if name.startswith('--') else f'--{name}'
        replacement = f'var({suggestion_name})'
        repairs.append(
            {
                'kind': 'css_invalid_var_slash_reference_token',
                'from': match.group(0),
                'to': replacement,
            }
        )
        return replacement

    repaired = _CSS_INVALID_VAR_SLASH_REFERENCE_RE.sub(
        replace_invalid_var_slash_reference,
        repaired,
    )

    def replace_invalid_background_tokens(match: re.Match[str]) -> str:
        property_name = str(match.group('property') or '').strip()
        value = str(match.group('value') or '')
        changed = False

        def replace_token(token_match: re.Match[str]) -> str:
            nonlocal changed
            token = str(token_match.group('token') or '').strip().lower()
            suggestion = _CSS_INVALID_BACKGROUND_SHORTHAND_TOKENS.get(token)
            if not suggestion:
                return token_match.group(0)
            changed = True
            repairs.append(
                {
                    'kind': 'css_invalid_background_shorthand_token',
                    'from': token_match.group(0),
                    'to': suggestion,
                    'property': property_name.lower(),
                }
            )
            if property_name.lower() == 'background-image':
                return ''
            return suggestion

        replacement_value = _CSS_INVALID_BACKGROUND_SHORTHAND_TOKEN_RE.sub(replace_token, value)
        if not changed:
            return match.group(0)
        replacement_value = re.sub(r'\s{2,}', ' ', replacement_value).strip()
        return f'{property_name}: {replacement_value}'

    repaired = _CSS_BACKGROUND_DECLARATION_RE.sub(replace_invalid_background_tokens, repaired)
    for typo, replacement in _CSS_KNOWN_PROPERTY_TYPOS.items():
        pattern = re.compile(rf'(?m)(?P<prefix>\b){re.escape(typo)}(?P<suffix>\s*:)', re.IGNORECASE)

        def replace_property(match: re.Match[str], *, typo: str = typo, replacement: str = replacement) -> str:
            repairs.append(
                {
                    'kind': 'css_known_property_typo',
                    'from': typo,
                    'to': replacement,
                }
            )
            return f"{match.group('prefix')}{replacement}{match.group('suffix')}"

        repaired = pattern.sub(replace_property, repaired)
    defined_properties = _css_custom_property_names(repaired)

    def replace_var_reference(match: re.Match[str]) -> str:
        name = str(match.group('name') or '').strip()
        suggestion = _css_custom_property_var_reference_suggestion(
            defined_properties,
            name,
        )
        if not suggestion:
            return match.group(0)
        replacement = f"var({suggestion}{match.group('suffix') or ')'}"
        repairs.append(
            {
                'kind': 'css_custom_property_var_reference_typo',
                'from': name,
                'to': suggestion,
            }
        )
        return replacement

    repaired = _CSS_VAR_REFERENCE_RE.sub(replace_var_reference, repaired)

    def replace_near_miss_var_reference(match: re.Match[str]) -> str:
        name = str(match.group('name') or '').strip()
        suggestion = _css_custom_property_var_reference_near_miss_suggestion(
            defined_properties,
            name,
        )
        if not suggestion:
            return match.group(0)
        replacement = f"var({suggestion}{match.group('suffix') or ')'}"
        repairs.append(
            {
                'kind': 'css_custom_property_var_reference_near_miss',
                'from': name,
                'to': suggestion,
            }
        )
        return replacement

    repaired = _CSS_ANY_VAR_REFERENCE_RE.sub(replace_near_miss_var_reference, repaired)
    if repaired == original or not repairs:
        return original, []
    after_issues = _css_syntax_sanity_issues(repaired)
    if len(after_issues) < len(before_issues):
        return repaired, repairs
    return original, []


def _repair_json_syntax_sanity_content(content: str) -> tuple[str, list[dict[str, Any]]]:
    original = str(content or '')
    before_issues = _json_syntax_sanity_issues(original)
    if not before_issues:
        return original, []

    candidate = _strip_fenced_json_boundary(original.strip())
    repairs: list[dict[str, Any]] = []
    if candidate != original.strip():
        repairs.append({'kind': 'json_strip_fence'})
    without_trailing_commas = re.sub(r',(\s*[}\]])', r'\1', candidate)
    if without_trailing_commas != candidate:
        repairs.append({'kind': 'json_remove_trailing_commas'})
        candidate = without_trailing_commas
    if not repairs:
        return original, []
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return original, []
    repaired = json.dumps(parsed, indent=2, ensure_ascii=False) + '\n'
    if not _json_syntax_sanity_issues(repaired):
        return repaired, repairs
    return original, []


def repair_text_artifact_syntax_content(
    extension: str,
    content: str,
) -> tuple[str, list[dict[str, Any]]]:
    normalized = _normalize_text_artifact_extension(extension)
    if normalized in {'html', 'htm'}:
        return _repair_html_syntax_sanity_content(content)
    if normalized == 'css':
        return _repair_css_syntax_sanity_content(content)
    if normalized == 'json':
        return _repair_json_syntax_sanity_content(content)
    return str(content or ''), []


_HTML_CSS_SELECTOR_BINDING_CONTENT_LIMIT = 60_000


def _bounded_repair_content_block(label: str, content: str, *, limit: int = _HTML_CSS_SELECTOR_BINDING_CONTENT_LIMIT) -> list[str]:
    text = str(content or '').strip()
    if not text:
        return []
    bounded_limit = max(1000, int(limit))
    truncated = len(text) > bounded_limit
    if truncated:
        text = text[:bounded_limit].rstrip()
    lines = [
        f'{label}:',
        '--- CURRENT SAVED FILE START ---',
        text,
        '--- CURRENT SAVED FILE END ---',
    ]
    if truncated:
        lines.append('Current saved file content was truncated for repair prompt size; preserve the unshown file structure unless directly required by the listed defect.')
    return lines

