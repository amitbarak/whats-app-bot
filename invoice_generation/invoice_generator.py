from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime
from _random import Random
BITS_COUNT_IN_INVOICE_ID = 16

def get_invoice_number():
    random_number_generator = Random()
    return random_number_generator.getrandbits(BITS_COUNT_IN_INVOICE_ID)

def generate_invoice(your_info, client_info, items, output_file='invoice.pdf', invoice_number = get_invoice_number()):
    doc = SimpleDocTemplate(output_file, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    # Header
    story.append(Paragraph(f"<b>INVOICE #{invoice_number}</b>", styles['Title']))
    story.append(Spacer(1, 12))

    # Company Info
    story.append(Paragraph("<b>Your Info:</b><br/>" + "<br/>".join(your_info), styles['Normal']))
    story.append(Spacer(1, 12))

    # Client Info
    story.append(Paragraph("<b>Bill To:</b><br/>" + "<br/>".join(client_info), styles['Normal']))
    story.append(Spacer(1, 24))

    # Table data
    table_data = [["Item", "Quantity", "Unit Price", "Total"]]
    total_amount = 0
    for desc, qty, unit_price in items:
        total = qty * unit_price
        total_amount += total
        table_data.append([desc, str(qty), f"${unit_price:.2f}", f"${total:.2f}"])

    # Add Total Row
    table_data.append(["", "", "<b>Total</b>", f"<b>${total_amount:.2f}</b>"])

    # Create table
    table = Table(table_data, hAlign='LEFT')
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")
    ]))

    story.append(table)
    story.append(Spacer(1, 24))

    # Footer
    story.append(Paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d')}", styles['Normal']))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Thank you for your business!", styles['Normal']))

    doc.build(story)
    print(f"Invoice saved to {output_file}")

# Example usage
if __name__ == "__main__":
    my_info = ["My Company", "123 Main St", "City, Country", "Email: info@company.com"]
    client_info = ["Client Name", "456 Client St", "Client City, Country", "Email: client@example.com"]
    items = [
        ("Website Design", 1, 500),
        ("Hosting (12 months)", 1, 120),
        ("Domain Registration", 1, 15)
    ]

    generate_invoice("001", my_info, client_info, items, output_file="invoice_001.pdf")
