"""Build the 88-entry MCP integration audit from the supplied curated PDF."""

from pathlib import Path
import re
import sys
from xml.sax.saxutils import escape

from PyPDF2 import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak


ROOT = Path(__file__).resolve().parents[1]
if len(sys.argv) != 2:
    raise SystemExit('Usage: python scripts/build_curated_status_pdf.py <curated-source.pdf>')
SOURCE = Path(sys.argv[1])
DEST = ROOT / 'output/pdf/curated-mcp-integration-status.pdf'

EXISTING = {
    1: 'Notion catalog; vendor OAuth.', 2: 'Confluence catalog using Atlassian remote MCP.',
    9: 'Guru catalog; remote sign-in.', 11: 'Egnyte catalog; remote sign-in.',
    12: 'Airtable catalog; remote sign-in.', 14: 'Readwise catalog; remote sign-in.',
    17: 'Fireflies catalog; remote sign-in.', 18: 'Granola catalog; remote sign-in.',
    19: 'Otter catalog; remote sign-in.', 20: 'Fathom catalog; remote sign-in.',
    21: 'Grain catalog; remote sign-in.', 23: 'Circleback catalog; remote sign-in.',
    25: 'Krisp catalog; remote sign-in.', 30: 'Linear catalog; read-only remote MCP.',
    31: 'Jira is covered by the existing catalog.', 32: 'GitHub is covered by the existing catalog.',
    33: 'Asana catalog; remote sign-in.', 34: 'ClickUp catalog; remote sign-in.',
    35: 'monday.com catalog; remote sign-in.', 36: 'Trello catalog; remote sign-in.',
    38: 'GitLab catalog; remote sign-in.', 39: 'Sentry catalog; remote sign-in.',
    46: 'HubSpot catalog; remote sign-in.', 47: 'Attio catalog; remote sign-in.',
    48: 'Close catalog; remote sign-in.', 49: 'Intercom catalog; remote sign-in.',
    60: 'BigQuery catalog; Google-hosted MCP.', 63: 'Supabase catalog; remote sign-in.',
    64: 'Neon catalog; remote sign-in.', 66: 'PlanetScale Insights catalog.',
    74: 'PostHog catalog; remote sign-in.', 75: 'Mixpanel catalog; remote sign-in.',
    76: 'Amplitude catalog; remote sign-in.',
}
BRANCH = {
    10: 'Box catalog copied from the separate vendor-agent branch; remote vendor endpoint.',
    26: 'Zoom catalog copied from the separate vendor-agent branch; remote vendor endpoint.',
    44: 'Salesforce read-only catalog included from the Salesforce branch.',
    67: 'MongoDB Atlas catalog copied from the separate vendor-agent branch.',
    68: 'ClickHouse catalog copied from the separate vendor-agent branch.',
    70: 'MotherDuck read-only hosted catalog included; PDF listed an older local setup.',
}
LOCAL = {3, 4, 5, 6, 7, 8, 13, 22, 27, 28, 29, 37, 40, 41, 42, 43,
         45, 54, 55, 57, 59, 61, 62, 65, 69, 72, 73, 84, 87, 88}
TENANT = {15, 50, 56, 58, 71, 81, 82, 83}
RESEARCH = {
    16: 'Official Mem-hosted endpoint reported; verify live tool list, access and logo before catalog.',
    24: 'Official Fellow endpoint and read tools documented; live connection and logo review pending.',
    51: 'Official Clarify endpoint and read tools documented; live connection and logo review pending.',
    52: 'Day AI endpoint and live tools still need first-party verification.',
    53: 'Official Outreach endpoint and read tools documented; live connection and logo review pending.',
    77: 'Verify Pendo endpoint, authentication and live tools from first-party documentation.',
    78: 'Verify Contentsquare endpoint, authentication and live tools from first-party documentation.',
    79: 'Verify Hex endpoint, authentication and live tools from first-party documentation.',
    80: 'Verify Omni endpoint, authentication and live tools from first-party documentation.',
    85: 'Verify Similarweb endpoint, authentication and live tools from first-party documentation.',
}


def entries():
    text = '\n'.join(page.extract_text() for page in PdfReader(str(SOURCE)).pages[:4])
    pattern = r'(?ms)^(\d{1,2}) (Docs|Meeting notes|Ticketing|CRM|Databases|Analytics) (.*?)(?=^\d{1,2} (?:Docs|Meeting notes|Ticketing|CRM|Databases|Analytics) |^Key:)'
    found = re.findall(pattern, text)
    assert len(found) == 88, f'Expected 88 rows, found {len(found)}'
    rows = []
    for number, category, raw in found:
        number = int(number)
        first = re.split(r'(?:\s|\))(?=Yes|Community|Vendor \(CData\))', raw.replace('\n', ' '), maxsplit=1)[0]
        name = re.sub(r'\s+', ' ', first).strip()
        name = re.sub(r'(?:Yes|Community|Vendor \(CData\)).*$', '', name).strip()
        if number in EXISTING:
            status, reason = 'Integrated', EXISTING[number]
        elif number in BRANCH:
            status, reason = 'On this branch', BRANCH[number]
        elif number in LOCAL:
            status, reason = 'Excluded', 'Customer/local server or third-party wrapper; no fixed original-vendor hosted endpoint.'
        elif number in TENANT:
            status, reason = 'Deferred', 'Customer-specific deployment or endpoint; current catalog requires one fixed service URL.'
        else:
            status, reason = 'Verification pending', RESEARCH.get(number, 'Verify vendor-owned fixed endpoint, authentication and live tools before publishing.')
        if number == 56:
            reason = 'Databricks Labs project is experimental/deprecated; managed endpoint is workspace-specific.'
        elif number == 58:
            reason = 'Snowflake Labs local server is deprecated; managed endpoint is account-specific.'
        elif number == 50:
            reason = 'Zoho MCP requires the customer to build a server; no ready-made fixed CRM endpoint.'
        elif number == 55:
            reason = 'CData wrapper is third-party and local, not a Pipedrive-hosted MCP.'
        elif number == 86:
            status, reason = 'Excluded', 'QuerySail is a third-party hosted wrapper, not a Google-hosted MCP.'
        rows.append((number, category, name, status, reason))
    assert [r[0] for r in rows] == list(range(1, 89))
    return rows


def build():
    DEST.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleCustom', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=19, leading=23, textColor=colors.HexColor('#12233B')))
    styles.add(ParagraphStyle(name='SmallCustom', parent=styles['BodyText'], fontSize=8, leading=11, spaceAfter=3))
    styles.add(ParagraphStyle(name='CellCustom', parent=styles['BodyText'], fontSize=7, leading=9))
    styles.add(ParagraphStyle(name='HeaderCustom', parent=styles['BodyText'], fontName='Helvetica-Bold', fontSize=7, leading=9, textColor=colors.white))
    doc = SimpleDocTemplate(str(DEST), pagesize=(8.5*inch, 11*inch), rightMargin=36, leftMargin=36, topMargin=40, bottomMargin=40)
    rows = entries()
    counts = {s: sum(r[3] == s for r in rows) for s in ['Integrated', 'On this branch', 'Excluded', 'Deferred', 'Verification pending']}
    story = [Paragraph('Curated MCP integration status', styles['TitleCustom']),
             Paragraph('Audit of all 88 entries in the October 2026 curated shortlist | 9 November 2026', styles['SmallCustom']),
             Paragraph('Integrated means a catalog exists on the checked upstream/main snapshot. On this branch means a catalog file has been brought into codex/curated-vendor-mcps. These labels do not mean the MCP has been published or live-tested with credentials.', styles['SmallCustom']),
             Paragraph('Status counts: ' + '  |  '.join(f'{k}: {v}' for k, v in counts.items()), styles['SmallCustom']),
             Spacer(1, 8)]
    for category in ['Docs', 'Meeting notes', 'Ticketing', 'CRM', 'Databases', 'Analytics']:
        story.append(Paragraph(escape(category), styles['Heading2']))
        data = [[Paragraph(x, styles['HeaderCustom']) for x in ['#', 'MCP', 'Status', 'How / why']]]
        for n, cat, name, status, reason in rows:
            if cat != category:
                continue
            data.append([Paragraph(str(n), styles['CellCustom']), Paragraph(escape(name), styles['CellCustom']),
                         Paragraph(escape(status), styles['CellCustom']), Paragraph(escape(reason), styles['CellCustom'])])
        table = Table(data, colWidths=[25, 142, 87, 286], repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#172B48')),
            ('VALIGN',(0,0),(-1,-1),'TOP'), ('GRID',(0,0),(-1,-1),0.25,colors.HexColor('#D8DFE8')),
            ('LEFTPADDING',(0,0),(-1,-1),5), ('RIGHTPADDING',(0,0),(-1,-1),5),
            ('TOPPADDING',(0,0),(-1,-1),5), ('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.extend([table, Spacer(1, 13)])
    story.append(Paragraph('Verification notes', styles['Heading2']))
    notes = [
        'The source PDF is a directory snapshot, not a live vendor specification. Remote and official claims require current first-party confirmation before publication.',
        'Tenant-specific vendor MCPs are deferred because the current catalog has one fixed service.url. No fabricated shared endpoint is used.',
        'Fellow: https://developers.fellow.ai/reference/mcp-server ; Clarify: https://docs.clarify.ai/en/articles/13367278-clarify-mcp ; Outreach: https://developers.outreach.io/mcp-server/tool-catalog',
        'Databricks and Snowflake endpoint assessment: repository docs/databricks-and-snowflake.md. Source shortlist: mcp-servers-curated (1).pdf, prepared October 2026.'
    ]
    for note in notes:
        story.append(Paragraph(escape(note), styles['SmallCustom']))
    doc.build(story)
    print(DEST, counts)


if __name__ == '__main__':
    build()
