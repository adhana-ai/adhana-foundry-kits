"""SEAM 2 — text out of a document. Add a format by adding one entry to EXTRACTORS.

This is the layer the corpus's five formats meet. It is also where "not extracted" -- one of the
four retrieval failure causes the Foundry Failure Modes page publishes -- actually happens, which
is why the corpus deliberately ships PDFs and DOCX rather than forty clean markdown files.

Every extractor returns plain text or raises. A format that silently returns "" would be worse
than one that fails: an empty document still indexes, still ranks, and still never answers, so the
failure would surface as a mysteriously bad retrieval score rather than as the extraction problem
it is.
"""
import os
import re
import zipfile
from html.parser import HTMLParser


class HtmlText(HTMLParser):
    """HTML to text, and to markdown, in one pass.

    Deliberately stdlib. A kit that needs a scraping dependency to read its own sample data has
    spent a dependency on the least interesting part of itself. tools/build_corpus.py imports this
    class rather than carrying its own copy -- the corpus and the runtime must agree about what
    the text of a document IS, and two parsers would eventually disagree.
    """

    SKIP = {"script", "style", "head", "nav"}
    HEAD = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### "}

    def __init__(self, md=False):
        super().__init__(convert_charrefs=True)
        self.md, self.out, self.skip, self.pre = md, [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "pre":
            self.pre += 1
            self.out.append("\n```\n" if self.md else "\n")
        elif tag in self.HEAD:
            self.out.append("\n\n" + (self.HEAD[tag] if self.md else ""))
        elif tag in ("p", "div", "tr", "br", "table"):
            self.out.append("\n")
        elif tag == "li":
            self.out.append("\n" + ("- " if self.md else "  "))

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag == "pre":
            self.pre = max(0, self.pre - 1)
            self.out.append("\n```\n" if self.md else "\n")
        elif tag in self.HEAD:
            self.out.append("\n")

    def handle_data(self, d):
        if not self.skip:
            self.out.append(d if self.pre else re.sub(r"\s+", " ", d))

    def text(self):
        s = re.sub(r"\n[ \t]+\n", "\n\n", "".join(self.out))
        return re.sub(r"\n{3,}", "\n\n", s).strip() + "\n"


def from_html(path, md=False):
    p = HtmlText(md)
    p.feed(open(path, encoding="utf-8", errors="replace").read())
    return p.text()


def from_plain(path):
    return open(path, encoding="utf-8", errors="replace").read()


def from_docx(path):
    """DOCX is a zip of XML. No dependency needed -- and worth knowing before adding one."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"<[^>]+>", "", xml)).strip() + "\n"


def from_pdf(path):
    """The one extractor with a real dependency, and the one that actually loses text.

    pypdf reads the text layer. A PDF whose text layer is missing or badly ordered comes back
    empty or scrambled -- that is not a bug to route around, it is the failure this corpus exists
    to exhibit. The taxonomy entry it produces is 'not extracted'.
    """
    try:
        from pypdf import PdfReader
    except ImportError:                                   # pragma: no cover
        raise RuntimeError("pdf extraction needs pypdf: pip install -r requirements.txt")
    pages = [(p.extract_text() or "") for p in PdfReader(path).pages]
    return "\n\n".join(pages).strip() + "\n"


EXTRACTORS = {
    ".md":   from_plain,
    ".txt":  from_plain,
    ".html": from_html,
    ".docx": from_docx,
    ".pdf":  from_pdf,
}


def extract(path):
    """Return (text, format). Raises on an unknown extension rather than skipping it -- a corpus
    that silently drops a file is a corpus whose document count is a lie."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in EXTRACTORS:
        raise ValueError("no extractor for %r -- add one to EXTRACTORS in src/extract.py" % ext)
    return EXTRACTORS[ext](path), ext.lstrip(".")
