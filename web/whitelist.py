"""Whitelist helpers — UI read-model backed by whitelist.json.

Reads from the root whitelist module (whitelist.json) which is the canonical
runtime store. The legacy WHITELIST_HANDLES config key is only consulted on
first-start seeding (handled inside the root module).
"""
from __future__ import annotations


def all_entries() -> list[str]:
    """Return all whitelisted handles + group GUIDs as a sorted list."""
    import whitelist as _wl  # noqa: PLC0415
    handles = sorted(_wl.all_handles())
    groups = sorted(_wl.all_groups())
    return handles + groups


def all_groups() -> set[str]:
    """Return set of whitelisted group GUIDs."""
    import whitelist as _wl  # noqa: PLC0415
    return _wl.all_groups()


def grouped_entries() -> dict:
    """Return whitelist entries grouped by contact name.

    Returns a dict with three keys:
      contacts  — list of {name, all_handles, whitelisted_handles, whitelisted}
                  for every known contact; sorted by name (case-insensitive).
                  Only contacts with ≥1 whitelisted handle are included.
      unknown   — list of whitelisted handles that have no Contacts entry.
      groups    — list of {guid, name, members, whitelisted} for all known
                  group chats; whitelisted=True when the GUID is in
                  whitelist.json. Unnamed groups use a synthetic name
                  built from participant contact names.
    """
    import whitelist as _wl  # noqa: PLC0415
    from web.main import CONTACTS, _list_named_groups  # noqa: PLC0415

    wl_handles: set = _wl.all_handles()   # lowercased
    wl_groups: set = _wl.all_groups()     # original case

    # Build name → set[handle] from CONTACTS (handle → name)
    name_to_handles: dict = {}
    for handle, name in CONTACTS.items():
        if name:
            name_to_handles.setdefault(name, set()).add(handle.lower())

    assigned: set = set()
    contacts_out = []
    for name in sorted(name_to_handles, key=str.lower):
        known = name_to_handles[name]
        wl_subset = wl_handles & known
        if not wl_subset:
            continue  # skip contacts with no whitelisted handles
        assigned |= wl_subset
        contacts_out.append({
            "name": name,
            "all_handles": sorted(known),
            "whitelisted_handles": sorted(wl_subset),
            "whitelisted": True,
        })

    # Whitelisted handles with no name mapping
    unknown_handles = sorted(wl_handles - assigned)

    # Groups — start with all named groups from chat.db
    named_groups = _list_named_groups()
    wl_group_guids_lower = {g.lower() for g in wl_groups}
    groups_out = []
    seen_guids: set = set()
    for g in named_groups:
        guid = g["guid"]
        groups_out.append({
            "guid": guid,
            "name": g["name"],
            "members": g.get("members", 0),
            "whitelisted": guid in wl_groups or guid.lower() in wl_group_guids_lower,
        })
        seen_guids.add(guid.lower())
    # Whitelisted GUIDs not in named groups (unnamed / unknown)
    for guid in sorted(wl_groups):
        if guid.lower() not in seen_guids:
            groups_out.append({
                "guid": guid,
                "name": guid,
                "members": 0,
                "whitelisted": True,
            })

    return {
        "contacts": contacts_out,
        "unknown": unknown_handles,
        "groups": groups_out,
    }
