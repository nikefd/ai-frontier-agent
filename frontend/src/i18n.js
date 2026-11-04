// Only static UI messages are translated. Interpolated article text, notes and
// user input are inserted verbatim, preserving the existing escaping boundary.
import english from './messages.en.json' with { type: 'json' };
export function resolveLanguage(query, saved, browser) {
  for (const value of [query, saved, browser]) {
    const base = String(value || '').toLowerCase().split('-')[0];
    if (base === 'zh' || base === 'en') return base;
  }
  return 'en';
}
let saved;
try { saved = localStorage.getItem('aif_language'); } catch { /* storage may be disabled */ }
export const language = resolveLanguage(new URLSearchParams(location.search).get('lang'), saved, navigator.language);
export const formatCount = (count, noun) => `${count} ${noun}${Number(count) === 1 ? '' : 's'}`;
export const isEnglish = () => language === 'en';
export function uiText(text) { return language === 'en' ? (english[text] ?? text) : text; }
export function uiTemplate(strings, ...values) {
  const key = strings.map((part, index) => part + (index < values.length ? `{${index}}` : '')).join('');
  return uiText(key).replace(/\{(\d+)\}/g, (match, index) => index < values.length ? String(values[index]) : match);
}
export function initI18n() {
  document.documentElement.lang = language === 'en' ? 'en' : 'zh-CN';
  document.title = uiText('AI 前沿');
  // Once, before data loads: only the static HTML shell. Dynamic views call
  // uiText/uiTemplate directly; there is no observer touching user content.
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT), nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    if (node.parentElement.closest('script,style,[data-language-picker]')) continue;
    const key = node.textContent.trim();
    if (key) node.textContent = node.textContent.replace(key, uiText(key));
  }
  for (const element of document.querySelectorAll('[title],[placeholder],[aria-label]')) {
    for (const attr of ['title', 'placeholder', 'aria-label']) {
      if (element.hasAttribute(attr)) element.setAttribute(attr, uiText(element.getAttribute(attr)));
    }
  }
  const picker = document.querySelector('#language-picker');
  picker.value = language;
  picker.addEventListener('change', () => {
    try { localStorage.setItem('aif_language', picker.value); } catch { /* URL still works */ }
    const url = new URL(location.href); url.searchParams.set('lang', picker.value); location.assign(url.href);
  });
  document.querySelectorAll('a[href="/rss/digest.xml"],link[rel="alternate"]').forEach(link => { link.href = '/rss/digest.xml?lang=' + language; });
}
