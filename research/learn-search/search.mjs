// Isolated reproduction of article-search edge cases, not production code.
export function searchArticles(rows, query) {
  const needle = query.trim().toLowerCase();
  return rows.filter(row => `${row.title || ''} ${row.summary || ''}`.toLowerCase().includes(needle));
}
