"""Convierte el Markdown que devuelven los modelos de lenguaje al subconjunto
de HTML que entiende Telegram (parse_mode=HTML): <b>, <i>, <s>, <code>,
<pre>, <a href>, <blockquote>.

Telegram no tiene titulos, listas ni tablas, asi que:
    # Titulo           -> <b>Titulo</b>
    - item / * item    -> • item
    | a | b | (tabla)  -> bloque <pre> con columnas alineadas
    ---                -> linea separadora

Todo el texto se escapa (&, <, >) y las etiquetas se generan siempre por
pares dentro de una linea, asi que el resultado es HTML bien formado salvo
Markdown muy retorcido (p. ej. negrita y cursiva cruzadas); para ese caso el
handler reenvia el fragmento como texto plano si Telegram lo rechaza.

`split_markdown` trocea ANTES de convertir (cortar HTML podria dejar
etiquetas abiertas), sin partir bloques de codigo ni tablas.
"""
from __future__ import annotations

import html
import re

_FENCE = re.compile(r"^\s*(```|~~~)\s*([\w+#.-]*)\s*$")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_QUOTE = re.compile(r"^\s{0,3}>\s?(.*)$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")

_INLINE_CODE = re.compile(r"`([^`\n]+)`")
# URL con un nivel de parentesis equilibrados (p. ej. enlaces de Wikipedia).
_LINK = re.compile(r"\[([^\]\n]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)")
_BOLD_ITALIC = re.compile(r"\*\*\*(?!\s)(.+?)(?<!\s)\*\*\*")
_BOLD = re.compile(r"\*\*(?!\s)(.+?)(?<!\s)\*\*|(?<!\w)__(?!\s)(.+?)(?<!\s)__(?!\w)")
_ITALIC = re.compile(r"(?<![*\w])\*(?![\s*])(.+?)(?<![\s*])\*(?![*\w])|(?<!\w)_(?![\s_])(.+?)(?<![\s_])_(?!\w)")
_STRIKE = re.compile(r"~~(?!\s)(.+?)(?<!\s)~~")
_PLACEHOLDER = "\x00{}\x00"
_TAG = re.compile(r"<(/?)([a-z]+)[^>]*>")
_SAFE_LINK_SCHEMES = ("http://", "https://", "tg://", "mailto:")

RULE_LINE = "──────────"


def markdown_to_telegram_html(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        fence = _FENCE.match(line)
        if fence:
            code, i = _collect_fenced(lines, i + 1, fence.group(1))
            language = fence.group(2)
            body = html.escape("\n".join(code), quote=False)
            if language:
                out.append(f'<pre><code class="language-{html.escape(language)}">{body}</code></pre>')
            else:
                out.append(f"<pre>{body}</pre>")
            continue

        if _TABLE_ROW.match(line) and i + 1 < len(lines) and _TABLE_SEPARATOR.match(lines[i + 1]):
            rows, i = _collect_table(lines, i)
            out.append(f"<pre>{html.escape(_render_table(rows), quote=False)}</pre>")
            continue

        quote = _QUOTE.match(line)
        if quote:
            quoted = []
            while i < len(lines) and (match := _QUOTE.match(lines[i])):
                quoted.append(inline_to_html(match.group(1)))
                i += 1
            out.append("<blockquote>" + "\n".join(quoted) + "</blockquote>")
            continue

        out.append(_block_line(line))
        i += 1

    return _collapse_blank_lines("\n".join(out)).strip()


def _block_line(line: str) -> str:
    if heading := _HEADING.match(line):
        return f"<b>{inline_to_html(heading.group(1))}</b>"
    if _RULE.match(line):
        return RULE_LINE
    if bullet := _BULLET.match(line):
        indent = " " * (len(bullet.group(1).expandtabs(4)) // 2 * 2)
        return f"{indent}• {inline_to_html(bullet.group(2))}"
    return inline_to_html(line)


def inline_to_html(text: str) -> str:
    """Formato en linea. El codigo y los enlaces se sacan antes a marcadores
    para que su contenido no se interprete como Markdown."""
    stash: list[str] = []

    def keep(fragment: str) -> str:
        stash.append(fragment)
        return _PLACEHOLDER.format(len(stash) - 1)

    text = _INLINE_CODE.sub(lambda m: keep(f"<code>{html.escape(m.group(1), quote=False)}</code>"), text)
    text = _LINK.sub(lambda m: keep(_link(m.group(1), m.group(2))), text)
    source = text
    text = html.escape(text, quote=False)
    text = _BOLD_ITALIC.sub(r"<b><i>\1</i></b>", text)
    text = _BOLD.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", text)
    text = _ITALIC.sub(lambda m: f"<i>{m.group(1) or m.group(2)}</i>", text)
    text = _STRIKE.sub(r"<s>\1</s>", text)
    if not _balanced(text):
        # Marcas cruzadas (p. ej. "**a *b** c*"): se envia la linea sin formato.
        text = html.escape(source, quote=False)
    return re.sub("\x00(\\d+)\x00", lambda m: stash[int(m.group(1))], text)


def _balanced(fragment: str) -> bool:
    stack: list[str] = []
    for closing, tag in _TAG.findall(fragment):
        if not closing:
            stack.append(tag)
        elif not stack or stack.pop() != tag:
            return False
    return not stack


def _link(label: str, url: str) -> str:
    inner = inline_to_html(label)
    # Solo esquemas seguros: el mismo HTML se pinta en el panel web.
    if not url.lower().startswith(_SAFE_LINK_SCHEMES):
        return inner
    return f'<a href="{html.escape(url, quote=True)}">{inner}</a>'


def _collect_fenced(lines: list[str], start: int, marker: str) -> tuple[list[str], int]:
    code = []
    i = start
    while i < len(lines):
        if lines[i].strip().startswith(marker):
            return code, i + 1
        code.append(lines[i])
        i += 1
    return code, i  # bloque sin cerrar: se cierra al final


def _collect_table(lines: list[str], start: int) -> tuple[list[list[str]], int]:
    rows = [_cells(lines[start])]
    i = start + 2  # salta la fila separadora |---|
    while i < len(lines) and _TABLE_ROW.match(lines[i]):
        rows.append(_cells(lines[i]))
        i += 1
    return rows, i


def _cells(row: str) -> list[str]:
    return [_plain(cell.strip()) for cell in row.strip().strip("|").split("|")]


def _plain(text: str) -> str:
    """Texto de una celda sin marcas Markdown (dentro de <pre> no hay formato)."""
    text = _LINK.sub(r"\1", text)
    text = _INLINE_CODE.sub(r"\1", text)
    for pattern in (_BOLD_ITALIC, _BOLD, _ITALIC, _STRIKE):
        text = pattern.sub(lambda m: next(g for g in m.groups() if g is not None), text)
    return text


def _render_table(rows: list[list[str]]) -> str:
    columns = max(len(row) for row in rows)
    rows = [row + [""] * (columns - len(row)) for row in rows]
    widths = [max(len(row[c]) for row in rows) for c in range(columns)]
    numeric = [
        all(_looks_numeric(row[c]) for row in rows[1:] if row[c]) and any(row[c] for row in rows[1:])
        for c in range(columns)
    ]

    def render(row: list[str]) -> str:
        cells = [
            cell.rjust(widths[c]) if numeric[c] else cell.ljust(widths[c])
            for c, cell in enumerate(row)
        ]
        return " │ ".join(cells).rstrip()

    separator = "─┼─".join("─" * width for width in widths)
    return "\n".join([render(rows[0]), separator, *(render(row) for row in rows[1:])])


def _looks_numeric(cell: str) -> bool:
    return bool(re.fullmatch(r"[+\-−]?[$€₽£¥]?\s?[\d\s.,]+\s?(%|[$€₽£¥]|[kKmMbB]|млн|млрд|тыс\.?)?", cell))


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


def split_markdown(markdown: str, limit: int) -> list[str]:
    """Trocea por lineas en fragmentos de como mucho `limit` caracteres. Si un
    corte cae dentro de un bloque ``` se cierra y se reabre en el siguiente
    fragmento, para que cada trozo se convierta por separado sin romperse."""
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    open_fence: str | None = None

    def flush() -> None:
        nonlocal current, size
        if open_fence is not None:
            current.append("```")
        text = "\n".join(current).strip("\n")
        if text:
            chunks.append(text)
        current = [open_fence] if open_fence is not None else []
        size = sum(len(line) + 1 for line in current)

    for line in markdown.replace("\r\n", "\n").split("\n"):
        while len(line) > limit:  # linea gigante sin saltos: corte duro
            if current:
                flush()
            head, line = line[:limit], line[limit:]
            current.append(head)
            size = len(head)
            flush()
        if size + len(line) + 1 > limit and current:
            flush()
        current.append(line)
        size += len(line) + 1
        fence = _FENCE.match(line)
        if fence:
            open_fence = None if open_fence is not None else line.strip()
    if open_fence is not None:
        open_fence = None
    text = "\n".join(current).strip("\n")
    if text:
        chunks.append(text)
    return chunks
