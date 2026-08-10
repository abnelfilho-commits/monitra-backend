"""
Renderer PDF do Report Engine.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from ..models import CanonicalReport
from .base_renderer import BaseRenderer


class PDFRenderer(BaseRenderer):
    """
    Renderiza um CanonicalReport em PDF.
    """

    code = "PDF"

    def render(
        self,
        report: CanonicalReport,
        output_path: str,
    ) -> str:

        styles = getSampleStyleSheet()

        document = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        story = []

        story.append(
            Paragraph(
                report.report_name,
                styles["Title"],
            )
        )

        story.append(
            Spacer(1, 0.4 * cm)
        )

        subject_name = (
            report.subject.get("nome")
            or report.subject.get("name")
            or f"Paciente {report.subject.get('id', '')}"
        )

        story.append(
            Paragraph(
                f"<b>Paciente:</b> {subject_name}",
                styles["BodyText"],
            )
        )

        story.append(
            Paragraph(
                (
                    f"<b>Período:</b> "
                    f"{report.period_start} a {report.period_end}"
                ),
                styles["BodyText"],
            )
        )

        story.append(
            Spacer(1, 0.7 * cm)
        )

        for section in report.sections:

            story.append(
                Paragraph(
                    section.title,
                    styles["Heading2"],
                )
            )

            story.append(
                Spacer(1, 0.2 * cm)
            )

            for component in section.components:

                if component.type == "TEXT":
                    content = str(
                        component.data or ""
                    )

                    paragraphs = content.split("\n\n")

                    for paragraph in paragraphs:

                        if not paragraph.strip():
                            continue

                        story.append(
                            Paragraph(
                                paragraph,
                                styles["BodyText"],
                            )
                        )

                        story.append(
                            Spacer(1, 0.25 * cm)
                        )

            story.append(
                Spacer(1, 0.5 * cm)
            )

        document.build(story)

        return output_path