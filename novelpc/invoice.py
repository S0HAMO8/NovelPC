"""
Invoice PDF generator (item 8).
Builds a simple, clean order invoice as a PDF using reportlab — a pure-Python
library with no system dependencies, so it installs cleanly on Windows/Mac/Linux
via plain `pip install reportlab`.
"""
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER


def generate_invoice_pdf(build, user, components):
    """
    build: Build model instance (must be status='ordered')
    user: User model instance
    components: list of Component model instances in the build
    Returns: BytesIO buffer containing the PDF
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm,
        leftMargin=18 * mm, rightMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleBlue', parent=styles['Title'], textColor=colors.HexColor('#0b1018'), fontSize=22)
    label_style = ParagraphStyle('Label', parent=styles['Normal'], textColor=colors.HexColor('#5a7a9a'), fontSize=9)
    value_style = ParagraphStyle('Value', parent=styles['Normal'], textColor=colors.HexColor('#0b1018'), fontSize=10)
    right_style = ParagraphStyle('Right', parent=styles['Normal'], alignment=TA_RIGHT, fontSize=10)
    center_small = ParagraphStyle('CenterSmall', parent=styles['Normal'], alignment=TA_CENTER, fontSize=8, textColor=colors.HexColor('#5a7a9a'))

    elements = []

    # ── Header ──
    elements.append(Paragraph("novelPC", title_style))
    elements.append(Paragraph("Gaming PC Builder — Order Invoice", label_style))
    elements.append(Spacer(1, 10 * mm))

    # ── Order meta info ──
    ordered_on = build.ordered_at.strftime('%d %B %Y, %I:%M %p') if build.ordered_at else '—'
    delivery = build.delivery_date.strftime('%d %B %Y') if build.delivery_date else '—'
    meta_data = [
        [Paragraph("Invoice For", label_style), Paragraph("Order Details", label_style)],
        [
            Paragraph(f"<b>{user.username}</b><br/>{user.email}<br/>{user.phone or '—'}<br/>{user.address or '—'}", value_style),
            Paragraph(
                f"<b>Order #:</b> {build.id}<br/>"
                f"<b>Ordered On:</b> {ordered_on}<br/>"
                f"<b>Payment Method:</b> {(build.payment_method or '—').upper()}<br/>"
                f"<b>Estimated Delivery:</b> {delivery}<br/>"
                f"<b>Status:</b> {build.status.upper()}",
                value_style
            ),
        ],
    ]
    meta_table = Table(meta_data, colWidths=[85 * mm, 85 * mm])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 8 * mm))

    # ── Component line items ──
    table_data = [["Type", "Component", "Brand", "Price (Rs.)"]]
    for comp in components:
        table_data.append([
            comp.type.replace('_', ' ').upper(),
            comp.name,
            comp.brand or '—',
            f"{comp.price:,.0f}"
        ])

    item_table = Table(table_data, colWidths=[28 * mm, 75 * mm, 35 * mm, 32 * mm])
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0b1018')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d0d0d0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f7fa')]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 6 * mm))

    # ── Customizations / add-ons ──
    if build.description:
        # reportlab's base Helvetica font has no ₹ glyph (renders as a black box),
        # so swap it for "Rs." which is guaranteed to render in any PDF viewer.
        safe_description = build.description.replace('₹', 'Rs. ')
        elements.append(Paragraph("<b>Customizations:</b>", value_style))
        elements.append(Paragraph(safe_description, label_style))
        elements.append(Spacer(1, 4 * mm))

    # ── Totals ──
    base_total = build.total_price or 0
    extras = build.extras_price or 0
    grand_total = base_total + extras
    totals_data = [
        ["Components Subtotal", f"Rs. {base_total:,.0f}"],
        ["Customizations / Add-ons", f"Rs. {extras:,.0f}"],
        ["Grand Total (Paid 100%)", f"Rs. {grand_total:,.0f}"],
    ]
    totals_table = Table(totals_data, colWidths=[138 * mm, 32 * mm])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('LINEABOVE', (0, 2), (-1, 2), 1, colors.HexColor('#0b1018')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(totals_table)
    elements.append(Spacer(1, 12 * mm))

    elements.append(Paragraph(
        "This is a system-generated invoice for a simulated college-project order. "
        "No real payment was processed.",
        center_small
    ))
    elements.append(Paragraph("Thank you for building with novelPC!", center_small))

    doc.build(elements)
    buffer.seek(0)
    return buffer
