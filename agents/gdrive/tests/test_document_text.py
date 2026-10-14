"""Turning a document's bytes into text.

The defect these tests exist to prevent is a silent one, and it shipped: the
first extractor matched `<t>` elements across every XML part in the zip, so it
read a spreadsheet's LABELS and dropped every NUMBER -- numeric cells are `<v>`,
not `<t>`. Measured on a real WorkDrive file whose Sr.no column and dates
vanished while the answer looked complete and authoritative.

So the fixtures here are shaped like real files, not like the extractor: a
worksheet that references shared strings by index, a Word paragraph split into
runs, a namespaced ODF body. A fixture built to match the parser proves nothing
about the parser.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from gdrive_agent.document_text import UnreadableDocument, extract


def zipped(parts: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return buffer.getvalue()


# ── spreadsheets: the format that lost its numbers ───────────────────────────

XLSX_NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


def xlsx(rows: list[list[str]], shared: list[str], sheet_name: str = "Sheet1") -> bytes:
    """A worksheet that references shared strings by INDEX, as a real one does.

    A cell carrying `t="s"` holds an index into sharedStrings; a cell with no `t`
    holds a literal number. Both appear in every real spreadsheet, and reading
    only the first is the bug.
    """
    def cell(value: str) -> str:
        if value in shared:
            return f'<c t="s"><v>{shared.index(value)}</v></c>'
        return f"<c><v>{value}</v></c>"

    body = "".join(
        f"<row>{''.join(cell(v) for v in row)}</row>" for row in rows
    )
    return zipped({
        "[Content_Types].xml": "<Types/>",
        "xl/workbook.xml": f'<workbook {XLSX_NS}><sheets><sheet name="{sheet_name}" sheetId="1"/></sheets></workbook>',
        "xl/sharedStrings.xml": f"<sst {XLSX_NS}>" + "".join(f"<si><t>{s}</t></si>" for s in shared) + "</sst>",
        "xl/worksheets/sheet1.xml": f"<worksheet {XLSX_NS}><sheetData>{body}</sheetData></worksheet>",
    })


def test_a_spreadsheets_numbers_are_read_and_not_only_its_labels():
    """The regression. `46265.0` was a date and `1..7` was the Sr.no column on
    the real file, and both were silently absent from the extraction."""
    data = xlsx(
        rows=[["Sr.no", "Result"], ["1", "Pass"], ["2", "Pass"], ["46265.0", "Fail"]],
        shared=["Sr.no", "Result", "Pass", "Fail"],
    )

    got = extract(data, "PCR 859_Unit Test.xlsx")

    assert "Sr.no" in got.text
    assert "1" in got.text and "2" in got.text, "numeric cells must survive"
    assert "46265.0" in got.text, "a date serial is a number, not a label"
    assert got.kind == "spreadsheet"


def test_a_row_stays_one_line_so_a_label_keeps_its_value():
    """Flattening loses the association between a heading and its figure, which
    is most of what a spreadsheet IS -- a model asked for the Q3 number cannot
    recover it from a list of words."""
    data = xlsx(
        rows=[["Quarter", "Revenue"], ["Q3", "48200"]],
        shared=["Quarter", "Revenue", "Q3"],
    )

    lines = extract(data, "figures.xlsx").text.splitlines()

    assert "Q3\t48200" in lines


def test_a_named_sheet_is_labelled_so_a_workbook_is_navigable():
    data = xlsx(rows=[["x"]], shared=["x"], sheet_name="Pricing")

    assert "--- sheet: Pricing ---" in extract(data, "book.xlsx").text


def test_an_inline_string_cell_is_read_too():
    # Some producers inline the string rather than sharing it.
    data = zipped({
        "xl/workbook.xml": f"<workbook {XLSX_NS}/>",
        "xl/worksheets/sheet1.xml":
            f'<worksheet {XLSX_NS}><sheetData><row>'
            f'<c t="inlineStr"><is><t>written inline</t></is></c>'
            f"</row></sheetData></worksheet>",
    })

    assert "written inline" in extract(data, "x.xlsx").text


# ── Word ─────────────────────────────────────────────────────────────────────

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def test_a_paragraph_split_across_runs_rejoins_without_gaps():
    """Formatting splits a sentence into runs. Joining them with spaces turns
    "the Q3 figure" into "the Q3 figure" only by luck, and mangles bolded words
    mid-sentence."""
    data = zipped({
        "word/document.xml":
            f"<w:document {W}><w:body><w:p>"
            f"<w:r><w:t>the </w:t></w:r><w:r><w:t>Q3</w:t></w:r><w:r><w:t> figure</w:t></w:r>"
            f"</w:p></w:body></w:document>",
    })

    assert extract(data, "memo.docx").text == "the Q3 figure"


def test_a_word_table_row_stays_one_line():
    data = zipped({
        "word/document.xml":
            f"<w:document {W}><w:body><w:tbl><w:tr>"
            f"<w:tc><w:p><w:r><w:t>Client</w:t></w:r></w:p></w:tc>"
            f"<w:tc><w:p><w:r><w:t>Revasure</w:t></w:r></w:p></w:tc>"
            f"</w:tr></w:tbl></w:body></w:document>",
    })

    assert "Client\tRevasure" in extract(data, "t.docx").text


def test_page_furniture_does_not_interleave_with_the_body():
    """Reading every XML part in zip order put a footer in the middle of a
    sentence. Only word/document.xml is the document."""
    data = zipped({
        "word/document.xml":
            f"<w:document {W}><w:body><w:p><w:r><w:t>the real body</w:t></w:r></w:p></w:body></w:document>",
        "word/footer1.xml": f"<w:ftr {W}><w:p><w:r><w:t>page 1 of 9</w:t></w:r></w:p></w:ftr>",
        "word/comments.xml": f"<w:comments {W}><w:p><w:r><w:t>ask legal</w:t></w:r></w:p></w:comments>",
    })

    got = extract(data, "doc.docx").text

    assert got == "the real body"


# ── PowerPoint ───────────────────────────────────────────────────────────────

A = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
     'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')


def test_a_deck_is_read_slide_by_slide_in_order():
    # Both prefixes declared: a slide really carries `p:` and `a:`, and an
    # undeclared prefix is a fixture bug that reads as a damaged file.
    def slide(text: str) -> str:
        return f"<p:sld {A}><a:t>{text}</a:t></p:sld>"

    # Written out of order on purpose: zip order is not slide order, and slide10
    # sorts before slide2 as a string.
    data = zipped({
        "ppt/slides/slide10.xml": slide("tenth"),
        "ppt/slides/slide2.xml": slide("second"),
        "ppt/slides/slide1.xml": slide("first"),
    })

    text = extract(data, "deck.pptx").text

    assert text.index("first") < text.index("second") < text.index("tenth")
    assert "--- slide 1 ---" in text


# ── OpenDocument ─────────────────────────────────────────────────────────────

ODF = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
       'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
       'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"')


def test_an_opendocument_text_file_is_read():
    data = zipped({
        "content.xml":
            f"<office:document-content {ODF}><office:body>"
            f"<text:p>an open document</text:p>"
            f"</office:body></office:document-content>",
    })

    got = extract(data, "notes.odt")

    assert "an open document" in got.text
    assert got.kind == "opendocument"


def test_an_opendocument_spreadsheet_row_stays_one_line():
    data = zipped({
        "content.xml":
            f"<office:document-content {ODF}><office:body><table:table><table:table-row>"
            f"<table:table-cell><text:p>Quarter</text:p></table:table-cell>"
            f"<table:table-cell><text:p>Q3</text:p></table:table-cell>"
            f"</table:table-row></table:table></office:body></office:document-content>",
    })

    assert "Quarter\tQ3" in extract(data, "s.ods").text


# ── PDF ──────────────────────────────────────────────────────────────────────

def one_page_pdf(text: str) -> bytes:
    """A real PDF whose text is genuinely extractable.

    Hand-built rather than assembled with a writer helper: a content stream is
    only extractable when the page also carries the font resource it names, and
    a fixture missing that produces a page pypdf reads as EMPTY -- which is
    indistinguishable from the scanned-document case this file also tests.
    """
    body = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(body)).encode() + b" >>\nstream\n" + body + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, payload in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + payload + b"\nendobj\n"

    start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{start}\n%%EOF\n").encode()
    return bytes(out)


def test_a_pdf_with_selectable_text_is_read():
    got = extract(one_page_pdf("Registered office in Girgaon"), "deed.pdf")

    assert "Girgaon" in got.text
    assert got.kind == "pdf"
    assert "--- page 1 ---" in got.text


def test_a_pdf_with_no_selectable_text_says_it_needs_ocr():
    """A scan is pictures of words. "Empty document" and "this needs OCR, which
    we do not have" send a reader somewhere completely different."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)

    with pytest.raises(UnreadableDocument, match="OCR"):
        extract(buffer.getvalue(), "scan.pdf")


def test_a_pdf_is_recognised_by_its_header_when_the_name_lies():
    got = extract(one_page_pdf("named wrong"), "actually-a-pdf.txt")

    assert "named wrong" in got.text


# ── markup, text, and the refusals ───────────────────────────────────────────

def test_html_keeps_its_content_and_drops_its_code():
    data = (b"<html><head><style>p{color:red}</style>"
            b"<script>var x=1</script></head><body><h1>Otto</h1>"
            b"<p>A travel platform.</p></body></html>")

    got = extract(data, "page.html")

    assert "Otto" in got.text and "A travel platform." in got.text
    assert "color:red" not in got.text and "var x" not in got.text


def test_rtf_control_words_are_stripped():
    data = rb"{\rtf1\ansi\deff0 {\b Pricing} was agreed\par}"

    assert "Pricing" in extract(data, "note.rtf").text


def test_plain_text_and_csv_are_read_as_themselves():
    assert extract(b"a,b\n1,2", "data.csv").text == "a,b\n1,2"
    assert extract(b"# Title\n\nbody", "readme.md").kind == "text"


def test_a_legacy_office_binary_is_refused_by_name():
    """.doc is not .docx. Saying "a pre-2007 Word binary" tells the reader to
    convert it; "unsupported" tells them nothing."""
    with pytest.raises(UnreadableDocument, match="pre-2007 Word binary"):
        extract(b"\xd0\xcf\x11\xe0garbage", "contract.doc")


def test_an_image_is_refused_as_an_image():
    with pytest.raises(UnreadableDocument, match="an image"):
        extract(b"\x89PNG\r\n\x1a\n\x00\x00", "diagram.png")


def test_an_archive_says_its_contents_are_not_read():
    with pytest.raises(UnreadableDocument, match="the files inside it are not read"):
        extract(zipped({"inner/file.txt": "hi"}), "bundle.zip")


def test_an_office_file_that_is_genuinely_empty_says_so():
    """Distinct from unreadable: the format was understood and held nothing."""
    data = zipped({"word/document.xml": f"<w:document {W}><w:body/></w:document>"})

    with pytest.raises(UnreadableDocument, match="no text in it"):
        extract(data, "blank.docx")


def test_a_damaged_office_file_says_it_is_damaged():
    data = zipped({"word/document.xml": "<w:document><not closed"})

    with pytest.raises(UnreadableDocument, match="damaged"):
        extract(data, "broken.docx")


def test_an_unknown_binary_lists_what_would_have_worked():
    with pytest.raises(UnreadableDocument, match="Office and OpenDocument"):
        extract(b"\x00\x01\x02\x03" * 100, "mystery.bin")


# ── the table a sheet already was ────────────────────────────────────────────
#
# _xlsx walked every row into cells and then joined them with tabs one line
# later. The structure existed and was being thrown away, so a spreadsheet could
# be quoted but never charted.


def test_a_spreadsheet_keeps_its_rows_as_well_as_its_text():
    data = xlsx([["Sr.no", "Amount"], ["1", "46265.0"]], shared=["Sr.no", "Amount"])

    got = extract(data, "figures.xlsx")

    assert got.columns == ["Sr.no", "Amount"]
    assert got.rows == [["1", "46265.0"]]
    # And the text is unchanged, because the agent still reads that.
    assert "46265.0" in got.text


def test_the_first_row_becomes_the_columns_only_when_it_looks_like_headings():
    # A sheet whose first row is already data must not lose that row to a header
    # it never had.
    got = extract(xlsx([["1", "46265.0"], ["2", "51200.0"]], shared=[]), "figures.xlsx")

    assert got.columns == ["column 1", "column 2"]
    assert got.rows == [["1", "46265.0"], ["2", "51200.0"]]


def test_a_sheet_of_only_headings_is_not_read_as_a_header_with_no_data():
    # One row that looks like headings is a one-row table, not an empty one.
    got = extract(xlsx([["Name", "Owner"]], shared=["Name", "Owner"]), "one.xlsx")

    assert got.rows == [["Name", "Owner"]]


def test_a_ragged_row_is_padded_to_the_column_count():
    # A row shorter than its header misaligns every cell after the gap.
    got = extract(xlsx([["A", "B", "C"], ["1"]], shared=["A", "B", "C"]), "ragged.xlsx")

    assert got.rows == [["1", "", ""]]


def test_a_document_that_is_not_a_spreadsheet_carries_no_rows():
    docx = zipped({
        "[Content_Types].xml": "<Types/>",
        "word/document.xml":
            '<document xmlns="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<body><p><r><t>Just a paragraph.</t></r></p></body></document>",
    })

    got = extract(docx, "notes.docx")

    assert got.rows is None
    assert got.columns is None


def _odf_bytes(mimetype: str, content: str) -> bytes:
    return zipped({"mimetype": mimetype, "content.xml": content})


ODF_NS = ('xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
          'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"')

SHEET = (f"<document {ODF_NS}><table:table>"
         "<table:table-row><table:table-cell><text:p>Name</text:p></table:table-cell>"
         "<table:table-cell><text:p>Hours</text:p></table:table-cell></table:table-row>"
         "<table:table-row><table:table-cell><text:p>Sahil</text:p></table:table-cell>"
         "<table:table-cell><text:p>12</text:p></table:table-cell></table:table-row>"
         "</table:table></document>")


def test_an_opendocument_spreadsheet_carries_its_rows():
    got = extract(_odf_bytes("application/vnd.oasis.opendocument.spreadsheet", SHEET),
                  "hours.ods")

    assert got.columns == ["Name", "Hours"]
    assert got.rows == [["Sahil", "12"]]


def test_a_table_inside_a_text_document_is_not_treated_as_its_data():
    # The reason rows are gated on the declared mimetype rather than on "it
    # contains a table". A table in a .odt illustrates the prose around it; it is
    # not the record, and charting it would be a confident wrong answer.
    got = extract(_odf_bytes("application/vnd.oasis.opendocument.text", SHEET),
                  "report.odt")

    assert got.rows is None
    assert got.columns is None
    # The table's contents still reach the model as text, as they always did.
    assert "Sahil" in got.text
