"""
Renderer PDF do Report Engine.
"""
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    KeepTogether,
)

from ..models import CanonicalReport
from .base_renderer import BaseRenderer

from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    KeepTogether,
    Table,
    TableStyle,
)


class PDFRenderer(BaseRenderer):
    """
    Renderiza um CanonicalReport em PDF.
    """

    code = "PDF"

    @staticmethod
    def _build_styles():

        base_styles = getSampleStyleSheet()

        return {
            "title": ParagraphStyle(
                name="IntegraCareTitle",
                parent=base_styles["Title"],
                fontName="Helvetica-Bold",
                fontSize=20,
                leading=24,
                alignment=TA_LEFT,
                spaceAfter=12,
                textColor=colors.HexColor("#0F172A"),
            ),

            "metadata": ParagraphStyle(
                name="IntegraCareMetadata",
                parent=base_styles["BodyText"],
                fontName="Helvetica",
                fontSize=9,
                leading=13,
                textColor=colors.HexColor("#64748B"),
            ),

            "section": ParagraphStyle(
                name="IntegraCareSection",
                parent=base_styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=15,
                spaceBefore=10,
                spaceAfter=7,
                textColor=colors.HexColor("#1D4ED8"),
            ),

            "body": ParagraphStyle(
                name="IntegraCareBody",
                parent=base_styles["BodyText"],
                fontName="Helvetica",
                fontSize=10,
                leading=15,
                spaceAfter=6,
                textColor=colors.HexColor("#0F172A"),
            ),
            
            "status_value": ParagraphStyle(
                name="IntegraCareStatusValue",
                parent=base_styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=11,
                leading=14,
                textColor=colors.HexColor("#0F172A"),
            ),
            
            "indicator_value": ParagraphStyle(
                name="IntegraCareIndicatorValue",
                parent=base_styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=11,
                leading=14,
                textColor=colors.HexColor("#0F172A"),
                alignment=TA_CENTER,
            ),

            "indicator_label": ParagraphStyle(
                name="IntegraCareIndicatorLabel",
                parent=base_styles["BodyText"],
                fontName="Helvetica",
                fontSize=8,
                leading=10,
                textColor=colors.HexColor("#64748B"),
                alignment=TA_CENTER,
            ),
        }

    ASSETS_DIR = Path(__file__).resolve().parent / "assets"

    LOGO_PATH = ASSETS_DIR / "logo-integracare.png"

    @staticmethod
    def _draw_page(canvas, document):
        """
        Desenha cabeçalho e rodapé em todas as páginas.
        """

        canvas.saveState()

        width, height = A4

        # ======================================================
        # CABEÇALHO
        # ======================================================

        # Integra Care
        if PDFRenderer.LOGO_PATH.exists():
            canvas.drawImage(
                str(PDFRenderer.LOGO_PATH),
                2 * cm,
                height - 2.15 * cm,
                width=4.5 * cm,
                height=2.25 * cm,
                preserveAspectRatio=True,
                mask="auto",
                anchor="w",
            )

        # Nome do relatório
        canvas.setFillColor(
            colors.HexColor("#64748B")
        )

        canvas.setFont(
            "Helvetica",
            8,
        )

        canvas.drawRightString(
            width - 2 * cm,
            height - 1.55 * cm,
            "Relatório Longitudinal Inteligente",
        )

        # Linha do cabeçalho
        canvas.setStrokeColor(
            colors.HexColor("#2563EB")
        )

        canvas.setLineWidth(0.8)

        canvas.line(
            2 * cm,
            height - 2.05 * cm,
            width - 2 * cm,
            height - 2.05 * cm,
        )

        # ======================================================
        # RODAPÉ
        # ======================================================

        # Linha do rodapé
        canvas.setStrokeColor(
            colors.HexColor("#E2E8F0")
        )

        canvas.setLineWidth(0.5)

        canvas.line(
            2 * cm,
            1.35 * cm,
            width - 2 * cm,
            1.35 * cm,
        )

        # Textos do rodapé
        canvas.setFillColor(
            colors.HexColor("#64748B")
        )

        canvas.setFont(
            "Helvetica",
            7,
        )

        canvas.drawString(
            2 * cm,
            0.9 * cm,
            "Integra Care Health Platform",
        )

        canvas.drawRightString(
            width - 2 * cm,
            0.9 * cm,
            f"Página {document.page}",
        )

        canvas.restoreState()

    def render(
        self,
        report: CanonicalReport,
        output_path: str,
    ) -> str:

        styles = self._build_styles()

        document = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2.8 * cm,
            bottomMargin=2 * cm,
        )

        story = []

        story.append(
            Paragraph(
                report.report_name,
                styles["title"],
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
                styles["metadata"],
            )
        )

        story.append(
            Paragraph(
                (
                    f"<b>Data de geração:</b> "
                    f"{report.generated_at.strftime('%d/%m/%Y')}"
                ),
                styles["metadata"],
            )
        )

        story.append(
            Spacer(1, 0.7 * cm)
        )

        for section in report.sections:

            section_story = []

            section_story.append(
                Paragraph(
                    section.title,
                    styles["section"],
                )
            )

            story.append(
                Spacer(1, 0.2 * cm)
            )

            for component in section.components:

                if component.type == "STATUS_CARD":

                    data = component.data or {}

                    risk = (
                        str(data.get("risk") or "sem_dados")
                        .replace("_", " ")
                        .title()
                    )

                    trend_raw = str(
                        data.get("trend") or "sem_dados"
                    ).lower()

                    trend = {
                        "estavel": "Estável",
                        "melhora": "Melhora",
                        "piora": "Piora",
                    }.get(
                        trend_raw,
                        trend_raw.replace("_", " ").title(),
                    )

                    clinical_moment_raw = str(
                        data.get("clinical_moment") or "sem_dados"
                    ).lower()

                    clinical_moment = {
                        "estavel": "Estável",
                        "melhora": "Melhora",
                        "piora": "Piora",
                    }.get(
                        clinical_moment_raw,
                        clinical_moment_raw.replace("_", " ").title(),
                    )

                    protocol = (
                        data.get("protocol")
                        or "Não informado"
                    )

                    card_data = [
                        [
                            Paragraph(
                                "<b>Risco atual</b>",
                                styles["metadata"],
                            ),
                            Paragraph(
                                "<b>Tendência</b>",
                                styles["metadata"],
                            ),
                            Paragraph(
                                "<b>Momento clínico</b>",
                                styles["metadata"],
                            ),
                        ],
                        [
                            Paragraph(
                                risk,
                                styles["status_value"],
                            ),
                            Paragraph(
                                trend,
                                styles["status_value"],
                            ),
                            Paragraph(
                                clinical_moment,
                                styles["status_value"],
                            ),
                        ],
                        [
                            Paragraph(
                                "<b>Protocolo assistencial</b>",
                                styles["metadata"],
                            ),
                            "",
                            "",
                        ],
                        [
                            Paragraph(
                                str(protocol),
                                styles["body"],
                            ),
                            "",
                            "",
                        ],
                    ]

                    card = Table(
                        card_data,
                        colWidths=[
                            5.2 * cm,
                            5.2 * cm,
                            5.2 * cm,
                        ],
                    )

                    card.setStyle(
                        TableStyle(
                            [
                                (
                                    "BACKGROUND",
                                    (0, 0),
                                    (-1, -1),
                                    colors.HexColor("#F8FAFC"),
                                ),
                                (
                                    "BOX",
                                    (0, 0),
                                    (-1, -1),
                                    0.7,
                                    colors.HexColor("#E2E8F0"),
                                ),
                                (
                                    "LINEABOVE",
                                    (0, 2),
                                    (-1, 2),
                                    0.4,
                                    colors.HexColor("#E2E8F0"),
                                ),
                                (
                                    "SPAN",
                                    (0, 2),
                                    (2, 2),
                                ),
                                (
                                    "SPAN",
                                    (0, 3),
                                    (2, 3),
                                ),
                                (
                                    "TOPPADDING",
                                    (0, 0),
                                    (-1, -1),
                                    8,
                                ),
                                (
                                    "BOTTOMPADDING",
                                    (0, 0),
                                    (-1, -1),
                                    8,
                                ),
                                (
                                    "LEFTPADDING",
                                    (0, 0),
                                    (-1, -1),
                                    10,
                                ),
                                (
                                    "RIGHTPADDING",
                                    (0, 0),
                                    (-1, -1),
                                    10,
                                ),
                                (
                                    "VALIGN",
                                    (0, 0),
                                    (-1, -1),
                                    "MIDDLE",
                                ),
                            ]
                        )
                    )

                    section_story.append(card)

                    section_story.append(
                        Spacer(1, 0.35 * cm)
                    )
                    
                if component.type == "JOURNEY_INDICATORS":

                    data = component.data or {}

                    indicators = [
                        ("Eventos", data.get("total_events", 0)),
                        ("Objetivos PTS", data.get("pts_objectives", 0)),
                        ("Sessões", data.get("planned_sessions", 0)),
                        ("Realizadas", data.get("completed_sessions", 0)),
                        ("Agendadas", data.get("scheduled_sessions", 0)),
                    ]

                    cards = []

                    for label, value in indicators:

                        card = Table(
                            [
                                [
                                    Paragraph(
                                        str(value),
                                        styles["indicator_value"],
                                    )
                                ],
                                [
                                    Paragraph(
                                        label,
                                        styles["indicator_label"],
                                    )
                                ],
                            ],
                            colWidths=[2.75 * cm],
                        )

                        card.setStyle(
                            TableStyle(
                                [
                                    (
                                        "BACKGROUND",
                                        (0, 0),
                                        (-1, -1),
                                        colors.HexColor("#F8FAFC"),
                                    ),
                                    (
                                        "BOX",
                                        (0, 0),
                                        (-1, -1),
                                        0.7,
                                        colors.HexColor("#E2E8F0"),
                                    ),
                                    (
                                        "TOPPADDING",
                                        (0, 0),
                                        (-1, -1),
                                        8,
                                    ),
                                    (
                                        "BOTTOMPADDING",
                                        (0, 0),
                                        (-1, -1),
                                        8,
                                    ),
                                    (
                                        "LEFTPADDING",
                                        (0, 0),
                                        (-1, -1),
                                        0,
                                    ),
                                    (
                                        "RIGHTPADDING",
                                        (0, 0),
                                        (-1, -1),
                                        0,
                                    ),
                                    (
                                        "ALIGN",
                                        (0, 0),
                                        (-1, -1),
                                        "CENTER",
                                    ),
                                    (
                                        "VALIGN",
                                        (0, 0),
                                        (-1, -1),
                                        "MIDDLE",
                                    ),
                                ]
                            )
                        )

                        cards.append(card)

                    indicators_table = Table(
                        [cards],
                        colWidths=[
                            3.05 * cm,
                            3.05 * cm,
                            3.05 * cm,
                            3.05 * cm,
                            3.05 * cm,
                        ],
                        hAlign="LEFT",
                    )

                    indicators_table.setStyle(
                        TableStyle(
                            [
                                (
                                    "VALIGN",
                                    (0, 0),
                                    (-1, -1),
                                    "TOP",
                                ),
                                (
                                    "LEFTPADDING",
                                    (0, 0),
                                    (-1, -1),
                                    0,
                                ),
                                (
                                    "RIGHTPADDING",
                                    (0, 0),
                                    (-1, -1),
                                    6,
                                ),
                            ]
                        )
                    )

                    section_story.append(
                        indicators_table
                    )

                    section_story.append(
                        Spacer(1, 0.35 * cm)
                    )
                    
                if component.type == "PTS_EXECUTION":

                    data = component.data or {}

                    status = str(
                        data.get("status") or "SEM_DADOS"
                    ).replace("_", " ").title()

                    total_objectives = data.get(
                        "total_objectives",
                        0,
                    )

                    total_plannings = data.get(
                        "total_plannings",
                        0,
                    )

                    total_sessions = data.get(
                        "total_sessions",
                        0,
                    )

                    completed_sessions = data.get(
                        "completed_sessions",
                        0,
                    )

                    scheduled_sessions = data.get(
                        "scheduled_sessions",
                        0,
                    )

                    missed_sessions = data.get(
                        "missed_sessions",
                        0,
                    )

                    cancelled_sessions = data.get(
                        "cancelled_sessions",
                        0,
                    )

                    execution_rate = data.get(
                        "execution_rate"
                    )

                    if execution_rate is not None:
                        execution_rate = float(
                            execution_rate
                        )

                    summary_table = Table(
                        [
                            [
                                Paragraph(
                                    "<b>Status do PTS</b>",
                                    styles["metadata"],
                                ),
                                Paragraph(
                                    "<b>Objetivos</b>",
                                    styles["indicator_label"],
                                ),
                                Paragraph(
                                    "<b>Planejamentos</b>",
                                    styles["indicator_label"],
                                ),
                            ],
                            [
                                Paragraph(
                                    status,
                                    styles["status_value"],
                                ),
                                Paragraph(
                                    str(total_objectives),
                                    styles["indicator_value"],
                                ),
                                Paragraph(
                                    str(total_plannings),
                                    styles["indicator_value"],
                                ),
                            ],
                        ],
                        colWidths=[
                            5.2 * cm,
                            5.2 * cm,
                            5.2 * cm,
                        ],
                    )

                    summary_table.setStyle(
                        TableStyle(
                            [
                                (
                                    "BACKGROUND",
                                    (0, 0),
                                    (-1, -1),
                                    colors.HexColor("#F8FAFC"),
                                ),
                                (
                                    "BOX",
                                    (0, 0),
                                    (-1, -1),
                                    0.7,
                                    colors.HexColor("#E2E8F0"),
                                ),
                                (
                                    "TOPPADDING",
                                    (0, 0),
                                    (-1, -1),
                                    8,
                                ),
                                (
                                    "BOTTOMPADDING",
                                    (0, 0),
                                    (-1, -1),
                                    8,
                                ),
                                (
                                    "LEFTPADDING",
                                    (0, 0),
                                    (-1, -1),
                                    10,
                                ),
                                (
                                    "RIGHTPADDING",
                                    (0, 0),
                                    (-1, -1),
                                    10,
                                ),
                                (
                                    "VALIGN",
                                    (0, 0),
                                    (-1, -1),
                                    "MIDDLE",
                                ),
                                (
                                    "ALIGN",
                                    (1, 0),
                                    (2, -1),
                                    "CENTER",
                                ),
                            ]
                        )
                    )

                    section_story.append(
                        summary_table
                    )

                    section_story.append(
                        Spacer(1, 0.35 * cm)
                    )

                    section_story.append(
                        Paragraph(
                            "<b>Execução assistencial</b>",
                            styles["metadata"],
                        )
                    )

                    section_story.append(
                        Spacer(1, 0.10 * cm)
                    )

                    if total_sessions > 0:

                        section_story.append(
                            Paragraph(
                                (
                                    f"{completed_sessions} de "
                                    f"{total_sessions} sessões realizadas "
                                    f"({execution_rate:.0f}%)"
                                ),
                                styles["body"],
                            )
                        )

                        section_story.append(
                            Spacer(1, 0.15 * cm)
                        )

                        progress_width = 15.6 * cm

                        completed_width = (
                            progress_width
                            * min(
                                max(execution_rate, 0),
                                100,
                            )
                            / 100
                        )

                        remaining_width = (
                            progress_width
                            - completed_width
                        )

                        progress_table = Table(
                            [[
                                "",
                                "",
                            ]],
                            colWidths=[
                                completed_width,
                                remaining_width,
                            ],
                            rowHeights=[
                                0.22 * cm,
                            ],
                        )

                        progress_table.setStyle(
                            TableStyle(
                                [
                                    (
                                        "BACKGROUND",
                                        (0, 0),
                                        (0, 0),
                                        colors.HexColor("#2563EB"),
                                    ),
                                    (
                                        "BACKGROUND",
                                        (1, 0),
                                        (1, 0),
                                        colors.HexColor("#E2E8F0"),
                                    ),
                                    (
                                        "LEFTPADDING",
                                        (0, 0),
                                        (-1, -1),
                                        0,
                                    ),
                                    (
                                        "RIGHTPADDING",
                                        (0, 0),
                                        (-1, -1),
                                        0,
                                    ),
                                    (
                                        "TOPPADDING",
                                        (0, 0),
                                        (-1, -1),
                                        0,
                                    ),
                                    (
                                        "BOTTOMPADDING",
                                        (0, 0),
                                        (-1, -1),
                                        0,
                                    ),
                                ]
                            )
                        )

                        section_story.append(
                            progress_table
                        )

                        section_story.append(
                            Spacer(1, 0.20 * cm)
                        )

                        section_story.append(
                            Paragraph(
                                (
                                    f"{scheduled_sessions} agendadas"
                                    f" &nbsp;&nbsp;•&nbsp;&nbsp; "
                                    f"{missed_sessions} faltas"
                                    f" &nbsp;&nbsp;•&nbsp;&nbsp; "
                                    f"{cancelled_sessions} canceladas"
                                ),
                                styles["metadata"],
                            )
                        )

                    else:

                        section_story.append(
                            Paragraph(
                                "Sem sessões assistenciais planejadas.",
                                styles["body"],
                            )
                        )

                    section_story.append(
                        Spacer(1, 0.35 * cm)
                    )
                    
                if component.type == "ASSESSMENT_SUMMARY":

                    from datetime import datetime

                    data = component.data or {}

                    assessments = data.get(
                        "assessments",
                        [],
                    )

                    cards = []

                    for assessment in assessments:

                        instrument = (
                            assessment.get("instrument")
                            or "Avaliação"
                        )

                        score = assessment.get("score")

                        classification = (
                            assessment.get("classification")
                            or "Não informado"
                        )

                        raw_date = assessment.get("date")

                        formatted_date = ""

                        if raw_date:
                            try:
                                parsed_date = datetime.fromisoformat(
                                    raw_date.replace(
                                        "Z",
                                        "+00:00",
                                    )
                                )

                                formatted_date = (
                                    parsed_date.strftime(
                                        "%d/%m/%Y"
                                    )
                                )

                            except ValueError:
                                formatted_date = raw_date

                        content = [
                            [
                                Paragraph(
                                    f"<b>{instrument}</b>",
                                    styles["status_value"],
                                )
                            ],
                            [
                                Paragraph(
                                    formatted_date,
                                    styles["metadata"],
                                )
                            ],
                            [
                                Paragraph(
                                    (
                                        f"Score: {score:g}"
                                        if score is not None
                                        else "Score não informado"
                                    ),
                                    styles["body"],
                                )
                            ],
                            [
                                Paragraph(
                                    classification,
                                    styles["body"],
                                )
                            ],
                        ]

                        card = Table(
                            content,
                            colWidths=[
                                3.45 * cm,
                            ],
                        )

                        card.setStyle(
                            TableStyle(
                                [
                                    (
                                        "BACKGROUND",
                                        (0, 0),
                                        (-1, -1),
                                        colors.HexColor("#F8FAFC"),
                                    ),
                                    (
                                        "BOX",
                                        (0, 0),
                                        (-1, -1),
                                        0.7,
                                        colors.HexColor("#E2E8F0"),
                                    ),
                                    (
                                        "TOPPADDING",
                                        (0, 0),
                                        (-1, -1),
                                        7,
                                    ),
                                    (
                                        "BOTTOMPADDING",
                                        (0, 0),
                                        (-1, -1),
                                        7,
                                    ),
                                    (
                                        "LEFTPADDING",
                                        (0, 0),
                                        (-1, -1),
                                        8,
                                    ),
                                    (
                                        "RIGHTPADDING",
                                        (0, 0),
                                        (-1, -1),
                                        8,
                                    ),
                                    (
                                        "VALIGN",
                                        (0, 0),
                                        (-1, -1),
                                        "TOP",
                                    ),
                                ]
                            )
                        )

                        cards.append(card)

                    if cards:

                        assessment_table = Table(
                            [cards],
                            colWidths=[
                                3.85 * cm
                                for _ in cards
                            ],
                            hAlign="LEFT",
                        )

                        assessment_table.setStyle(
                            TableStyle(
                                [
                                    (
                                        "VALIGN",
                                        (0, 0),
                                        (-1, -1),
                                        "TOP",
                                    ),
                                    (
                                        "LEFTPADDING",
                                        (0, 0),
                                        (-1, -1),
                                        0,
                                    ),
                                    (
                                        "RIGHTPADDING",
                                        (0, 0),
                                        (-1, -1),
                                        6,
                                    ),
                                ]
                            )
                        )

                        section_story.append(
                            assessment_table
                        )

                        section_story.append(
                            Spacer(1, 0.35 * cm)
                        )

                if component.type == "DIAGNOSIS_SUMMARY":

                    from datetime import datetime

                    data = component.data or {}

                    cid = (
                        data.get("cid")
                        or "Não informado"
                    )

                    clinical_description = (
                        data.get("clinical_description")
                        or "Não informado"
                    )

                    raw_date = data.get(
                        "diagnosis_date"
                    )

                    formatted_date = ""

                    if raw_date:
                        try:
                            parsed_date = datetime.fromisoformat(
                                raw_date
                            )

                            formatted_date = parsed_date.strftime(
                                "%d/%m/%Y"
                            )

                        except ValueError:
                            formatted_date = raw_date

                    physician_name = (
                        data.get("physician_name")
                        or "Não informado"
                    )

                    physician_specialty = (
                        data.get("physician_specialty")
                        or ""
                    )

                    physician_registry = (
                        data.get("physician_registry")
                        or ""
                    )

                    diagnosis_table = Table(
                        [
                            [
                                Paragraph(
                                    "<b>CID</b>",
                                    styles["metadata"],
                                ),
                                Paragraph(
                                    "<b>Data do diagnóstico</b>",
                                    styles["metadata"],
                                ),
                            ],
                            [
                                Paragraph(
                                    cid,
                                    styles["status_value"],
                                ),
                                Paragraph(
                                    formatted_date,
                                    styles["status_value"],
                                ),
                            ],
                            [
                                Paragraph(
                                    "<b>Descrição clínica</b>",
                                    styles["metadata"],
                                ),
                                "",
                            ],
                            [
                                Paragraph(
                                    clinical_description,
                                    styles["body"],
                                ),
                                "",
                            ],
                            [
                                Paragraph(
                                    "<b>Profissional responsável</b>",
                                    styles["metadata"],
                                ),
                                "",
                            ],
                            [
                                Paragraph(
                                    physician_name,
                                    styles["body"],
                                ),
                                "",
                            ],
                            [
                                Paragraph(
                                    (
                                        f"{physician_specialty}"
                                        f"{' · ' if physician_specialty and physician_registry else ''}"
                                        f"{physician_registry}"
                                    ),
                                    styles["metadata"],
                                ),
                                "",
                            ],
                        ],
                        colWidths=[
                            7.8 * cm,
                            7.8 * cm,
                        ],
                    )

                    diagnosis_table.setStyle(
                        TableStyle(
                            [
                                (
                                    "BACKGROUND",
                                    (0, 0),
                                    (-1, -1),
                                    colors.HexColor("#F8FAFC"),
                                ),
                                (
                                    "BOX",
                                    (0, 0),
                                    (-1, -1),
                                    0.7,
                                    colors.HexColor("#E2E8F0"),
                                ),
                                (
                                    "SPAN",
                                    (0, 2),
                                    (1, 2),
                                ),
                                (
                                    "SPAN",
                                    (0, 3),
                                    (1, 3),
                                ),
                                (
                                    "SPAN",
                                    (0, 4),
                                    (1, 4),
                                ),
                                (
                                    "SPAN",
                                    (0, 5),
                                    (1, 5),
                                ),
                                (
                                    "SPAN",
                                    (0, 6),
                                    (1, 6),
                                ),
                                (
                                    "LINEABOVE",
                                    (0, 2),
                                    (-1, 2),
                                    0.4,
                                    colors.HexColor("#E2E8F0"),
                                ),
                                (
                                    "LINEABOVE",
                                    (0, 4),
                                    (-1, 4),
                                    0.4,
                                    colors.HexColor("#E2E8F0"),
                                ),
                                (
                                    "TOPPADDING",
                                    (0, 0),
                                    (-1, -1),
                                    7,
                                ),
                                (
                                    "BOTTOMPADDING",
                                    (0, 0),
                                    (-1, -1),
                                    7,
                                ),
                                (
                                    "LEFTPADDING",
                                    (0, 0),
                                    (-1, -1),
                                    10,
                                ),
                                (
                                    "RIGHTPADDING",
                                    (0, 0),
                                    (-1, -1),
                                    10,
                                ),
                                (
                                    "VALIGN",
                                    (0, 0),
                                    (-1, -1),
                                    "TOP",
                                ),
                            ]
                        )
                    )

                    section_story.append(
                        diagnosis_table
                    )

                    section_story.append(
                        Spacer(1, 0.35 * cm)
                    )

                if component.type == "TEXT":
                    content = str(
                        component.data or ""
                    )

                    paragraphs = content.split("\n\n")

                    for paragraph in paragraphs:

                        if not paragraph.strip():
                            continue

                        section_story.append(
                            Paragraph(
                                paragraph,
                                styles["body"],
                            )
                        )

                        section_story.append(
                            Spacer(1, 0.25 * cm)
                        )
                        
            story.append(
                KeepTogether(section_story)
            )
            story.append(
                Spacer(1, 0.5 * cm)
            )

        document.build(
            story,
            onFirstPage=self._draw_page,
            onLaterPages=self._draw_page,
        )

        return output_path