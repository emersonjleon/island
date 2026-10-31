"""`{% vite_entry "lobby" %}` emits the script and style tags for a frontend entry.

With VITE_DEV_SERVER set, tags point at the Vite dev server (hot reload).
Otherwise they come from the build manifest under static/dist/.
"""
import json
from functools import lru_cache
from pathlib import Path

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString, mark_safe

register = template.Library()

ENTRY_DIR = "src/entries"


@lru_cache(maxsize=4)
def _load_manifest(path: str, mtime: float) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def manifest() -> dict:
    path = Path(settings.VITE_MANIFEST_PATH)
    if not path.exists():
        return {}
    return _load_manifest(str(path), path.stat().st_mtime)


def _css_files(chunk_key: str, chunks: dict, seen: set[str]) -> list[str]:
    if chunk_key in seen or chunk_key not in chunks:
        return []
    seen.add(chunk_key)
    chunk = chunks[chunk_key]
    files: list[str] = []
    for imported in chunk.get("imports", []):
        files += _css_files(imported, chunks, seen)
    return files + list(chunk.get("css", []))


@register.simple_tag
def vite_entry(name: str) -> SafeString:
    source = f"{ENTRY_DIR}/{name}.ts"
    dev = settings.VITE_DEV_SERVER.rstrip("/")
    if dev:
        return format_html(
            '<script type="module" src="{}/@vite/client"></script>\n'
            '<script type="module" src="{}/{}"></script>',
            dev,
            dev,
            source,
        )
    chunks = manifest()
    chunk = chunks.get(source)
    if chunk is None:
        # No build yet: render nothing so server pages still work without the client.
        return format_html("<!-- vite entry {} not built -->", name)
    css = format_html_join(
        "\n",
        '<link rel="stylesheet" href="{}">',
        ((static(f"dist/{f}"),) for f in _css_files(source, chunks, set())),
    )
    script = format_html('<script type="module" src="{}"></script>', static(f"dist/{chunk['file']}"))
    return mark_safe(f"{css}\n{script}" if css else script)
