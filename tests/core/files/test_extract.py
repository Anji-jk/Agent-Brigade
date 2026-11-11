import io

import pytest

PdfWriter = pytest.importorskip("pypdf").PdfWriter

pytest.importorskip("docx")
Document = pytest.importorskip("docx").Document

from core.files.extract import MAX_BYTES, FileRejected, extract_text  # noqa: E402


def text_pdf(text: str) -> bytes:
    """A one-page PDF with real text, written by hand (pypdf cannot add text)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


def blank_pdf(password: str | None = None) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    if password:
        writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_text_and_markdown_are_read_with_or_without_bom():
    assert (
        extract_text("a.txt", "\ufeffLine one\r\nLine two  \r\n".encode()) == "Line one\nLine two"
    )
    assert extract_text("a.MD", b"# Title\n- point") == "# Title\n- point"


def test_old_windows_text_files_are_read():
    assert extract_text("a.txt", "café".encode("cp1252")) == "café"


def test_docx_paragraphs_and_tables_are_read():
    document = Document()
    document.add_paragraph("Reminder before expiry")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Days"
    table.rows[0].cells[1].text = "30"
    out = io.BytesIO()
    document.save(out)
    assert extract_text("req.docx", out.getvalue()) == "Reminder before expiry\nDays | 30"


def test_pdf_text_is_read():
    assert extract_text("req.pdf", text_pdf("Managers see expiring certificates")) == (
        "Managers see expiring certificates"
    )


@pytest.mark.parametrize(
    "name, data, expected",
    [
        ("a.exe", b"x", "only .txt, .md, .docx, .pdf"),
        ("a.txt", b"", "is empty"),
        ("a.txt", b" \n \n", "has no text"),
        ("a.txt", b"x" * (MAX_BYTES + 1), "larger than 10 MB"),
        ("a.docx", b"plain text, not a docx", "could not be read as a .docx file"),
        ("a.pdf", b"%PDF-broken", "could not be read as a .pdf file"),
        ("scan.pdf", blank_pdf(), "probably a scan"),
        ("locked.pdf", blank_pdf("secret"), "password-protected"),
        ("big.txt", b"x" * 150_001, "split it into parts"),
    ],
)
def test_unusable_files_are_refused_with_the_reason(name, data, expected):
    with pytest.raises(FileRejected, match=expected):
        extract_text(name, data)
