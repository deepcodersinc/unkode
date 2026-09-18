"""Where unkode keeps its files.

Everything lives under `.unkode/` in the project root. Maps written by older
versions sat loose in the root as `unkode.yaml`; those are still readable so
existing repos keep working until they migrate.
"""

from pathlib import Path

UNKODE_DIR = ".unkode"

ARCH = f"{UNKODE_DIR}/arch.yaml"
MERMAID = f"{UNKODE_DIR}/arch_map.md"
HTML = f"{UNKODE_DIR}/arch_map.html"
CONFIG = f"{UNKODE_DIR}/config.yaml"

# Pre-.unkode layout, still read so older repos keep working.
LEGACY_ARCH = "unkode.yaml"
LEGACY_MERMAID = "arch_map.md"
LEGACY_HTML = "arch_map.html"

# Paths git should ignore when deciding whether the codebase changed.
OWN_FILES = {ARCH, MERMAID, HTML, CONFIG, LEGACY_ARCH, LEGACY_MERMAID, LEGACY_HTML}


def arch_candidates():
    """Both locations for the architecture map, current layout first."""
    return [ARCH, LEGACY_ARCH]


def find_arch(explicit=None):
    """Resolve the architecture map, preferring `.unkode/` over the legacy root file.

    Returns the path as a string, or None when no map exists anywhere.
    """
    if explicit:
        return explicit if Path(explicit).exists() else None
    for candidate in arch_candidates():
        if Path(candidate).exists():
            return candidate
    return None


def using_legacy_layout():
    """True when a root-level map exists and has not been moved into `.unkode/`."""
    return Path(LEGACY_ARCH).exists() and not Path(ARCH).exists()


def ensure_dir(path):
    """Create the parent directory for `path` if it does not exist."""
    parent = Path(path).parent
    if parent and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
