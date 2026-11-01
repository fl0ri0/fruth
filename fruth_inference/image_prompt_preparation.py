"""Parse prepared image cohorts without promoting or executing them.

The ordered prompts and exact count are candidate payloads. Admission, branch
slot binding, current-turn authority and provider selection remain caller duties.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Optional
from fruth_core.transports import TEXT_ARTIFACT_EXTENSIONS
from fruth_inference.execution_planner import split_visible_image_payload


_MULTI_IMAGE_PROMPT_SECTION_RE = re.compile(
    r'(?ims)^\s*(?:[-*#>]+\s*)?(?:[^\n:]{0,60}\b(?:image|bild|prompt|scene|variation|variante|version)\b[^\n:]{0,30})\s*:\s*(?P<body>.*?)(?=^\s*(?:[-*#>]+\s*)?(?:[^\n:]{0,60}\b(?:image|bild|prompt|scene|variation|variante|version)\b[^\n:]{0,30})\s*:|\Z)'
)


_PARAGRAPH_BREAK_RE = re.compile(r'(?:\r?\n){2,}')


_MULTI_IMAGE_HEADING_LINE_RE = re.compile(
    r'(?i)^(?:(?:image|bild|scene|variation|variante|variant|version|prompt)\s*(?:\d+|[ivx]+)?|(?:image|bild)\s+prompt\s*(?:\d+|[ivx]+)?)(?:\s*(?:[-–—:]|\().*)?$'
)


_INLINE_LABELED_IMAGE_PROMPT_LINE_RE = re.compile(
    r'(?i)^\s*(?:[-*#>\u2022]+\s*)?'
    r'(?:(?:\*\*+|__+|`+|\*+)\s*)*'
    r'(?:'
    r'(?:image|bild|visual|scene)(?:[\s_-]*prompt)?[\s_-]*(?:\d+|[ivx]+)?(?:\s*\([^)]+\))?'
    r'|prompt[\s_-]*(?:\d+|[ivx]+)?(?:\s*\([^)]+\))?'
    r'|[a-z0-9][\w ._-]{0,80}\.(?:png|jpe?g|webp|gif|avif)'
    r')'
    r'\s*(?:(?:\*\*+|__+|`+|\*+)\s*)*:\s*(?P<body>.*)$'
)


_SEQUENTIAL_BOLD_ALPHA_IMAGE_PROMPT_LINE_RE = re.compile(
    r'^\s*(?:[-*#>\u2022]+\s+)?'
    r'(?P<wrapper>\*\*|__)'
    r'(?P<label>[A-Z])\s*:\s*'
    r'(?P=wrapper)\s*'
    r'(?P<body>.+?)\s*$'
)


_PLAIN_ALPHA_IMAGE_PROMPT_LINE_RE = re.compile(
    r'^\s*(?P<label>[A-Z])\s*:\s*(?P<body>.+?)\s*$'
)


_ARTIFACT_LABELED_IMAGE_PROMPT_HEADING_RE = re.compile(
    r'(?i)^\s*(?:[-*#>\u2022]+\s*)?(?:\*\*+|__+|\*)?\s*'
    r'(?:artifact|artefakt)\s*(?:\d+|[ivx]+)?\s*:\s*'
    r'(?:'
    r'(?:image|visual)\s*(?:generation\s*)?prompt'
    r'|bild(?:generierungs?|\s+generation)?[-\s]*prompt'
    r')'
    r'(?:\s*(?:\([^)]+\)|\[[^\]]+\]))?'
    r'\s*(?:\*\*+|__+|\*)?\s*:?\s*$'
)


_ARTIFACT_SECTION_HEADING_RE = re.compile(
    r'(?i)^\s*(?:[-*#>\u2022]+\s*)?(?:\*\*+|__+|\*)?\s*'
    r'(?:artifact|artefakt)\s*(?:\d+|[ivx]+)?\s*:\s*\S.*$'
)


_NUMBERED_ARTIFACT_SECTION_HEADING_RE = re.compile(
    r'(?i)^\s*(?:[-*#>\u2022]+\s*)?(?:\*\*+|__+|\*)?\s*'
    r'(?:artifact|artefakt)\s*(?P<index>\d+|[ivx]+)\s*:\s*'
    r'(?P<title>\S.*?)\s*(?:\*\*+|__+|\*)?\s*$'
)


_EMBEDDED_LABELED_IMAGE_PROMPT_RE = re.compile(
    r'(?ims)(?:^|[\r\n])\s*(?:[-*#>\u2022]+\s*)?(?:\*\*+|__+|\*)?\s*'
    r'(?:visual\s+prompt|image\s+prompt|bild[-\s]?prompt|prompt)'
    r'\s*(?:\*\*+|__+|\*)?\s*:\s*(?P<body>.*?)(?='
    r'(?:[\r\n]\s*(?:[-*#>\u2022]+\s*)?(?:\*\*+|__+|\*)?\s*'
    r'(?:asset\s+id|@?username|user\s*name|caption|influencer|'
    r'visual\s+prompt|image\s+prompt|bild[-\s]?prompt|prompt)\b'
    r'\s*(?:\*\*+|__+|\*)?\s*:)|\Z)'
)


_IMAGE_ASSET_LABEL_PREFIX_RE = re.compile(
    r'(?is)^(?:(?:\*\*+|__+|`+|\*+)\s*)*'
    r'(?:(?:<b>|<strong>)\s*)?'
    r'[a-z0-9][\w ._-]{0,100}\.(?:png|jpe?g|webp|gif|avif)'
    r'(?:\s*</(?:b|strong)>)?'
    r'\s*(?:(?:\*\*+|__+|`+|\*+)\s*)*:\s*'
)


_FILENAME_SOCIAL_ASSET_ROW_RE = re.compile(
    r'(?im)^\s*(?:[-*#>\u2022]+\s*)?(?:\d{1,3}|[ivx]+)[.)]\s*'
    r'(?:\*\*+|__+|`+|\*+)?\s*'
    r'(?:(?:<b>|<strong>)\s*)?'
    r'(?P<filename>[a-z0-9][\w ._-]{0,140}\.(?:png|jpe?g|webp|gif|avif))'
    r'(?:\s*</(?:b|strong)>)?'
    r'\s*(?:\*\*+|__+|`+|\*+)?\s*:\s*(?P<body>[^\n]+)$'
)


_STRUCTURAL_PAGE_IMAGE_ASSET_LABEL_RE = re.compile(
    r'(?i)\b(?:hero(?:[-_\s]?(?:bg|background))?|background|banner|cover|masthead)'
    r'[\w ._-]{0,40}\.(?:png|jpe?g|webp|gif|avif)\b'
)


_NUMBERED_PREPARED_IMAGE_PROMPT_RE = re.compile(
    r'(?ms)(?:^|\n)\s*(?:\d{1,2}|[ivx]+)[.)]\s+'
    r'(?P<body>.*?)(?=(?:\n\s*(?:\d{1,2}|[ivx]+)[.)]\s+)|\Z)'
)


_NAMED_TEXT_ARTIFACT_FILENAME_RE = re.compile(
    r'(?<![A-Za-z0-9._-])'
    r'[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.(?:'
    + '|'.join(sorted(TEXT_ARTIFACT_EXTENSIONS, key=len, reverse=True))
    + r')(?![A-Za-z0-9_-])',
    re.IGNORECASE,
)


def _parse_image_batch_expected_count(
    raw_value: Any,
    *,
    present: bool,
) -> tuple[int, bool]:
    """Return ``(count, invalid)`` without treating malformed metadata as absent.

    A missing/empty field is the legacy single-image shape. Once a non-empty
    count carrier is present, malformed or out-of-range values must remain
    visible to the image contract instead of silently becoming zero.
    """

    if not present or raw_value in (None, '', [], {}):
        return 0, False
    if isinstance(raw_value, bool):
        return 0, True
    try:
        count = int(raw_value)
    except (TypeError, ValueError):
        return 0, True
    if count < 1 or count > 26:
        return 0, True
    if isinstance(raw_value, float) and not raw_value.is_integer():
        return 0, True
    return count, False


_NUMBERED_IMAGE_PROMPT_SEGMENT_PATTERNS = (
    r'(?ms)(?:^|\n)\s*\d+[.)]\s*(?P<body>.*?)(?=(?:\n\s*\d+[.)]\s*)|\Z)',
    r'(?ms)(?:^|\s)\d+[.)]\s*(?P<body>.*?)(?=(?:\s+\d+[.)]\s+)|\Z)',
)


_NUMBERED_PREPARED_IMAGE_SIGNAL_RE = re.compile(
    r'\b(?:'
    r'image|bild|photo|photograph|photography|foto|selfie|portrait|macro|'
    r'cinematic|camera|lens|lighting|render|illustration|poster|scene|shot|'
    r'close[-\s]?up|wide[-\s]?angle|hyper[-\s]?realistic'
    r')\b',
    re.IGNORECASE,
)


_PARAGRAPH_IMAGE_PROMPT_STRONG_SIGNAL_RE = re.compile(
    r'\b(?:'
    r'photo|photograph|photography|foto|selfie|portrait|macro|cinematic|camera|'
    r'lens|lighting|render|illustration|painting|poster|scene|shot|close[-\s]?up|'
    r'wide[-\s]?angle|hyper[-\s]?realistic|bokeh|depth\s+of\s+field'
    r')\b',
    re.IGNORECASE,
)


_SOCIAL_MANIFEST_HANDLE_RE = re.compile(
    r'^(?:[-*#>\u2022]+\s*)?(?:\*\*+|__+|\*+|`+)?\s*@(?P<handle>[A-Za-z0-9][\w.-]{1,100})'
)


_HEX_BYTE_FRAGMENT_RE = re.compile(r'(?:<0x[0-9a-fA-F]{2}>)+')


_SOCIAL_MANIFEST_VISUAL_SIGNAL_RE = re.compile(
    r'\b(?:'
    r'image|photo|photograph|photography|selfie|portrait|macro|micro|cinematic|'
    r'camera|lens|lighting|glow|bokeh|underwater|aerial|wide[-\s]?angle|'
    r'close[-\s]?up|ultra[-\s]?wide|extreme|chiaroscuro|high[-\s]?contrast|'
    r'saturated|vibrant|shallow\s+depth|depth\s+of\s+field|motion\s+blur|'
    r'texture|textures|reflection|reflections|backlight|sunlight|forest|jungle|'
    r'desert|ocean|canopy|macro\s+lens'
    r')\b',
    re.IGNORECASE,
)


_SOCIAL_MANIFEST_CAPTION_COPY_RE = re.compile(
    r'\b(?:'
    r'my|me|mine|ich|mein|meine|mich|posted|post|snacks?|vibes?|lifestyle|'
    r'goals?|dreams?|mood|waiting|stay|just|found|living|levels?\s+are|'
    r'off\s+the\s+charts|isn[\'’]?t\s+just|hungry|nap\s+time'
    r')\b',
    re.IGNORECASE,
)


_SOCIAL_ASSET_FILENAME_STOPWORDS = {
    'asset',
    'assets',
    'background',
    'banner',
    'bg',
    'card',
    'cover',
    'file',
    'gallery',
    'global',
    'hero',
    'image',
    'img',
    'main',
    'photo',
    'pic',
    'picture',
    'post',
    'selfie',
    'snout',
    'thumb',
    'thumbnail',
    'visual',
}


_MARKDOWN_SEPARATOR_LINE_RE = re.compile(r'^\s*(?:\*{3,}|-{3,}|_{3,})\s*$')


def _strip_handoff_markdown_wrappers(value: Any) -> str:
    text = str(value or '').strip()
    while text:
        updated = text
        for prefix, suffix in (('**', '**'), ('__', '__'), ('*', '*'), ('_', '_'), ('`', '`')):
            if updated.startswith(prefix) and updated.endswith(suffix) and len(updated) > len(prefix) + len(suffix):
                updated = updated[len(prefix):-len(suffix)].strip()
        updated = updated.strip('[]').strip()
        if updated == text:
            break
        text = updated
    return text


def _clean_social_manifest_piece(value: Any) -> str:
    text = _strip_handoff_markdown_wrappers(value).strip()
    text = _HEX_BYTE_FRAGMENT_RE.sub(' ', text)
    text = re.sub(r'^\s*(?:[-*#>\u2022]+\s*)+', '', text).strip()
    text = re.sub(
        r'^(?:id|asset\s*id|user|username|handle|influencer|caption|location|scenario|style|visual\s*style|visual\s+prompt|image\s+prompt|prompt)\s*:\s*',
        '',
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = re.split(
        r'\s+(?:\*\*+|__+|\*+)?(?:category|section|part|phase)\s*:',
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    text = re.split(r'\s+#{1,6}\s+', text, maxsplit=1)[0].strip()
    text = text.strip('`*_ ')
    text = text.strip().strip('"“”')
    text = re.sub(r'\s+', ' ', text).strip(' ,;')
    return text


def _split_social_manifest_labeled_piece(value: Any) -> tuple[str, str]:
    text = str(value or '').strip()
    if not text:
        return '', ''
    text = re.sub(r'^\s*(?:[-*#>\u2022]+\s*)+', '', text).strip()
    match = re.match(
        r'(?is)^(?:\*\*+|__+|`+|\*+)?\s*'
        r'(?P<label>[a-z][\w\s/-]{0,48}?)'
        r'\s*(?:\*\*+|__+|`+|\*+)?\s*:\s*'
        r'(?P<body>.*)$',
        text,
    )
    if not match:
        return '', _clean_social_manifest_piece(text)
    label = re.sub(r'\s+', ' ', str(match.group('label') or '')).strip().lower()
    body = _clean_social_manifest_piece(match.group('body'))
    return label, body


def _social_manifest_handle_to_subject(value: Any) -> str:
    text = str(value or '').strip().lstrip('@')
    text = re.sub(r'\.(?:png|jpe?g|webp|gif|avif)$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[_\-.]+', ' ', text)
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    return re.sub(r'\s+', ' ', text).strip(' ,;')


def _social_manifest_subject_to_prompt_piece(value: Any) -> str:
    subject = _social_manifest_handle_to_subject(value)
    if not subject:
        return ''
    if subject.lower() == subject:
        subject = subject.title()
    return subject


def _social_manifest_piece_looks_like_caption_copy(value: Any) -> bool:
    raw_text = str(value or '').strip()
    text = _clean_social_manifest_piece(raw_text)
    if not text:
        return False
    if _SOCIAL_MANIFEST_VISUAL_SIGNAL_RE.search(text):
        return False
    if _HEX_BYTE_FRAGMENT_RE.search(raw_text):
        return True
    if re.search(r'[!?]|\.{2,}', raw_text):
        return True
    return bool(_SOCIAL_MANIFEST_CAPTION_COPY_RE.search(text))


def _strip_unlabeled_social_manifest_image_prompt_metadata(raw_value: Any) -> str:
    text = str(raw_value or '').strip()
    if not text or ',' not in text or _image_prompt_candidate_is_code_or_css_polluted(text):
        return ''
    parts = [_clean_social_manifest_piece(part) for part in text.split(',')]
    parts = [part for part in parts if part]
    if len(parts) < 3:
        return ''
    # A grammatical image-prompt opener is prose, not an unlabeled social
    # handle.  Misclassifying it would normalize semantic punctuation in the
    # subject (for example, ``hyper-detailed`` became ``hyper detailed``).
    if re.match(r'(?i)^(?:a|an|the)\s+', parts[0]):
        return ''
    if _SOCIAL_MANIFEST_VISUAL_SIGNAL_RE.search(parts[0]):
        return ''
    visual_index = -1
    for index, part in enumerate(parts[1:], start=1):
        if _image_prompt_candidate_is_code_or_css_polluted(part):
            continue
        if _SOCIAL_MANIFEST_VISUAL_SIGNAL_RE.search(part):
            visual_index = index
            break
    if visual_index <= 0:
        return ''
    subject = _social_manifest_subject_to_prompt_piece(parts[0])
    context_parts = [
        part
        for part in parts[1:visual_index]
        if part
        and not _social_manifest_piece_looks_like_caption_copy(part)
        and not _image_prompt_candidate_is_code_or_css_polluted(part)
    ]
    visual_parts = [
        part
        for part in parts[visual_index:]
        if part and not _image_prompt_candidate_is_code_or_css_polluted(part)
    ]
    if not visual_parts:
        return ''
    cleaned = ', '.join(part for part in [subject, *context_parts, *visual_parts] if part)
    cleaned = re.sub(r'[`|@]+', '', cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip(' ,;')


def _clean_social_manifest_prefix_prompt_body(raw_value: Any) -> str:
    body = _clean_social_manifest_piece(raw_value)
    body = re.sub(r'(?i)(?:\*\*+|__+|`+|\*+)?\s*style\s*:\s*', '', body)
    body = re.sub(r'(?:\*\*+|__+|`+)', '', body)
    return re.sub(r'\s+', ' ', body).strip(' ,;')


def _social_manifest_prefix_body_looks_like_image_prompt(raw_value: Any) -> bool:
    body = _clean_social_manifest_prefix_prompt_body(raw_value)
    if not body or _image_prompt_candidate_is_code_or_css_polluted(body):
        return False
    if (
        _SOCIAL_MANIFEST_VISUAL_SIGNAL_RE.search(body)
        or _NUMBERED_PREPARED_IMAGE_SIGNAL_RE.search(body)
    ):
        return True
    words = re.findall(r'\w+', body)
    if len(words) < 6:
        return False
    if re.search(r'(?i)(?:^|[;,.]\s*)(?:a|an|the)\s+[a-z][\w-]+', body):
        return True
    if re.search(r'(?i)\bstyle\s*:', str(raw_value or '')):
        return True
    return False


def _strip_social_manifest_prefix_label(raw_value: Any) -> str:
    text = str(raw_value or '').strip()
    if not text or ':' not in text or '|' in text or _image_prompt_candidate_is_code_or_css_polluted(text):
        return ''
    match = re.match(
        r'(?is)^\s*(?:[-*#>\u2022]+\s*)?'
        r'(?P<label>@?[A-Za-z0-9][\w ._-]{1,100}?)'
        r'(?P<wrapper>\s*(?:\*\*+|__+|\*+|`+)*)\s*:\s*'
        r'(?P<body>.+)$',
        text,
    )
    if not match:
        return ''
    label_raw = str(match.group('label') or '').strip()
    wrapper = str(match.group('wrapper') or '')
    body = _clean_social_manifest_prefix_prompt_body(match.group('body'))
    if not label_raw or not body or _image_prompt_candidate_is_code_or_css_polluted(body):
        return ''
    if not _social_manifest_prefix_body_looks_like_image_prompt(match.group('body')):
        return ''
    label = _clean_social_manifest_piece(label_raw)
    if not label:
        return ''
    if re.match(
        r'(?i)^(?:id|asset\s*id|prompt|image|bild|visual|scene|style|caption|user|username|handle)\b',
        label,
    ):
        return ''
    label_has_visual_signal = bool(
        _SOCIAL_MANIFEST_VISUAL_SIGNAL_RE.search(label)
        or _NUMBERED_PREPARED_IMAGE_SIGNAL_RE.search(label)
    )
    label_is_metadata = bool(
        label_raw.lstrip().startswith('@')
        or wrapper.strip()
        or re.search(r'[_@]', label_raw)
        or len(re.findall(r'\w+', label)) <= 4
    )
    if not label_is_metadata:
        return ''
    if label_has_visual_signal and not label_raw.lstrip().startswith('@') and not wrapper.strip():
        return ''
    return re.sub(r'\s+', ' ', body).strip(' ,;')


def _strip_social_manifest_image_prompt_metadata(raw_value: Any) -> str:
    text = str(raw_value or '').strip()
    if not text:
        return ''
    prefix_label_body = _strip_social_manifest_prefix_label(text)
    if prefix_label_body:
        return prefix_label_body
    if '|' not in text:
        return _strip_unlabeled_social_manifest_image_prompt_metadata(text)
    labeled_parts = [_split_social_manifest_labeled_piece(part) for part in text.split('|')]
    prompt_labels = {'prompt', 'visual prompt', 'image prompt', 'bild prompt', 'bild-prompt'}
    for label, body in labeled_parts:
        if label in prompt_labels and body and not _image_prompt_candidate_is_code_or_css_polluted(body):
            return re.sub(r'\s+', ' ', body).strip(' ,;')
    parts = [body for _label, body in labeled_parts]
    parts = [part for part in parts if part]
    if len(parts) < 3:
        return ''
    handle_part = ''
    for label, body in labeled_parts:
        if label in {'user', 'username', 'handle', 'influencer'} and body:
            handle_part = body
            break
    if not handle_part:
        handle_part = parts[0]
    handle_match = _SOCIAL_MANIFEST_HANDLE_RE.match(handle_part)
    if not handle_match:
        return ''
    visual_index = -1
    for index in range(len(parts) - 1, 0, -1):
        part = parts[index]
        if _image_prompt_candidate_is_code_or_css_polluted(part):
            continue
        if _SOCIAL_MANIFEST_VISUAL_SIGNAL_RE.search(part):
            visual_index = index
            break
    if visual_index <= 0:
        return ''
    subject = _social_manifest_subject_to_prompt_piece(handle_match.group('handle'))
    context_labels = {'location', 'scenario', 'setting', 'context', 'mood', 'style', 'visual style'}
    context_parts: list[str] = []
    for index, part in enumerate(parts[1:visual_index], start=1):
        if not part or _image_prompt_candidate_is_code_or_css_polluted(part):
            continue
        if _social_manifest_piece_looks_like_caption_copy(part):
            continue
        label = labeled_parts[index][0]
        if label in context_labels:
            context_parts.append(part)
    visual = parts[visual_index]
    cleaned = ', '.join(part for part in [subject, *context_parts, visual] if part)
    cleaned = re.sub(r'[`|@]+', '', cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip(' ,;')


def _normalize_handoff_heading_line(raw_line: Any) -> str:
    text = _strip_handoff_markdown_wrappers(raw_line)
    text = re.sub(r'^\s*#{1,6}\s*', '', text).strip()
    text = re.sub(r'^\s*[-*>\u2022]+\s*', '', text).strip()
    # Decorative emoji and pictograms are presentation, not heading identity.
    # Strip only the non-word prefix so translated/alphanumeric headings remain
    # intact and later structural classifiers can reason about their wording.
    text = re.sub(r'^[\W_]+', '', text, flags=re.UNICODE).strip()
    return text.rstrip(':').strip()


def _is_image_prompt_section_heading(raw_line: Any) -> bool:
    heading = _normalize_handoff_heading_line(raw_line).lower()
    if not heading:
        return False
    if any(token in heading for token in ('index.html', 'styles.css', 'html', 'css')):
        return False
    match_heading = re.sub(r'\s*(?:\([^)]*\)|\[[^\]]*\])\s*$', '', heading).strip()
    if re.search(r'\b(?:image|bild|visual|asset|art)[\w\s/_-]{0,80}manifests?\b', match_heading):
        return True
    return bool(
        re.fullmatch(
            r'(?:image|bild|visual|asset|art)[\w\s/-]{0,80}(?:prompt|prompts|requirements|instructions?|directions?|assets|briefs?|manifests?)',
            match_heading,
        )
        or re.fullmatch(
            r'(?:prompt|prompts|requirements|instructions?|directions?|assets|briefs?|manifests?)[\w\s/-]{0,80}(?:image|bild|visual|art)',
            match_heading,
        )
    )


def _is_named_text_artifact_section_heading(raw_line: Any) -> bool:
    raw_text = str(raw_line or '').strip()
    if not raw_text or '\n' in raw_text or '\r' in raw_text or len(raw_text) > 320:
        return False
    normalized = _normalize_handoff_heading_line(raw_text)
    if not _NAMED_TEXT_ARTIFACT_FILENAME_RE.search(normalized):
        return False
    markdown_heading = bool(
        re.match(r'^\s*(?:#{1,6}\s+|\*\*|__|[-*>\u2022]+\s+)', raw_text)
    )
    named_artifact_label = bool(
        re.match(
            r'(?i)^(?:updated?|revised?|new|final|complete|replacement|'
            r'artifact|file|document|page|stylesheet|script|data|'
            r'aktualisiert(?:e|en|er|es)?|überarbeitet(?:e|en|er|es)?|'
            r'neu(?:e|en|er|es)?|datei|dokument|seite)\b',
            normalized,
        )
    )
    filename_only = bool(
        re.fullmatch(
            r'(?i)(?:updated?\s+|revised?\s+|final\s+|complete\s+)?'
            r'[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.(?:'
            + '|'.join(sorted(TEXT_ARTIFACT_EXTENSIONS, key=len, reverse=True))
            + r')(?:\s*\([^\n]{1,160}\))?\s*:?',
            normalized,
        )
    )
    return bool(markdown_heading or named_artifact_label or filename_only)


def _is_image_prompt_section_stop(raw_line: Any) -> bool:
    stripped = str(raw_line or '').strip()
    if not stripped:
        return False
    if _MARKDOWN_SEPARATOR_LINE_RE.fullmatch(stripped):
        return True
    lowered = _normalize_handoff_heading_line(stripped).lower()
    if stripped.startswith('```'):
        return True
    if _is_named_text_artifact_section_heading(stripped):
        return True
    if re.fullmatch(r'#{1,6}\s+\S.*', stripped):
        normalized_heading = _normalize_handoff_heading_line(stripped)
        if not (
            _is_image_prompt_section_heading(stripped)
            or _MULTI_IMAGE_HEADING_LINE_RE.fullmatch(normalized_heading)
            or _INLINE_LABELED_IMAGE_PROMPT_LINE_RE.match(stripped)
            or _ARTIFACT_LABELED_IMAGE_PROMPT_HEADING_RE.fullmatch(stripped)
        ):
            return True
    if re.fullmatch(r'(?:html|css|javascript|js|index|styles?|page files?|text artifacts?)', lowered):
        return True
    if re.match(r'(?:phase|internal phase|closure|materialization|artifact|runtime)\s+contract\b', lowered):
        return True
    if lowered in {'summary', 'notes', 'implementation notes'} or lowered.startswith(
        ('summary:', 'notes:', 'implementation notes:')
    ):
        return True
    html_probe = re.sub(r'^\s*(?:\d{1,3}|[ivx]+)[.)]\s*', '', stripped, flags=re.IGNORECASE).strip()
    html_probe = _IMAGE_ASSET_LABEL_PREFIX_RE.sub('', html_probe).strip()
    if re.search(r'(?i)</?[a-z][^>]*>|(?:href|src)\s*=|url\(', html_probe):
        return True
    return False


def _image_prompt_candidate_is_code_or_css_polluted(raw_value: Any) -> bool:
    text = str(raw_value or '').strip()
    if not text:
        return False
    lowered = text.lower()
    if re.search(r'(?m)^\s*\|[^|\n]+\|', text):
        return True
    if any(
        _is_named_text_artifact_section_heading(line)
        for line in text.splitlines()
    ):
        return True
    if any(token in lowered for token in ('```', '<html', '</', 'url(')):
        return True
    if re.search(r'(?is)</?[a-z][^>]*>|(?:href|src)\s*=', text):
        return True
    if re.match(r'(?is)^\s*@(?:media|keyframes|supports|container|font-face)\b', text):
        return True
    if re.search(
        r'(?is)\{[^}]*\b(?:margin|padding|box-sizing|font-family|'
        r'background(?:-color|-image)?|color|display|position|width|height|'
        r'line-height|overflow-x|transform|box-shadow|opacity|animation|'
        r'transition|font-size|border(?:-radius|-color|-width|-style)?|'
        r'object-fit|grid(?:-template(?:-columns|-rows)?|-area)?|'
        r'justify-content|align-items|gap|top|right|bottom|left|z-index|'
        r'--[\w-]+)\s*:',
        text,
    ):
        return True
    if re.match(
        r'(?is)^\s*(?:css\s+)?(?::root|body|html|[*#.]|'
        r'(?:[.#][\w-]+|[a-z][\w-]*)(?:[.#:\s>\[\]=\'"(),+-][^{;\n]*)?)\s*\{',
        text,
    ):
        return True
    if (
        re.match(r'(?is)^\s*(?:[.#][\w-]+|[a-z][\w-]*|[*])[^{}\n]{0,180}\{', text)
        and re.search(r'(?is)\{[^}]*\b[a-z-]+\s*:', text)
    ):
        return True
    if re.match(
        r'(?is)^\s*(?:css\s+)?(?:margin|padding|box-sizing|font-family|'
        r'background(?:-color|-image)?|color|display|position|width|height|'
        r'line-height|overflow-x|transform|box-shadow|opacity|animation|'
        r'transition|font-size|border(?:-radius|-color|-width|-style)?|'
        r'object-fit|grid(?:-template(?:-columns|-rows)?|-area)?|'
        r'justify-content|align-items|gap|top|right|bottom|left|z-index|'
        r'--[\w-]+)\s*:',
        text,
    ):
        return True
    return False


def _filename_social_asset_subject_piece(filename: Any) -> str:
    stem = Path(str(filename or '')).stem
    tokens = [
        token
        for token in re.split(r'[\s_.-]+', stem)
        if token
    ]
    filtered = [
        token
        for token in tokens
        if not re.fullmatch(r'\d+', token)
        and token.lower() not in _SOCIAL_ASSET_FILENAME_STOPWORDS
    ]
    if not filtered:
        filtered = [token for token in tokens if token and not re.fullmatch(r'\d+', token)]
    return _social_manifest_subject_to_prompt_piece(' '.join(filtered))


def _social_manifest_piece_is_quoted(raw_value: Any) -> bool:
    text = str(raw_value or '').strip()
    if not text:
        return False
    _label, body = _split_social_manifest_labeled_piece(text)
    if body and body != _clean_social_manifest_piece(text):
        text = body
    text = _strip_handoff_markdown_wrappers(text).strip()
    return (
        (text.startswith('"') and text.endswith('"'))
        or (text.startswith('“') and text.endswith('”'))
        or (text.startswith("'") and text.endswith("'"))
    )


def _filename_social_asset_prompt_from_row(filename: Any, body: Any) -> str:
    subject = _filename_social_asset_subject_piece(filename)
    if not subject:
        return ''
    raw_parts = [part for part in str(body or '').split('|') if str(part or '').strip()]
    if len(raw_parts) < 2:
        return ''
    labeled_parts = [_split_social_manifest_labeled_piece(part) for part in raw_parts]
    has_social_handle = any(
        (
            label in {'user', 'username', 'handle', 'influencer'}
            and value
        )
        or _SOCIAL_MANIFEST_HANDLE_RE.match(str(raw_parts[index] or '').strip())
        or str(raw_parts[index] or '').strip().lstrip('`*_ ').startswith('@')
        for index, (label, value) in enumerate(labeled_parts)
    )
    if not has_social_handle:
        return ''
    prompt_labels = {'prompt', 'visual prompt', 'image prompt', 'bild prompt', 'bild-prompt'}
    for label, value in labeled_parts:
        if label in prompt_labels and value and not _image_prompt_candidate_is_code_or_css_polluted(value):
            return re.sub(r'\s+', ' ', value).strip(' ,;')
    visual_parts: list[str] = []
    for index, raw_part in enumerate(raw_parts):
        label, value = labeled_parts[index]
        if not value or _image_prompt_candidate_is_code_or_css_polluted(value):
            continue
        if label in {'id', 'asset id', 'user', 'username', 'handle', 'influencer', 'caption'}:
            continue
        if _SOCIAL_MANIFEST_HANDLE_RE.match(value) or str(raw_part or '').strip().lstrip('`*_ ').startswith('@'):
            continue
        if _social_manifest_piece_is_quoted(raw_part):
            continue
        if _social_manifest_piece_looks_like_caption_copy(raw_part):
            continue
        is_last_piece = index == len(raw_parts) - 1
        if (
            label in {'location', 'scenario', 'setting', 'context', 'mood', 'style', 'visual style'}
            or is_last_piece
            or _SOCIAL_MANIFEST_VISUAL_SIGNAL_RE.search(value)
            or _NUMBERED_PREPARED_IMAGE_SIGNAL_RE.search(value)
        ):
            if value not in visual_parts:
                visual_parts.append(value)
    prompt = ', '.join(part for part in [subject, *visual_parts] if part)
    prompt = re.sub(r'[`|@]+', '', prompt)
    prompt = re.sub(r'\s+', ' ', prompt).strip(' ,;')
    if not prompt or _image_prompt_candidate_is_code_or_css_polluted(prompt):
        return ''
    if len(re.findall(r'\w+', prompt)) < 4:
        prompt = f'{prompt}, social media portrait'
    return re.sub(r'\s+', ' ', prompt).strip(' ,;')


def _extract_filename_social_asset_image_prompt_lines(
    prepared_text: str,
    *,
    expected_count: int = 0,
) -> list[str]:
    prompts: list[str] = []
    for match in _FILENAME_SOCIAL_ASSET_ROW_RE.finditer(str(prepared_text or '')):
        prompt = _filename_social_asset_prompt_from_row(
            match.group('filename'),
            match.group('body'),
        )
        if prompt:
            prompts.append(prompt)
        if expected_count > 0 and len(prompts) >= expected_count:
            break
    if expected_count > 0:
        return prompts[:expected_count]
    return prompts


def _image_prompt_batch_looks_like_weak_social_copy(prompts: Any) -> bool:
    if not isinstance(prompts, list) or not prompts:
        return False
    weak_count = 0
    for raw_prompt in prompts:
        prompt = str(raw_prompt or '').strip()
        if not prompt or _image_prompt_candidate_is_code_or_css_polluted(prompt):
            weak_count += 1
            continue
        if (
            _SOCIAL_MANIFEST_VISUAL_SIGNAL_RE.search(prompt)
            or _NUMBERED_PREPARED_IMAGE_SIGNAL_RE.search(prompt)
        ):
            continue
        words = re.findall(r'\w+', prompt)
        if len(words) <= 8:
            weak_count += 1
            continue
        if _social_manifest_piece_looks_like_caption_copy(prompt):
            weak_count += 1
    return weak_count >= max(1, (len(prompts) + 1) // 2)


def _embedded_labeled_image_prompt_body(raw_value: Any) -> str:
    text = str(raw_value or '').strip()
    if not text:
        return ''
    matches = list(_EMBEDDED_LABELED_IMAGE_PROMPT_RE.finditer(text))
    if not matches:
        return ''
    return str(matches[-1].group('body') or '').strip()


def _clean_numbered_image_prompt_candidate(raw_value: Any) -> str:
    text = str(raw_value or '').strip()
    if not text:
        return ''
    bounded_lines: list[str] = []
    for raw_line in text.splitlines():
        if _is_image_prompt_section_stop(raw_line):
            break
        bounded_lines.append(raw_line)
    text = '\n'.join(bounded_lines).strip()
    if not text:
        return ''
    if _NAMED_TEXT_ARTIFACT_FILENAME_RE.search(text):
        return ''
    embedded_body = _embedded_labeled_image_prompt_body(text)
    if embedded_body:
        text = embedded_body
    social_manifest_body = _strip_social_manifest_image_prompt_metadata(text)
    if social_manifest_body:
        text = social_manifest_body
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'^[:\-–—]\s*', '', text).strip()
    text = _strip_handoff_markdown_wrappers(text).strip()
    text = re.sub(r'^(?:>\s*)+', '', text).strip()
    text = _IMAGE_ASSET_LABEL_PREFIX_RE.sub('', text).strip()
    text = re.sub(r'^(?:\*\*+|__+|`+)\s*', '', text).strip()
    text = re.sub(r'\s*(?:\*\*+|__+|`+)$', '', text).strip()
    lowered = text.lower()
    if not text:
        return ''
    if _image_prompt_candidate_is_code_or_css_polluted(text):
        return ''
    if re.fullmatch(r'(?:image\s+generation\s+)?prompts?', lowered):
        return ''
    if len(re.findall(r'\w+', text)) < 3:
        return ''
    return text


def _clean_image_prompt_boundary_candidate(raw_value: Any) -> str:
    return _clean_numbered_image_prompt_candidate(raw_value)


def _is_non_image_markdown_section_heading(raw_line: Any) -> bool:
    line = str(raw_line or '').strip()
    if not line or _is_image_prompt_section_heading(line):
        return False
    if re.fullmatch(r'#{1,6}\s+\S.*', line):
        return True
    return bool(
        re.fullmatch(
            r'(?P<wrapper>\*\*|__)\s*\S(?:.*\S)?\s*(?P=wrapper)',
            line,
        )
    )


def _extract_sequential_bold_alpha_image_prompt_lines(
    prepared_text: str,
    *,
    expected_count: int = 0,
    require_image_heading: bool = False,
) -> list[str]:
    """Extract a strongly ordered Markdown A/B/C image-prompt sequence.

    Single-letter labels are otherwise too ambiguous to treat as image prompts.
    Requiring bold wrappers, an A start, at least two consecutive labels, and no
    gaps keeps this parser distinct from general prose and section headings.
    """
    prompts: list[str] = []
    next_label_code = ord('A')
    sequence_started = False
    image_section_seen = not require_image_heading
    for raw_line in str(prepared_text or '').splitlines():
        line = str(raw_line or '').strip()
        if not line:
            continue
        if require_image_heading and not image_section_seen:
            if _is_image_prompt_section_heading(raw_line):
                image_section_seen = True
            continue
        if (
            require_image_heading
            and not sequence_started
            and (
                _is_image_prompt_section_stop(raw_line)
                or _is_non_image_markdown_section_heading(raw_line)
            )
        ):
            break
        match = _SEQUENTIAL_BOLD_ALPHA_IMAGE_PROMPT_LINE_RE.fullmatch(raw_line)
        if not sequence_started:
            if not match or str(match.group('label') or '') != 'A':
                continue
            sequence_started = True
        elif not match:
            break
        label = str(match.group('label') or '')
        if label != chr(next_label_code):
            break
        prompt = _clean_image_prompt_boundary_candidate(match.group('body'))
        if not prompt:
            break
        prompts.append(prompt)
        next_label_code += 1
        if expected_count > 0 and len(prompts) >= expected_count:
            break
    if len(prompts) < 2:
        return []
    if expected_count > 0:
        return prompts[:expected_count]
    return prompts


def _extract_leading_plain_alpha_image_prompt_lines(
    prepared_text: str,
    *,
    expected_count: int,
) -> list[str]:
    """Extract an exact graph-counted leading A/B/C producer sequence.

    Plain single-letter labels are ambiguous without caller-owned preparation
    context. This helper therefore returns authority only for a complete leading
    sequence whose count is already proven by the image-generation graph.
    """
    normalized_count = int(expected_count or 0)
    if normalized_count < 2 or normalized_count > 26:
        return []
    lines = str(prepared_text or '').splitlines()
    first_index = next(
        (index for index, raw_line in enumerate(lines) if str(raw_line or '').strip()),
        None,
    )
    if first_index is None:
        return []
    prompts: list[str] = []
    for offset in range(normalized_count):
        line_index = first_index + offset
        if line_index >= len(lines) or not str(lines[line_index] or '').strip():
            return []
        match = _PLAIN_ALPHA_IMAGE_PROMPT_LINE_RE.fullmatch(lines[line_index])
        if not match or str(match.group('label') or '') != chr(ord('A') + offset):
            return []
        prompt = _clean_image_prompt_boundary_candidate(match.group('body'))
        if not prompt:
            return []
        prompts.append(prompt)
    next_index = first_index + normalized_count
    if next_index < len(lines):
        next_match = _PLAIN_ALPHA_IMAGE_PROMPT_LINE_RE.fullmatch(lines[next_index])
        if next_match:
            return []
    return prompts if len(prompts) == normalized_count else []


def _contains_plain_alpha_image_prompt_line(prepared_text: str) -> bool:
    return any(
        _PLAIN_ALPHA_IMAGE_PROMPT_LINE_RE.fullmatch(str(raw_line or ''))
        for raw_line in str(prepared_text or '').splitlines()
    )


def _inline_labeled_image_prompt_body(raw_line: Any) -> Optional[str]:
    match = _INLINE_LABELED_IMAGE_PROMPT_LINE_RE.match(str(raw_line or ''))
    if not match:
        if _ARTIFACT_LABELED_IMAGE_PROMPT_HEADING_RE.fullmatch(str(raw_line or '')):
            return ''
        return None
    body = str(match.group('body') or '').strip()
    body = re.sub(r'^(?:\*\*+|__+|`+)\s*', '', body).strip()
    return body


def _inline_labeled_image_prompt_body_is_title(raw_value: Any) -> bool:
    text = str(raw_value or '').strip()
    wrapped_plain_title = bool(
        re.fullmatch(r'(?:\([^()\n]{1,120}\)|\[[^\[\]\n]{1,120}\])', text)
    )
    wrapped_markdown_title = bool(re.search(r'(?:\*\*+|__+)\s*$', text))
    if not text or not (wrapped_plain_title or wrapped_markdown_title):
        return False
    normalized = re.sub(r'(?:\*\*+|__+|`+)', '', text).strip()
    if wrapped_plain_title:
        normalized = normalized[1:-1].strip()
    if not normalized or re.search(r'[.!?]\s*$', normalized):
        return False
    return len(re.findall(r'\w+', normalized)) <= 10


def _extract_inline_labeled_image_prompt_lines(
    prepared_text: str,
    *,
    expected_count: int = 0,
) -> list[str]:
    lines = str(prepared_text or '').splitlines()
    prompts: list[str] = []
    index = 0
    while index < len(lines):
        raw_line = str(lines[index] or '')
        stripped = raw_line.strip()
        if prompts and (_MARKDOWN_SEPARATOR_LINE_RE.fullmatch(stripped) or _is_image_prompt_section_stop(stripped)):
            break
        body = _inline_labeled_image_prompt_body(raw_line)
        if body is None:
            index += 1
            continue
        collect_following_body = (
            not body
            or _inline_labeled_image_prompt_body_is_title(body)
        )
        if collect_following_body:
            collected: list[str] = []
            lookahead = index + 1
            while lookahead < len(lines):
                next_line = str(lines[lookahead] or '')
                next_stripped = next_line.strip()
                if (
                    _inline_labeled_image_prompt_body(next_line) is not None
                    or _ARTIFACT_SECTION_HEADING_RE.fullmatch(next_line)
                    or _MARKDOWN_SEPARATOR_LINE_RE.fullmatch(next_stripped)
                    or _is_image_prompt_section_stop(next_stripped)
                ):
                    break
                if next_stripped:
                    collected.append(next_line)
                lookahead += 1
            if collected or not body:
                body = '\n'.join(collected).strip()
            index = lookahead
        else:
            index += 1
        prompt = _clean_image_prompt_boundary_candidate(body)
        if prompt and prompt not in prompts:
            prompts.append(prompt)
        if expected_count > 0 and len(prompts) >= expected_count:
            break
    if expected_count > 0:
        return prompts[:expected_count]
    return prompts


def _extract_numbered_artifact_image_prompt_bodies(
    prepared_text: str,
    *,
    expected_count: int = 0,
) -> list[str]:
    """Read rich image bodies from numbered artifact sections.

    Some preparation models label image artifacts with their subject (for
    example ``Artifact 2: Forged Carbon Watch``) instead of the literal words
    ``Image Prompt``.  The heading is identity evidence, not a usable backend
    prompt.  Only the following body can become prompt authority, and only
    when it contains concrete visual-production language.  Filename and other
    non-image artifact sections remain hard boundaries.
    """

    lines = str(prepared_text or '').splitlines()
    prompts: list[str] = []
    index = 0
    while index < len(lines):
        heading_match = _NUMBERED_ARTIFACT_SECTION_HEADING_RE.fullmatch(
            str(lines[index] or '')
        )
        if not heading_match:
            index += 1
            continue
        collected: list[str] = []
        lookahead = index + 1
        while lookahead < len(lines):
            next_line = str(lines[lookahead] or '')
            next_stripped = next_line.strip()
            if (
                _ARTIFACT_SECTION_HEADING_RE.fullmatch(next_line)
                or _MARKDOWN_SEPARATOR_LINE_RE.fullmatch(next_stripped)
                or _is_image_prompt_section_stop(next_stripped)
            ):
                break
            if next_stripped:
                collected.append(next_line)
            lookahead += 1
        body = _clean_image_prompt_boundary_candidate('\n'.join(collected))
        if (
            body
            and _PARAGRAPH_IMAGE_PROMPT_STRONG_SIGNAL_RE.search(body)
            and body not in prompts
        ):
            prompts.append(body)
        index = max(lookahead, index + 1)
        if expected_count > 0 and len(prompts) >= expected_count:
            break
    if expected_count > 0:
        return prompts[:expected_count]
    return prompts


def _split_numbered_image_prompt_segment(segment: str) -> list[str]:
    text = str(segment or '').strip()
    if not text:
        return []
    for pattern in _NUMBERED_IMAGE_PROMPT_SEGMENT_PATTERNS:
        prompts: list[str] = []
        for match in re.finditer(pattern, text):
            cleaned = _clean_numbered_image_prompt_candidate(match.group('body'))
            if cleaned and cleaned not in prompts:
                prompts.append(cleaned)
        if len(prompts) >= 2:
            return prompts
    return []


def _split_numbered_image_prompt_raw_items(segment: str) -> list[str]:
    text = str(segment or '').strip()
    if not text:
        return []
    for pattern in _NUMBERED_IMAGE_PROMPT_SEGMENT_PATTERNS:
        items = [
            str(match.group('body') or '').strip()
            for match in re.finditer(pattern, text)
            if str(match.group('body') or '').strip()
        ]
        if len(items) >= 2:
            return items
    return []


def _numbered_image_prompts_allow_structural_surplus(
    segment: str,
    prompts: list[str],
    *,
    expected_count: int = 0,
) -> bool:
    if expected_count <= 0 or len(prompts) != expected_count + 1:
        return False
    raw_items = _split_numbered_image_prompt_raw_items(segment)
    if len(raw_items) != len(prompts):
        return False
    structural_count = sum(
        1
        for item in raw_items
        if _STRUCTURAL_PAGE_IMAGE_ASSET_LABEL_RE.search(item)
    )
    return structural_count == 1 and len(raw_items) - structural_count >= expected_count


def _limit_numbered_image_prompts_for_expected_count(
    prompts: list[str],
    *,
    expected_count: int = 0,
    segment: str = '',
) -> list[str]:
    if expected_count <= 0 or len(prompts) <= expected_count:
        return prompts
    if _numbered_image_prompts_allow_structural_surplus(
        segment,
        prompts,
        expected_count=expected_count,
    ):
        return prompts
    return prompts[:expected_count]


def _markdown_table_cells(raw_line: Any) -> list[str]:
    line = str(raw_line or '').strip()
    if not line.startswith('|') or '|' not in line[1:]:
        return []
    line = line.strip('|')
    return [
        _strip_handoff_markdown_wrappers(cell).strip()
        for cell in line.split('|')
    ]


def _markdown_table_separator_cells(cells: list[str]) -> bool:
    return bool(cells) and all(
        re.fullmatch(r':?-{3,}:?', str(cell or '').strip())
        for cell in cells
    )


def _markdown_table_prompt_column_index(cells: list[str]) -> int:
    normalized = [
        re.sub(r'[^a-z0-9]+', ' ', str(cell or '').strip().lower()).strip()
        for cell in cells
    ]
    preferred_patterns = (
        r'\bvisual\b.*\bprompt\b',
        r'\bprompt\b.*\bspecification\b',
        r'\bvisual\b.*\bspecification\b',
        r'\bimage\b.*\bprompt\b',
        r'\bprompt\b',
    )
    for pattern in preferred_patterns:
        for index, cell in enumerate(normalized):
            if re.search(pattern, cell):
                return index
    return -1


def _markdown_table_header_token(raw_value: Any) -> str:
    return re.sub(r'[^a-z0-9@]+', ' ', str(raw_value or '').strip().lower()).strip()


def _markdown_table_row_context_role(header_value: Any) -> str:
    header = _markdown_table_header_token(header_value)
    if not header:
        return ''
    if re.search(r'(?:^|\s)(?:id|asset|file|path|filename|image|img|slot|order|number)(?:\s|$)', header):
        return ''
    if '@' in header or re.search(r'\b(?:user\s*name|username|handle|influencer|subject|species|animal|character|name)\b', header):
        return 'subject'
    if re.search(r'\bcaption\b', header):
        return ''
    if re.search(r'\b(?:location|scenario|setting|context|mood|description|place)\b', header):
        return 'context'
    return ''


def _markdown_table_row_context_piece_is_placeholder(value: str, *, role: str) -> bool:
    text = re.sub(r'\s+', ' ', str(value or '').strip().lower()).strip(' .,:;_-')
    if not text:
        return True
    compact = re.sub(r'[\s_-]+', '', text)
    if compact in {'na', 'none', 'null', 'tbd', 'todo', 'placeholder'}:
        return True
    if role == 'subject' and re.fullmatch(
        r'(?:animal|influencer|user|username|handle|subject|species|character|asset|image|img|snout|selfie)\d{0,4}',
        compact,
    ):
        return True
    if role == 'context' and re.fullmatch(
        r'(?:caption|location|scenario|setting|context|mood|description|place)\d{0,4}',
        compact,
    ):
        return True
    return False


def _markdown_table_row_context_piece(cell_value: Any, *, role: str) -> str:
    text = _clean_social_manifest_piece(cell_value)
    if not text:
        return ''
    handle_match = _SOCIAL_MANIFEST_HANDLE_RE.match(text)
    if role == 'subject' and handle_match:
        text = _social_manifest_handle_to_subject(handle_match.group('handle'))
    else:
        text = re.sub(r'^@', '', text).strip()
    text = re.sub(r'\.(?:png|jpe?g|webp|gif|avif)$', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'[`|]+', '', text)
    text = re.sub(r'\s+', ' ', text).strip(' ,;.')
    if not text or _image_prompt_candidate_is_code_or_css_polluted(text):
        return ''
    if _markdown_table_row_context_piece_is_placeholder(text, role=role):
        return ''
    return text


def _image_prompt_candidate_has_subject_anchor(prompt: str) -> bool:
    text = str(prompt or '').strip()
    if not text:
        return False
    lowered = text.lower()
    visual_lead_words = {
        'aerial',
        'black',
        'bright',
        'cinematic',
        'cold',
        'crisp',
        'dappled',
        'dark',
        'deep',
        'dreamy',
        'extreme',
        'golden',
        'high',
        'low',
        'macro',
        'moody',
        'motion',
        'soft',
        'surface',
        'tropical',
        'ultra',
        'underwater',
        'vibrant',
        'warm',
        'wide',
    }
    if re.search(r'\b(?:of|with|showing|featuring|depicting|portrait of|photo of|shot of)\s+(?:a|an|the)?\s*[a-z0-9][\w-]+', lowered):
        return True
    article_match = re.search(r'\b(?:a|an|the)\s+([a-z][\w-]+)', lowered)
    if article_match and article_match.group(1) not in visual_lead_words:
        return True
    capitalized_entities = re.findall(r'(?<!^)\b[A-Z][a-z]+(?:[-\s][A-Z][a-z]+){0,3}\b', text)
    if capitalized_entities:
        return True
    return False


_HTML_IMG_TAG_RE = re.compile(r'(?is)<img\b(?P<attrs>[^>]*)>')


_HTML_ATTR_RE = re.compile(
    r'''(?is)\b(?P<name>[a-z_:][\w:.-]*)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)'''
)


_HTML_TEXT_TAG_RE = re.compile(
    r'(?is)<(?P<tag>p|span|h[1-6]|strong|em)\b(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>'
)


_HTML_HEX_BYTE_FRAGMENT_RE = re.compile(r'(?:<0x[0-9a-fA-F]{2}>)+')


_HTML_CARD_CONTEXT_CLASS_RE = re.compile(
    r'(?i)\b(?:caption|style|tag|prompt|description|text|location|scenario|mood)\b'
)


_HTML_CARD_HANDLE_CLASS_RE = re.compile(r'(?i)\b(?:user|username|handle|influencer|author)\b')


_HTML_CARD_CONTEXT_STOP_RE = re.compile(r'(?is)<footer\b|</(?:section|main|article)\b')


def _html_attrs(raw_attrs: Any) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _HTML_ATTR_RE.finditer(str(raw_attrs or '')):
        name = str(match.group('name') or '').strip().lower()
        value = html.unescape(str(match.group('value') or '').strip())
        if name:
            attrs[name] = value
    return attrs


def _clean_html_prompt_text(raw_value: Any) -> str:
    text = html.unescape(str(raw_value or ''))
    text = re.sub(r'(?is)<(?:script|style)\b.*?</(?:script|style)>', ' ', text)
    text = _HTML_HEX_BYTE_FRAGMENT_RE.sub(' ', text)
    text = re.sub(r'(?is)<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = text.strip().strip('"“”')
    return text.strip(' ,;')


def _html_card_context_piece(raw_value: Any, *, role: str = '') -> str:
    text = _clean_html_prompt_text(raw_value)
    if not text:
        return ''
    if role == 'handle':
        handle_match = _SOCIAL_MANIFEST_HANDLE_RE.match(text)
        if handle_match:
            text = _social_manifest_handle_to_subject(handle_match.group('handle'))
        else:
            text = text.lstrip('@')
    else:
        text = _clean_social_manifest_piece(text)
    text = re.sub(r'\s+', ' ', text).strip(' ,;.')
    if not text or _image_prompt_candidate_is_code_or_css_polluted(text):
        return ''
    return text


def _extract_html_image_card_prompt_units(
    prepared_text: str,
    *,
    expected_count: int = 0,
) -> list[str]:
    text = str(prepared_text or '')
    if '<img' not in text.lower():
        return []
    image_matches = list(_HTML_IMG_TAG_RE.finditer(text))
    if len(image_matches) < 2:
        return []
    prompts: list[str] = []
    for index, match in enumerate(image_matches):
        attrs = _html_attrs(match.group('attrs'))
        alt = _html_card_context_piece(attrs.get('alt'))
        src = str(attrs.get('src') or '').strip()
        if not alt and not src:
            continue
        next_start = image_matches[index + 1].start() if index + 1 < len(image_matches) else len(text)
        raw_segment = text[match.end(): min(next_start, match.end() + 1800)]
        stop_match = _HTML_CARD_CONTEXT_STOP_RE.search(raw_segment)
        segment = raw_segment[:stop_match.start()] if stop_match else raw_segment
        context_parts: list[str] = []
        handle_parts: list[str] = []
        for text_match in _HTML_TEXT_TAG_RE.finditer(segment):
            tag_attrs = _html_attrs(text_match.group('attrs'))
            class_text = str(tag_attrs.get('class') or '').strip()
            body = str(text_match.group('body') or '')
            role = 'handle' if _HTML_CARD_HANDLE_CLASS_RE.search(class_text) else ''
            if role == 'handle' or _clean_html_prompt_text(body).lstrip().startswith('@'):
                piece = _html_card_context_piece(body, role='handle')
                if piece and piece not in handle_parts:
                    handle_parts.append(piece)
                continue
            if class_text and not _HTML_CARD_CONTEXT_CLASS_RE.search(class_text):
                continue
            piece = _html_card_context_piece(body)
            if piece and piece not in context_parts:
                context_parts.append(piece)
        seed_parts = [alt] if alt else handle_parts[:1]
        if not seed_parts:
            continue
        prompt = _clean_image_prompt_boundary_candidate(', '.join([*seed_parts, *context_parts]))
        if prompt and prompt not in prompts:
            prompts.append(prompt)
        if expected_count > 0 and len(prompts) >= expected_count:
            break
    if expected_count > 0:
        return prompts[:expected_count]
    return prompts


def _markdown_table_compose_row_context_prompt(
    header_cells: list[str],
    row_cells: list[str],
    prompt_column: int,
    prompt: str,
) -> str:
    cleaned_prompt = _clean_image_prompt_boundary_candidate(prompt)
    if not cleaned_prompt:
        return ''
    if _image_prompt_candidate_has_subject_anchor(cleaned_prompt):
        return cleaned_prompt
    context_parts: list[str] = []
    for index, header in enumerate(header_cells):
        if index == prompt_column or index >= len(row_cells):
            continue
        role = _markdown_table_row_context_role(header)
        if not role:
            continue
        piece = _markdown_table_row_context_piece(row_cells[index], role=role)
        if piece and piece not in context_parts:
            context_parts.append(piece)
    if not context_parts:
        return cleaned_prompt
    composed = ', '.join([*context_parts, cleaned_prompt])
    return _clean_image_prompt_boundary_candidate(composed)


def _extract_markdown_table_image_prompts_from_lines(
    raw_lines: list[str],
    *,
    expected_count: int = 0,
) -> list[str]:
    table_candidates: list[list[str]] = []
    prompt_column = -1
    header_cells: list[str] = []
    table_started = False
    current_prompts: list[str] = []

    def finish_current_table() -> None:
        nonlocal prompt_column, header_cells, table_started, current_prompts
        if len(current_prompts) >= 2:
            table_candidates.append(list(current_prompts))
        prompt_column = -1
        header_cells = []
        table_started = False
        current_prompts = []

    for raw_line in [*raw_lines, '']:
        cells = _markdown_table_cells(raw_line)
        if not cells:
            if table_started or prompt_column >= 0:
                finish_current_table()
            continue
        if prompt_column < 0:
            candidate_column = _markdown_table_prompt_column_index(cells)
            if candidate_column < 0:
                continue
            prompt_column = candidate_column
            header_cells = list(cells)
            table_started = True
            continue
        table_started = True
        if _markdown_table_separator_cells(cells):
            continue
        if prompt_column >= len(cells):
            continue
        prompt = _markdown_table_compose_row_context_prompt(
            header_cells,
            cells,
            prompt_column,
            cells[prompt_column],
        )
        if prompt and prompt not in current_prompts:
            current_prompts.append(prompt)
        if expected_count > 0 and len(current_prompts) >= expected_count:
            return current_prompts[:expected_count]

    if not table_candidates:
        return []
    if expected_count > 0:
        for prompts in table_candidates:
            if len(prompts) >= expected_count:
                return prompts[:expected_count]
    best_candidate = max(table_candidates, key=len)
    return best_candidate[:expected_count] if expected_count > 0 else best_candidate


def _extract_markdown_table_image_prompt_section(
    prepared_text: str,
    *,
    expected_count: int = 0,
) -> list[str]:
    text = str(prepared_text or '').strip()
    if not text:
        return []
    lines = text.splitlines()
    start_index: Optional[int] = None
    for index, raw_line in enumerate(lines):
        if _is_image_prompt_section_heading(raw_line):
            start_index = index + 1
            break
    if start_index is None:
        return []
    section_lines: list[str] = []
    for raw_line in lines[start_index:]:
        if _is_image_prompt_section_stop(raw_line):
            break
        section_lines.append(str(raw_line or ''))
    return _extract_markdown_table_image_prompts_from_lines(
        section_lines,
        expected_count=expected_count,
    )


def _extract_markdown_table_image_prompt_anywhere(
    prepared_text: str,
    *,
    expected_count: int = 0,
) -> list[str]:
    text = str(prepared_text or '').strip()
    if not text:
        return []
    return _extract_markdown_table_image_prompts_from_lines(
        text.splitlines(),
        expected_count=expected_count,
    )


def _extract_social_manifest_pipe_image_prompt_lines(
    prepared_text: str,
    *,
    expected_count: int = 0,
) -> list[str]:
    prompts: list[str] = []
    for raw_line in str(prepared_text or '').splitlines():
        line = str(raw_line or '').strip()
        if not line:
            continue
        numbered_match = re.match(
            r'^\s*(?:[-*#>\u2022]+\s*)?(?:\d{1,3}|[ivx]+)[.)]\s+',
            line,
            flags=re.IGNORECASE,
        )
        prefix_prompt = _strip_social_manifest_prefix_label(line)
        if '|' not in line and numbered_match is None and not prefix_prompt:
            continue
        body = re.sub(
            r'^\s*(?:[-*#>\u2022]+\s*)?(?:\d{1,3}|[ivx]+)[.)]\s+',
            '',
            line,
            flags=re.IGNORECASE,
        ).strip()
        prompt = _strip_social_manifest_image_prompt_metadata(body)
        if prompt and prompt not in prompts:
            prompts.append(prompt)
        if expected_count > 0 and len(prompts) >= expected_count:
            break
    if expected_count > 0:
        return prompts[:expected_count]
    return prompts


def _extract_numbered_image_prompt_section(
    prepared_text: str,
    *,
    expected_count: int = 0,
) -> list[str]:
    text = str(prepared_text or '').strip()
    if not text:
        return []
    lines = text.splitlines()
    start_index: Optional[int] = None
    for index, raw_line in enumerate(lines):
        if _is_image_prompt_section_heading(raw_line):
            start_index = index + 1
            break
    if start_index is None:
        return []
    section_lines: list[str] = []
    for raw_line in lines[start_index:]:
        if _is_image_prompt_section_stop(raw_line):
            break
        section_lines.append(str(raw_line or ''))
    section_text = '\n'.join(section_lines)
    prompts = _split_numbered_image_prompt_segment(section_text)
    return _limit_numbered_image_prompts_for_expected_count(
        prompts,
        expected_count=expected_count,
        segment=section_text,
    )


def _extract_numbered_prepared_image_prompt_units(
    prepared_text: str,
    *,
    expected_count: int = 0,
) -> list[str]:
    text = str(prepared_text or '').strip()
    if not text:
        return []
    prompts: list[str] = []
    for match in _NUMBERED_PREPARED_IMAGE_PROMPT_RE.finditer(text):
        body = str(match.group('body') or '').strip()
        if not body:
            continue
        if _is_image_prompt_section_stop(body):
            break
        cleaned = _clean_numbered_image_prompt_candidate(body)
        if not cleaned:
            continue
        if not _NUMBERED_PREPARED_IMAGE_SIGNAL_RE.search(cleaned):
            continue
        if cleaned not in prompts:
            prompts.append(cleaned)
        if expected_count > 1 and len(prompts) >= expected_count:
            break
    if len(prompts) < 2:
        return []
    return prompts[:expected_count] if expected_count > 0 else prompts


def extract_batch_image_prompts(
    prepared_text: str,
    *,
    expected_count: int = 0,
    allow_plain_alpha_sequence: bool = False,
) -> list[str]:
    normalized_text = str(prepared_text or '').strip()
    prompts: list[str] = []
    # A narrowly typed indexed JSON batch is also unambiguous preparation.
    # Do not mine arbitrary JSON, sibling fields, data files or partial slots.
    if expected_count > 1 and normalized_text.startswith('['):
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('Ambiguous duplicate image prompt key')
                result[key] = value
            return result

        try:
            indexed_batch = json.loads(normalized_text, object_pairs_hook=unique_object)
        except (ValueError, TypeError):
            indexed_batch = None
        if isinstance(indexed_batch, list) and len(indexed_batch) == expected_count:
            indexed_prompts = []
            for index, item in enumerate(indexed_batch, start=1):
                key = f'prompt_{index}'
                if not isinstance(item, dict) or set(item) != {key}:
                    break
                value = item[key]
                if not isinstance(value, str) or not value.strip():
                    break
                indexed_prompts.append(value.strip())
            if len(indexed_prompts) == expected_count and len(set(indexed_prompts)) == expected_count:
                return indexed_prompts
    plain_alpha_candidate_present = bool(
        allow_plain_alpha_sequence
        and _contains_plain_alpha_image_prompt_line(normalized_text)
    )
    numbered_section_prompts = _extract_numbered_image_prompt_section(
        normalized_text,
        expected_count=expected_count,
    )
    filename_social_asset_prompts = _extract_filename_social_asset_image_prompt_lines(
        normalized_text,
        expected_count=expected_count,
    )
    if numbered_section_prompts and (
        expected_count <= 0 or len(numbered_section_prompts) >= expected_count
    ):
        if (
            filename_social_asset_prompts
            and (expected_count <= 0 or len(filename_social_asset_prompts) >= expected_count)
            and _image_prompt_batch_looks_like_weak_social_copy(numbered_section_prompts)
        ):
            return (
                filename_social_asset_prompts[:expected_count]
                if expected_count > 0
                else filename_social_asset_prompts
            )
        return numbered_section_prompts
    table_section_prompts = _extract_markdown_table_image_prompt_section(
        normalized_text,
        expected_count=expected_count,
    )
    if table_section_prompts and (
        expected_count <= 0 or len(table_section_prompts) >= expected_count
    ):
        return table_section_prompts[:expected_count] if expected_count > 0 else table_section_prompts
    table_anywhere_prompts = _extract_markdown_table_image_prompt_anywhere(
        normalized_text,
        expected_count=expected_count,
    )
    if table_anywhere_prompts and (
        expected_count <= 0 or len(table_anywhere_prompts) >= expected_count
    ):
        return table_anywhere_prompts[:expected_count] if expected_count > 0 else table_anywhere_prompts
    if filename_social_asset_prompts and (
        expected_count <= 0 or len(filename_social_asset_prompts) >= expected_count
    ):
        return filename_social_asset_prompts[:expected_count] if expected_count > 0 else filename_social_asset_prompts
    inline_labeled_prompts = _extract_inline_labeled_image_prompt_lines(
        normalized_text,
        expected_count=expected_count,
    )
    if inline_labeled_prompts and (
        expected_count <= 0 or len(inline_labeled_prompts) >= expected_count
    ):
        return inline_labeled_prompts[:expected_count] if expected_count > 0 else inline_labeled_prompts
    artifact_body_prompts = _extract_numbered_artifact_image_prompt_bodies(
        normalized_text,
        expected_count=expected_count,
    )
    if artifact_body_prompts and (
        expected_count <= 0 or len(artifact_body_prompts) >= expected_count
    ):
        return artifact_body_prompts[:expected_count] if expected_count > 0 else artifact_body_prompts
    sequential_alpha_prompts = _extract_sequential_bold_alpha_image_prompt_lines(
        normalized_text,
        expected_count=expected_count,
        require_image_heading=True,
    )
    if sequential_alpha_prompts and (
        expected_count <= 0 or len(sequential_alpha_prompts) >= expected_count
    ):
        return sequential_alpha_prompts[:expected_count] if expected_count > 0 else sequential_alpha_prompts
    if allow_plain_alpha_sequence:
        plain_alpha_prompts = _extract_leading_plain_alpha_image_prompt_lines(
            normalized_text,
            expected_count=expected_count,
        )
        if plain_alpha_prompts:
            return plain_alpha_prompts
    social_manifest_prompts = _extract_social_manifest_pipe_image_prompt_lines(
        normalized_text,
        expected_count=expected_count,
    )
    if social_manifest_prompts and (
        expected_count <= 0 or len(social_manifest_prompts) >= expected_count
    ):
        return social_manifest_prompts[:expected_count] if expected_count > 0 else social_manifest_prompts
    numbered_prepared_prompts = _extract_numbered_prepared_image_prompt_units(
        normalized_text,
        expected_count=expected_count,
    )
    if numbered_prepared_prompts and (
        expected_count <= 0 or len(numbered_prepared_prompts) >= expected_count
    ):
        return numbered_prepared_prompts[:expected_count] if expected_count > 0 else numbered_prepared_prompts
    for prompt in table_section_prompts:
        if prompt and prompt not in prompts:
            prompts.append(prompt)
        if expected_count > 0 and len(prompts) >= expected_count:
            break
    if prompts and (expected_count <= 0 or len(prompts) >= expected_count):
        return prompts[:expected_count] if expected_count > 0 else prompts
    for prompt in table_anywhere_prompts:
        if prompt and prompt not in prompts:
            prompts.append(prompt)
        if expected_count > 0 and len(prompts) >= expected_count:
            break
    if prompts and (expected_count <= 0 or len(prompts) >= expected_count):
        return prompts[:expected_count] if expected_count > 0 else prompts
    for prompt in filename_social_asset_prompts:
        if prompt:
            prompts.append(prompt)
        if expected_count > 0 and len(prompts) >= expected_count:
            break
    if prompts and (expected_count <= 0 or len(prompts) >= expected_count):
        return prompts[:expected_count] if expected_count > 0 else prompts
    if expected_count <= 1:
        for prompt in social_manifest_prompts:
            if prompt and prompt not in prompts:
                prompts.append(prompt)
            if expected_count > 0 and len(prompts) >= expected_count:
                break
        if prompts and (expected_count <= 0 or len(prompts) >= expected_count):
            return prompts[:expected_count] if expected_count > 0 else prompts
    for prompt in inline_labeled_prompts:
        if prompt and prompt not in prompts:
            prompts.append(prompt)
        if expected_count > 0 and len(prompts) >= expected_count:
            break
    if prompts and (expected_count <= 0 or len(prompts) >= expected_count):
        return prompts[:expected_count] if expected_count > 0 else prompts
    for prompt in _extract_labeled_multi_image_prompts(
        normalized_text,
        expected_count=expected_count,
    ):
        if prompt and prompt not in prompts:
            prompts.append(prompt)
        if expected_count > 0 and len(prompts) >= expected_count:
            break
    if prompts and (expected_count <= 0 or len(prompts) >= expected_count):
        return prompts[:expected_count] if expected_count > 0 else prompts
    for prompt in _extract_html_image_card_prompt_units(
        normalized_text,
        expected_count=expected_count,
    ):
        if prompt and prompt not in prompts:
            prompts.append(prompt)
        if expected_count > 0 and len(prompts) >= expected_count:
            break
    if prompts and (expected_count <= 0 or len(prompts) >= expected_count):
        return prompts[:expected_count] if expected_count > 0 else prompts
    for match in _MULTI_IMAGE_PROMPT_SECTION_RE.finditer(normalized_text):
        body = str(match.group('body') or '').strip()
        if not body:
            continue
        extracted = split_visible_image_payload(body)
        prompt = _clean_image_prompt_boundary_candidate(extracted.get('artifact_prompt') or body)
        if prompt and prompt not in prompts:
            prompts.append(prompt)
    if plain_alpha_candidate_present:
        return []
    if len(prompts) <= 1 and expected_count > 1:
        for paragraph in _PARAGRAPH_BREAK_RE.split(normalized_text):
            body = str(paragraph or '').strip()
            if not body:
                continue
            extracted = split_visible_image_payload(body)
            prompt = _clean_image_prompt_boundary_candidate(extracted.get('artifact_prompt') or body)
            if (
                prompt
                and _PARAGRAPH_IMAGE_PROMPT_STRONG_SIGNAL_RE.search(prompt)
                and prompt not in prompts
            ):
                prompts.append(prompt)
            if len(prompts) >= expected_count:
                break
    if expected_count > 1 and len(prompts) < expected_count:
        return []
    if expected_count > 0 and len(prompts) > expected_count:
        return prompts[:expected_count]
    return prompts


def _extract_labeled_multi_image_prompts(
    prepared_text: str,
    *,
    expected_count: int = 0,
) -> list[str]:
    lines = str(prepared_text or '').splitlines()
    prompts: list[str] = []
    current_lines: list[str] = []
    active_heading: Optional[str] = None

    def flush_current_section() -> None:
        body = '\n'.join(current_lines).strip()
        if not body:
            return
        extracted = split_visible_image_payload(body)
        prompt = _clean_image_prompt_boundary_candidate(extracted.get('artifact_prompt') or body)
        if prompt and prompt not in prompts:
            prompts.append(prompt)

    for raw_line in lines:
        inline_payload = split_visible_image_payload(str(raw_line or '').strip())
        inline_prompt = str(inline_payload.get('artifact_prompt') or '').strip()
        inline_source = str(inline_payload.get('artifact_prompt_source') or '').strip()
        if inline_prompt and inline_source and inline_source != 'full_display_text':
            if active_heading is not None:
                flush_current_section()
            active_heading = None
            current_lines = []
            if inline_prompt not in prompts:
                prompts.append(inline_prompt)
            if expected_count > 0 and len(prompts) >= expected_count:
                break
            continue
        heading = _normalize_handoff_heading_line(raw_line)
        if heading and _MULTI_IMAGE_HEADING_LINE_RE.fullmatch(heading):
            if active_heading is not None:
                flush_current_section()
            active_heading = heading
            current_lines = []
            continue
        if active_heading is None:
            continue
        if _is_image_prompt_section_stop(raw_line):
            flush_current_section()
            active_heading = None
            current_lines = []
            break
        current_lines.append(str(raw_line or ''))
    if active_heading is not None:
        flush_current_section()
    if prompts and (expected_count <= 0 or len(prompts) >= expected_count):
        return prompts[:expected_count] if expected_count > 0 else prompts
    if expected_count > 0 and len(prompts) > expected_count:
        return prompts[:expected_count]
    return prompts
