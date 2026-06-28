"""Memory layer — materialized memory (panels), episodic memory (journal), and
conversation memory (conversations + messages), all in one SQLite file.

Design:
- A separate UI db keeps agent memory physically isolated from the host's
  business data, so the agent's write permission is naturally confined here.
- Panels store *recipes* (declarative specs), not snapshots, so opening a page
  always recomputes from live data.
- The journal is append-only; the harness writes agent actions, the host writes
  user actions. A summary can be injected into the system prompt for recall.

This module is optional: a host with no dashboard can ignore panels entirely and
use only conversations + journal, or skip memory altogether.
"""
import json
import sqlite3
import time
from pathlib import Path

from .expr import is_safe_expr, safe_eval

VIZ_TYPES = {"metric-card", "table", "line-chart", "bar-chart", "markdown"}
REFRESH_TYPES = {"live", "daily", "static"}


class Memory:
    """Owns one ui.db and all CRUD over panels / journal / conversations.

    ``builtin_panels``: list of (id, title, tab, note) the host pre-registers so
    the agent's memory matches what the page actually renders. ``transforms``: a
    dict of scalar post-processors {name: fn(data) -> dict} for metric cards.
    """

    def __init__(self, db_path, *, builtin_panels=None, transforms=None,
                 tool_names=None):
        self.db_path = Path(db_path)
        self.builtin_panels = builtin_panels or []
        self.transforms = dict(transforms or {})
        # tool names allowed as a panel data source (for spec validation)
        self.tool_names = set(tool_names or [])

    # ── connection / schema ──────────────────────────────────────────
    def _conn(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        c.execute("""CREATE TABLE IF NOT EXISTS panels (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, viz TEXT NOT NULL,
            query_tool TEXT NOT NULL, query_args TEXT NOT NULL DEFAULT '{}',
            transform TEXT NOT NULL DEFAULT 'none', refresh TEXT NOT NULL DEFAULT 'daily',
            note TEXT DEFAULT '', origin_conversation TEXT DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'conversation', tab TEXT DEFAULT 'dashboard',
            columns TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL, archived_at TEXT, last_viewed_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL,
            kind TEXT NOT NULL, name TEXT NOT NULL, detail TEXT DEFAULT '',
            conversation_id TEXT DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT 'New chat',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
            meta TEXT DEFAULT '', created_at TEXT NOT NULL)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id)")
        return c

    @staticmethod
    def _now():
        return time.strftime("%Y-%m-%d %H:%M:%S")

    # ── journal (episodic memory) ────────────────────────────────────
    def journal_append(self, actor, kind, name, detail="", conversation_id=""):
        c = self._conn()
        try:
            c.execute("INSERT INTO journal (ts, actor, kind, name, detail, conversation_id) "
                      "VALUES (?,?,?,?,?,?)",
                      (self._now(), actor, kind, name,
                       detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False),
                       conversation_id))
            c.commit()
        finally:
            c.close()

    def journal_recent(self, limit=50, kind=None):
        c = self._conn()
        try:
            sql, params = "SELECT * FROM journal ", []
            if kind:
                sql += "WHERE kind = ? "
                params.append(kind)
            sql += "ORDER BY id DESC LIMIT ?"
            params.append(min(int(limit), 200))
            return [dict(r) for r in c.execute(sql, params).fetchall()]
        finally:
            c.close()

    def journal_summary_for_prompt(self, limit=12):
        """Recent-activity summary to inject as episodic recall (one line each)."""
        rows = self.journal_recent(limit)
        if not rows:
            return ""
        lines = [f"- {r['ts']} [{r['actor']}] {r['name']}"
                 + (f": {r['detail'][:60]}" if r["detail"] else "") for r in rows]
        return "Recent activity (journal):\n" + "\n".join(lines)

    # ── panels (materialized memory) ─────────────────────────────────
    def validate_spec(self, spec):
        """Schema-validate a panel spec. Returns an error string or None."""
        if not isinstance(spec, dict):
            return "spec must be an object"
        pid = spec.get("id", "")
        if not pid or not all(ch.isalnum() or ch in "-_" for ch in pid):
            return "id must be alphanumeric / hyphen"
        if not spec.get("title"):
            return "missing title"
        if spec.get("viz") not in VIZ_TYPES:
            return f"viz must be one of {sorted(VIZ_TYPES)}"
        if spec.get("refresh", "daily") not in REFRESH_TYPES:
            return f"refresh must be one of {sorted(REFRESH_TYPES)}"
        if spec.get("transform", "none") not in ({"none"} | set(self.transforms)):
            return f"transform must be one of {sorted({'none'} | set(self.transforms))}"
        q = spec.get("query", {})
        if not isinstance(q, dict) or not q.get("tool"):
            return "query.tool is required"
        if self.tool_names and q["tool"] not in self.tool_names:
            return f"query.tool must be a registered tool: {sorted(self.tool_names)}"
        cols = spec.get("columns")
        if cols is not None:
            if not isinstance(cols, list):
                return "columns must be a list"
            for col in cols:
                if not isinstance(col, dict) or not col.get("title"):
                    return "each column needs a title"
                if "expr" in col and not is_safe_expr(col["expr"]):
                    return f"column '{col['title']}' expr is unsafe: {col['expr']}"
                if "field" not in col and "expr" not in col:
                    return f"column '{col['title']}' needs field or expr"
        return None

    def create_panel(self, spec, conversation_id=""):
        err = self.validate_spec(spec)
        if err:
            return {"error": f"spec validation failed: {err}"}
        c = self._conn()
        try:
            existing = c.execute("SELECT status FROM panels WHERE id=?", (spec["id"],)).fetchone()
            if existing and existing["status"] == "active":
                return {"error": f"panel {spec['id']} already exists"}
            c.execute("INSERT OR REPLACE INTO panels (id,title,viz,query_tool,query_args,transform,"
                      "refresh,note,columns,origin_conversation,status,created_at) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (spec["id"], spec["title"], spec["viz"], spec["query"]["tool"],
                       json.dumps(spec["query"].get("args", {}), ensure_ascii=False),
                       spec.get("transform", "none"), spec.get("refresh", "daily"),
                       spec.get("note", ""), json.dumps(spec.get("columns", []), ensure_ascii=False),
                       conversation_id, "active", self._now()))
            c.commit()
            return {"ok": True, "id": spec["id"], "message": f"panel '{spec['title']}' created"}
        finally:
            c.close()

    def archive_panel(self, panel_id):
        c = self._conn()
        try:
            row = c.execute("SELECT id, kind FROM panels WHERE id=? OR title=?",
                            (panel_id, panel_id)).fetchone()
            if not row:
                return {"error": f"no panel named {panel_id}"}
            if row["kind"] == "builtin":
                return {"error": f"{panel_id} is a builtin panel; view-only"}
            cur = c.execute("UPDATE panels SET status='archived', archived_at=? "
                            "WHERE id=? AND status='active'", (self._now(), row["id"]))
            c.commit()
            if cur.rowcount == 0:
                return {"error": f"panel {panel_id} already archived"}
            return {"ok": True, "message": f"panel '{panel_id}' archived"}
        finally:
            c.close()

    def list_panels(self, include_archived=False):
        self._register_builtins()
        c = self._conn()
        try:
            sql = "SELECT * FROM panels "
            if not include_archived:
                sql += "WHERE status='active' "
            sql += "ORDER BY CASE kind WHEN 'builtin' THEN 0 ELSE 1 END, tab, created_at DESC"
            return [dict(r) for r in c.execute(sql).fetchall()]
        finally:
            c.close()

    def _register_builtins(self):
        """Idempotently register host-provided builtin panels so the agent's
        memory matches the page."""
        if not self.builtin_panels:
            return
        c = self._conn()
        try:
            existing = {r["id"] for r in c.execute("SELECT id FROM panels WHERE kind='builtin'").fetchall()}
            for pid, title, tab, note in self.builtin_panels:
                if pid not in existing:
                    c.execute("INSERT INTO panels (id,title,viz,query_tool,transform,refresh,note,"
                              "kind,tab,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                              (pid, title, "builtin", "", "none", "live", note,
                               "builtin", tab, "active", self._now()))
            c.commit()
        finally:
            c.close()

    def touch_panel(self, panel_id):
        c = self._conn()
        try:
            c.execute("UPDATE panels SET last_viewed_at=? WHERE id=?", (self._now(), panel_id))
            c.commit()
        finally:
            c.close()

    def apply_transform(self, name, data):
        """Run a host-registered scalar transform; 'none'/unknown returns data."""
        if name in ("none", "", None):
            return data
        fn = self.transforms.get(name)
        return fn(data) if fn else data

    # ── conversations (conversation memory) ──────────────────────────
    def ensure_conversation(self, conv_id):
        c = self._conn()
        try:
            if not c.execute("SELECT id FROM conversations WHERE id=?", (conv_id,)).fetchone():
                c.execute("INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?,?,?,?)",
                          (conv_id, "New chat", self._now(), self._now()))
                c.commit()
        finally:
            c.close()

    def list_conversations(self, limit=50):
        c = self._conn()
        try:
            return [dict(r) for r in c.execute(
                "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id) AS msg_count "
                "FROM conversations c ORDER BY c.updated_at DESC LIMIT ?", (min(int(limit), 100),)).fetchall()]
        finally:
            c.close()

    def get_messages(self, conv_id):
        c = self._conn()
        try:
            rows = c.execute("SELECT role, content, meta, created_at FROM messages "
                             "WHERE conversation_id=? ORDER BY id", (conv_id,)).fetchall()
            out = []
            for r in rows:
                m = {"role": r["role"], "content": r["content"], "created_at": r["created_at"]}
                if r["meta"]:
                    try:
                        m.update(json.loads(r["meta"]))
                    except Exception:
                        pass
                out.append(m)
            return out
        finally:
            c.close()

    def add_message(self, conv_id, role, content, meta=None):
        self.ensure_conversation(conv_id)
        c = self._conn()
        try:
            c.execute("INSERT INTO messages (conversation_id, role, content, meta, created_at) "
                      "VALUES (?,?,?,?,?)",
                      (conv_id, role, content or "",
                       json.dumps(meta, ensure_ascii=False) if meta else "", self._now()))
            c.execute("UPDATE conversations SET updated_at=? WHERE id=?", (self._now(), conv_id))
            c.commit()
        finally:
            c.close()

    def message_count(self, conv_id):
        c = self._conn()
        try:
            return c.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conv_id,)).fetchone()[0]
        finally:
            c.close()

    def set_title(self, conv_id, title):
        c = self._conn()
        try:
            c.execute("UPDATE conversations SET title=? WHERE id=?", (title[:40], conv_id))
            c.commit()
        finally:
            c.close()

    def delete_conversation(self, conv_id):
        c = self._conn()
        try:
            c.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
            c.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
            c.commit()
            return {"ok": True}
        finally:
            c.close()

    def auto_title(self, conv_id, first_user_msg):
        """Generate a short title after the first message (LLM, with fallback)."""
        title = first_user_msg.strip().replace("\n", " ")[:20]
        try:
            from .llm import chat
            r = chat([
                {"role": "system", "content": "Summarize the user's question into a short 3-8 word title. "
                                              "Output only the title, no punctuation or quotes."},
                {"role": "user", "content": first_user_msg[:200]},
            ], temperature=0.3, max_tokens=30)
            t = (r.get("content") or "").strip().strip("\"'《》「」").replace("\n", "")
            if t:
                title = t[:40]
        except Exception:
            pass
        self.set_title(conv_id, title)
        return title
