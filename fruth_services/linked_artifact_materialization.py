"""Saved linked-artifact inspection, exact dependency rebinding and composition.

Consumes canonical accepted artifact projections and exact branch identities.
This concrete file adapter owns bounded repairs; it cannot claim workers, promote
new work, freeze frames or publish results. Final Closure remains independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from fruth_services import text_artifact_materialization
from fruth_services import branch_result_contracts
from fruth_services.text_artifact_syntax import text_artifact_syntax_sanity_issues_for_extension
from fruth_services.state_flow import observe_state
import copy
import hashlib
import json
import logging
import os
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping, Optional
from fruth_inference.intent_obligations import required_intent_obligations
from fruth_server.recovery_contract import (
    RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
    RECOVERY_ACTION_RETRY_SAME_BRANCH,
)
from fruth_services.artifact_contracts import (
    artifact_authority_rank,
    artifact_logical_identities_match,
    select_authoritative_artifact_records,
)
from fruth_services.response_artifact_bundles import JS_QUOTED_RE, FETCH_LITERAL_PREFIX_RE
from fruth_services.responses import _is_public_output_artifact_record


class _SectionImageMarkup(HTMLParser):
    """Collect image markup inside an explicitly named semantic section."""

    _void_tags = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                  'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, role: str):
        super().__init__()
        self.role = role
        self.stack: list[tuple[str, bool]] = []
        self.markup: list[str] = []
        self.styles: list[str] = []
        self.elements: list[list[tuple[str, dict[str, Any]]]] = []
        self.element_stack: list[tuple[str, dict[str, Any]]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        hooks = ' '.join(str(attributes.get(key) or '') for key in ('id', 'class'))
        owns_role = bool(self.role) and self.role in re.split(r'[^a-z0-9]+', hooks.lower())
        active = owns_role or bool(self.stack and self.stack[-1][1])
        element = (tag, attributes)
        self.elements.append([*self.element_stack, element])
        if active and (tag in {'img', 'source'} or attributes.get('style')):
            self.markup.append(self.get_starttag_text())
        if tag not in self._void_tags:
            self.stack.append((tag, active))
            self.element_stack.append(element)

    def handle_data(self, data):
        if self.stack and self.stack[-1][0] == 'style':
            self.styles.append(data)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                del self.element_stack[index:]
                break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self._void_tags:
            self.handle_endtag(tag)

    @staticmethod
    def selector_matches(selector: str, lineage: list[tuple[str, dict[str, Any]]]) -> bool:
        """Prove simple tag/class/id descendant or child bindings, not a CSS cascade.

        Unsupported selectors do not establish layout evidence. In particular,
        a sibling, pseudo-class or negated selector must not style every image.
        """
        selector = selector.strip()
        if not re.fullmatch(r'[\w.*#\s>\-]+', selector):
            return False
        parts = re.findall(r'[^\s>]+|>', selector)
        if not parts or parts[0] == '>' or parts[-1] == '>':
            return False

        def matches(part, element):
            tag, attrs = element
            tokens = re.findall(r'^[\w*-]+|[.#][\w-]+', part)
            if ''.join(tokens) != part:
                return False
            for token in tokens:
                if token.startswith('.'):
                    if token[1:] not in str(attrs.get('class') or '').split():
                        return False
                elif token.startswith('#'):
                    if token[1:] != attrs.get('id'):
                        return False
                elif token != '*' and token.lower() != tag:
                    return False
            return True

        def match_at(part_index, element_index):
            if element_index < 0 or not matches(parts[part_index], lineage[element_index]):
                return False
            if part_index == 0:
                return True
            if parts[part_index - 1] == '>':
                return part_index >= 2 and match_at(part_index - 2, element_index - 1)
            return any(match_at(part_index - 1, i) for i in range(element_index - 1, -1, -1))

        return bool(lineage) and match_at(len(parts) - 1, len(lineage) - 1)


_LINK_REBIND_TEXT_EXTENSIONS = {'html', 'htm', 'css', 'js', 'mjs', 'cjs', 'json'}


_LINK_REBIND_HTML_TARGET_EXTENSIONS = {'html', 'htm', 'css', 'js', 'mjs', 'cjs'}


_TERMINAL_MATERIALIZABLE_LOCAL_DEPENDENCY_EXTENSIONS = {
    'html', 'htm', 'css', 'js', 'mjs', 'cjs', 'json'
}


_LINK_REBIND_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}


_LINK_REBIND_EXTENSION_FAMILIES = {
    'image': frozenset({'png', 'jpg', 'jpeg', 'webp', 'gif', 'avif', 'svg'}),
    'audio': frozenset({'wav', 'mp3', 'm4a', 'flac', 'aac', 'ogg', 'opus', 'webm'}),
    'video': frozenset({'mp4', 'mov', 'm4v', 'webm', 'avi', 'mkv', 'ogv'}),
    'font': frozenset({'woff', 'woff2', 'ttf', 'otf', 'eot'}),
    'style': frozenset({'css', 'scss', 'sass', 'less'}),
    'script': frozenset({'js', 'mjs', 'cjs', 'ts'}),
}


_LINK_REBIND_URL_RE = re.compile(
    r'(?P<prefix>\burl\(\s*[\'"]?)(?P<url>[^\'")]+)(?P<suffix>[\'"]?\s*\))',
    re.IGNORECASE,
)


_LINK_REBIND_ATTR_RE = re.compile(
    r'(?P<prefix>\b(?:href|src)\s*=\s*)(?P<quote>[\'"])(?P<url>[^\'"]*)(?P=quote)',
    re.IGNORECASE,
)


_LINK_REBIND_FETCH_RE = re.compile(
    r'(?P<prefix>\bfetch\s*\(\s*)(?P<quote>[\'"])(?P<url>[^\'"]+)(?P=quote)(?=\s*[,\)])',
    re.IGNORECASE,
)


_INLINE_SCRIPT_RE = re.compile(
    r'<script\b[^>]*>(?P<body>[\s\S]*?)</script\s*>',
    re.IGNORECASE,
)


_JS_COLLECTION_ITERATOR_RE = re.compile(
    r'(?P<collection>(?:[A-Za-z_$][A-Za-z0-9_$]*\s*\.\s*)*[A-Za-z_$][A-Za-z0-9_$]*)'
    r'\s*\.\s*(?:forEach|map)\s*\(\s*(?:\(\s*)?'
    r'(?P<item>[A-Za-z_$][A-Za-z0-9_$]*)\s*(?:\)\s*)?=>\s*\{',
    re.IGNORECASE,
)


_JS_FETCH_RESPONSE_ASSIGNMENT_RE = re.compile(
    r'\b(?:const|let|var)\s+(?P<response>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:await\s+)?$',
    re.IGNORECASE,
)


_JS_AWAITED_JSON_BINDING_RE = re.compile(
    r'\b(?:const|let|var)\s+(?P<binding>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*await\s+'
    r'(?P<response>[A-Za-z_$][A-Za-z0-9_$]*)\s*\.\s*json\s*\(\s*\)',
    re.IGNORECASE,
)


_JS_INVALID_IDENTIFIER_SEPARATOR_RE = re.compile(
    r'\b[A-Za-z_$][A-Za-z0-9_$]*(?P<separator>[^\x00-\x7f\s]+)'
    r'[A-Za-z_$][A-Za-z0-9_$]*\b'
)


def _static_fetch_url_is_local_file_dependency(value: str) -> bool:
    token = str(value or '').strip()
    if not token or _EXTERNAL_LINK_RE.match(token) or token.startswith(('/', '\\')):
        return False
    path_token = token.split('?', 1)[0].split('#', 1)[0].strip()
    extension = Path(path_token).suffix.lower().lstrip('.')
    return extension in _TERMINAL_MATERIALIZABLE_LOCAL_DEPENDENCY_EXTENSIONS


_LINK_REBIND_PLACEHOLDER_RE = re.compile(
    r'\b(?:(?:temp|temporary)[_\-\s]?(?:placeholder|image|asset|media)[_\-\s]?(?:src|source|url|path|ref|href)|'
    r'(?:placeholder|replace[_\-\s]?me|todo|tbd|dummy|sample|example)'
    r'(?:[_\-\s]?(?:src|source|url|path|ref|href))?|'
    r'asset[_\-\s]?placeholder|image[_\-\s]?placeholder|generated[_\-\s]?image|'
    r'(?:img|image|asset|media)[_\-\s]?(?:path|url|ref)(?:[_\-\s]?\d+)?|'
    r'hero[_\-\s]?image|image[_\-\s]?artifact|your[_\-\s]?(?:image|asset)|'
    r'platzhalter|ersetzen|beispiel)\b',
    re.IGNORECASE,
)


_LINK_REBIND_JSON_PATH_KEY_RE = re.compile(
    r'^(?:'
    r'(?:image|picture|photo|audio|sound|voice|video|movie|media|asset|artifact|font|style|stylesheet|script)'
    r'|(?:image|picture|photo|audio|sound|voice|video|movie|media|asset|artifact|font|style|stylesheet|script)[_-](?:paths?|urls?|uris?|srcs?|hrefs?|files?)'
    r'|(?:paths?|urls?|uris?|srcs?|hrefs?|files?)'
    r'|.+[_-](?:paths?|urls?|uris?|srcs?|hrefs?|files?)'
    r')$',
    re.IGNORECASE,
)


_EXTERNAL_LINK_RE = re.compile(r'^(?:[a-z][a-z0-9+.-]*:|//|#)', re.IGNORECASE)


_TERMINAL_HERO_LOCAL_IMAGE_SIGNAL_RE = re.compile(
    r'\b(?:hero|hero[-_\s]?image|background|hintergrund|titelbild|title\s+image)\b',
    re.IGNORECASE,
)


_TERMINAL_HTML_HERO_BLOCK_RE = re.compile(
    r'<(?P<tag>header|section|main|div)\b(?P<attrs>[^>]*)>'
    r'(?P<body>[\s\S]{0,12000}?)</\s*(?P=tag)\s*>',
    re.IGNORECASE,
)


_TERMINAL_CSS_HERO_BLOCK_RE = re.compile(
    r'(?P<selectors>[^{}]*(?:[.#][A-Za-z0-9_-]*hero[A-Za-z0-9_-]*|\bheader\b)[^{}]*)\{(?P<body>[^{}]*)\}',
    re.IGNORECASE,
)

@dataclass(frozen=True)
class LinkedArtifactMaterialization:
    branch_id: Callable[[Mapping[str, Any]], str]
    build_canonical_response_artifacts: Callable[[dict[str, Any]], list[dict[str, Any]]]
    normalize_capability: Callable[[Any], Optional[str]]
    image_generation_capability: Callable[[], str]

    @classmethod
    def _text_artifact_target_path_from_mapping(cls, payload: Any) -> str:
        if not isinstance(payload, Mapping):
            return ''
        for key in ('target_path', 'text_artifact_target_path'):
            value = str(payload.get(key) or '').strip()
            if value:
                return value
        for key in ('text_artifact_request', 'artifact_request'):
            value = cls._text_artifact_target_path_from_mapping(payload.get(key))
            if value:
                return value
        execution_contract = payload.get('execution_contract')
        if isinstance(execution_contract, Mapping):
            value = cls._text_artifact_target_path_from_mapping(execution_contract)
            if value:
                return value
        return ''

    def _image_artifact_record_sort_key(self, record: Mapping[str, Any]) -> tuple[int, int, str]:
        branch_id = self.branch_id(record)
        phase_id = str(record.get('phase_id') or '').strip()
        for priority, token in enumerate((branch_id, phase_id)):
            match = re.search(r'-(\d+)$', token)
            if match:
                return priority, int(match.group(1)), token
        return 9, 999_999, branch_result_contracts._artifact_record_path(record)

    @staticmethod
    def _normalized_text_artifact_source_name_for_match(value: Any) -> str:
        token = str(value or '').strip()
        if not token:
            return ''
        name = Path(token).name
        if Path(name).suffix:
            name = Path(name).stem
        return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

    @classmethod
    def _artifact_record_matches_text_artifact_source_name(
        cls,
        record: Mapping[str, Any],
        expected_source_name: str,
    ) -> bool:
        expected = cls._normalized_text_artifact_source_name_for_match(expected_source_name)
        if not expected:
            return True
        artifact_request = (
            record.get('artifact_request')
            if isinstance(record.get('artifact_request'), Mapping)
            else record.get('text_artifact_request')
            if isinstance(record.get('text_artifact_request'), Mapping)
            else {}
        )
        explicit_names = [
            record.get('text_artifact_source_name'),
            record.get('source_name'),
            artifact_request.get('source_name'),
            record.get('name'),
        ]
        normalized_explicit_names = {
            cls._normalized_text_artifact_source_name_for_match(value)
            for value in explicit_names
            if str(value or '').strip()
        }
        if normalized_explicit_names:
            if expected in normalized_explicit_names:
                return True
            extension = branch_result_contracts._artifact_record_extension(record)
            if extension:
                expected_identity = (extension, expected)
                return any(
                    artifact_logical_identities_match(
                        expected_identity,
                        (extension, explicit_name),
                    )
                    for explicit_name in normalized_explicit_names
                )
            return False

        path = branch_result_contracts._artifact_record_path(record)
        path_name = cls._normalized_text_artifact_source_name_for_match(path)
        return bool(
            path_name == expected
            or path_name.endswith(f'-{expected}')
        )

    @staticmethod
    def _relative_artifact_link(*, from_path: str, to_path: str) -> str:
        if not from_path or not to_path:
            return to_path
        try:
            relative = os.path.relpath(to_path, start=str(Path(from_path).expanduser().parent))
        except (OSError, ValueError):
            return to_path
        return relative.replace(os.sep, '/')

    @staticmethod
    def _url_is_external_or_empty(value: str) -> bool:
        token = str(value or '').strip()
        return not token or bool(_EXTERNAL_LINK_RE.match(token))

    @staticmethod
    def _link_rebind_is_dynamic_template_url(
        content: str, position: int, url: str, *, target_path: str,
    ) -> bool:
        """An interpolated JS template URL is an expression, not a missing file.

        Limit the exemption to script source and actual template literals so
        literal HTML placeholders still reach the ordinary repair checks.
        This is a static mutation guard, not proof that the expression resolves.
        """
        if not re.search(r'(?<!\\)(?:\\\\)*\$\{', url):
            return False
        extension = Path(target_path).suffix.lower()
        script = content
        offset = 0
        if extension not in {'.js', '.mjs', '.cjs'}:
            enclosing = next(
                (match for match in _INLINE_SCRIPT_RE.finditer(content)
                 if match.start('body') <= position < match.end('body')),
                None,
            )
            if enclosing is None:
                return False
            script = enclosing.group('body')
            offset = enclosing.start('body')
        # Consume ordinary quoted strings and comments as well, so backticks
        # inside them cannot grant a template-expression exemption.
        tokens = re.finditer(
            r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|'
            r'//[^\n]*|/\*[\s\S]*?\*/|`(?:\\.|[^`\\])*`',
            script,
        )
        return any(
            match.group(0).startswith('`')
            and match.start() < position - offset < match.end()
            for match in tokens
        )

    @staticmethod
    def _link_rebind_search_text(record: Mapping[str, Any]) -> str:
        values: list[str] = []
        request_payload = record.get('artifact_request') if isinstance(record.get('artifact_request'), Mapping) else {}
        metadata = record.get('metadata') if isinstance(record.get('metadata'), Mapping) else {}
        for value in (
            branch_result_contracts._artifact_record_path(record),
            branch_result_contracts._artifact_record_source_name(record),
            record.get('name'),
            record.get('prompt'),
            record.get('artifact_prompt'),
            record.get('prompt_preview'),
            record.get('content'),
            record.get('semantic_intent'),
            record.get('objective'),
            record.get('deliverable'),
            record.get('link_rebind_search_text'),
            request_payload.get('source_name'),
            request_payload.get('prompt'),
            metadata.get('prompt_preview'),
        ):
            text = str(value or '').strip()
            if text:
                values.append(text)
        return ' '.join(values)

    @staticmethod
    def _link_rebind_semantic_tokens(value: str) -> set[str]:
        raw_tokens = {
            token
            for token in re.split(r'[^a-z0-9]+', str(value or '').lower())
            if len(token) >= 3
        }
        expanded_raw_tokens = set(raw_tokens)
        for token in raw_tokens:
            match = re.fullmatch(r'([a-z]{3,})\d+', token)
            if match:
                expanded_raw_tokens.add(match.group(1))
        generic_tokens = {
            'artifact',
            'generated',
            'image',
            'images',
            'latest',
            'placeholder',
            'picture',
            'photo',
            'png',
            'jpg',
            'jpeg',
            'webp',
        }
        tokens = {token for token in expanded_raw_tokens if token not in generic_tokens}
        synonym_groups = (
            {'lab', 'laboratory', 'laboratories'},
            {'greenhouse', 'biome', 'botanical', 'verdant', 'aeroponic', 'aeroponics'},
            {'exterior', 'external', 'hero', 'outside'},
        )
        expanded = set(tokens)
        for group in synonym_groups:
            if tokens & group:
                expanded.update(group)
        return expanded

    @classmethod
    def _link_rebind_semantic_score(cls, url: str, record: Mapping[str, Any]) -> int:
        token = str(url or '').split('?', 1)[0].split('#', 1)[0]
        basename = Path(token).name
        stem = Path(basename).stem
        url_tokens = cls._link_rebind_semantic_tokens(f'{basename} {stem}')
        if not url_tokens:
            return 0
        record_tokens = cls._link_rebind_semantic_tokens(cls._link_rebind_search_text(record))
        if not record_tokens:
            return 0
        overlap = url_tokens & record_tokens
        if not overlap:
            return 0
        score = len(overlap)
        if stem.lower() in str(cls._link_rebind_search_text(record)).lower():
            score += 3
        return score

    def _collect_link_rebind_artifact_records(self, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(payload, Mapping):
            return []
        public_artifact_refs: set[str] = set()
        public_artifact_paths: set[str] = set()

        def normalized_artifact_path(value: Any) -> str:
            token = str(value or '').strip()
            if not token:
                return ''
            try:
                return str(Path(token).expanduser().resolve(strict=False))
            except (OSError, ValueError):
                return token

        def add_public_output_identity(raw_record: Any) -> None:
            if not isinstance(raw_record, Mapping):
                return
            artifact_ref = str(
                raw_record.get('artifact_ref')
                or raw_record.get('ref')
                or raw_record.get('artifact_id')
                or ''
            ).strip()
            if artifact_ref:
                public_artifact_refs.add(artifact_ref)
            path = normalized_artifact_path(branch_result_contracts._artifact_record_path(raw_record))
            if path:
                public_artifact_paths.add(path)
            for key in ('artifact', 'output_artifact'):
                add_public_output_identity(raw_record.get(key))
            for key in ('artifacts', 'output_artifacts'):
                for artifact in raw_record.get(key) or []:
                    add_public_output_identity(artifact)

        public_output_lists: list[list[Any]] = []
        for raw_outputs in (payload.get('outputs'),):
            if isinstance(raw_outputs, list):
                public_output_lists.append(raw_outputs)
        response_frame = (
            payload.get('response_frame')
            if isinstance(payload.get('response_frame'), Mapping)
            else {}
        )
        frame_output = (
            response_frame.get('output')
            if isinstance(response_frame.get('output'), Mapping)
            else {}
        )
        if not public_output_lists and isinstance(frame_output.get('outputs'), list):
            public_output_lists.append(frame_output.get('outputs') or [])
        legacy_output = (
            payload.get('output')
            if isinstance(payload.get('output'), Mapping)
            else {}
        )
        if not public_output_lists and isinstance(legacy_output.get('outputs'), list):
            public_output_lists.append(legacy_output.get('outputs') or [])
        for output_list in public_output_lists:
            for output in output_list:
                if _is_public_output_artifact_record(output):
                    add_public_output_identity(output)
        has_public_artifact_identity = bool(
            public_output_lists or public_artifact_refs or public_artifact_paths
        )

        def record_is_public_output(record: Mapping[str, Any]) -> bool:
            artifact_ref = str(
                record.get('artifact_ref')
                or record.get('ref')
                or record.get('artifact_id')
                or ''
            ).strip()
            if artifact_ref and artifact_ref in public_artifact_refs:
                return True
            path = normalized_artifact_path(branch_result_contracts._artifact_record_path(record))
            return bool(path and path in public_artifact_paths)

        slot_by_ref: dict[str, Mapping[str, Any]] = {}
        for slot in payload.get('output_slots') or []:
            if not isinstance(slot, Mapping):
                continue
            artifact_ref = str(slot.get('artifact_ref') or slot.get('ref') or '').strip()
            if artifact_ref:
                slot_by_ref[artifact_ref] = slot

        records: list[dict[str, Any]] = []
        index_by_key: dict[tuple[str, str, str, str], int] = {}

        def merge_record_fields(existing: dict[str, Any], incoming: Mapping[str, Any]) -> None:
            for key, value in incoming.items():
                if value in (None, '', [], {}):
                    continue
                if existing.get(key) in (None, '', [], {}):
                    existing[key] = value
                    continue
                if key == 'link_rebind_search_text':
                    current = str(existing.get(key) or '').strip()
                    incoming_text = str(value or '').strip()
                    if incoming_text and incoming_text not in current:
                        existing[key] = f'{current} {incoming_text}'.strip()

        def add_record(raw_record: Any, *, defaults: Optional[Mapping[str, Any]] = None) -> None:
            if not isinstance(raw_record, Mapping):
                return
            record = dict(defaults or {})
            record.update(dict(raw_record))
            if has_public_artifact_identity:
                record['_link_rebind_public_output'] = record_is_public_output(record)
            artifact_ref = str(record.get('artifact_ref') or record.get('ref') or '').strip()
            slot = slot_by_ref.get(artifact_ref) if artifact_ref else None
            if isinstance(slot, Mapping):
                record['_link_rebind_output_slot'] = True
                for key in ('branch_id', 'phase_id', 'slot_id'):
                    if record.get(key) in (None, '', [], {}) and slot.get(key) not in (None, '', [], {}):
                        record[key] = slot.get(key)
            artifact_type = str(record.get('type') or record.get('kind') or '').strip().lower()
            path = branch_result_contracts._artifact_record_path(record)
            if not artifact_type and path:
                extension = Path(path).suffix.lower().lstrip('.')
                extension_families = self._link_rebind_extension_families(extension)
                artifact_type = next(
                    (
                        family
                        for family in ('image', 'audio', 'video', 'font', 'style', 'script')
                        if family in extension_families
                    ),
                    'text',
                )
                record['type'] = artifact_type
                record.setdefault('kind', artifact_type)
            key = (
                artifact_type,
                path,
                str(record.get('branch_id') or '').strip(),
                str(record.get('phase_id') or '').strip(),
            )
            if not artifact_type and not path:
                return
            if key in index_by_key:
                merge_record_fields(records[index_by_key[key]], record)
                return
            index_by_key[key] = len(records)
            records.append({key: value for key, value in record.items() if value not in (None, '', [], {})})

        raw_artifacts = payload.get('artifacts')
        if isinstance(raw_artifacts, Mapping):
            for key in ('output', 'reference', 'input'):
                for artifact in raw_artifacts.get(key) or []:
                    add_record(
                        artifact,
                        defaults={
                            '_link_rebind_public_output': key == 'output',
                        },
                    )
        else:
            for artifact in raw_artifacts or []:
                add_record(
                    artifact,
                    defaults={
                        '_link_rebind_public_output': not has_public_artifact_identity,
                    },
                )
        for key in ('input_artifacts', 'reference_artifacts', 'selected_reference_artifacts'):
            for artifact in payload.get(key) or []:
                add_record(artifact)
        for artifact in self.build_canonical_response_artifacts(dict(payload)):
            add_record(artifact)
        for item in payload.get('saved_text_artifacts') or []:
            source = item if isinstance(item, Mapping) else {'path': item}
            add_record({'type': 'text', **dict(source)})
        if str(payload.get('saved_text_path') or '').strip():
            add_record({'type': 'text', 'path': payload.get('saved_text_path')})
        if str(payload.get('saved_image_path') or '').strip():
            add_record({'type': 'image', 'path': payload.get('saved_image_path')})
        if str(payload.get('saved_audio_path') or '').strip():
            add_record({'type': 'audio', 'path': payload.get('saved_audio_path')})

        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        batch_prompts = [
            str(item or '').strip()
            for item in (late_fill.get('batch_prompts') or [])
            if str(item or '').strip()
        ]
        image_result_index = 0
        for result in late_fill.get('fill_results') or []:
            if not isinstance(result, Mapping):
                continue
            execution_contract = (
                result.get('execution_contract')
                if isinstance(result.get('execution_contract'), Mapping)
                else {}
            )
            artifact_request = (
                result.get('artifact_request')
                if isinstance(result.get('artifact_request'), Mapping)
                else (
                    execution_contract.get('artifact_request')
                    if isinstance(execution_contract.get('artifact_request'), Mapping)
                    else {}
                )
            )
            defaults = {
                'branch_id': result.get('branch_id'),
                'phase_id': result.get('phase_id'),
                'depends_on': (
                    result.get('depends_on')
                    or execution_contract.get('depends_on')
                    or execution_contract.get('dependencies')
                ),
                'dependency_contract': (
                    result.get('dependency_contract')
                    or execution_contract.get('dependency_contract')
                ),
                'source': 'late_fill_result',
                'source_response_id': str(payload.get('id') or '').strip() or None,
            }
            if str(result.get('saved_text_path') or '').strip():
                add_record(
                    {
                        'type': 'text',
                        'path': result.get('saved_text_path'),
                        'content': result.get('result_text') or result.get('content_payload'),
                        'text_artifact_extension': (
                            result.get('text_artifact_extension')
                            or execution_contract.get('text_artifact_extension')
                            or artifact_request.get('extension')
                        ),
                        'text_artifact_source_name': (
                            result.get('text_artifact_source_name')
                            or execution_contract.get('text_artifact_source_name')
                            or artifact_request.get('source_name')
                        ),
                        'text_artifact_source': (
                            result.get('text_artifact_source')
                            or execution_contract.get('text_artifact_source')
                            or artifact_request.get('source')
                        ),
                        'text_artifact_target_path': (
                            result.get('text_artifact_target_path')
                            or execution_contract.get('text_artifact_target_path')
                            or artifact_request.get('target_path')
                        ),
                        'artifact_request': artifact_request or None,
                    },
                    defaults=defaults,
                )
            if str(result.get('saved_image_path') or '').strip():
                prompt_text = str(
                    result.get('artifact_prompt')
                    or result.get('prompt')
                    or result.get('content_payload')
                    or ''
                ).strip()
                if not prompt_text and image_result_index < len(batch_prompts):
                    prompt_text = batch_prompts[image_result_index]
                image_result_index += 1
                add_record(
                    {
                        'type': 'image',
                        'path': result.get('saved_image_path'),
                        'prompt': prompt_text or None,
                        'artifact_prompt': prompt_text or None,
                        'link_rebind_search_text': prompt_text or None,
                    },
                    defaults=defaults,
                )
            if str(result.get('saved_audio_path') or '').strip():
                add_record(
                    {
                        'type': 'audio',
                        'path': result.get('saved_audio_path'),
                        'mime_type': result.get('audio_mimetype'),
                    },
                    defaults=defaults,
                )
            for artifact in result.get('artifacts') or []:
                add_record(artifact, defaults=defaults)
        return select_authoritative_artifact_records(
            records,
            response_id=str(payload.get('id') or '').strip(),
        )

    @classmethod
    def _preferred_asset_for_url(
        cls,
        url: str,
        candidates: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if not candidates:
            return None
        token = str(url or '').strip()
        basename = Path(token.split('?', 1)[0].split('#', 1)[0]).name.lower()
        stem = Path(basename).stem.lower()
        extension = Path(basename).suffix.lower().lstrip('.')
        matching_extension = [
            record
            for record in candidates
            if not extension or branch_result_contracts._artifact_record_extension(record) == extension
        ]
        pool = matching_extension or candidates
        for record in pool:
            path = branch_result_contracts._artifact_record_path(record)
            asset_basename = Path(path).name.lower() if path else ''
            asset_stem = Path(path).stem.lower() if path else ''
            source_name = branch_result_contracts._artifact_record_source_name(record).lower()
            if basename and basename == asset_basename:
                return record
            if stem and stem in {asset_stem, source_name}:
                return record
            if stem and source_name and (stem in source_name or source_name in stem):
                return record
        scored = [
            (cls._link_rebind_semantic_score(url, record), index, record)
            for index, record in enumerate(pool)
        ]
        scored = [item for item in scored if item[0] > 0]
        if scored:
            scored.sort(key=lambda item: (-item[0], item[1]))
            return scored[0][2]
        if extension == 'css':
            for record in pool:
                source_name = branch_result_contracts._artifact_record_source_name(record).lower()
                if source_name in {'style', 'styles'} or source_name.endswith('_styles'):
                    return record
        return pool[0] if len(pool) == 1 else None

    @classmethod
    def _link_rebind_url_matches_record_identity(
        cls,
        url: str,
        record: Mapping[str, Any],
    ) -> bool:
        """Return whether a local link names the current text artifact itself."""
        token = str(url or '').split('?', 1)[0].split('#', 1)[0].strip()
        if not token:
            return False
        requested_extension = Path(token).suffix.lower().lstrip('.')
        record_extension = branch_result_contracts._artifact_record_extension(record)
        if requested_extension and record_extension and requested_extension != record_extension:
            return False
        requested_name = Path(token).name
        record_path = branch_result_contracts._artifact_record_path(record)
        if requested_name and record_path and requested_name.lower() == Path(record_path).name.lower():
            return True
        return cls._artifact_record_matches_text_artifact_source_name(
            record,
            requested_name,
        )

    @classmethod
    def _exact_asset_record_for_url(
        cls,
        url: str,
        candidates: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        """Resolve a sibling text artifact from exact name and output ownership."""
        token = str(url or '').split('?', 1)[0].split('#', 1)[0].strip()
        requested_name = Path(token).name
        if not requested_name:
            return None
        matches: list[tuple[tuple[int, ...], dict[str, Any]]] = []
        for record in candidates:
            path = branch_result_contracts._artifact_record_path(record)
            exact_basename = bool(
                path
                and Path(path).name.lower() == requested_name.lower()
            )
            exact_source_name = cls._artifact_record_matches_text_artifact_source_name(
                record,
                requested_name,
            )
            if not exact_basename and not exact_source_name:
                continue
            target_path = str(record.get('text_artifact_target_path') or '').strip()
            target_is_record_path = False
            if path and target_path:
                try:
                    target_is_record_path = (
                        Path(target_path).expanduser().resolve(strict=False)
                        == Path(path).expanduser().resolve(strict=False)
                    )
                except (OSError, ValueError):
                    target_is_record_path = target_path == path
            rank = (
                *artifact_authority_rank(record),
                int(record.get('_link_rebind_output_slot') is True),
                int(bool(str(record.get('slot_id') or '').strip())),
                int(
                    bool(str(record.get('branch_id') or '').strip())
                    and bool(str(record.get('phase_id') or '').strip())
                ),
                int(target_is_record_path),
                int(str(record.get('source') or '').strip() == 'late_fill_result'),
                int(record.get('_link_rebind_public_output') is True),
                int(exact_basename),
            )
            matches.append((rank, record))
        if not matches:
            return None
        best_rank = max(rank for rank, _record in matches)
        strongest = [record for rank, record in matches if rank == best_rank]
        strongest_paths = {
            branch_result_contracts._artifact_record_path(record)
            for record in strongest
            if branch_result_contracts._artifact_record_path(record)
        }
        if len(strongest_paths) <= 1:
            return strongest[0]
        # Preserve deterministic legacy behavior for unbound evidence, but do
        # not guess between two response/branch-owned current generations.
        return strongest[0] if best_rank[0] < 3 else None

    @classmethod
    def _unique_artifact_records_by_path(cls, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: list[dict[str, Any]] = []
        index_by_path: dict[str, int] = {}
        for record in records:
            path = branch_result_contracts._artifact_record_path(record)
            if not path:
                continue
            if path not in index_by_path:
                index_by_path[path] = len(unique)
                unique.append(dict(record))
                continue
            existing = unique[index_by_path[path]]
            for key, value in record.items():
                if value in (None, '', [], {}):
                    continue
                if existing.get(key) in (None, '', [], {}):
                    existing[key] = value
                    continue
                if key == 'link_rebind_search_text':
                    current = str(existing.get(key) or '').strip()
                    incoming = str(value or '').strip()
                    if incoming and incoming not in current:
                        existing[key] = f'{current} {incoming}'.strip()
        return unique

    @staticmethod
    def _link_rebind_extension_families(extension: str) -> set[str]:
        token = str(extension or '').strip().lower().lstrip('.')
        if not token:
            return set()
        return {
            family
            for family, extensions in _LINK_REBIND_EXTENSION_FAMILIES.items()
            if token in extensions
        }

    @classmethod
    def _link_rebind_record_declared_families(cls, record: Mapping[str, Any]) -> set[str]:
        families: set[str] = set()
        artifact_type = str(record.get('type') or record.get('kind') or '').strip().lower()
        mime_type = str(record.get('mime_type') or record.get('content_type') or '').strip().lower()
        for family in ('image', 'audio', 'video', 'font'):
            if artifact_type == family or mime_type.startswith(f'{family}/'):
                families.add(family)
        if artifact_type in {'style', 'stylesheet'} or mime_type == 'text/css':
            families.add('style')
        if artifact_type in {'script', 'javascript'} or mime_type in {'text/javascript', 'application/javascript'}:
            families.add('script')
        return families

    @classmethod
    def _link_rebind_record_families(cls, record: Mapping[str, Any]) -> set[str]:
        return (
            cls._link_rebind_record_declared_families(record)
            or cls._link_rebind_extension_families(branch_result_contracts._artifact_record_extension(record))
        )

    @staticmethod
    def _link_rebind_record_identity_tokens(record: Mapping[str, Any]) -> set[str]:
        if not isinstance(record, Mapping):
            return set()
        return {
            token
            for key in (
                'branch_id',
                'phase_id',
                'task_id',
                'workload_task_id',
                'obligation_id',
                'output_obligation_ref',
            )
            if (token := str(record.get(key) or '').strip())
        }

    @staticmethod
    def _link_rebind_dependency_values(record: Mapping[str, Any]) -> list[str]:
        values: list[str] = []
        if not isinstance(record, Mapping):
            return values
        execution_contract = (
            record.get('execution_contract')
            if isinstance(record.get('execution_contract'), Mapping)
            else {}
        )
        for raw_values in (
            record.get('depends_on'),
            record.get('dependsOn'),
            execution_contract.get('depends_on'),
            execution_contract.get('dependencies'),
        ):
            candidates = raw_values if isinstance(raw_values, (list, tuple, set)) else [raw_values]
            for value in candidates:
                token = str(value or '').strip()
                if token and token not in values:
                    values.append(token)
        return values

    @classmethod
    def _link_rebind_consumer_dependency_ids(
        cls,
        payload: Mapping[str, Any],
        consumer_record: Mapping[str, Any],
        *,
        identity_only: bool = False,
    ) -> list[str]:
        dependency_ids = cls._link_rebind_dependency_values(consumer_record)
        consumer_tokens = cls._link_rebind_record_identity_tokens(consumer_record)
        consumer_path = branch_result_contracts._artifact_record_path(consumer_record)

        runtime = payload.get('runtime') if isinstance(payload.get('runtime'), Mapping) else {}
        graph = (
            runtime.get('request_phase_graph')
            if isinstance(runtime.get('request_phase_graph'), Mapping)
            else {}
        )
        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        records: list[Mapping[str, Any]] = []
        for key in ('phases', 'downstream_branches'):
            records.extend(
                item
                for item in (graph.get(key) if isinstance(graph.get(key), list) else [])
                if isinstance(item, Mapping)
            )
        for key in (
            'pending_branches',
            'active_branches',
            'completed_branches',
            'failed_branches',
            'cancelled_branches',
            'fill_results',
        ):
            records.extend(
                item
                for item in (late_fill.get(key) if isinstance(late_fill.get(key), list) else [])
                if isinstance(item, Mapping)
            )

        def record_targets_consumer(record: Mapping[str, Any]) -> bool:
            if identity_only:
                branch_id = consumer_record.get('branch_id')
                if branch_id and record.get('branch_id'):
                    return record.get('branch_id') == branch_id
                return bool(
                    consumer_record.get('phase_id')
                    and record.get('phase_id') == consumer_record.get('phase_id')
                )
            if consumer_tokens & cls._link_rebind_record_identity_tokens(record):
                return True
            artifact_request = (
                record.get('artifact_request')
                if isinstance(record.get('artifact_request'), Mapping)
                else {}
            )
            target_path = str(
                record.get('text_artifact_target_path')
                or artifact_request.get('target_path')
                or ''
            ).strip()
            return bool(consumer_path and target_path and consumer_path == target_path)

        for record in records:
            if not record_targets_consumer(record):
                continue
            for dependency_id in cls._link_rebind_dependency_values(record):
                if dependency_id not in dependency_ids:
                    dependency_ids.append(dependency_id)

        expanded_ids = list(dependency_ids)
        for record in records:
            record_tokens = cls._link_rebind_record_identity_tokens(record)
            if not record_tokens.intersection(dependency_ids):
                continue
            for token in record_tokens:
                if token not in expanded_ids:
                    expanded_ids.append(token)
        return expanded_ids

    @classmethod
    def _link_rebind_asset_records_for_consumer(
        cls,
        payload: Mapping[str, Any],
        consumer_record: Mapping[str, Any],
        asset_records: list[dict[str, Any]],
        *,
        identity_only: bool = False,
    ) -> tuple[list[dict[str, Any]], list[str], str]:
        dependency_ids = cls._link_rebind_consumer_dependency_ids(
            payload, consumer_record, identity_only=identity_only,
        )
        if not dependency_ids:
            return list(asset_records), [], 'artifact_set_fallback_without_declared_dependencies'
        dependency_tokens = set(dependency_ids)
        runtime = payload.get('runtime') if isinstance(payload.get('runtime'), Mapping) else {}
        graph = (
            runtime.get('request_phase_graph')
            if isinstance(runtime.get('request_phase_graph'), Mapping)
            else {}
        )
        graph_records = [
            item
            for key in ('phases', 'downstream_branches')
            for item in (graph.get(key) if isinstance(graph.get(key), list) else [])
            if isinstance(item, Mapping)
        ]
        consumer_tokens = cls._link_rebind_record_identity_tokens(consumer_record)
        consumer_graph_records = [
            record
            for record in graph_records
            if cls._link_rebind_record_identity_tokens(record) & consumer_tokens
        ]
        if identity_only:
            # A compact saved result can omit the binding policy while the
            # exact pending/active repair still owns it. Do not consult other
            # branches through a shared artifact ref or target path.
            consumer_graph_records = [
                record for record in graph_records
                if record.get('branch_id') == consumer_record.get('branch_id')
                or (
                    not record.get('branch_id') and consumer_record.get('phase_id')
                    and record.get('phase_id') == consumer_record.get('phase_id')
                )
            ]
            late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
            consumer_graph_records.extend(
                record
                for key in ('pending_branches', 'active_branches', 'failed_branches')
                for record in late_fill.get(key) or []
                if isinstance(record, Mapping)
                and record.get('branch_id') == consumer_record.get('branch_id')
            )

        def has_local_visual_binding(record: Mapping[str, Any]) -> bool:
            execution_contract = (
                record.get('execution_contract')
                if isinstance(record.get('execution_contract'), Mapping)
                else {}
            )
            values = (
                record.get('dependency_contract'),
                execution_contract.get('dependency_contract'),
            )
            return any(
                'local_visual_asset_binding' in str(value or '').strip().lower()
                for value in values
            )

        local_visual_binding = has_local_visual_binding(consumer_record) or any(
            has_local_visual_binding(record)
            for record in consumer_graph_records
        )
        dependency_graph_records = [
            record
            for record in graph_records
            if cls._link_rebind_record_identity_tokens(record) & dependency_tokens
        ]

        def graph_record_requires_artifact(record: Mapping[str, Any]) -> bool:
            output_contract = (
                record.get('output_contract')
                if isinstance(record.get('output_contract'), Mapping)
                else {}
            )
            output_type = str(record.get('output_type') or '').strip().lower()
            role = str(record.get('role') or '').strip().lower()
            fulfillment_policy = str(output_contract.get('fulfillment_policy') or '').strip().lower()
            return bool(
                record.get('requires_artifact') is True
                or output_type in {'image', 'audio', 'video', 'file', 'artifact'}
                or role == 'text_artifact_output'
                or 'artifact' in fulfillment_policy
            )

        artifact_dependency_records = [
            record
            for record in dependency_graph_records
            if graph_record_requires_artifact(record)
        ]
        if not local_visual_binding and not artifact_dependency_records:
            return list(asset_records), [], 'artifact_set_fallback_for_ordering_dependencies'

        matched = [
            record
            for record in asset_records
            if cls._link_rebind_record_identity_tokens(record) & dependency_tokens
        ]
        if not local_visual_binding:
            return matched, dependency_ids, 'consumer_declared_dependency_binding'

        shared_text_targets = [
            record
            for record in asset_records
            if str(record.get('type') or record.get('kind') or '').strip().lower() == 'text'
            and branch_result_contracts._artifact_record_extension(record) in _LINK_REBIND_HTML_TARGET_EXTENSIONS
        ]
        selected = cls._unique_artifact_records_by_path([*matched, *shared_text_targets])
        media_dependency_records = [
            record
            for record in artifact_dependency_records
            if str(record.get('output_type') or '').strip().lower() in {'image', 'audio', 'video'}
            or str(record.get('capability') or '').strip().lower()
            in {'image_generation', 'text_to_speech', 'audio_generation', 'video_generation'}
        ]
        if not media_dependency_records and local_visual_binding:
            media_dependency_records = dependency_graph_records
        missing_media_dependency = any(
            not any(
                cls._link_rebind_record_identity_tokens(asset_record)
                & cls._link_rebind_record_identity_tokens(dependency_record)
                for asset_record in matched
            )
            for dependency_record in media_dependency_records
        )
        if missing_media_dependency:
            return selected, dependency_ids, 'consumer_declared_media_dependency_missing'
        return (
            selected,
            dependency_ids,
            'consumer_declared_dependency_binding_with_shared_text_targets',
        )

    @staticmethod
    def _link_rebind_normalize_json_key(key: str) -> str:
        value = re.sub(
            r'(?<=[a-z0-9])(?=[A-Z])',
            '_',
            str(key or '').strip(),
        )
        return re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')

    @classmethod
    def _link_rebind_json_path_key_family(cls, key: str) -> str:
        normalized = cls._link_rebind_normalize_json_key(key)
        if not normalized or not _LINK_REBIND_JSON_PATH_KEY_RE.fullmatch(normalized):
            return ''
        for family, tokens in (
            ('image', ('image', 'picture', 'photo')),
            ('audio', ('audio', 'sound', 'voice')),
            ('video', ('video', 'movie')),
            ('font', ('font',)),
            ('style', ('style', 'stylesheet', 'css')),
            ('script', ('script', 'javascript', 'js')),
        ):
            if any(token in normalized.split('_') for token in tokens):
                return family
        return ''

    @classmethod
    def _link_rebind_infer_single_family(cls, records: list[dict[str, Any]]) -> str:
        families: set[str] = set()
        for record in records:
            families.update(cls._link_rebind_record_families(record))
        return next(iter(families)) if len(families) == 1 else ''

    @staticmethod
    def _link_rebind_attr_context_family(content: str, match_start: int) -> str:
        tag_start = str(content or '').rfind('<', 0, max(0, match_start))
        if tag_start < 0:
            return ''
        source = str(content or '')
        tag_prefix = source[tag_start:match_start].lower()
        tag_match = re.match(r'<\s*([a-z0-9:-]+)', tag_prefix)
        tag_name = tag_match.group(1) if tag_match else ''
        if tag_name in {'img', 'picture'}:
            return 'image'
        if tag_name == 'audio':
            return 'audio'
        if tag_name == 'video':
            return 'video'
        if tag_name == 'source':
            tag_end = source.find('>', match_start)
            tag_text = source[tag_start : tag_end + 1 if tag_end >= 0 else match_start].lower()
            type_match = re.search(r'\btype\s*=\s*[\'"]?(audio|video)/', tag_text)
            if type_match:
                return str(type_match.group(1) or '')
            preceding = source[:tag_start].lower()
            audio_open = preceding.rfind('<audio')
            video_open = preceding.rfind('<video')
            picture_open = preceding.rfind('<picture')
            if audio_open > preceding.rfind('</audio') and audio_open > max(video_open, picture_open):
                return 'audio'
            if video_open > preceding.rfind('</video') and video_open > max(audio_open, picture_open):
                return 'video'
            if picture_open > preceding.rfind('</picture') and picture_open > max(audio_open, video_open):
                return 'image'
        if tag_name == 'script':
            return 'script'
        if tag_name == 'link':
            if re.search(r'\brel\s*=\s*[\'"]?stylesheet\b', tag_prefix):
                return 'style'
            if re.search(r'\bas\s*=\s*[\'"]?font\b', tag_prefix):
                return 'font'
        return ''

    @staticmethod
    def _link_rebind_css_context_family(content: str, match_start: int) -> str:
        prefix = str(content or '')[max(0, match_start - 240):match_start].lower()
        if '@font-face' in prefix and prefix.rfind('@font-face') > prefix.rfind('}'):
            return 'font'
        declaration_start = max(prefix.rfind('{'), prefix.rfind(';'))
        declaration_prefix = prefix[declaration_start + 1 :]
        if re.search(
            r'\b(?:background(?:-image)?|border-image(?:-source)?|list-style-image)\s*:[^{};]*$',
            declaration_prefix,
        ):
            return 'image'
        return ''

    @staticmethod
    def _link_rebind_family_matches(
        record: Mapping[str, Any],
        families: set[str],
    ) -> bool:
        if not families:
            return False
        return bool(LinkedArtifactMaterialization._link_rebind_record_families(record) & families)

    @classmethod
    def _link_rebind_records_for_family(
        cls,
        family: str,
        records: list[dict[str, Any]],
        *,
        declared_only: bool = False,
    ) -> list[dict[str, Any]]:
        token = str(family or '').strip().lower()
        if not token:
            return []
        for family_name, extensions in _LINK_REBIND_EXTENSION_FAMILIES.items():
            if token in extensions:
                token = family_name
                break
        declared_matches = [
            record
            for record in records
            if token in cls._link_rebind_record_declared_families(record)
        ]
        if declared_matches or declared_only:
            return declared_matches
        return [
            record
            for record in records
            if token in cls._link_rebind_record_families(record)
        ]

    @classmethod
    def _link_rebind_records_for_extension(
        cls,
        extension: str,
        records: list[dict[str, Any]],
        *,
        preferred_family: str = '',
    ) -> list[dict[str, Any]]:
        token = str(extension or '').strip().lower().lstrip('.')
        if not token:
            family_records = cls._link_rebind_records_for_family(preferred_family, records)
            if family_records:
                return family_records
            return list(records)
        exact_matches = [
            record
            for record in records
            if branch_result_contracts._artifact_record_extension(record) == token
        ]
        if preferred_family and exact_matches:
            preferred_exact_matches = cls._link_rebind_records_for_family(
                preferred_family,
                exact_matches,
                declared_only=True,
            )
            if preferred_exact_matches:
                return preferred_exact_matches
        elif exact_matches:
            return exact_matches
        family_records = cls._link_rebind_records_for_family(preferred_family, records)
        if family_records:
            return family_records
        if exact_matches:
            return exact_matches
        families = cls._link_rebind_extension_families(token)
        if not families:
            return []
        return [
            record
            for record in records
            if cls._link_rebind_family_matches(record, families)
        ]

    @classmethod
    def _local_link_target_exists(cls, url: str, *, target_path: str) -> bool:
        if cls._url_is_external_or_empty(url):
            return True
        token = str(url or '').split('?', 1)[0].split('#', 1)[0].strip()
        if not token:
            return True
        try:
            path = Path(token).expanduser()
            if not path.is_absolute():
                path = Path(target_path).expanduser().parent / token
            return path.exists()
        except (OSError, ValueError):
            return False

    @classmethod
    def _local_link_target_path(cls, url: str, *, target_path: str) -> str:
        if cls._url_is_external_or_empty(url):
            return ''
        token = str(url or '').split('?', 1)[0].split('#', 1)[0].strip()
        if not token:
            return ''
        try:
            path = Path(token).expanduser()
            if not path.is_absolute():
                if not target_path:
                    return ''
                path = Path(target_path).expanduser().parent / token
            return str(path.resolve(strict=False))
        except (OSError, ValueError):
            return ''

    @classmethod
    def _link_url_needs_rebind(
        cls,
        url: str,
        asset_records: list[dict[str, Any]],
        *,
        target_path: str = '',
        preferred_family: str = '',
        preferred_record: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        if cls._url_is_external_or_empty(url):
            token = str(url or '').strip()
            if not token or not _EXTERNAL_LINK_RE.match(token):
                return False
            if str(preferred_family or '').strip().lower() != 'image':
                return False
            return any(
                branch_result_contracts._artifact_record_path(record)
                and 'image' in cls._link_rebind_record_families(record)
                for record in asset_records
            )
        token = str(url or '').split('?', 1)[0].split('#', 1)[0].strip()
        if not token:
            return False
        extension = Path(token).suffix.lower().lstrip('.')
        if not extension:
            matching_records = cls._link_rebind_records_for_extension(
                '',
                asset_records,
                preferred_family=preferred_family,
            )
            if not matching_records:
                return False
            if _LINK_REBIND_PLACEHOLDER_RE.search(url):
                return True
            if target_path and cls._local_link_target_exists(url, target_path=target_path):
                if preferred_record:
                    current_path = cls._local_link_target_path(url, target_path=target_path)
                    selected_path = branch_result_contracts._artifact_record_path(preferred_record)
                    if current_path and selected_path:
                        try:
                            selected_path = str(Path(selected_path).expanduser().resolve(strict=False))
                        except (OSError, ValueError):
                            pass
                        return current_path != selected_path
                return False
            return bool(preferred_family)
        matching_records = cls._link_rebind_records_for_extension(
            extension,
            asset_records,
            preferred_family=preferred_family,
        )
        if not matching_records:
            return False
        if _LINK_REBIND_PLACEHOLDER_RE.search(url):
            return True
        if target_path and cls._local_link_target_exists(url, target_path=target_path):
            if preferred_record:
                current_path = cls._local_link_target_path(url, target_path=target_path)
                selected_path = branch_result_contracts._artifact_record_path(preferred_record)
                if current_path and selected_path:
                    try:
                        selected_path = str(Path(selected_path).expanduser().resolve(strict=False))
                    except (OSError, ValueError):
                        pass
                    return current_path != selected_path
            return False
        return True

    def _rebind_text_artifact_content(
        self,
        content: str,
        *,
        target_path: str,
        target_record: Mapping[str, Any],
        asset_records: list[dict[str, Any]],
        fallback_asset_records: Optional[list[dict[str, Any]]] = None,
        static_fetch_asset_records: Optional[list[dict[str, Any]]] = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        changes: list[dict[str, Any]] = []
        used_asset_paths: set[str] = set()

        def is_exact_named_text_link(url: str) -> bool:
            extension = Path(str(url or '').split('?', 1)[0].split('#', 1)[0]).suffix.lower().lstrip('.')
            return extension in _LINK_REBIND_TEXT_EXTENSIONS

        def choose_asset_record(
            url: str,
            candidates: list[dict[str, Any]],
        ) -> Optional[dict[str, Any]]:
            viable_candidates = [
                record
                for record in candidates
                if branch_result_contracts._artifact_record_path(record)
            ]
            if not viable_candidates:
                return None
            if is_exact_named_text_link(url):
                # A named local text dependency is one logical file even when
                # repair attempts left sibling candidates behind. Repeated
                # links must keep resolving to the same first canonical
                # identity instead of consuming a different sibling per use.
                return self._exact_asset_record_for_url(url, viable_candidates)
            unused_candidates = [
                record
                for record in viable_candidates
                if branch_result_contracts._artifact_record_path(record) not in used_asset_paths
            ]
            record = self._preferred_asset_for_url(url, unused_candidates)
            if not record and unused_candidates:
                record = unused_candidates[0]
            if not record:
                record = self._preferred_asset_for_url(url, viable_candidates) or viable_candidates[0]
            if not record:
                return None
            linked_path = branch_result_contracts._artifact_record_path(record)
            if linked_path:
                used_asset_paths.add(linked_path)
            return record

        def replacement_for_asset(
            url: str,
            candidates: list[dict[str, Any]],
        ) -> tuple[str, Optional[dict[str, Any]]]:
            record = choose_asset_record(url, candidates)
            if not record:
                return url, None
            linked_path = branch_result_contracts._artifact_record_path(record)
            if not linked_path:
                return url, None
            return self._relative_artifact_link(from_path=target_path, to_path=linked_path), record

        def unique_same_response_family_fallback(
            extension: str,
            preferred_family: str,
        ) -> tuple[list[dict[str, Any]], str]:
            family = str(preferred_family or '').strip().lower()
            if not family:
                extension_families = self._link_rebind_extension_families(extension)
                if len(extension_families) == 1:
                    family = next(iter(extension_families))
            if family not in {'image', 'audio', 'video', 'font'}:
                return [], ''
            family_records = self._unique_artifact_records_by_path(
                self._link_rebind_records_for_family(
                    family,
                    list(fallback_asset_records or []),
                )
            )
            concrete_records: list[dict[str, Any]] = []
            for record in family_records:
                path = branch_result_contracts._artifact_record_path(record)
                if not path:
                    continue
                try:
                    if not Path(path).expanduser().is_file():
                        continue
                except OSError:
                    continue
                concrete_records.append(record)
            if len(concrete_records) != 1:
                return [], ''
            return concrete_records, family

        def replace_attr(match: re.Match[str]) -> str:
            url = match.group('url')
            if not url.strip():
                # An empty image slot has no identity to rank or infer. Bind
                # only one concrete dependency already scoped to this consumer;
                # response-wide siblings cannot supply the missing authority.
                family = self._link_rebind_attr_context_family(content, match.start())
                if family != 'image' or not re.search(r'\bsrc\s*=', match.group('prefix'), re.IGNORECASE):
                    return match.group(0)
                candidates = self._unique_artifact_records_by_path(
                    self._link_rebind_records_for_family('image', asset_records)
                )
                if len(candidates) != 1:
                    return match.group(0)
                linked_path = branch_result_contracts._artifact_record_path(candidates[0])
                if not linked_path or not Path(linked_path).expanduser().is_file():
                    return match.group(0)
                replacement = self._relative_artifact_link(from_path=target_path, to_path=linked_path)
                if not replacement:
                    return match.group(0)
                changes.append({'from': url, 'to': replacement, 'linked_path': linked_path,
                                'kind': 'attribute_link', 'selection_policy': 'unique_declared_image_dependency'})
                return f"{match.group('prefix')}{match.group('quote')}{replacement}{match.group('quote')}"
            if self._link_rebind_is_dynamic_template_url(
                match.string, match.start('url'), url, target_path=target_path,
            ):
                return match.group(0)
            if self._link_rebind_url_matches_record_identity(url, target_record):
                if self._local_link_target_exists(url, target_path=target_path):
                    return match.group(0)
                linked_path = branch_result_contracts._artifact_record_path(target_record)
                if not linked_path:
                    return match.group(0)
                path_token = str(url or '').split('?', 1)[0].split('#', 1)[0]
                suffix = str(url or '')[len(path_token):]
                replacement = (
                    self._relative_artifact_link(
                        from_path=target_path,
                        to_path=linked_path,
                    )
                    + suffix
                )
                if replacement == url:
                    return match.group(0)
                changes.append(
                    {
                        'from': url,
                        'to': replacement,
                        'linked_path': linked_path,
                        'kind': 'self_attribute_link',
                    }
                )
                return (
                    f"{match.group('prefix')}{match.group('quote')}"
                    f"{replacement}{match.group('quote')}"
                )
            extension = Path(url.split('?', 1)[0].split('#', 1)[0]).suffix.lower().lstrip('.')
            preferred_family = self._link_rebind_attr_context_family(content, match.start())
            candidates = self._link_rebind_records_for_extension(
                extension,
                asset_records,
                preferred_family=preferred_family,
            )
            if is_exact_named_text_link(url):
                named_text_records = (
                    static_fetch_asset_records
                    if static_fetch_asset_records is not None
                    else asset_records
                )
                exact_named_candidates = [
                    record
                    for record in self._link_rebind_records_for_extension(
                        extension,
                        named_text_records,
                        preferred_family=preferred_family,
                    )
                    if self._link_rebind_url_matches_record_identity(url, record)
                ]
                if exact_named_candidates:
                    candidates = exact_named_candidates
            fallback_family = ''
            if not candidates:
                candidates, fallback_family = unique_same_response_family_fallback(
                    extension,
                    preferred_family,
                )
            preferred_record = (
                choose_asset_record(url, candidates)
                if is_exact_named_text_link(url)
                else None
            )
            if not self._link_url_needs_rebind(
                url,
                candidates,
                target_path=target_path,
                preferred_family=preferred_family,
                preferred_record=preferred_record,
            ):
                return match.group(0)
            if preferred_record:
                record = preferred_record
                replacement = self._relative_artifact_link(
                    from_path=target_path,
                    to_path=branch_result_contracts._artifact_record_path(record),
                )
            else:
                replacement, record = replacement_for_asset(url, candidates)
            if not record or replacement == url:
                return match.group(0)
            changes.append(
                {
                    'from': url,
                    'to': replacement,
                    'linked_path': branch_result_contracts._artifact_record_path(record),
                    'kind': (
                        'external_image_attribute_link'
                        if _EXTERNAL_LINK_RE.match(str(url or '').strip())
                        else 'attribute_link'
                    ),
                    **(
                        {
                            'selection_policy': (
                                'unique_same_response_family_fallback_after_declared_dependency_gap'
                            ),
                            'fallback_family': fallback_family,
                        }
                        if fallback_family
                        else {}
                    ),
                }
            )
            return f"{match.group('prefix')}{match.group('quote')}{replacement}{match.group('quote')}"

        def replace_url(match: re.Match[str]) -> str:
            url = match.group('url')
            if self._link_rebind_is_dynamic_template_url(
                match.string, match.start('url'), url, target_path=target_path,
            ):
                return match.group(0)
            if self._link_rebind_url_matches_record_identity(url, target_record):
                return match.group(0)
            extension = Path(url.split('?', 1)[0].split('#', 1)[0]).suffix.lower().lstrip('.')
            preferred_family = self._link_rebind_css_context_family(content, match.start())
            candidates = self._link_rebind_records_for_extension(
                extension,
                asset_records,
                preferred_family=preferred_family,
            )
            if not self._link_url_needs_rebind(
                url,
                candidates,
                target_path=target_path,
                preferred_family=preferred_family,
            ):
                return match.group(0)
            record = choose_asset_record(url, candidates)
            if not record:
                return match.group(0)
            linked_path = branch_result_contracts._artifact_record_path(record)
            replacement = self._relative_artifact_link(from_path=target_path, to_path=linked_path)
            if not record or replacement == url:
                return match.group(0)
            changes.append(
                {
                    'from': url,
                    'to': replacement,
                    'linked_path': linked_path,
                    'kind': 'css_url',
                }
            )
            return f"{match.group('prefix')}{replacement}{match.group('suffix')}"

        def replace_fetch(match: re.Match[str]) -> str:
            url = match.group('url')
            if self._link_rebind_url_matches_record_identity(url, target_record):
                return match.group(0)
            if not _static_fetch_url_is_local_file_dependency(url):
                return match.group(0)
            extension = Path(url.split('?', 1)[0].split('#', 1)[0]).suffix.lower().lstrip('.')
            requested_token = url.split('?', 1)[0].split('#', 1)[0]
            requested_name = Path(requested_token).name.lower()
            fetch_records = (
                static_fetch_asset_records
                if static_fetch_asset_records is not None
                else asset_records
            )
            candidates = [
                record
                for record in self._link_rebind_records_for_extension(extension, fetch_records)
                if (
                    Path(branch_result_contracts._artifact_record_path(record)).name.lower() == requested_name
                    or self._artifact_record_matches_text_artifact_source_name(
                        record,
                        requested_name,
                    )
                )
            ]
            preferred_record = self._exact_asset_record_for_url(url, candidates)
            if not self._link_url_needs_rebind(
                url,
                candidates,
                target_path=target_path,
                preferred_record=preferred_record,
            ):
                return match.group(0)
            if preferred_record:
                record = preferred_record
                replacement = self._relative_artifact_link(
                    from_path=target_path,
                    to_path=branch_result_contracts._artifact_record_path(record),
                )
            else:
                replacement, record = replacement_for_asset(url, candidates)
            if not record or replacement == url:
                return match.group(0)
            changes.append(
                {
                    'from': url,
                    'to': replacement,
                    'linked_path': branch_result_contracts._artifact_record_path(record),
                    'kind': 'static_fetch_link',
                    'selection_policy': 'exact_named_static_fetch_dependency',
                }
            )
            return f"{match.group('prefix')}{match.group('quote')}{replacement}{match.group('quote')}"

        rebound = _LINK_REBIND_ATTR_RE.sub(replace_attr, content)
        rebound = _LINK_REBIND_URL_RE.sub(replace_url, rebound)
        rebound = _LINK_REBIND_FETCH_RE.sub(replace_fetch, rebound)
        return rebound, changes

    def _rebind_json_artifact_content(
        self,
        content: str,
        *,
        target_path: str,
        asset_records: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        try:
            document = json.loads(str(content or ''))
        except (TypeError, ValueError, json.JSONDecodeError):
            return content, []

        changes: list[dict[str, Any]] = []
        used_asset_paths: set[str] = set()

        def choose_asset_record(
            url: str,
            candidates: list[dict[str, Any]],
        ) -> Optional[dict[str, Any]]:
            viable = [
                record
                for record in candidates
                if branch_result_contracts._artifact_record_path(record)
            ]
            unused = [
                record
                for record in viable
                if branch_result_contracts._artifact_record_path(record) not in used_asset_paths
            ]
            record = self._preferred_asset_for_url(url, unused)
            if not record and unused:
                record = unused[0]
            if not record:
                record = self._preferred_asset_for_url(url, viable)
                if not record and len(viable) == 1:
                    record = viable[0]
            linked_path = branch_result_contracts._artifact_record_path(record or {})
            if linked_path:
                used_asset_paths.add(linked_path)
            return record

        def pointer_token(value: Any) -> str:
            return str(value).replace('~', '~0').replace('/', '~1')

        def visit(value: Any, *, field_key: str = '', pointer: str = '') -> Any:
            if isinstance(value, dict):
                return {
                    key: visit(
                        child,
                        field_key=str(key),
                        pointer=f'{pointer}/{pointer_token(key)}',
                    )
                    for key, child in value.items()
                }
            if isinstance(value, list):
                return [
                    visit(
                        child,
                        field_key=field_key,
                        pointer=f'{pointer}/{index}',
                    )
                    for index, child in enumerate(value)
                ]
            if not isinstance(value, str):
                return value
            preferred_family = self._link_rebind_json_path_key_family(field_key)
            normalized_key = self._link_rebind_normalize_json_key(field_key)
            if not normalized_key or not _LINK_REBIND_JSON_PATH_KEY_RE.fullmatch(normalized_key):
                return value
            token = value.split('?', 1)[0].split('#', 1)[0]
            extension = Path(token).suffix.lower().lstrip('.')
            candidates = self._link_rebind_records_for_extension(
                extension,
                asset_records,
                preferred_family=preferred_family,
            )
            if not preferred_family:
                preferred_family = self._link_rebind_infer_single_family(candidates)
                candidates = self._link_rebind_records_for_extension(
                    extension,
                    asset_records,
                    preferred_family=preferred_family,
                )
            if not self._link_url_needs_rebind(
                value,
                candidates,
                target_path=target_path,
                preferred_family=preferred_family,
            ):
                return value
            record = choose_asset_record(value, candidates)
            linked_path = branch_result_contracts._artifact_record_path(record or {})
            if not linked_path:
                return value
            replacement = self._relative_artifact_link(
                from_path=target_path,
                to_path=linked_path,
            )
            if not replacement or replacement == value:
                return value
            changes.append(
                {
                    'from': value,
                    'to': replacement,
                    'linked_path': linked_path,
                    'kind': 'json_path_link',
                    'json_pointer': pointer or '/',
                    'json_field': field_key,
                }
            )
            return replacement

        rebound_document = visit(document)
        if not changes:
            return content, []
        rebound = json.dumps(rebound_document, ensure_ascii=False, indent=2)
        if str(content or '').endswith('\n'):
            rebound += '\n'
        return rebound, changes

    def _terminal_link_rebind_write_owners(
        self,
        payload: Mapping[str, Any],
        records: list[dict[str, Any]],
        *,
        target_path: str,
        original: str,
        rebound: str,
        asset_records: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Bind a real write to independently verified, already-owned repairs.

        Path grouping is only physical write coalescing. Ownership comes from
        unmerged saved records plus the exact branch's bounded repair contract.
        Never copy identities from same-target pending work into a saved record.
        """
        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        branches = [
            branch
            for key in ('pending_branches', 'active_branches', 'failed_branches')
            for branch in late_fill.get(key) or []
            if isinstance(branch, Mapping)
        ]
        # Public artifact selection may collapse a repair result into the
        # canonical document. Keep its explicit execution identity for this
        # bounded write; it does not become a second public artifact.
        owned_records = [
            *records,
            *[
                {**result, 'type': 'text', 'path': result['saved_text_path']}
                for result in late_fill.get('fill_results') or []
                if isinstance(result, Mapping)
                and result.get('saved_text_path')
                and not result.get('error')
                and str(result.get('status') or '') not in {'failed', 'cancelled', 'superseded'}
            ],
        ]
        owners: dict[str, dict[str, str]] = {}
        for record in owned_records:
            branch_id = str(record.get('branch_id') or '').strip()
            phase_id = str(record.get('phase_id') or '').strip()
            if (
                not branch_id
                or branch_result_contracts._artifact_record_path(record) != target_path
                or str(record.get('type') or record.get('kind') or '') != 'text'
            ):
                continue
            matching = [branch for branch in branches if branch.get('branch_id') == branch_id]
            if not matching:
                continue
            phases = {
                str(item.get('phase_id')).strip()
                for item in [*owned_records, *matching]
                if item.get('branch_id') == branch_id
                if item.get('phase_id')
            }
            if len(phases) > 1:
                continue
            phase_id = next(iter(phases), '')
            # Every projection of this identity must describe the same bounded
            # link repair; an unrelated edit cannot inherit its write proof.
            if any(
                branch.get('repair_action') != 'rebind_dependency_evidence'
                or not text_artifact_materialization._artifact_gap_is_authoritative_bounded_text_artifact_repair(branch)
                or text_artifact_materialization._text_artifact_revision_required(branch)
                or not text_artifact_materialization._text_artifact_path_matches_target(
                    target_path,
                    self._text_artifact_target_path_from_mapping(branch)
                    or self._text_artifact_target_path_from_mapping(branch.get('artifact_request') or {}),
                )
                for branch in matching
            ):
                continue
            scoped_assets, _dependency_ids, _policy = self._link_rebind_asset_records_for_consumer(
                payload, record, asset_records, identity_only=True,
            )
            if branch_result_contracts._artifact_record_extension(record) == 'json':
                candidate, changes = self._rebind_json_artifact_content(
                    original, target_path=target_path, asset_records=scoped_assets,
                )
            else:
                candidate, changes = self._rebind_text_artifact_content(
                    original, target_path=target_path, target_record=record,
                    asset_records=scoped_assets,
                    fallback_asset_records=[],
                    static_fetch_asset_records=scoped_assets,
                )
            if not changes or candidate != rebound:
                continue
            owners[branch_id] = {
                'branch_id': branch_id,
                **({'phase_id': phase_id} if phase_id else {}),
            }
        return list(owners.values())

    @observe_state('late_fill.linked_artifact_rebind', 'saved_artifact_bindings', 'rebound_artifact_state', labels=('NEW_AUTHORITY_BOUNDARY',), new_authority_boundary=True)
    def rebind_terminal_linked_artifacts(
        self,
        payload: dict[str, Any],
        *,
        current_outputs: Optional[list[dict[str, Any]]] = None,
        accepted_fill_results: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        # Use the freshly reconciled eligibility view only for binding. Publishing
        # it before Closure would add output handles to unrelated repair/rebase
        # evidence collection; the normal final frame still owns publication.
        records = self._collect_link_rebind_artifact_records(
            {**payload, 'outputs': current_outputs}
            if current_outputs is not None else payload
        )
        if not records:
            return payload
        text_records = self._unique_artifact_records_by_path(
            [
                record
                for record in records
                if str(record.get('type') or record.get('kind') or '').strip().lower() == 'text'
                and branch_result_contracts._artifact_record_extension(record) in _LINK_REBIND_TEXT_EXTENSIONS
                and branch_result_contracts._artifact_record_path(record)
            ]
        )
        asset_records = [
            record
            for record in records
            if branch_result_contracts._artifact_record_path(record)
        ]
        asset_records = self._unique_artifact_records_by_path(asset_records)
        if not text_records or not asset_records:
            return payload

        updated_payload = dict(payload or {})
        rebinds: list[dict[str, Any]] = []
        updated_content_by_path: dict[str, str] = {}
        for record in text_records:
            target_path = branch_result_contracts._artifact_record_path(record)
            available_asset_records = [
                item
                for item in asset_records
                if branch_result_contracts._artifact_record_path(item) != target_path
            ]
            consumer_asset_records, dependency_ids, selection_policy = (
                self._link_rebind_asset_records_for_consumer(
                    payload,
                    record,
                    available_asset_records,
                )
            )
            fallback_asset_records = (
                [
                    item
                    for item in available_asset_records
                    if item.get('_link_rebind_public_output') is True
                ]
                if dependency_ids
                else []
            )
            try:
                target = Path(target_path).expanduser()
                if not target.is_file() or target.stat().st_size > 512_000:
                    continue
                original = target.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            if branch_result_contracts._artifact_record_extension(record) == 'json':
                rebound, changes = self._rebind_json_artifact_content(
                    original,
                    target_path=target_path,
                    asset_records=consumer_asset_records,
                )
            else:
                rebound, changes = self._rebind_text_artifact_content(
                    original,
                    target_path=target_path,
                    target_record=record,
                    asset_records=consumer_asset_records,
                    fallback_asset_records=fallback_asset_records,
                    static_fetch_asset_records=available_asset_records,
                )
            if not changes or rebound == original:
                continue
            for change in changes:
                change.setdefault('selection_policy', selection_policy)
                if (
                    dependency_ids
                    and change.get('selection_policy') != 'exact_named_static_fetch_dependency'
                ):
                    change['consumer_dependency_ids'] = list(dependency_ids)
            write_owners = self._terminal_link_rebind_write_owners(
                payload, records, target_path=target_path,
                original=original, rebound=rebound,
                asset_records=available_asset_records,
            )
            try:
                target.write_text(rebound, encoding='utf-8')
            except OSError as exc:
                logging.warning('Could not rebind linked artifact paths in %s: %s', target_path, exc)
                continue
            updated_content_by_path[target_path] = rebound
            for owner in write_owners or [{}]:
                rebinds.append({
                    'kind': 'fruth.linked_artifact_rebind',
                    'target_path': target_path,
                    'target_extension': branch_result_contracts._artifact_record_extension(record),
                    'target_source_name': branch_result_contracts._artifact_record_source_name(record),
                    'change_count': len(changes),
                    'changes': changes,
                    'status': 'applied',
                    'source': 'terminal_late_fill_link_rebind',
                    **owner,
                })

        if not rebinds:
            return updated_payload

        def update_text_record_content(raw_record: Any) -> Any:
            if not isinstance(raw_record, dict):
                return raw_record
            record = dict(raw_record)
            path = branch_result_contracts._artifact_record_path(record)
            if path in updated_content_by_path:
                record['content'] = updated_content_by_path[path]
                if 'result_text' in record:
                    record['result_text'] = updated_content_by_path[path]
                if 'content_payload' in record:
                    record['content_payload'] = updated_content_by_path[path]
            return record

        if isinstance(updated_payload.get('artifacts'), list):
            updated_payload['artifacts'] = [
                update_text_record_content(item)
                for item in updated_payload.get('artifacts') or []
            ]
        if isinstance(updated_payload.get('saved_text_artifacts'), list):
            updated_payload['saved_text_artifacts'] = [
                update_text_record_content(item)
                for item in updated_payload.get('saved_text_artifacts') or []
            ]
        late_fill = dict(updated_payload.get('late_fill') or {}) if isinstance(updated_payload.get('late_fill'), Mapping) else {}
        if isinstance(late_fill.get('fill_results'), list):
            late_fill['fill_results'] = [
                copy.deepcopy(item) if item in (accepted_fill_results or [])
                else update_text_record_content(item)
                for item in late_fill.get('fill_results') or []
            ]
        existing_rebinds = [
            dict(item)
            for item in (late_fill.get('linked_artifact_rebinds') or [])
            if isinstance(item, Mapping)
        ]
        late_fill['linked_artifact_rebinds'] = [*existing_rebinds, *rebinds]
        late_fill['linked_artifact_rebind_status'] = 'applied'
        updated_payload['late_fill'] = late_fill
        return updated_payload

    def _terminal_generated_image_records(self, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        records = self._collect_link_rebind_artifact_records(payload)
        return self._unique_artifact_records_by_path(
            [
                record
                for record in records
                if (
                    str(record.get('type') or record.get('kind') or '').strip().lower() == 'image'
                    or branch_result_contracts._artifact_record_extension(record) in _LINK_REBIND_IMAGE_EXTENSIONS
                )
                and branch_result_contracts._artifact_record_path(record)
            ]
        )

    @staticmethod
    def _terminal_materialization_text_record_content(record: Mapping[str, Any]) -> str:
        path = branch_result_contracts._artifact_record_path(record)
        if not path:
            return ''
        try:
            target = Path(path).expanduser()
            if not target.is_file() or target.stat().st_size > 512_000:
                return ''
            return target.read_text(encoding='utf-8', errors='replace')
        except OSError:
            return ''

    @classmethod
    def _terminal_content_has_unresolved_link_placeholder(
        cls,
        content: str,
        dependency_records: list[dict[str, Any]],
        *,
        target_path: str = '',
    ) -> bool:
        if not content:
            return False

        for match in _LINK_REBIND_ATTR_RE.finditer(str(content or '')):
            url = str(match.group('url') or '').strip()
            if cls._link_rebind_is_dynamic_template_url(
                content, match.start('url'), url, target_path=target_path,
            ):
                continue
            if not url:
                continue
            extension = Path(url.split('?', 1)[0].split('#', 1)[0]).suffix.lower().lstrip('.')
            preferred_family = cls._link_rebind_attr_context_family(content, match.start())
            candidates = cls._link_rebind_records_for_extension(
                extension,
                dependency_records,
                preferred_family=preferred_family,
            )
            if cls._link_url_needs_rebind(
                url,
                candidates,
                target_path=target_path,
                preferred_family=preferred_family,
            ):
                return True

        for match in _LINK_REBIND_URL_RE.finditer(str(content or '')):
            url = str(match.group('url') or '').strip()
            if cls._link_rebind_is_dynamic_template_url(
                content, match.start('url'), url, target_path=target_path,
            ):
                continue
            if not url:
                continue
            extension = Path(url.split('?', 1)[0].split('#', 1)[0]).suffix.lower().lstrip('.')
            preferred_family = cls._link_rebind_css_context_family(content, match.start())
            candidates = cls._link_rebind_records_for_extension(
                extension,
                dependency_records,
                preferred_family=preferred_family,
            )
            if cls._link_url_needs_rebind(
                url,
                candidates,
                target_path=target_path,
                preferred_family=preferred_family,
            ):
                return True

        for match in _LINK_REBIND_FETCH_RE.finditer(str(content or '')):
            url = str(match.group('url') or '').strip()
            if not _static_fetch_url_is_local_file_dependency(url):
                continue
            extension = Path(url.split('?', 1)[0].split('#', 1)[0]).suffix.lower().lstrip('.')
            candidates = cls._link_rebind_records_for_extension(extension, dependency_records)
            if cls._link_url_needs_rebind(
                url,
                candidates,
                target_path=target_path,
            ):
                return True
        return False

    @classmethod
    def _terminal_json_content_has_unresolved_dependency_link(
        cls,
        content: str,
        dependency_records: list[dict[str, Any]],
        *,
        target_path: str,
    ) -> bool:
        try:
            document = json.loads(str(content or ''))
        except (TypeError, ValueError, json.JSONDecodeError):
            return True

        def visit(value: Any, *, field_key: str = '') -> bool:
            if isinstance(value, Mapping):
                return any(
                    visit(child, field_key=str(key))
                    for key, child in value.items()
                )
            if isinstance(value, list):
                return any(visit(child, field_key=field_key) for child in value)
            if not isinstance(value, str):
                return False
            normalized_key = cls._link_rebind_normalize_json_key(field_key)
            if not normalized_key or not _LINK_REBIND_JSON_PATH_KEY_RE.fullmatch(normalized_key):
                return False
            preferred_family = cls._link_rebind_json_path_key_family(field_key)
            token = value.split('?', 1)[0].split('#', 1)[0]
            extension = Path(token).suffix.lower().lstrip('.')
            candidates = cls._link_rebind_records_for_extension(
                extension,
                dependency_records,
                preferred_family=preferred_family,
            )
            if not preferred_family:
                preferred_family = cls._link_rebind_infer_single_family(candidates)
                candidates = cls._link_rebind_records_for_extension(
                    extension,
                    dependency_records,
                    preferred_family=preferred_family,
                )
            return cls._link_url_needs_rebind(
                value,
                candidates,
                target_path=target_path,
                preferred_family=preferred_family,
            )

        return visit(document)

    @staticmethod
    def _mask_inline_javascript_non_code(content: str) -> str:
        """Mask strings/comments before applying deliberately small JS checks."""
        text = str(content or '')
        token_re = re.compile(
            r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`|'
            r'//[^\n]*|/\*[\s\S]*?\*/)'
        )

        def mask(match: re.Match[str]) -> str:
            return ''.join('\n' if char == '\n' else ' ' for char in match.group(0))

        return token_re.sub(mask, text)

    @classmethod
    def _inline_javascript_binding_issues(cls, content: str) -> list[str]:
        issues: list[str] = []
        for script_match in _INLINE_SCRIPT_RE.finditer(str(content or '')):
            script = cls._mask_inline_javascript_non_code(script_match.group('body') or '')
            invalid_identifier = next(
                (
                    match
                    for match in _JS_INVALID_IDENTIFIER_SEPARATOR_RE.finditer(script)
                    if len(str(match.group('separator') or '')) >= 2
                    and all(
                        unicodedata.category(char).startswith(('P', 'S'))
                        for char in str(match.group('separator') or '')
                    )
                ),
                None,
            )
            if invalid_identifier:
                issues.append(
                    'inline JavaScript contains a suspicious repeated identifier separator near '
                    f'`{invalid_identifier.group(0)}`'
                )
        return issues[:4]

    def _terminal_web_binding_contract_open_checks(
        self,
        payload: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Detect small, high-confidence HTML/inline-JS to local-JSON mismatches.

        This is intentionally not a JavaScript interpreter.  It only checks
        direct ``array.forEach(item => ...)``/``map`` consumers against the
        concrete JSON array they fetch, plus suspicious repeated punctuation
        inside an inline-JS identifier.  A directly consumed collection is
        required to exist and be an array; optional fields and arbitrary JS
        semantics stay outside this guard. Browser execution remains separate.
        """
        records = self._collect_link_rebind_artifact_records(payload)
        text_records = self._unique_artifact_records_by_path(
            [
                record
                for record in records
                if str(record.get('type') or record.get('kind') or '').strip().lower() == 'text'
                and branch_result_contracts._artifact_record_extension(record) in _LINK_REBIND_TEXT_EXTENSIONS
                and branch_result_contracts._artifact_record_path(record)
            ]
        )
        if not text_records:
            return []
        html_paths = {
            branch_result_contracts._artifact_record_path(record)
            for record in text_records
            if branch_result_contracts._artifact_record_extension(record) in {'html', 'htm'}
        }
        dependency_records = [
            record
            for record in text_records
            if branch_result_contracts._artifact_record_path(record) not in html_paths
            and branch_result_contracts._artifact_record_extension(record)
            in _TERMINAL_MATERIALIZABLE_LOCAL_DEPENDENCY_EXTENSIONS
        ]
        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        checks: list[dict[str, Any]] = []
        seen_checks: set[tuple[str, str, str]] = set()

        def dependency_for_url(url: str, source_path: str) -> Optional[dict[str, Any]]:
            token = str(url or '').split('?', 1)[0].split('#', 1)[0].strip()
            requested_name = Path(token).name.lower()
            target_path = self._local_link_target_path(token, target_path=source_path)
            for record in dependency_records:
                record_path = branch_result_contracts._artifact_record_path(record)
                if target_path and record_path and str(Path(record_path).resolve()) == target_path:
                    return record
                if record_path and Path(record_path).name.lower() == requested_name:
                    return record
                if branch_result_contracts._artifact_record_source_name(record).lower() == Path(requested_name).stem.lower():
                    return record
            return None

        def append_check(
            target_record: Mapping[str, Any],
            reason: str,
            evidence: str,
            *,
            consumer_record: Optional[Mapping[str, Any]] = None,
        ) -> None:
            target_path = branch_result_contracts._artifact_record_path(target_record)
            target_extension = branch_result_contracts._artifact_record_extension(target_record)
            target_source_name = branch_result_contracts._artifact_record_source_name(target_record)
            key = (target_path, evidence, reason)
            if not target_path or key in seen_checks:
                return
            seen_checks.add(key)
            branch_hint = self._terminal_text_branch_hint_for_dependency(
                late_fill=late_fill,
                extension=target_extension,
                source_name=target_source_name,
                target_path=target_path,
            )
            branch_id = str(
                branch_hint.get('branch_id')
                or target_record.get('branch_id')
                or ''
            ).strip()
            phase_id = str(
                branch_hint.get('phase_id')
                or target_record.get('phase_id')
                or branch_id
                or ''
            ).strip()
            target_content = self._terminal_materialization_text_record_content(target_record)
            if len(target_content) > 90_000:
                target_content = f'{target_content[:90_000].rstrip()}\n\n[content truncated for repair prompt size]'
            consumer_path = branch_result_contracts._artifact_record_path(consumer_record or {})
            consumer_content = self._terminal_materialization_text_record_content(consumer_record or {})
            if len(consumer_content) > 45_000:
                consumer_content = f'{consumer_content[:45_000].rstrip()}\n\n[consumer content truncated for repair prompt size]'
            content_lines = [
                f'Target text artifact: {target_path}',
                'Deterministic web binding issue:',
                f'- {reason}',
            ]
            if consumer_path and consumer_path != target_path:
                content_lines.extend(
                    [
                        f'Bound local consumer: {consumer_path}',
                        '--- CURRENT CONSUMER START ---',
                        consumer_content,
                        '--- CURRENT CONSUMER END ---',
                    ]
                )
            content_lines.extend(
                [
                    '--- CURRENT TARGET START ---',
                    target_content,
                    '--- CURRENT TARGET END ---',
                    'Repair only the target artifact so the deterministic local web binding is coherent. '
                    'Preserve valid copy, layout, navigation, and artifact links. Output only the complete target file body.',
                ]
            )
            checks.append(
                {
                    'check_kind': 'web_runtime_binding',
                    'status': 'pending',
                    'evidence': evidence,
                    'role': 'linked_artifact_binding_review',
                    'requires_artifact': True,
                    'repair_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
                    'recovery_action': RECOVERY_ACTION_RETRY_SAME_BRANCH,
                    'repair_action_reason': 'saved local web artifacts violate a deterministic binding contract',
                    'reason': reason,
                    'branch_id': branch_id or None,
                    'phase_id': phase_id or None,
                    'source_path': consumer_path or target_path,
                    'dependency_source_path': consumer_path or None,
                    'content_payload': '\n'.join(content_lines).strip(),
                    'stage_direction': 'materialize_requested_text_artifact',
                    'dependency_policy': 'target_artifact_snapshot_only',
                    'text_artifact_extension': target_extension,
                    'text_artifact_source_name': target_source_name,
                    'text_artifact_source': 'closure_web_binding_repair',
                    'text_artifact_target_path': target_path,
                    'artifact_request': {
                        'extension': target_extension,
                        'source_name': target_source_name,
                        'source': 'closure_web_binding_repair',
                        'target_path': target_path,
                    },
                    'content_payload_source': 'terminal_web_runtime_binding_review',
                    'review_criteria': ['static_local_web_binding'],
                }
            )

        for source_record in text_records:
            extension = branch_result_contracts._artifact_record_extension(source_record)
            if extension not in {'html', 'htm', 'js', 'mjs', 'cjs'}:
                continue
            source_path = branch_result_contracts._artifact_record_path(source_record)
            content = self._terminal_materialization_text_record_content(source_record)
            if not content:
                continue
            javascript_content = (
                content
                if extension in {'html', 'htm'}
                else f'<script>{content}</script>'
            )
            for issue in self._inline_javascript_binding_issues(javascript_content):
                append_check(
                    source_record,
                    issue,
                    'inline_javascript_binding_mismatch',
                    consumer_record=source_record,
                )

            for fetch_match in _LINK_REBIND_FETCH_RE.finditer(content):
                url = str(fetch_match.group('url') or '').strip()
                if (
                    not _static_fetch_url_is_local_file_dependency(url)
                    or not url.lower().split('?', 1)[0].split('#', 1)[0].endswith('.json')
                ):
                    continue
                dependency = dependency_for_url(url, source_path)
                if not dependency:
                    continue
                dependency_content = self._terminal_materialization_text_record_content(dependency)
                try:
                    document = json.loads(dependency_content)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                script_start = fetch_match.end()
                next_fetch = _LINK_REBIND_FETCH_RE.search(content, script_start)
                script_end = next_fetch.start() if next_fetch else len(content)
                script_content = content[script_start:script_end]
                fetch_prefix = content[max(0, fetch_match.start() - 240):fetch_match.start()]
                response_assignment = _JS_FETCH_RESPONSE_ASSIGNMENT_RE.search(fetch_prefix)
                response_name = str(
                    response_assignment.group('response')
                    if response_assignment
                    else ''
                ).strip()
                bound_json_roots = {
                    str(binding.group('binding') or '').strip()
                    for binding in _JS_AWAITED_JSON_BINDING_RE.finditer(script_content)
                    if response_name
                    and str(binding.group('response') or '').strip() == response_name
                    and str(binding.group('binding') or '').strip()
                }
                for iterator in _JS_COLLECTION_ITERATOR_RE.finditer(script_content):
                    collection_path = re.sub(r'\s+', '', iterator.group('collection') or '')
                    collection_key = collection_path.rsplit('.', 1)[-1]
                    body_end = script_content.find('});', iterator.end())
                    body = script_content[iterator.end(): body_end if body_end >= 0 else iterator.end() + 12000]
                    item_name = iterator.group('item')
                    properties = {
                        match.group(1)
                        for match in re.finditer(
                            rf'\b{re.escape(item_name)}\s*\.\s*([A-Za-z_$][A-Za-z0-9_$]*)\b',
                            body,
                        )
                    }
                    path_parts = [part for part in collection_path.split('.') if part]
                    bound_collection = bool(
                        path_parts
                        and path_parts[0] in bound_json_roots
                    )
                    collection_found = True
                    values: Any
                    if bound_collection:
                        values = document
                        for path_part in path_parts[1:]:
                            if not isinstance(values, Mapping) or path_part not in values:
                                collection_found = False
                                values = None
                                break
                            values = values[path_part]
                    else:
                        values = document.get(collection_key) if isinstance(document, Mapping) else None
                    if bound_collection and not collection_found:
                        append_check(
                            dependency,
                            f'Fetched JSON path `{".".join(path_parts[1:]) or collection_path}` is consumed as `{collection_path}` but is missing',
                            'static_json_consumer_contract_mismatch',
                            consumer_record=source_record,
                        )
                        continue
                    if bound_collection and not isinstance(values, list):
                        append_check(
                            dependency,
                            f'Fetched JSON path `{".".join(path_parts[1:]) or collection_path}` is consumed as `{collection_path}` but is not an array',
                            'static_json_consumer_contract_mismatch',
                            consumer_record=source_record,
                        )
                        continue
                    if not isinstance(values, list) or not values:
                        continue
                    if not all(isinstance(item, Mapping) for item in values):
                        if bound_collection and properties:
                            append_check(
                                dependency,
                                f'JSON collection `{collection_path}` is consumed as object items but contains a non-object value',
                                'static_json_consumer_contract_mismatch',
                                consumer_record=source_record,
                            )
                        continue
                    for property_name in sorted(properties):
                        if any(property_name not in item for item in values):
                            append_check(
                                dependency,
                                f'JSON collection `{collection_key}` is consumed as `{item_name}.{property_name}` but at least one item lacks that field',
                                'static_json_consumer_contract_mismatch',
                                consumer_record=source_record,
                            )
        return checks

    @classmethod
    def _terminal_linked_artifact_dependency_records(
        cls,
        payload: Mapping[str, Any],
        records: list[dict[str, Any]],
        consumer_record: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]], bool]:
        """Select owed links, not the candidate pool used to repair existing links.

        A dependency edge alone also represents ordering or saved-data consumption.
        Only the existing link contracts create an absent-link duty. Keep that
        duty unresolved when its exact producer binding is missing or ambiguous.
        """
        graph = (payload.get('runtime') or {}).get('request_phase_graph') or {}
        graph_records = [
            record for key in ('phases', 'downstream_branches')
            for record in graph.get(key) or [] if isinstance(record, Mapping)
        ]

        def same_owner(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
            keys = ('branch_id', 'phase_id')
            return bool(
                any(left.get(key) and left.get(key) == right.get(key) for key in keys)
                and all(not left.get(key) or not right.get(key)
                        or left[key] == right[key] for key in keys)
            )

        dependency_ids: set[str] = set()
        required = False
        link_contracts = {'local_visual_asset_binding', 'shared_css_binding'}
        owners = [consumer_record, *[
            record for record in graph_records if same_owner(consumer_record, record)
        ]]
        for owner in required_intent_obligations(owners):
            execution = owner.get('execution_contract') or {}
            if (owner.get('dependency_contract') or execution.get('dependency_contract')) not in link_contracts:
                continue
            required = True
            dependency_ids.update(owner.get('required_image_phase_ids')
                                  or cls._link_rebind_dependency_values(owner))
        for obligation in required_intent_obligations(graph.get('intent_obligations')):
            target = {'branch_id': obligation.get('target_branch_id'),
                      'phase_id': obligation.get('target_phase_id')}
            if (obligation.get('dependency_contract') in link_contracts
                    and same_owner(consumer_record, target)):
                required = True
                dependency_ids.update(obligation.get('source_phase_ids') or [])
        if not required:
            return [], False

        selected: list[dict[str, Any]] = []
        missing = not dependency_ids
        response_id = str(payload.get('id') or '')
        for dependency_id in dependency_ids:
            producers = [record for record in graph_records
                         if dependency_id in cls._link_rebind_record_identity_tokens(record)]
            matches = [
                record for record in records
                if dependency_id in cls._link_rebind_record_identity_tokens(record)
                and (not producers or any(same_owner(record, producer) for producer in producers))
                and not (response_id and record.get('source_response_id')
                         and record['source_response_id'] != response_id)
                and record.get('_link_rebind_public_output') is not False
                and record.get('diagnostic_only') is not True
                and record.get('materialization_eligible') is not False
                and record.get('status') not in {'failed', 'cancelled', 'waived', 'superseded'}
                and branch_result_contracts._artifact_record_path(record)
            ]
            matches = cls._unique_artifact_records_by_path(matches)
            if len(matches) != 1:
                missing = True
            else:
                selected.extend(matches)
        return cls._unique_artifact_records_by_path(selected), missing

    @classmethod
    def _terminal_artifact_link_urls(cls, record: Mapping[str, Any], content: str) -> list[str]:
        """Read references using the same syntax boundaries as terminal rebinding."""
        urls: list[str] = []
        if branch_result_contracts._artifact_record_extension(record) == 'json':
            def visit(value: Any, key: str = '') -> None:
                if isinstance(value, Mapping):
                    for child_key, child in value.items():
                        visit(child, str(child_key))
                elif isinstance(value, list):
                    for child in value:
                        visit(child, key)
                elif isinstance(value, str) and _LINK_REBIND_JSON_PATH_KEY_RE.fullmatch(
                    cls._link_rebind_normalize_json_key(key)
                ):
                    urls.append(value)
            try:
                visit(json.loads(content))
            except (TypeError, ValueError):
                pass  # Syntax validation retains ownership of malformed JSON.
            return urls
        path = branch_result_contracts._artifact_record_path(record)
        for pattern in (_LINK_REBIND_ATTR_RE, _LINK_REBIND_URL_RE):
            for match in pattern.finditer(content):
                url = match.group('url')
                if not cls._link_rebind_is_dynamic_template_url(
                    content, match.start('url'), url, target_path=path,
                ):
                    urls.append(url)
        urls.extend(match.group('url') for match in _LINK_REBIND_FETCH_RE.finditer(content)
                    if _static_fetch_url_is_local_file_dependency(match.group('url')))
        scripts = ([content] if branch_result_contracts._artifact_record_extension(record) in {'js', 'mjs', 'cjs'}
                   else [match.group('body') for match in _INLINE_SCRIPT_RE.finditer(content)])
        for script in scripts:
            fetch_values = {match.group('value') for match in FETCH_LITERAL_PREFIX_RE.finditer(script)}
            urls.extend(match.group('value') for match in JS_QUOTED_RE.finditer(script)
                        if match.group('value') not in fetch_values)
        return urls

    def _terminal_text_branch_hint_for_dependency(
        self,
        *,
        late_fill: Mapping[str, Any],
        extension: str,
        source_name: str,
        target_path: str,
    ) -> dict[str, Any]:
        target_extension = str(extension or '').strip().lower().lstrip('.')
        target_source_name = str(source_name or '').strip().lower()
        normalized_target_path = text_artifact_materialization._normalized_text_artifact_path_for_match(
            target_path
        )
        candidate_branches = [
            branch
            for branch_key in (
                'completed_branches',
                'pending_branches',
                'active_branches',
                'failed_branches',
            )
            for branch in (late_fill.get(branch_key) or [])
            if isinstance(branch, Mapping)
        ]

        def branch_artifact_identity(
            branch: Mapping[str, Any],
        ) -> tuple[str, str, str]:
            artifact_request = (
                branch.get('artifact_request')
                if isinstance(branch.get('artifact_request'), Mapping)
                else {}
            )
            return (
                str(
                    branch.get('text_artifact_extension')
                    or artifact_request.get('extension')
                    or ''
                ).strip().lower().lstrip('.'),
                str(
                    branch.get('text_artifact_source_name')
                    or artifact_request.get('source_name')
                    or ''
                ).strip().lower(),
                str(
                    branch.get('text_artifact_target_path')
                    or artifact_request.get('target_path')
                    or ''
                ).strip(),
            )

        if normalized_target_path:
            for branch in candidate_branches:
                _branch_extension, _branch_source_name, branch_target_path = (
                    branch_artifact_identity(branch)
                )
                if branch_target_path and text_artifact_materialization._text_artifact_path_matches_target(
                    branch_target_path,
                    normalized_target_path,
                ):
                    return dict(branch)

        # Source-name fallback is only for incomplete target metadata.  Two
        # explicit unequal targets are distinct artifact authorities even when
        # their extension and source name are identical.
        for branch in candidate_branches:
            branch_extension, branch_source_name, branch_target_path = (
                branch_artifact_identity(branch)
            )
            if normalized_target_path and branch_target_path:
                continue
            if (
                target_extension
                and target_source_name
                and branch_extension == target_extension
                and branch_source_name == target_source_name
            ):
                return dict(branch)
        return {}

    def _terminal_unresolved_local_dependency_link_open_checks(
        self,
        payload: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        records = self._collect_link_rebind_artifact_records(payload)
        text_records = self._unique_artifact_records_by_path(
            [
                record
                for record in records
                if str(record.get('type') or record.get('kind') or '').strip().lower() == 'text'
                and branch_result_contracts._artifact_record_extension(record) in _LINK_REBIND_TEXT_EXTENSIONS
                and branch_result_contracts._artifact_record_path(record)
            ]
        )
        if not text_records:
            return []
        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        checks: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        def append_missing_link_check(source_record: Mapping[str, Any], url: str) -> None:
            source_path = branch_result_contracts._artifact_record_path(source_record)
            token = str(url or '').split('?', 1)[0].split('#', 1)[0].strip()
            extension = Path(token).suffix.lower().lstrip('.')
            if extension not in _TERMINAL_MATERIALIZABLE_LOCAL_DEPENDENCY_EXTENSIONS:
                return
            target_path = self._local_link_target_path(token, target_path=source_path)
            if not target_path or self._local_link_target_exists(token, target_path=source_path):
                return
            key = (source_path, token, target_path)
            if key in seen:
                return
            seen.add(key)
            source_content = self._terminal_materialization_text_record_content(source_record)
            source_content_sha256 = hashlib.sha256(
                source_content.encode('utf-8')
            ).hexdigest()
            if len(source_content) > 90_000:
                source_content = f'{source_content[:90_000].rstrip()}\n\n[content truncated for repair prompt size]'
            source_name = Path(token).stem or ('styles' if extension == 'css' else f'generated-{extension}')
            branch_hint = self._terminal_text_branch_hint_for_dependency(
                late_fill=late_fill,
                extension=extension,
                source_name=source_name,
                target_path=target_path,
            )
            branch_id = str(
                branch_hint.get('branch_id') or ''
            ).strip()
            phase_id = str(
                branch_hint.get('phase_id')
                or branch_id
                or ''
            ).strip()
            if extension == 'json':
                repair_instruction = (
                    f'Create or repair only the missing `{Path(target_path).name}` JSON artifact. '
                    'Use the static fetch consumer and its expected data access as binding context. '
                    'Output only the complete, valid JSON document.'
                )
            else:
                repair_instruction = (
                    f'Create or repair only the missing `{Path(target_path).name}` {extension} artifact. '
                    'Use the current source file selectors, classes, ids, and script/style expectations as binding context. '
                    'Preserve the existing HTML structure, copy, image links, and layout intent. '
                    'Output only the complete target file body.'
                )
            content_payload = '\n'.join(
                [
                    f'Target text artifact: {target_path}',
                    f'Missing local dependency linked from: {source_path}',
                    f'Missing link token: {url}',
                    f'Dependency type: {extension}',
                    'Dependency consumer file content (diagnostic context only; not target bytes):',
                    '--- DEPENDENCY CONSUMER START ---',
                    source_content,
                    '--- DEPENDENCY CONSUMER END ---',
                    repair_instruction,
                ]
            ).strip()
            checks.append(
                {
                    'check_kind': 'linked_artifact_binding',
                    'status': 'pending',
                    'evidence': 'unresolved_local_dependency_link',
                    'reason': 'final web artifact links a local dependency file that does not exist or is not materialized',
                    'capability': 'chat',
                    'output_type': 'text',
                    'role': 'linked_artifact_binding_review',
                    'branch_id': branch_id or None,
                    'phase_id': phase_id or None,
                    'requires_artifact': True,
                    'repair_action': RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
                    'recovery_action': RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
                    'repair_action_reason': 'missing local web dependency must be materialized before terminal closure',
                    'content_payload': content_payload,
                    'content_payload_source': 'closure_local_dependency_link_review',
                    'stage_direction': 'materialize_requested_text_artifact',
                    'dependency_source_path': source_path,
                    'dependency_consumer_path': source_path,
                    'dependency_consumer_content_sha256': source_content_sha256,
                    'target_artifact_path': target_path,
                    'missing_dependency_url': str(url or '').strip(),
                    'missing_dependency_target_path': target_path,
                    'text_artifact_extension': extension,
                    'text_artifact_source_name': source_name,
                    'text_artifact_source': 'closure_local_dependency_link',
                    'text_artifact_target_path': target_path,
                    'artifact_request': {
                        'extension': extension,
                        'source_name': source_name,
                        'source': 'closure_local_dependency_link',
                        'target_path': target_path,
                    },
                }
            )

        for record in text_records:
            source_path = branch_result_contracts._artifact_record_path(record)
            content = self._terminal_materialization_text_record_content(record)
            if not source_path or not content:
                continue
            for match in _LINK_REBIND_ATTR_RE.finditer(content):
                if self._link_rebind_is_dynamic_template_url(
                    content, match.start('url'), match.group('url'), target_path=source_path,
                ):
                    continue
                append_missing_link_check(record, str(match.group('url') or '').strip())
            for match in _LINK_REBIND_URL_RE.finditer(content):
                if self._link_rebind_is_dynamic_template_url(
                    content, match.start('url'), match.group('url'), target_path=source_path,
                ):
                    continue
                append_missing_link_check(record, str(match.group('url') or '').strip())
            for match in _LINK_REBIND_FETCH_RE.finditer(content):
                url = str(match.group('url') or '').strip()
                if _static_fetch_url_is_local_file_dependency(url):
                    append_missing_link_check(record, url)
        return checks

    def _terminal_linked_artifact_contract_is_fulfilled(
        self, payload: Mapping[str, Any], *,
        current_outputs: Optional[list[dict[str, Any]]] = None,
    ) -> bool:
        if current_outputs is not None and isinstance(payload.get('outputs'), list):
            payload = {**payload, 'outputs': current_outputs}
        records = self._collect_link_rebind_artifact_records(payload)
        text_records = [
            record
            for record in records
            if str(record.get('type') or record.get('kind') or '').strip().lower() == 'text'
            and branch_result_contracts._artifact_record_extension(record) in _LINK_REBIND_TEXT_EXTENSIONS
            and branch_result_contracts._artifact_record_path(record)
        ]
        if not text_records:
            return False
        if self._terminal_unresolved_local_dependency_link_open_checks(payload):
            return False
        if self._terminal_web_binding_contract_open_checks(payload):
            return False

        content_by_path: dict[str, str] = {}
        for record in text_records:
            path = branch_result_contracts._artifact_record_path(record)
            content = self._terminal_materialization_text_record_content(record)
            if path:
                content_by_path[path] = content
        if not any(content_by_path.values()):
            return False

        text_record_by_path = {
            branch_result_contracts._artifact_record_path(record): record
            for record in text_records
            if branch_result_contracts._artifact_record_path(record)
        }
        required_by_path: dict[str, list[dict[str, Any]]] = {}
        links_by_path: dict[str, set[str]] = {}
        for target_path, content in content_by_path.items():
            consumer_record = text_record_by_path.get(target_path, {})
            required_records, missing = self._terminal_linked_artifact_dependency_records(
                payload, records, consumer_record,
            )
            if missing:
                return False
            required_by_path[target_path] = required_records
            consumer_dependency_records, _dependency_ids, _selection_policy = (
                self._link_rebind_asset_records_for_consumer(
                    payload,
                    consumer_record,
                    [record for record in records
                     if branch_result_contracts._artifact_record_path(record) != target_path],
                )
            )
            if branch_result_contracts._artifact_record_extension(consumer_record) == 'json':
                unresolved = self._terminal_json_content_has_unresolved_dependency_link(
                    content,
                    consumer_dependency_records,
                    target_path=target_path,
                )
            else:
                unresolved = self._terminal_content_has_unresolved_link_placeholder(
                    content,
                    consumer_dependency_records,
                    target_path=target_path,
                )
            if unresolved:
                return False
            linked_paths: set[str] = set()
            for url in self._terminal_artifact_link_urls(consumer_record, content):
                linked_path = self._local_link_target_path(url, target_path=target_path)
                if not linked_path:
                    continue
                extension = Path(url.split('?', 1)[0].split('#', 1)[0]).suffix.lower().lstrip('.')
                if (
                    (extension in _TERMINAL_MATERIALIZABLE_LOCAL_DEPENDENCY_EXTENSIONS
                     or self._link_rebind_extension_families(extension))
                    and not self._local_link_target_exists(url, target_path=target_path)
                ):
                    return False
                linked_paths.add(linked_path)
            links_by_path[str(Path(target_path).resolve(strict=False))] = linked_paths

        for source_path, dependencies in required_by_path.items():
            # A page may expose an image through its saved CSS/JS/JSON dependency.
            # Only actual links from this consumer join the closure; disconnected
            # sibling content cannot satisfy its contract.
            normalized_source = str(Path(source_path).resolve(strict=False))
            pending = [normalized_source]
            if branch_result_contracts._artifact_record_extension(text_record_by_path[source_path]) == 'css':
                # The existing visual contract is also carried by a page's
                # stylesheet for preparation ordering. Its image cohort belongs
                # to the composed page, not to a second gallery inside the CSS.
                # Admit only a saved page that actually links this stylesheet
                # and owes the same producers. JSON manifests remain consumers
                # in their own right and cannot borrow their callers' links.
                required_paths = {branch_result_contracts._artifact_record_path(record) for record in dependencies}
                pending.extend(
                    str(Path(page_path).resolve(strict=False))
                    for page_path, page_dependencies in required_by_path.items()
                    if branch_result_contracts._artifact_record_extension(text_record_by_path[page_path]) in {'html', 'htm'}
                    and normalized_source in links_by_path.get(str(Path(page_path).resolve(strict=False)), set())
                    and required_paths.issubset({branch_result_contracts._artifact_record_path(record) for record in page_dependencies})
                )
            reachable: set[str] = set()
            while pending:
                current = pending.pop()
                for linked in links_by_path.get(current, set()) - reachable:
                    reachable.add(linked)
                    pending.append(linked)
            for record in dependencies:
                path = Path(branch_result_contracts._artifact_record_path(record)).resolve(strict=False)
                if str(path) not in reachable or not path.is_file():
                    return False
        return True

    @staticmethod
    def _terminal_exact_link_tokens_for_artifact(
        *,
        source_path: str,
        target_path: str,
    ) -> set[str]:
        tokens: set[str] = set()
        target = str(target_path or '').strip()
        if not target:
            return tokens
        tokens.add(target)
        target_name = Path(target).name
        if target_name:
            tokens.add(target_name)
        if source_path:
            relative = LinkedArtifactMaterialization._relative_artifact_link(
                from_path=source_path,
                to_path=target,
            )
            if relative:
                tokens.add(relative)
        return {token for token in tokens if token}

    @staticmethod
    def _terminal_exact_content_has_artifact_link(
        content: str,
        *,
        source_path: str,
        target_path: str,
    ) -> bool:
        text = str(content or '')
        if not text.strip():
            return False
        return any(
            token and token in text
            for token in LinkedArtifactMaterialization._terminal_exact_link_tokens_for_artifact(
                source_path=source_path,
                target_path=target_path,
            )
        )

    @staticmethod
    def _terminal_html_hero_snippets(content: str) -> list[str]:
        text = str(content or '')
        snippets: list[str] = []
        for match in _TERMINAL_HTML_HERO_BLOCK_RE.finditer(text):
            tag = str(match.group('tag') or '').strip().lower()
            attrs = str(match.group('attrs') or '')
            if tag != 'header' and not _TERMINAL_HERO_LOCAL_IMAGE_SIGNAL_RE.search(attrs):
                continue
            snippet = match.group(0)
            if snippet and snippet not in snippets:
                snippets.append(snippet)
        return snippets

    @staticmethod
    def _terminal_css_hero_snippets(content: str) -> list[str]:
        text = str(content or '')
        snippets: list[str] = []
        for match in _TERMINAL_CSS_HERO_BLOCK_RE.finditer(text):
            snippet = match.group(0)
            if snippet and snippet not in snippets:
                snippets.append(snippet)
        return snippets

    @staticmethod
    def _terminal_html_inline_style_blocks(content: str) -> list[str]:
        text = str(content or '')
        return [
            str(match.group('body') or '')
            for match in re.finditer(
                r'(?is)<style\b[^>]*>(?P<body>.*?)</style\s*>',
                text,
            )
            if str(match.group('body') or '').strip()
        ]

    @classmethod
    def _terminal_hero_local_image_required(
        cls,
        prompt_text: str,
        *,
        html_contents: list[str],
        css_contents: list[str],
    ) -> bool:
        if _TERMINAL_HERO_LOCAL_IMAGE_SIGNAL_RE.search(str(prompt_text or '')):
            return True
        return any(cls._terminal_html_hero_snippets(content) for content in html_contents) or any(
            cls._terminal_css_hero_snippets(content) for content in css_contents
        )

    def _terminal_hero_image_composition_open_check(
        self,
        payload: Mapping[str, Any],
        *,
        request_payload: Optional[Mapping[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        records = self._collect_link_rebind_artifact_records(payload)
        text_records = self._unique_artifact_records_by_path(
            [
                record
                for record in records
                if str(record.get('type') or record.get('kind') or '').strip().lower() == 'text'
                and branch_result_contracts._artifact_record_extension(record) in _LINK_REBIND_TEXT_EXTENSIONS
                and branch_result_contracts._artifact_record_path(record)
            ]
        )
        html_records = [
            record
            for record in text_records
            if branch_result_contracts._artifact_record_extension(record) in {'html', 'htm'}
        ]
        if not html_records:
            return None
        css_records = [
            record
            for record in text_records
            if branch_result_contracts._artifact_record_extension(record) == 'css'
        ]
        image_records = self._terminal_generated_image_records(payload)
        if not image_records:
            return None

        content_by_path: dict[str, str] = {}
        for record in text_records:
            source_path = branch_result_contracts._artifact_record_path(record)
            content = self._terminal_materialization_text_record_content(record)
            if source_path and content:
                content_by_path[source_path] = content
        if not content_by_path:
            return None

        html_contents = [
            content_by_path.get(branch_result_contracts._artifact_record_path(record), '')
            for record in html_records
        ]
        html_inline_css_contents = [
            style_block
            for content in html_contents
            for style_block in self._terminal_html_inline_style_blocks(content)
        ]
        css_contents = [
            content_by_path.get(branch_result_contracts._artifact_record_path(record), '')
            for record in css_records
        ] + html_inline_css_contents
        prompt_text = str(
            (request_payload or {}).get('prompt')
            or (request_payload or {}).get('input')
            or ((payload.get('request') or {}).get('prompt') if isinstance(payload.get('request'), Mapping) else '')
            or ''
        ).strip()
        if not self._terminal_hero_local_image_required(
            prompt_text,
            html_contents=html_contents,
            css_contents=css_contents,
        ):
            return None

        snippets: list[tuple[str, str]] = []
        for record in html_records:
            source_path = branch_result_contracts._artifact_record_path(record)
            for snippet in self._terminal_html_hero_snippets(content_by_path.get(source_path, '')):
                snippets.append((source_path, snippet))
        for record in css_records:
            source_path = branch_result_contracts._artifact_record_path(record)
            for snippet in self._terminal_css_hero_snippets(content_by_path.get(source_path, '')):
                snippets.append((source_path, snippet))
        for record in html_records:
            source_path = branch_result_contracts._artifact_record_path(record)
            html_content = content_by_path.get(source_path, '')
            for style_block in self._terminal_html_inline_style_blocks(html_content):
                for snippet in self._terminal_css_hero_snippets(style_block):
                    snippets.append((source_path, snippet))
        if not snippets:
            return None

        for source_path, snippet in snippets:
            for image_record in image_records:
                image_path = branch_result_contracts._artifact_record_path(image_record)
                if (
                    image_path
                    and self._terminal_exact_content_has_artifact_link(
                        snippet,
                        source_path=source_path,
                        target_path=image_path,
                    )
                ):
                    return None

        target_record = next(
            (
                record for record in css_records
                if self._terminal_css_hero_snippets(content_by_path.get(branch_result_contracts._artifact_record_path(record), ''))
            ),
            html_records[0],
        )
        target_extension = branch_result_contracts._artifact_record_extension(target_record) or 'html'
        target_name = branch_result_contracts._artifact_record_source_name(target_record) or ('styles' if target_extension == 'css' else 'index')
        target_path = branch_result_contracts._artifact_record_path(target_record)
        target_content = content_by_path.get(target_path, '') if target_path else ''
        bounded_content = target_content
        if len(bounded_content) > 90_000:
            bounded_content = f'{bounded_content[:90_000].rstrip()}\n\n[content truncated for repair prompt size]'
        generated_paths = [
            branch_result_contracts._artifact_record_path(record)
            for record in image_records
            if branch_result_contracts._artifact_record_path(record)
        ]
        generated_lines = [
            f'- {path} (relative from target: {self._relative_artifact_link(from_path=target_path, to_path=path)})'
            for path in generated_paths
        ]
        content_payload = '\n'.join(
            [
                f'Target text artifact: {target_path or target_name}',
                'Hero image composition defect:',
                '- The composed page has a hero/header area but no concrete generated image artifact path is used in that hero area.',
                'Generated image artifact paths available for hero binding:',
                *generated_lines,
                'Current saved target file content:',
                '--- CURRENT SAVED FILE START ---',
                bounded_content,
                '--- CURRENT SAVED FILE END ---',
                'Update only the target text artifact. Bind one concrete generated image path above into the hero/header image or background. Preserve existing valid links, copy, layout intent, and unrelated structure.',
            ]
        ).strip()
        return {
            'check_kind': 'hero_image_composition',
            'status': 'pending',
            'evidence': 'generated_image_not_represented_in_hero',
            'reason': 'final composed page hero/header area does not use a generated local image artifact',
            'capability': 'chat',
            'output_type': 'text',
            'role': 'linked_artifact_binding_review',
            'branch_id': str(target_record.get('branch_id') or '').strip() or None,
            'phase_id': str(target_record.get('phase_id') or target_record.get('branch_id') or '').strip() or None,
            'requires_artifact': True,
            'repair_action': RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
            'recovery_action': RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
            'repair_action_reason': 'final composed page must bind a generated local image into the hero/header area',
            'content_payload': content_payload,
            'content_payload_source': 'closure_hero_image_composition',
            'stage_direction': 'materialize_requested_text_artifact',
            'generated_image_count': len(generated_paths),
            'represented_image_count': 0,
            'missing_image_count': 1,
            'missing_image_paths': generated_paths[:8],
            'text_artifact_extension': target_extension,
            'text_artifact_source_name': target_name,
            'text_artifact_source': 'closure_hero_image_composition',
            'text_artifact_target_path': target_path,
            'artifact_request': {
                'extension': target_extension,
                'source_name': target_name,
                'source': 'closure_hero_image_composition',
                'target_path': target_path,
            },
        }

    @staticmethod
    def _css_url_quote(value: str) -> str:
        return str(value or '').replace('\\', '/').replace("'", "\\'")

    @classmethod
    def _repair_terminal_hero_css_content(
        cls,
        content: str,
        *,
        image_link: str,
    ) -> tuple[str, str]:
        text = str(content or '')
        link = cls._css_url_quote(image_link)
        if not text.strip() or not link:
            return text, ''
        for match in _TERMINAL_CSS_HERO_BLOCK_RE.finditer(text):
            block = match.group(0)
            if image_link in block or Path(image_link).name in block:
                return text, ''
            body = str(match.group('body') or '')
            for declaration_match in re.finditer(
                r'(?P<prefix>\bbackground(?:-image)?\s*:\s*)'
                r'(?P<value>[^;{}]*)(?P<suffix>;|$)',
                body,
                flags=re.IGNORECASE | re.DOTALL,
            ):
                url_match = _LINK_REBIND_URL_RE.search(str(declaration_match.group('value') or ''))
                if not url_match:
                    continue
                url = str(url_match.group('url') or '').strip()
                if cls._url_is_external_or_empty(url) or _LINK_REBIND_PLACEHOLDER_RE.search(url):
                    url_start = declaration_match.start('value') + url_match.start('url')
                    url_end = declaration_match.start('value') + url_match.end('url')
                    next_body = f'{body[:url_start]}{link}{body[url_end:]}'
                    return (
                        f'{text[:match.start("body")]}{next_body}{text[match.end("body"):]}',
                        'replace_hero_background_url',
                    )

            insertion = (
                "\n    background-image: url('"
                f"{link}"
                "');\n"
                '    background-size: cover;\n'
                '    background-position: center;\n'
                '    background-repeat: no-repeat;'
            )
            next_body = f'{body.rstrip()}{insertion}\n'
            return (
                f'{text[:match.start("body")]}{next_body}{text[match.end("body"):]}',
                'append_hero_background_image',
            )
        return text, ''

    @classmethod
    def _repair_terminal_hero_html_content(
        cls,
        content: str,
        *,
        image_link: str,
    ) -> tuple[str, str]:
        text = str(content or '')
        link = str(image_link or '').replace('\\', '/')
        if not text.strip() or not link:
            return text, ''
        css_declaration = (
            f"background-image: url('{cls._html_attribute_escape(link)}'); "
            'background-size: cover; background-position: center; background-repeat: no-repeat;'
        )
        for match in _TERMINAL_HTML_HERO_BLOCK_RE.finditer(text):
            tag = str(match.group('tag') or '').strip().lower()
            attrs = str(match.group('attrs') or '')
            if tag != 'header' and not _TERMINAL_HERO_LOCAL_IMAGE_SIGNAL_RE.search(attrs):
                continue
            block = match.group(0)
            if image_link in block or Path(image_link).name in block:
                return text, ''
            style_match = re.search(
                r'\bstyle\s*=\s*(?P<quote>[\'"])(?P<value>.*?)(?P=quote)',
                attrs,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if style_match:
                style_value = str(style_match.group('value') or '').strip()
                separator = '; ' if style_value and not style_value.endswith(';') else ' '
                next_style = f'{style_value}{separator}{css_declaration}'.strip()
                next_attrs = (
                    f'{attrs[:style_match.start("value")]}'
                    f'{next_style}'
                    f'{attrs[style_match.end("value"):]}'
                )
                operation = 'append_hero_inline_background_image'
            else:
                next_attrs = f'{attrs} style="{css_declaration}"'
                operation = 'add_hero_inline_background_image'
            return (
                f'{text[:match.start("attrs")]}{next_attrs}{text[match.end("attrs"):]}',
                operation,
            )
        return text, ''

    def _repair_terminal_hero_image_composition(
        self,
        payload: dict[str, Any],
        *,
        request_payload: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return payload
        check = self._terminal_hero_image_composition_open_check(
            payload,
            request_payload=request_payload,
        )
        if not check:
            return payload
        target_path = str(check.get('text_artifact_target_path') or '').strip()
        if not target_path:
            return payload
        image_paths = [
            str(path or '').strip()
            for path in (check.get('missing_image_paths') or [])
            if str(path or '').strip()
        ]
        image_path = next(
            (
                path for path in image_paths
                if Path(path).expanduser().is_file()
            ),
            '',
        )
        if not image_path:
            return payload
        try:
            target = Path(target_path).expanduser()
            if not target.is_file() or target.stat().st_size > 512_000:
                return payload
            original = target.read_text(encoding='utf-8', errors='replace')
        except OSError:
            return payload

        image_link = self._relative_artifact_link(from_path=target_path, to_path=image_path)
        extension = str(
            check.get('text_artifact_extension')
            or Path(target_path).suffix.lower().lstrip('.')
        ).strip().lower()
        if extension == 'css':
            repaired, operation = self._repair_terminal_hero_css_content(
                original,
                image_link=image_link,
            )
        elif extension in {'html', 'htm'}:
            repaired, operation = self._repair_terminal_hero_html_content(
                original,
                image_link=image_link,
            )
        else:
            return payload
        if not operation or repaired == original:
            return payload

        snippets = (
            self._terminal_css_hero_snippets(repaired)
            if extension == 'css'
            else self._terminal_html_hero_snippets(repaired)
        )
        if not any(
            self._terminal_exact_content_has_artifact_link(
                snippet,
                source_path=target_path,
                target_path=image_path,
            )
            for snippet in snippets
        ):
            return payload

        original_issues = text_artifact_syntax_sanity_issues_for_extension(
            extension,
            original,
        )
        repaired_issues = text_artifact_syntax_sanity_issues_for_extension(
            extension,
            repaired,
        )
        if len(repaired_issues) > len(original_issues):
            logging.warning(
                'Skipping hero image composition repair for %s because syntax sanity regressed from %s to %s issue(s)',
                target_path,
                len(original_issues),
                len(repaired_issues),
            )
            return payload

        try:
            target.write_text(repaired, encoding='utf-8')
        except OSError as exc:
            logging.warning('Could not repair hero image composition in %s: %s', target_path, exc)
            return payload

        updated_payload = dict(payload or {})
        late_fill = (
            dict(updated_payload.get('late_fill') or {})
            if isinstance(updated_payload.get('late_fill'), Mapping)
            else {}
        )
        repair_entry = {
            'kind': 'fruth.hero_image_composition_repair',
            'operation': operation,
            'target_path': target_path,
            'target_extension': extension,
            'target_source_name': check.get('text_artifact_source_name'),
            'to_path': image_path,
            'to_token': image_link,
            'status': 'applied',
            'source': 'terminal_hero_image_composition_repair',
        }
        existing_repairs = [
            dict(item)
            for item in (late_fill.get('hero_image_composition_repairs') or [])
            if isinstance(item, Mapping)
        ]
        late_fill['hero_image_composition_repairs'] = [*existing_repairs, repair_entry]
        late_fill['hero_image_composition_repair_status'] = 'applied'
        late_fill['hero_image_composition_repaired_paths'] = [image_path]
        updated_payload['late_fill'] = late_fill
        return updated_payload

    @staticmethod
    def _terminal_composed_site_role_label(
        prompt: str,
        *,
        cohort_content: str,
    ) -> str:
        text = str(prompt or '').strip()
        if not text:
            return ''
        section_roles = [
            role for role in ('hero', 'listening')
            if re.search(rf'\b{role}\b', text, re.IGNORECASE)
        ]
        if len(section_roles) == 1:
            return section_roles[0]
        candidates = [
            str(match.group(1) or match.group(2) or '').strip()
            for match in re.finditer(r'["“]([^"”]{2,80})["”]|\'([^\']{2,80})\'', text)
        ]
        for candidate in candidates:
            if candidate and candidate.lower() in cohort_content.lower():
                return candidate
        role_match = re.search(
            r'(?is)\b(?:interior|portrait|view|scene|image|photo)\s+(?:of|for)\s+(?:the\s+)?'
            r'([^,.;:]{2,80})',
            text,
        )
        if role_match:
            candidate = re.sub(r'\s+', ' ', str(role_match.group(1) or '')).strip(' "\'')
            if candidate and candidate.lower() in cohort_content.lower():
                return candidate
        return ''

    @classmethod
    def _terminal_composed_site_role_is_bound(
        cls,
        *,
        role_label: str,
        image_path: str,
        content_by_path: Mapping[str, str],
    ) -> bool:
        label = str(role_label or '').strip().lower()
        if not label or not image_path:
            return True
        if label in {'hero', 'listening'}:
            for source_path, content in content_by_path.items():
                candidates: list[str] = []
                css_sources: list[str] = []
                if Path(source_path).suffix.lower() in {'.html', '.htm'}:
                    parser = _SectionImageMarkup(label)
                    parser.feed(str(content or ''))
                    candidates = parser.markup
                    css_sources = parser.styles
                elif Path(source_path).suffix.lower() == '.css':
                    css_sources = [str(content or '')]
                for css in css_sources:
                    for selectors, declarations in re.findall(r'(?is)([^{}]+)\{([^{}]*)\}', css):
                        for selector in selectors.split(','):
                            # Sibling combinators and functional pseudo-classes
                            # do not prove that the image belongs inside this role.
                            if re.search(r'[+~()]', selector):
                                continue
                            if re.search(rf'[.#]{label}(?:[-_][\w-]+)?(?![\w-])', selector):
                                candidates.append(declarations)
                if any(cls._terminal_exact_content_has_artifact_link(
                    candidate, source_path=source_path, target_path=image_path,
                ) for candidate in candidates):
                    return True
            return False
        normalized_label = re.sub(r'[^a-z0-9]+', ' ', label).strip()
        for source_path, content in content_by_path.items():
            source = str(content or '')
            lowered = source.lower()
            normalized_source = re.sub(r'[^a-z0-9]+', ' ', lowered)
            for token in cls._terminal_exact_link_tokens_for_artifact(
                source_path=source_path,
                target_path=image_path,
            ):
                if not token:
                    continue
                start = 0
                while True:
                    position = source.find(token, start)
                    if position < 0:
                        break
                    window = source[max(0, position - 1800):position + len(token) + 1800]
                    if label in window.lower():
                        return True
                    normalized_window = re.sub(r'[^a-z0-9]+', ' ', window.lower())
                    if normalized_label and normalized_label in normalized_window:
                        return True
                    start = position + len(token)
            if normalized_label and normalized_label in normalized_source:
                # A CSS nth-child or custom-property binding can keep the
                # human label in a nearby comment while the exact path lives
                # in the same target file.
                if cls._terminal_exact_content_has_artifact_link(
                    source,
                    source_path=source_path,
                    target_path=image_path,
                ):
                    return True
        return False

    @staticmethod
    def _terminal_composed_site_unstyled_image_paths(
        *,
        generated_paths: list[str],
        html_content_by_path: Mapping[str, str],
        css_content_by_path: Mapping[str, str],
        script_content_by_path: Mapping[str, str],
    ) -> list[str]:
        """Require layout evidence for each generated image, on its actual page.

        This is a static binding check, not browser rendering or aesthetic review.
        Parent section sizing and another image's CSS cannot satisfy an img.
        """
        owner = LinkedArtifactMaterialization
        covered: set[str] = set()
        unstyled: set[str] = set()

        def rules(content):
            text = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
            return [
                (selector.strip(), declarations)
                for selectors, declarations in re.findall(r'([^{}]+)\{([^{}]*)\}', text)
                for selector in selectors.split(',')
            ]

        def sizes_image(declarations):
            return any(
                property_name.lower() in {'width', 'max-width', 'height', 'max-height'}
                and value.strip().lower().removesuffix('!important').strip()
                    not in {'', 'auto', 'none', 'initial', 'inherit', 'unset', 'revert'}
                for property_name, value in re.findall(r'(?:^|;)\s*([\w-]+)\s*:([^;]+)', declarations)
            )

        for html_path, content in html_content_by_path.items():
            parser = _SectionImageMarkup('')
            parser.feed(content)
            page_rules = [(html_path, selector, declarations)
                          for style in parser.styles for selector, declarations in rules(style)]
            for css_path, css in css_content_by_path.items():
                if any(
                    lineage[-1][0] == 'link'
                    and 'stylesheet' in str(lineage[-1][1].get('rel') or '').lower().split()
                    and owner._terminal_exact_content_has_artifact_link(
                        str(lineage[-1][1].get('href') or ''),
                        source_path=html_path, target_path=css_path,
                    )
                    for lineage in parser.elements
                ):
                    page_rules.extend((css_path, selector, declarations)
                                      for selector, declarations in rules(css))
            # Preserve the existing layout evidence for script-rendered cards.
            # This check does not execute JS or prove its data/DOM contract;
            # the shared web-binding review owns that. It must never excuse
            # an unstyled concrete img occurrence checked below.
            dynamic_sources = [(html_path, script) for script in re.findall(
                r'(?is)<script\b[^>]*>(.*?)</script\s*>', content,
            )]
            dynamic_sources.extend(
                (script_path, script) for script_path, script in script_content_by_path.items()
                if any(
                    lineage[-1][0] == 'script'
                    and owner._terminal_exact_content_has_artifact_link(
                        str(lineage[-1][1].get('src') or ''),
                        source_path=html_path, target_path=script_path,
                    ) for lineage in parser.elements
                )
            )
            if any(sizes_image(css) and re.search(r'(?i)(?:img\b|image|photo|media|gallery|card)', selector)
                   for _, selector, css in page_rules):
                for script_path, script in dynamic_sources:
                    if not re.search(r'''(?i)<img\b|createElement\(\s*['"]img['"]''', script):
                        continue
                    covered.update(path for path in generated_paths
                                   if owner._terminal_exact_content_has_artifact_link(
                                       script, source_path=script_path, target_path=path,
                                   ))
            for lineage in parser.elements:
                tag, attrs = lineage[-1]
                bound_styles = [(html_path, str(attrs.get('style') or ''))]
                bound_styles.extend(
                    (path, declarations) for path, selector, declarations in page_rules
                    if parser.selector_matches(selector, lineage)
                )
                if tag == 'img':
                    sources = ' '.join(str(attrs.get(k) or '') for k in ('src', 'srcset'))
                    # A picture source is displayed by its sibling img element.
                    if len(lineage) > 1 and lineage[-2][0] == 'picture':
                        sources += ' ' + ' '.join(
                            str(other[-1][1].get('srcset') or '')
                            for other in parser.elements
                            if len(other) > 1 and other[-2] is lineage[-2] and other[-1][0] == 'source'
                        )
                    for image_path in generated_paths:
                        if owner._terminal_exact_content_has_artifact_link(
                            sources, source_path=html_path, target_path=image_path,
                        ):
                            covered.add(image_path)
                            if not any(sizes_image(css) for _, css in bound_styles):
                                unstyled.add(image_path)
                for style_path, declarations in bound_styles:
                    backgrounds = re.findall(
                        r'(?:^|;)\s*background(?:-image)?\s*:([^;]+)', declarations, re.IGNORECASE,
                    )
                    for image_path in generated_paths:
                        if any(owner._terminal_exact_content_has_artifact_link(
                            background, source_path=style_path, target_path=image_path,
                        ) for background in backgrounds):
                            covered.add(image_path)
        return [path for path in generated_paths if path in unstyled or path not in covered]

    def _terminal_composed_site_image_composition_open_checks(
        self,
        payload: Mapping[str, Any],
    ) -> Optional[list[dict[str, Any]]]:
        records = self._collect_link_rebind_artifact_records(payload)
        text_records = self._unique_artifact_records_by_path(
            [
                record
                for record in records
                if str(record.get('type') or record.get('kind') or '').strip().lower() == 'text'
                and branch_result_contracts._artifact_record_extension(record) in _LINK_REBIND_TEXT_EXTENSIONS
                and branch_result_contracts._artifact_record_path(record)
            ]
        )
        html_records = [
            record
            for record in text_records
            if branch_result_contracts._artifact_record_extension(record) in {'html', 'htm'}
        ]
        css_records = [
            record
            for record in text_records
            if branch_result_contracts._artifact_record_extension(record) == 'css'
        ]
        script_records = [
            record
            for record in text_records
            if branch_result_contracts._artifact_record_extension(record) in {'js', 'mjs', 'cjs'}
        ]
        # Every generated HTML cohort uses the same closure/repair owner,
        # including single pages with embedded CSS and one generated image.
        if not html_records:
            return None

        late_fill = payload.get('late_fill') if isinstance(payload.get('late_fill'), Mapping) else {}
        image_branch_ids = {
            self.branch_id(item)
            for item in [
                *(late_fill.get('completed_branches') or []),
                *(late_fill.get('fill_results') or []),
            ]
            if isinstance(item, Mapping)
            and (
                self.normalize_capability(item.get('capability')) == self.image_generation_capability()
                or str(item.get('output_type') or '').strip().lower() == 'image'
                or str(item.get('saved_image_path') or '').strip()
            )
            and self.branch_id(item)
        }
        if not image_branch_ids:
            return None
        image_records = self._unique_artifact_records_by_path(
            [
                record
                for record in records
                if (
                    str(record.get('type') or record.get('kind') or '').strip().lower() == 'image'
                    or branch_result_contracts._artifact_record_extension(record) in _LINK_REBIND_IMAGE_EXTENSIONS
                )
                and branch_result_contracts._artifact_record_path(record)
            ]
        )
        generated_image_records: list[dict[str, Any]] = []
        for record in image_records:
            record_branch_id = self.branch_id(record)
            if record_branch_id and record_branch_id in image_branch_ids:
                generated_image_records.append(record)
            elif not record_branch_id and len(image_records) == len(image_branch_ids):
                generated_image_records.append(record)
        if not generated_image_records:
            generated_image_records = image_records
        generated_image_records.sort(key=self._image_artifact_record_sort_key)
        if not generated_image_records:
            return None

        content_by_path: dict[str, str] = {}
        for record in text_records:
            path = branch_result_contracts._artifact_record_path(record)
            content = self._terminal_materialization_text_record_content(record)
            if path and content:
                content_by_path[path] = content
        if not content_by_path:
            return None
        generated_paths = [
            branch_result_contracts._artifact_record_path(record)
            for record in generated_image_records
            if branch_result_contracts._artifact_record_path(record)
        ]
        represented_paths = {
            image_path
            for image_path in generated_paths
            if any(
                self._terminal_exact_content_has_artifact_link(
                    content,
                    source_path=source_path,
                    target_path=image_path,
                )
                for source_path, content in content_by_path.items()
            )
        }
        missing_paths = [path for path in generated_paths if path not in represented_paths]
        detached_marker_present = any(
            'data-fruth-repair="composed-page-image-representation"' in content
            or "data-fruth-repair='composed-page-image-representation'" in content
            or 'class="fruth-generated-media"' in content
            or "class='fruth-generated-media'" in content
            for record in html_records
            for content in [content_by_path.get(branch_result_contracts._artifact_record_path(record), '')]
        )
        cohort_content = '\n'.join(content_by_path.values())
        batch_prompts = [
            str(item or '').strip()
            for item in (late_fill.get('batch_prompts') or [])
            if str(item or '').strip()
        ]
        image_assignments: list[dict[str, Any]] = []
        role_binding_defects: list[dict[str, str]] = []
        for index, image_path in enumerate(generated_paths):
            prompt = batch_prompts[index] if index < len(batch_prompts) else ''
            role_label = self._terminal_composed_site_role_label(
                prompt,
                cohort_content=cohort_content,
            )
            assignment = {
                'slot': index + 1,
                'path': image_path,
                'prompt': prompt,
                'role_label': role_label,
            }
            image_assignments.append(assignment)
            if role_label and not self._terminal_composed_site_role_is_bound(
                role_label=role_label,
                image_path=image_path,
                content_by_path=content_by_path,
            ):
                role_binding_defects.append(
                    {'path': image_path, 'role_label': role_label}
                )
        unstyled_image_paths = self._terminal_composed_site_unstyled_image_paths(
            generated_paths=generated_paths,
            html_content_by_path={branch_result_contracts._artifact_record_path(record): content_by_path.get(
                branch_result_contracts._artifact_record_path(record), '') for record in html_records},
            css_content_by_path={branch_result_contracts._artifact_record_path(record): content_by_path.get(
                branch_result_contracts._artifact_record_path(record), '') for record in css_records},
            script_content_by_path={branch_result_contracts._artifact_record_path(record): content_by_path.get(
                branch_result_contracts._artifact_record_path(record), '') for record in script_records},
        )
        layout_binding_defect = bool(unstyled_image_paths)
        if not (
            missing_paths
            or detached_marker_present
            or role_binding_defects
            or layout_binding_defect
        ):
            return []

        target_records = [*html_records, *css_records, *script_records]
        cohort_snapshots: list[str] = []
        remaining_snapshot_budget = 180_000
        cohort_snapshot_truncated = False
        for record in target_records:
            path = branch_result_contracts._artifact_record_path(record)
            content = content_by_path.get(path, '')
            allowance = min(60_000, max(0, remaining_snapshot_budget))
            snapshot = content[:allowance]
            if len(snapshot) < len(content):
                cohort_snapshot_truncated = True
                snapshot = f'{snapshot.rstrip()}\n[cohort snapshot truncated]'
            remaining_snapshot_budget -= min(len(content), allowance)
            cohort_snapshots.extend(
                [
                    f'--- COHORT FILE {path} START ---',
                    snapshot,
                    f'--- COHORT FILE {path} END ---',
                ]
            )
        assignment_lines: list[str] = []
        for assignment in image_assignments:
            role_text = (
                f'role label: {assignment["role_label"]}'
                if assignment.get('role_label')
                else 'role label: use the ordered prompt as role evidence'
            )
            assignment_lines.extend(
                [
                    f'- Image slot {assignment["slot"]}: {assignment["path"]}',
                    f'  {role_text}',
                    f'  generation prompt: {assignment["prompt"] or "unavailable"}',
                ]
            )
        defect_lines = [
            f'- Missing concrete image references: {len(missing_paths)}',
            f'- Detached runtime repair section present: {str(detached_marker_present).lower()}',
            f'- Unbound named image roles: {len(role_binding_defects)}',
            *(f'- Image {item["path"]} must be inside the {item["role_label"]} section or its CSS background.'
              for item in role_binding_defects),
            f'- Image layout CSS missing: {str(layout_binding_defect).lower()}',
            *(f'- Image lacks bound sizing/layout: {path}' for path in unstyled_image_paths),
        ]
        image_phase_ids = list(
            dict.fromkeys(
                str(record.get('phase_id') or record.get('branch_id') or '').strip()
                for record in generated_image_records
                if str(record.get('phase_id') or record.get('branch_id') or '').strip()
            )
        )
        input_refs = [
            {
                'kind': 'artifact',
                'artifact_ref': record.get('artifact_ref') or record.get('ref'),
                'path': branch_result_contracts._artifact_record_path(record),
                'role': 'generated_image_role_evidence',
            }
            for record in generated_image_records
        ]
        input_refs.extend(
            {
                'kind': 'artifact',
                'artifact_ref': record.get('artifact_ref') or record.get('ref'),
                'path': branch_result_contracts._artifact_record_path(record),
                'role': 'composed_site_cohort_snapshot',
            }
            for record in target_records
        )
        checks: list[dict[str, Any]] = []
        for record in target_records:
            target_path = branch_result_contracts._artifact_record_path(record)
            target_extension = branch_result_contracts._artifact_record_extension(record)
            target_name = branch_result_contracts._artifact_record_source_name(record) or Path(target_path).stem
            target_content = content_by_path.get(target_path, '')
            bounded_target_content = target_content
            if len(bounded_target_content) > 90_000:
                bounded_target_content = (
                    f'{bounded_target_content[:90_000].rstrip()}\n[target content truncated for repair prompt size]'
                )
            if target_extension in {'html', 'htm'}:
                target_instruction = (
                    'Keep this page in its existing role. Add or preserve semantic hooks and direct image markup '
                    'only where this page owns it. For embedded styles, provide responsive image sizing and cropping. '
                    'Remove any Fruth detached repair section from this target. '
                    'If JavaScript owns repeated cards, keep the shell compatible with that renderer.'
                )
                if detached_marker_present:
                    target_instruction += (
                        ' Delete the entire section marked class="fruth-generated-media" or '
                        'data-fruth-repair="composed-page-image-representation", including its wrapper. '
                        'Keep its required images only in their assigned site sections.'
                    )
                for defect in role_binding_defects:
                    label = defect['role_label']
                    if label in {'hero', 'listening'} and re.search(
                        rf'(?i)\b(?:class|id)\s*=\s*[\'"][^\'"]*\b{label}\b', target_content,
                    ):
                        link = self._relative_artifact_link(from_path=target_path, to_path=defect['path'])
                        target_instruction += (
                            f' Inside the existing {label} element, insert an img element '
                            f'whose src is "{link}". Preserve its existing text and controls.'
                        )
            elif target_extension == 'css':
                target_instruction = (
                    'Give the existing image-bearing hero, cards, galleries, or media regions a deliberate '
                    'responsive layout. Style the exact hooks used by the cohort; include stable sizing and '
                    'cropping such as aspect-ratio/object-fit where appropriate.'
                )
                if layout_binding_defect:
                    target_instruction += (
                        ' Add an img sizing rule, for example img {max-width:100%;height:auto;}, '
                        'or equivalent rules for the existing image selectors. A flex/grid rule '
                        'on the surrounding section alone does not constrain an oversized img.'
                    )
            else:
                target_instruction = (
                    'Bind the ordered image paths to the existing semantic data/items and rendered markup. '
                    'Preserve interaction, selection, calculations, and unrelated behavior.'
                )
            content_payload = '\n'.join(
                [
                    f'Target text artifact: {target_path}',
                    'Composed-site image-role and layout repair.',
                    'Verified defects:',
                    *defect_lines,
                    'Ordered generated-image assignments:',
                    *assignment_lines,
                    '<fruth_promoted_context>',
                    'Read-only cohort snapshots for cross-file consistency:',
                    *cohort_snapshots,
                    'Current saved target file content:',
                    '--- CURRENT SAVED TARGET START ---',
                    bounded_target_content,
                    '--- CURRENT SAVED TARGET END ---',
                    '</fruth_promoted_context>',
                    '<fruth_bounded_task>',
                    f'Repair only {target_path} ({target_extension}).',
                    'Correct these defects in place; copying the defective snapshot is not a repair:',
                    *defect_lines,
                    f'Target-specific instruction: {target_instruction}',
                    f'Return exactly one {target_extension} fenced block with the complete replacement for {Path(target_path).name}.',
                    'Do not create a new sibling file. Do not rewrite another cohort file from this branch.',
                    'Do not append a catch-all image dump or a fruth-generated-media detached repair section.',
                    'Preserve existing valid local links and use concrete relative paths from this target when it references an image.',
                    '</fruth_bounded_task>',
                ]
            ).strip()
            target_token = hashlib.sha256(target_path.encode('utf-8')).hexdigest()[:12]
            branch_id = (
                str(record.get('branch_id') or record.get('phase_id') or '').strip()
                or f'branch-composed-site-image-repair-{target_token}'
            )
            phase_id = (
                str(record.get('phase_id') or record.get('branch_id') or '').strip()
                or branch_id
            )
            execution_contract = {
                'kind': 'fruth.composed_site_image_cohort_repair_contract',
                'repair_mode': 'composed_site_image_cohort_target',
                'execution_scope': 'target_artifact_snapshot_only',
                'branch_id': branch_id,
                'phase_id': phase_id,
                'capability': 'chat',
                'output_type': 'text',
                'target_path': target_path,
                'target_extension': target_extension,
                'cohort_paths': [branch_result_contracts._artifact_record_path(item) for item in target_records],
                'generated_image_paths': generated_paths,
                'image_assignments': image_assignments,
                'cohort_snapshot_truncated': cohort_snapshot_truncated,
                'root_prompt_replay_allowed': False,
                'sibling_write_allowed': False,
            }
            checks.append(
                {
                    'check_kind': 'composed_page_image_representation',
                    'status': 'pending',
                    'evidence': 'composed_site_image_role_or_layout_unmet',
                    'reason': 'composed site image roles and layout are not yet proven by final saved files',
                    'capability': 'chat',
                    'output_type': 'text',
                    'role': 'linked_artifact_binding_review',
                    'branch_id': branch_id,
                    'phase_id': phase_id,
                    'repair_owner_branch_id': str(record.get('branch_id') or '').strip() or None,
                    'repair_owner_phase_id': str(record.get('phase_id') or '').strip() or None,
                    'depends_on': image_phase_ids or None,
                    'input_refs': input_refs,
                    'execution_contract': execution_contract,
                    'output_contract': {
                        'output_type': 'text',
                        'required': True,
                        'target_path': target_path,
                        'fulfillment_policy': 'target_bound_saved_artifact_replacement',
                    },
                    'review_criteria': [
                        'uses_dependency_evidence',
                        'does_not_restart_root_request',
                    ],
                    'requires_artifact': True,
                    'repair_action': RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
                    'recovery_action': RECOVERY_ACTION_REBIND_DEPENDENCY_EVIDENCE,
                    'repair_action_reason': 'repair the existing composed-site file cohort against ordered image-role evidence',
                    'content_payload': content_payload,
                    'content_payload_source': 'closure_composed_site_image_composition',
                    'stage_direction': 'materialize_requested_text_artifact',
                    'generated_image_count': len(generated_paths),
                    'represented_image_count': len(represented_paths),
                    'missing_image_count': len(missing_paths),
                    'generated_image_paths': generated_paths,
                    'missing_image_paths': missing_paths,
                    'represented_image_paths': sorted(represented_paths),
                    'image_assignments': image_assignments,
                    'role_binding_defects': role_binding_defects,
                    'detached_repair_section_present': detached_marker_present,
                    'layout_binding_defect': layout_binding_defect,
                    'unstyled_image_paths': unstyled_image_paths,
                    'text_artifact_extension': target_extension,
                    'text_artifact_source_name': target_name,
                    'text_artifact_source': 'closure_composed_site_image_composition',
                    'text_artifact_target_path': target_path,
                    'repair_scope': 'composed_site_cohort_target',
                    'resource_class': 'local_text_io',
                    'dependency_policy': 'target_artifact_snapshot_only',
                    'artifact_request': {
                        'extension': target_extension,
                        'source_name': target_name,
                        'source': 'closure_composed_site_image_composition',
                        'target_path': target_path,
                    },
                }
            )
        return checks

    @staticmethod
    def _html_attribute_escape(value: str) -> str:
        return (
            str(value or '')
            .replace('&', '&amp;')
            .replace('"', '&quot;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
        )

