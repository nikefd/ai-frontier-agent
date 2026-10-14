// Safe Markdown rendering for every LLM/user-controlled content surface.
import DOMPurify from 'dompurify';
import { marked } from 'marked';

const PURIFY_OPTIONS = {
  USE_PROFILES: { html: true },
  ALLOW_DATA_ATTR: false,
  SANITIZE_NAMED_PROPS: true,
  FORBID_TAGS: [
    'base', 'button', 'embed', 'form', 'frame', 'frameset', 'iframe', 'img',
    'input', 'link', 'math', 'meta', 'object', 'script', 'select', 'style',
    'svg', 'textarea',
  ],
  FORBID_ATTR: ['style'],
};

function sanitize(html) {
  return DOMPurify.sanitize(html, PURIFY_OPTIONS);
}

export function renderMarkdown(text) {
  return sanitize(marked.parse(text || ''));
}

export function renderMarkdownInline(text) {
  return sanitize(marked.parseInline(text || ''));
}
