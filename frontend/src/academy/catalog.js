import models from './models.json' with { type: 'json' };
export { models };
export const staleRecord = (record, now = Date.now()) => now - Date.parse(record.verified_on + 'T00:00:00Z') > 30 * 86400000;
export function filterModels(query = '', provider = '', task = '', access = '') {
  const needle = query.trim().toLowerCase();
  return models.filter(m => (!needle || `${m.name} ${m.provider} ${m.family}`.toLowerCase().includes(needle)) && (!provider || m.provider === provider) && (!task || m.task === task) && (!access || m.access === access));
}
export function relatedModels(text) {
  const normalized = String(text || '').toLowerCase();
  return models.filter(m => normalized.includes(m.name.toLowerCase())).slice(0, 3);
}
const progressKey = 'aif_academy_progress_v1';
let volatileProgress = {};
export function readProgress() {
  try { const value = JSON.parse(localStorage.getItem(progressKey) || '{}'); if (value && typeof value === 'object' && !Array.isArray(value)) return value; } catch { /* storage unavailable */ }
  return volatileProgress;
}
export function saveCompletion(id) {
  volatileProgress = { ...readProgress(), [id]: true };
  try { localStorage.setItem(progressKey, JSON.stringify(volatileProgress)); return true; } catch { return false; }
}
export function clearProgress() { volatileProgress = {}; try { localStorage.removeItem(progressKey); } catch { /* no persistence */ } }
