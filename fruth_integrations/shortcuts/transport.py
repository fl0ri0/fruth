"""PCC loopback wire validation used by Fruth's ordinary chat transport owner."""

import json


class PCCText(str):
    def __new__(cls, content, evidence):
        value = super().__new__(cls, content)
        value.pcc_execution = evidence
        return value


def chat_payload(model, messages, *, timeout_sec, stream=False):
    if model != 'auto':
        raise ValueError('Apple PCC requires the auto model.')
    return {'model': model, 'messages': messages, 'stream': stream, 'fruth_timeout_sec': timeout_sec}


def validate_response(data):
    if not isinstance(data, dict) or data.get('error'):
        raise ValueError('PCC returned an error or malformed response.')
    choices = data.get('choices')
    if data.get('model') != 'auto' or not isinstance(choices, list) or len(choices) != 1:
        raise ValueError('PCC returned an unexpected model or choice.')
    choice = choices[0]
    if not isinstance(choice, dict) or choice.get('finish_reason') != 'stop':
        raise ValueError('PCC response is incomplete.')
    message = choice.get('message') or {}
    if not isinstance(message, dict):
        raise ValueError('Invalid PCC message.')
    content = message.get('content')
    evidence = data.get('pcc_execution') or {}
    if not isinstance(evidence, dict):
        raise ValueError('Invalid PCC execution evidence.')
    if (message.get('refusal') or not isinstance(content, str) or not content.strip()
            or evidence.get('status') != 'completed' or evidence.get('model') not in {'cloud', 'cloud-pro'}):
        raise ValueError('PCC completed without verified text execution.')
    return PCCText(content, evidence)


def stream_deltas(response):
    """Buffer until the exact completion and DONE markers arrive."""
    content = ''
    finished = False
    evidence = None
    try:
        for raw in response.iter_lines(decode_unicode=False):
            line = raw.decode('utf-8') if isinstance(raw, bytes) else raw
            if not line or line.startswith(('event:', ':')):
                continue
            if not line.startswith('data:'):
                raise ValueError('Malformed PCC stream framing.')
            value = line[5:].strip()
            if value == '[DONE]':
                data = {'model': 'auto', 'choices': [{'message': {'content': content},
                        'finish_reason': 'stop' if finished else None}], 'pcc_execution': evidence}
                answer = validate_response(data)
                response.fruth_pcc_execution = answer.pcc_execution
                yield answer
                return
            data = json.loads(value)
            if not isinstance(data, dict) or data.get('model') != 'auto' or data.get('error'):
                raise ValueError('Invalid PCC stream event.')
            choices = data.get('choices')
            if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                raise ValueError('Invalid PCC stream choice.')
            choice = choices[0]
            if finished or choice.get('finish_reason') not in (None, 'stop'):
                raise ValueError('Incomplete or repeated PCC completion.')
            delta = choice.get('delta') or {}
            if not isinstance(delta, dict):
                raise ValueError('Invalid PCC stream delta.')
            text = delta.get('content', '')
            if delta.get('refusal') or not isinstance(text, str):
                raise ValueError('PCC refusal or invalid delta.')
            content += text
            current_evidence = data.get('pcc_execution')
            if evidence is not None and current_evidence != evidence:
                raise ValueError('PCC execution identity changed during response.')
            evidence = current_evidence
            finished = choice.get('finish_reason') == 'stop'
        raise ValueError('PCC disconnected before completion; no partial result accepted.')
    finally:
        response.close()
