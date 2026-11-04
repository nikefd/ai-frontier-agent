"""Request-local output language; scheduled jobs retain the Chinese default."""
from contextlib import contextmanager
from contextvars import ContextVar

_language = ContextVar('aif_language', default='zh')


def current_language() -> str:
    return _language.get()


@contextmanager
def output_language(language: str):
    token = _language.set('en' if language == 'en' else 'zh')
    try:
        yield
    finally:
        _language.reset(token)


def localized_messages(messages: list[dict], language: str | None = None) -> list[dict]:
    if (language or current_language()) != 'en':
        return messages
    instruction = ('Write all human-readable answers, titles, explanations and JSON text values in English. '
                   'Keep the requested JSON keys, identifiers, URLs, enum values and response schema unchanged. '
                   'This language preference overrides instructions to write Chinese. Do not translate quoted source titles unnecessarily.')
    result = [dict(message) for message in messages]
    if result and result[0].get('role') == 'system':
        result[0]['content'] = str(result[0].get('content') or '') + '\n\n' + instruction
    else:
        result.insert(0, {'role': 'system', 'content': instruction})
    return result


def localized_text(chinese: str, english: str) -> str:
    return english if current_language() == 'en' else chinese
