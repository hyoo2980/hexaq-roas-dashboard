def shorten_adset_name(name: str) -> str:
    """Adset names are often long with audience/targeting codes after a marker
    letter 'S' -- cut right after the first 'S' to keep tables/embeds compact.
    Names with no 'S' are left untouched."""
    idx = name.find("S")
    return name[: idx + 1] if idx != -1 else name
