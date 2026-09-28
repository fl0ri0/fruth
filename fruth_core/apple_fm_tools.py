"""Bounded Apple CLI image tools, separate from the fm serve HTTP transport."""

from __future__ import annotations

import base64
import hashlib
import json
import platform
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from fruth_runtime.child_process_env import sanitized_child_process_env

APPLE_FM_IMAGE_TOOL_MODES = {'apple_ocr': ('ocr', 'getText'),
                             'apple_barcode': ('barcode', 'readBarcodes')}
_IMAGE_LABEL = 'input'


class AppleFMImageToolError(RuntimeError):
    """An enabled tool without a verified result is not successful recognition."""


def _fm_binary():
    return shutil.which('fm') if platform.system() == 'Darwin' else None


@lru_cache(maxsize=4)
def _probe_tools(binary, modified_ns):
    del modified_ns  # Invalidate discovery when the installed executable changes.
    try:
        result = subprocess.run(
            [binary, 'respond', '--help'], capture_output=True, text=True,
            encoding='utf-8', errors='replace', stdin=subprocess.DEVNULL,
            timeout=5, env=sanitized_child_process_env(),
        )
        if result.returncode:
            return ()
        help_text = result.stdout
        if not all(flag in help_text for flag in ('--tool', '--image', '--label', '--save-transcript')):
            return ()
        tool_help = re.search(r'--tool\b(.*?)(?=\n\s+--|\Z)', help_text, re.S)
        return tuple(mode for mode, (name, _) in APPLE_FM_IMAGE_TOOL_MODES.items()
                     if tool_help and re.search(r'\b' + name + r'\b', tool_help.group(1)))
    except (OSError, subprocess.SubprocessError):
        return ()


def available_apple_fm_image_tool_modes():
    """Read-only, cached CLI capability observation; no license or asset mutation."""
    binary = _fm_binary()
    try:
        return list(_probe_tools(binary, Path(binary).stat().st_mtime_ns)) if binary else []
    except OSError:
        return []


def _image_bytes(encoded):
    if not isinstance(encoded, str):
        raise ValueError('Apple image tools require an inline image.')
    if encoded.startswith('data:'):
        header, encoded = encoded.split(',', 1)
        if not header.startswith('data:image/') or not header.endswith(';base64'):
            raise ValueError('Apple image tools require a base64 image.')
    raw = base64.b64decode(encoded, validate=True)
    if not raw:
        raise ValueError('Apple image tools require a non-empty image.')
    return raw


def parse_image_tool_transcript(document, *, mode, source_bytes, instance_id):
    """Validate actual native tool invocation/result linkage, ignoring final model prose."""
    expected_name = APPLE_FM_IMAGE_TOOL_MODES[mode][1]
    try:
        wrapper = document['transcript']
        if (document['modelName'] != 'system' or wrapper['version'] != '1.1'
                or wrapper['type'] != 'FoundationModels.Transcript'):
            raise ValueError('Unsupported transcript format or model.')
        entries = wrapper['transcript']['entries']
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise ValueError('Invalid transcript entries.')
        images, calls, results = [], {}, []
        assets = set()
        for entry in entries:
            if entry.get('error'):
                raise ValueError('Transcript contains an error.')
            for asset in (entry.get('metadata') or {}).get('assetIDs', []):
                if isinstance(asset, str):
                    assets.add(asset)
            for part in entry.get('contents', []):
                if part.get('type') == 'attachment':
                    attachment = part['attachment']
                    if (entry.get('role') != 'user' or attachment.get('type') != 'image'
                            or attachment.get('label') != _IMAGE_LABEL):
                        raise ValueError('Unexpected transcript attachment.')
                    images.append(_image_bytes(attachment['data']))
            for call in entry.get('toolCalls', []):
                if (entry.get('role') != 'response' or call['name'] != expected_name
                        or call['id'] in calls or len(images) != 1
                        or json.loads(call['arguments']) != {'image': {'attachmentLabel': _IMAGE_LABEL}}):
                    raise ValueError('Tool call does not match the requested tool and image.')
                calls[call['id']] = call
            if entry.get('role') == 'tool':
                call_id = entry['toolCallID']
                if call_id not in calls or entry['toolName'] != expected_name:
                    raise ValueError('Unmatched tool result.')
                parts = entry['contents']
                if not isinstance(parts, list) or any(
                    part.get('type') != 'text' or not isinstance(part.get('text'), str)
                    for part in parts
                ):
                    raise ValueError('Unsupported tool result content.')
                results.append({'tool_call_id': call_id, 'tool_name': expected_name,
                                'text': '\n'.join(part['text'] for part in parts)})
        if len(images) != 1 or len(calls) != 1 or len(results) != 1:
            raise ValueError('Expected one image, one tool call and its result; AFM may have skipped or repeated the tool.')
        result = results[0]
        result['empty'] = not result['text'].strip()
        result['sha256'] = hashlib.sha256(result['text'].encode('utf-8')).hexdigest()
        source_digest = hashlib.sha256(source_bytes).hexdigest()
        attachment_digest = hashlib.sha256(images[0]).hexdigest()
        evidence = {
            'kind': 'fruth.apple_fm_image_tool_evidence', 'version': 1,
            'authority': 'runtime_fm_cli_transcript_validation', 'status': 'verified',
            'transport': 'fm.respond', 'api_model': 'system', 'instance_id': instance_id,
            'execution_scope': 'local_cli_session', 'mode': mode,
            'source_image_sha256': source_digest, 'source_size_bytes': len(source_bytes),
            'attachment_label': _IMAGE_LABEL, 'attachment_sha256': attachment_digest,
            'attachment_size_bytes': len(images[0]),
            'image_reencoded': source_digest != attachment_digest,
            'reported_asset_ids': sorted(assets), 'result': result,
        }
        return result['text'], evidence
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise AppleFMImageToolError(f'Apple image tool execution was not verified: {exc}') from exc


def run_apple_fm_image_tool(*, mode, image_b64, instance_id, timeout_sec):
    if mode not in APPLE_FM_IMAGE_TOOL_MODES:
        raise ValueError('Unknown Apple image tool mode.')
    source = _image_bytes(image_b64)
    if mode not in available_apple_fm_image_tool_modes():
        raise AppleFMImageToolError('The installed fm respond CLI does not advertise this image tool.')
    tool, function = APPLE_FM_IMAGE_TOOL_MODES[mode]
    instructions = (f'Always use the {function} tool to read images. '
                    f'The image is labeled {_IMAGE_LABEL}.')
    prompt = ('What does the image say?' if tool == 'ocr' else
              f'Read any barcode in the image using {function}. The image label is {_IMAGE_LABEL}.')
    # One private session, no resume, retries, model fallback or final-prose substitution.
    with tempfile.TemporaryDirectory(prefix='fruth-apple-image-tool-') as directory:
        image_path = Path(directory) / 'input.image'
        transcript_path = Path(directory) / 'transcript.json'
        image_path.write_bytes(source)
        command = [_fm_binary(), 'respond', '--model', 'system', '--tool', tool,
                   '--instructions', instructions, '--image', str(image_path),
                   '--label', _IMAGE_LABEL, '--no-stream',
                   '--save-transcript', str(transcript_path), '--text', prompt]
        try:
            completed = subprocess.run(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                timeout=timeout_sec, env=sanitized_child_process_env(),
            )
        except subprocess.TimeoutExpired as exc:
            # subprocess.run kills and reaps its own child on timeout.
            raise AppleFMImageToolError('Apple image tool timed out; no verified result was returned.') from exc
        except OSError as exc:
            raise AppleFMImageToolError('Could not execute the installed Apple image tool.') from exc
        if completed.returncode:
            raise AppleFMImageToolError(
                f'Apple {tool} tool failed (fm exit {completed.returncode}); no verified result was returned.'
            )
        try:
            document = json.loads(transcript_path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise AppleFMImageToolError('Apple image tool did not save a valid execution transcript.') from exc
        return parse_image_tool_transcript(document, mode=mode, source_bytes=source, instance_id=instance_id)
