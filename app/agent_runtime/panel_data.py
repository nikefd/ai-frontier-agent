"""Panel data resolver — resolves a panel spec into rendered data.

Given a panel id: load its spec from memory, call its data-source tool, then
either apply custom columns (field/expr) or a scalar transform. Panels store
recipes, so this always recomputes from live data.
"""
import json

from .expr import safe_eval


def _apply_columns(raw, columns):
    """Apply column declarations row-by-row to the data array in a tool result
    (field = direct read, expr = restricted evaluation)."""
    # A tool may return several arrays; use the longest as the data source —
    # usually the detail/series the user cares about.
    src = None
    if isinstance(raw, dict):
        arrays = [v for v in raw.values() if isinstance(v, list)]
        if arrays:
            src = max(arrays, key=len)
    if src is None:
        return {"rows": []}
    rows = []
    for item in src:
        if not isinstance(item, dict):
            continue
        row = {}
        for col in columns:
            title = col["title"]
            if "expr" in col:
                row[title] = safe_eval(col["expr"], item)
            else:
                row[title] = item.get(col["field"], "")
        rows.append(row)
    return {"rows": rows}


def resolve(panel_id, memory, registry):
    """Resolve one panel. ``memory`` is a :class:`~sparrow.memory.Memory`,
    ``registry`` is a :class:`~sparrow.registry.ToolRegistry`."""
    panels = {p["id"]: p for p in memory.list_panels(include_archived=True)}
    p = panels.get(panel_id)
    if not p:
        return {"error": f"panel not found: {panel_id}"}
    # Builtin panels are rendered by the host's own UI, not via spec resolution.
    if p.get("kind") == "builtin":
        return {"id": panel_id, "title": p["title"], "viz": "builtin", "kind": "builtin",
                "note": p["note"], "data": {"builtin": True}}
    raw = registry.run(p["query_tool"], json.loads(p["query_args"] or "{}"))
    if isinstance(raw, dict) and raw.get("error"):
        return {"id": panel_id, "error": raw["error"]}
    columns = []
    try:
        columns = json.loads(p.get("columns") or "[]")
    except (ValueError, TypeError):
        columns = []
    if columns:
        data = _apply_columns(raw, columns)
    else:
        data = memory.apply_transform(p["transform"], raw)
    memory.touch_panel(panel_id)
    return {"id": panel_id, "title": p["title"], "viz": p["viz"],
            "kind": p.get("kind", "conversation"), "note": p["note"],
            "origin": p["origin_conversation"], "created_at": p["created_at"], "data": data}
