from io import BytesIO
from pathlib import Path
from typing import Optional
from datetime import datetime, date

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def calcular_idade(data_nascimento):
    if not data_nascimento:
        return None

    if isinstance(data_nascimento, str):
        try:
            data_nascimento = datetime.fromisoformat(data_nascimento).date()
        except ValueError:
            return None

    hoje = date.today()
    return hoje.year - data_nascimento.year - (
        (hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day)
    )


def formatar_data_br(data_valor):
    if not data_valor:
        return "-"

    if isinstance(data_valor, str):
        try:
            data_valor = datetime.fromisoformat(data_valor).date()
        except ValueError:
            return str(data_valor)

    if hasattr(data_valor, "strftime"):
        return data_valor.strftime("%d/%m/%Y")

    return str(data_valor)


def formatar_data_hora_br(data_valor):
    if not data_valor:
        return "-"

    if isinstance(data_valor, str):
        try:
            dt = datetime.fromisoformat(data_valor)
            # Se vier meia-noite exata, exibe só data
            if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
                return dt.strftime("%d/%m/%Y")
            return dt.strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return str(data_valor)

    if isinstance(data_valor, datetime):
        if data_valor.hour == 0 and data_valor.minute == 0 and data_valor.second == 0:
            return data_valor.strftime("%d/%m/%Y")
        return data_valor.strftime("%d/%m/%Y %H:%M")

    if hasattr(data_valor, "strftime"):
        return data_valor.strftime("%d/%m/%Y")

    return str(data_valor)


def classificar_status_paciente(eventos: list[dict]) -> str:
    if not eventos:
        return "sem_dados"

    registros = [e for e in eventos if e.get("tipo_evento") == "REGISTRO_DIARIO"]
    if not registros:
        return "sem_dados"

    score = 0

    for r in registros:
        texto = (r.get("descricao") or "").lower()

        if "sono: muito bom" in texto or "sono: bom" in texto:
            score += 1
        if "irritabilidade: nenhuma" in texto or "irritabilidade: leve" in texto:
            score += 1
        if "crise sensorial: não" in texto or "crise sensorial: nao" in texto:
            score += 1

        if "sono: ruim" in texto or "sono: muito ruim" in texto:
            score -= 1
        if "irritabilidade: alta" in texto or "irritabilidade: muito alta" in texto:
            score -= 1
        if "crise sensorial: alta" in texto:
            score -= 1

    if score >= 2:
        return "verde"
    if score <= -2:
        return "vermelho"
    return "amarelo"


def cor_status(status: str):
    if status == "verde":
        return HexColor("#22c55e")
    if status == "amarelo":
        return HexColor("#eab308")
    if status == "vermelho":
        return HexColor("#ef4444")
    return HexColor("#9ca3af")


def label_status(status: str) -> str:
    if status == "verde":
        return "Ótimo"
    if status == "amarelo":
        return "Alerta"
    if status == "vermelho":
        return "Piorou"
    return "Sem dados clínicos"


def extrair_score_clinico(eventos: list[dict]) -> dict:
    registros = [e for e in eventos if e.get("tipo_evento") == "REGISTRO_DIARIO"]

    if not registros:
        return {
            "sono": 0,
            "irritabilidade": 0,
            "crise": 0,
            "total_registros": 0,
        }

    score_sono = 0
    score_irritabilidade = 0
    score_crise = 0
    quantidade = 0

    for r in registros:
        texto = (r.get("descricao") or "").lower()
        quantidade += 1

        if "sono: muito bom" in texto:
            score_sono += 5
        elif "sono: bom" in texto:
            score_sono += 4
        elif "sono: regular" in texto:
            score_sono += 3
        elif "sono: ruim" in texto:
            score_sono += 2
        elif "sono: muito ruim" in texto:
            score_sono += 1

        if "irritabilidade: nenhuma" in texto:
            score_irritabilidade += 5
        elif "irritabilidade: leve" in texto:
            score_irritabilidade += 4
        elif "irritabilidade: moderada" in texto:
            score_irritabilidade += 3
        elif "irritabilidade: alta" in texto:
            score_irritabilidade += 2
        elif "irritabilidade: muito alta" in texto:
            score_irritabilidade += 1

        if "crise sensorial: não" in texto or "crise sensorial: nao" in texto:
            score_crise += 5
        elif "crise sensorial: sim" in texto:
            score_crise += 3
        elif "crise sensorial: moderada" in texto:
            score_crise += 2
        elif "crise sensorial: alta" in texto:
            score_crise += 1

    return {
        "sono": round(score_sono / quantidade) if quantidade else 0,
        "irritabilidade": round(score_irritabilidade / quantidade) if quantidade else 0,
        "crise": round(score_crise / quantidade) if quantidade else 0,
        "total_registros": quantidade,
    }


def gerar_resumo_clinico(score: dict) -> str:
    if not score or score.get("total_registros", 0) == 0:
        return "Ainda não há dados clínicos suficientes para gerar análise."

    sono_val = score.get("sono", 0)
    irrit_val = score.get("irritabilidade", 0)
    crise_val = score.get("crise", 0)

    sono = (
        "sono predominantemente bom"
        if sono_val >= 4
        else "sono regular"
        if sono_val == 3
        else "sono de baixa qualidade"
    )

    irrit = (
        "irritabilidade baixa"
        if irrit_val >= 4
        else "irritabilidade moderada"
        if irrit_val == 3
        else "irritabilidade elevada"
    )

    crise = (
        "baixa ocorrência de crises sensoriais"
        if crise_val >= 4
        else "crises sensoriais ocasionais"
        if crise_val == 3
        else "crises sensoriais frequentes"
    )

    conclusao = "estabilidade clínica"

    if sono_val <= 2 or irrit_val <= 2 or crise_val <= 2:
        conclusao = "necessidade de atenção clínica"

    if sono_val >= 4 and irrit_val >= 4 and crise_val >= 4:
        conclusao = "boa evolução clínica"

    return (
        f"Nos últimos registros observou-se {sono}, {irrit} e {crise}. "
        f"O quadro geral sugere {conclusao}."
    )


def _encontrar_logo_path() -> Optional[Path]:
    base_dir = Path(__file__).resolve().parents[1]
    candidatos = [
        base_dir / "static" / "icon-monitra.png",
        base_dir / "assets" / "icon-monitra.png",
        base_dir / "icon-monitra.png",
    ]

    for caminho in candidatos:
        if caminho.exists():
            return caminho
    return None


def _build_header(styles):
    body = styles["BodyText"]
    logo_path = _encontrar_logo_path()

    if logo_path:
        logo = Image(str(logo_path), width=1.8 * cm, height=1.8 * cm)

        brand_text = Paragraph(
            "<b>MONITRA</b><br/><font size='9'>Inteligência clínica em tempo real</font>",
            ParagraphStyle(
                "BrandText",
                parent=body,
                fontName="Helvetica",
                fontSize=10,
                leading=12,
                textColor=white,
            ),
        )

        header = Table(
            [[logo, brand_text]],
            colWidths=[2.4 * cm, 13.6 * cm],
        )
        header.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), HexColor("#0F8F5B")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return header

    fallback = Table(
        [["MONITRA"]],
        colWidths=[16 * cm],
    )
    fallback.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), HexColor("#0F8F5B")),
                ("TEXTCOLOR", (0, 0), (-1, -1), white),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 16),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return fallback


def _build_score_chart(score_clinico: dict) -> Drawing:
    drawing = Drawing(16 * cm, 7.2 * cm)

    titulo = String(
        0,
        6.6 * cm,
        "Gráfico clínico resumido",
        fontName="Helvetica-Bold",
        fontSize=12,
        fillColor=black,
    )
    drawing.add(titulo)

    chart = VerticalBarChart()
    chart.x = 1.2 * cm
    chart.y = 1.2 * cm
    chart.height = 4.2 * cm
    chart.width = 11.5 * cm

    chart.data = [[
        score_clinico.get("sono", 0),
        score_clinico.get("irritabilidade", 0),
        score_clinico.get("crise", 0),
    ]]

    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 5
    chart.valueAxis.valueStep = 1
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 8

    chart.categoryAxis.categoryNames = ["Sono", "Irritabilidade", "Crise"]
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.dy = -2

    chart.barWidth = 1.1 * cm
    chart.groupSpacing = 0.7 * cm
    chart.barSpacing = 0.2 * cm

    chart.bars[0].fillColor = HexColor("#0F8F5B")
    chart.bars[0].strokeColor = HexColor("#0B5D3B")

    drawing.add(chart)

    legend = Legend()
    legend.x = 13.4 * cm
    legend.y = 4.6 * cm
    legend.alignment = "right"
    legend.fontName = "Helvetica"
    legend.fontSize = 8
    legend.colorNamePairs = [
        (HexColor("#0F8F5B"), "Score médio clínico"),
    ]
    drawing.add(legend)

    observacao = String(
        0,
        0.4 * cm,
        "Escala: 0 = sem dados | 1-2 = atenção | 3 = regular | 4-5 = favorável",
        fontName="Helvetica",
        fontSize=8,
        fillColor=HexColor("#4b5563"),
    )
    drawing.add(observacao)

    return drawing


def gerar_pdf_paciente(paciente: dict, eventos: list[dict]) -> bytes:
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title = styles["Title"]
    body = styles["BodyText"]
    heading = styles["Heading2"]

    body.fontName = "Helvetica"
    body.fontSize = 10
    body.leading = 14

    title.fontName = "Helvetica-Bold"
    title.fontSize = 18

    heading.fontName = "Helvetica-Bold"
    heading.fontSize = 15
    heading.spaceAfter = 8

    status = classificar_status_paciente(eventos)
    score_clinico = extrair_score_clinico(eventos)
    resumo_clinico = gerar_resumo_clinico(score_clinico)

    total_intervencoes = len(
        [e for e in eventos if e.get("tipo_evento") == "INTERVENCAO"]
    )
    total_registros = len(
        [e for e in eventos if e.get("tipo_evento") == "REGISTRO_DIARIO"]
    )
    ultimo_evento = eventos[0] if eventos else None

    idade = calcular_idade(paciente.get("data_nascimento"))
    data_nascimento_fmt = formatar_data_br(paciente.get("data_nascimento"))
    idade_txt = f" | {idade} anos" if idade is not None else ""

    story = []

    story.append(_build_header(styles))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Relatório Clínico do Paciente", title))
    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            f"<b>Paciente:</b> {paciente.get('nome', '-')}"
            f"<br/><b>Nascimento:</b> {data_nascimento_fmt}{idade_txt}"
            f"<br/><b>Gênero:</b> {paciente.get('genero') or '-'}"
            f"<br/><b>Profissional:</b> {paciente.get('profissional_nome') or '-'}"
            f"<br/><b>Clínica:</b> {paciente.get('clinica_nome') or '-'}"
            f"<br/><b>Responsável:</b> {paciente.get('responsavel_nome') or '-'}"
            f"<br/><b>Email:</b> {paciente.get('responsavel_email') or '-'}",
            body,
        )
    )
    story.append(Spacer(1, 12))

    status_table = Table(
        [[f"Status clínico atual: {label_status(status)}"]],
        colWidths=[16 * cm],
    )
    status_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), cor_status(status)),
                ("TEXTCOLOR", (0, 0), (-1, -1), black),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 12),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.75, black),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(status_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Resumo clínico automático", heading))
    story.append(Paragraph(resumo_clinico, body))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Resumo Clínico", heading))
    resumo_table = Table(
        [
            ["Intervenções", str(total_intervencoes)],
            ["Registros diários", str(total_registros)],
            ["Base clínica", f"{score_clinico.get('total_registros', 0)} registro(s) analisado(s)"],
            [
                "Último evento",
                "Intervenção"
                if ultimo_evento and ultimo_evento.get("tipo_evento") == "INTERVENCAO"
                else "Registro Diário"
                if ultimo_evento
                else "-",
            ],
            [
                "Data do último evento",
                formatar_data_hora_br(ultimo_evento.get("data")) if ultimo_evento else "-",
            ],
        ],
        colWidths=[8 * cm, 8 * cm],
    )
    resumo_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#f3f4f6")),
                ("GRID", (0, 0), (-1, -1), 0.5, black),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(resumo_table)
    story.append(Spacer(1, 14))

    story.append(_build_score_chart(score_clinico))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Timeline Clínica", heading))

    if not eventos:
        story.append(Paragraph("Nenhum evento encontrado.", body))
    else:
        timeline_style = ParagraphStyle(
            "TimelineCell",
            parent=body,
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            spaceAfter=0,
            spaceBefore=0,
        )

        timeline_header_style = ParagraphStyle(
            "TimelineHeader",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
        )

        timeline_rows = [
            [
                Paragraph("Data", timeline_header_style),
                Paragraph("Tipo", timeline_header_style),
                Paragraph("Descrição", timeline_header_style),
            ]
        ]

        for e in eventos[:30]:
            data_txt = formatar_data_hora_br(e.get("data"))
            tipo_txt = (
                "Intervenção"
                if e.get("tipo_evento") == "INTERVENCAO"
                else "Registro Diário"
            )
            descricao_txt = str(e.get("descricao", "-")).replace("\n", "<br/>")

            timeline_rows.append(
                [
                    Paragraph(data_txt, timeline_style),
                    Paragraph(tipo_txt, timeline_style),
                    Paragraph(descricao_txt, timeline_style),
                ]
            )

        timeline_table = Table(
            timeline_rows,
            colWidths=[3.0 * cm, 3.4 * cm, 9.6 * cm],
            repeatRows=1,
        )

        timeline_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#e5e7eb")),
                    ("GRID", (0, 0), (-1, -1), 0.5, black),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )

        story.append(timeline_table)

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            f"Emitido em: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            body,
        )
    )

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
