"""Validate and select the two renditions of one cached briefing."""
import json
import re

from .llm_client import LLMUnavailable


def parse_bilingual_briefing(text: str) -> dict[str, str]:
    text = text.strip()
    if text.startswith('```'):
        text = '\n'.join(text.splitlines()[1:-1])
    try:
        value = json.loads(text)
        if not isinstance(value, dict) or any(not isinstance(value.get(key), str) or not value[key].strip()
                                              for key in ('body', 'body_en')):
            raise ValueError('Both briefing languages are required')
        references = [set(re.findall(r'\[(\d+)\]', value[key])) for key in ('body', 'body_en')]
        if references[0] != references[1]:
            raise ValueError('The two renditions must preserve the same source references')
    except (ValueError, TypeError) as error:
        raise LLMUnavailable('The model did not return a complete bilingual briefing; previous cache retained') from error
    return {key: value[key].strip() for key in ('body', 'body_en')}


def select_briefing(cached, language: str):
    if not isinstance(cached, dict):
        return None
    selected = dict(cached)
    if language == 'en':
        selected['body'] = cached.get('body_en') or ''
    selected['language'] = language
    return selected
