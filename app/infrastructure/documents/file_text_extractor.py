"""Adaptador de DocumentTextExtractor: saca el texto de los ficheros que se
suben a la base de conocimiento, segun su extension.

- Texto plano y formatos de configuracion: se decodifican (UTF-8, y si falla
  cp1251 -- documentos rusos de Windows -- y por ultimo latin-1).
- HTML/XML: se quitan las etiquetas.
- DOCX: es un zip; se lee word/document.xml con la libreria estandar.
- PDF: pypdf (solo PDFs con texto; uno escaneado no tiene texto que leer).
"""
from __future__ import annotations

import io
import re
import zipfile
from html.parser import HTMLParser
from pathlib import PurePath
from xml.etree import ElementTree

from application.ports.document_text_extractor import DocumentError

_TEXT_EXTENSIONS = (
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml", ".toml",
    ".ini", ".conf", ".cfg", ".properties", ".sql", ".log",
)
_MARKUP_EXTENSIONS = (".html", ".htm", ".xml")
_WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class FileTextExtractor:
    supported_extensions = (*_TEXT_EXTENSIONS, *_MARKUP_EXTENSIONS, ".docx", ".pdf")

    def extract(self, filename: str, data: bytes) -> str:
        name = PurePath(filename).name.lower()
        if name.endswith(".pdf"):
            return _pdf_text(data)
        if name.endswith(".docx"):
            return _docx_text(data)
        if name.endswith(_MARKUP_EXTENSIONS):
            return _markup_text(_decode(data))
        if name.endswith(_TEXT_EXTENSIONS):
            return _decode(data)
        raise DocumentError("formato no soportado (usa PDF, DOCX, TXT, MD, CSV, JSON, YAML…).")


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


class _TextCollector(HTMLParser):
    _SKIPPED = {"script", "style"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag, attrs) -> None:
        if tag in self._SKIPPED:
            self._skipping += 1

    def handle_endtag(self, tag) -> None:
        if tag in self._SKIPPED and self._skipping:
            self._skipping -= 1

    def handle_data(self, data) -> None:
        if not self._skipping:
            self.parts.append(data)


def _markup_text(markup: str) -> str:
    collector = _TextCollector()
    collector.feed(markup)
    return _tidy("".join(collector.parts))


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise DocumentError("el DOCX está dañado o no es un documento de Word.") from exc
    paragraphs = []
    for paragraph in root.iter(f"{_WORD_NAMESPACE}p"):
        pieces = []
        for node in paragraph.iter():
            if node.tag == f"{_WORD_NAMESPACE}t" and node.text:
                pieces.append(node.text)
            elif node.tag == f"{_WORD_NAMESPACE}tab":
                pieces.append("\t")
        paragraphs.append("".join(pieces))
    return _tidy("\n".join(paragraphs))


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # falta la dependencia en la imagen
        raise DocumentError("falta la librería pypdf en el servidor para leer PDF.") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("el PDF está protegido con contraseña.")
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise DocumentError("el PDF está dañado o no se puede leer.") from exc
    return _tidy("\n\n".join(pages))


def _tidy(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
