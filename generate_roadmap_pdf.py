import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# 1. Register Cyrillic Fonts (Arial on macOS)
FONT_REGULAR_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

pdfmetrics.registerFont(TTFont("Arial", FONT_REGULAR_PATH))
pdfmetrics.registerFont(TTFont("Arial-Bold", FONT_BOLD_PATH))

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        # Top Header line
        self.setStrokeColor(colors.HexColor("#1e2329"))
        self.setLineWidth(0.8)
        self.line(40, A4[1] - 40, A4[0] - 40, A4[1] - 40)

        # Header text
        self.setFont("Arial", 8)
        self.setFillColor(colors.HexColor("#717b88"))
        self.drawString(40, A4[1] - 34, "HYPERSCREENER · HYPERLIQUID SMART TERMINAL")
        self.drawRightString(A4[0] - 40, A4[1] - 34, "ROADMAP & CHECKLIST")

        # Bottom Footer line
        self.line(40, 42, A4[0] - 40, 42)
        # Footer text
        self.drawString(40, 30, "Конфіденційно · План розробки торгового інструменту")
        page_str = f"Сторінка {self._pageNumber} з {page_count}"
        self.drawRightString(A4[0] - 40, 30, page_str)
        self.restoreState()


def build_pdf(output_path: str):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=55,
        bottomMargin=55
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        fontName="Arial-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0b0e11"),
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        fontName="Arial",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#4b5563"),
        spaceAfter=15
    )
    h1_style = ParagraphStyle(
        "SectionH1",
        fontName="Arial-Bold",
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=12,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        "BodyTextCustom",
        fontName="Arial",
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#334155")
    )
    item_title_style = ParagraphStyle(
        "ItemTitle",
        fontName="Arial-Bold",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#0f172a")
    )
    item_desc_style = ParagraphStyle(
        "ItemDesc",
        fontName="Arial",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#64748b")
    )
    status_style = ParagraphStyle(
        "StatusBadge",
        fontName="Arial-Bold",
        fontSize=8,
        leading=10,
        alignment=1
    )

    story = []

    # Title Banner
    story.append(Paragraph("HYPERSCREENER: ПЛАН РОЗВИТКУ ТА ЧЕКЛИСТ", title_style))
    story.append(Paragraph("Покрокова дорожня карта перетворення скрінера у професійний автономний торговий термінал на Hyperliquid", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0ecb81"), spaceBefore=0, spaceAfter=14))

    # Summary box
    summary_data = [
        [
            Paragraph("<b>Поточний стан проєкту:</b> Реалізовано графік TradingView Lightweight Charts, прямі дані з Hyperliquid (230+ монет), детекцію зон підтримки та опору з підрахунком дотиків, свіжі FVG, нахилені тренд-лінії, детекцію хибних пробоїв і сувору ізоляцію таймфреймів (дефолт 1D).", body_style)
        ]
    ]
    summary_table = Table(summary_data, colWidths=[515])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#e2e8f0")),
        ('PADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 14))

    # Definition of Roadmap Sections
    sections = [
        {
            "title": "ЕТАП 1: Live WebSocket Data & Мінімальна затримка (Рекомендовано)",
            "desc": "Перехід від періодичного REST-опитування до постійного прямого біржового сокету.",
            "items": [
                ("[ ]", "1.1. Інтеграція wss://api.hyperliquid.xyz/ws", "Підключення фонового WebSocket стріму до подій candle та allMids. Оновлення останньої свічки в реальному часі без перезавантаження."),
                ("[ ]", "1.2. Реконект-менеджер (Auto-reconnection)", "Автоматичне відновлення з'єднання з біржею при обриві мережі з експоненційним бекоффом без зависання інтерфейсу."),
                ("[ ]", "1.3. Live-свіп детекція на лету", "Фіксація проколу рівня в мілісекунду, коли свічка торкається екстремуму, а не раз на 6 секунд."),
            ]
        },
        {
            "title": "ЕТАП 2: Система сповіщень та мобільність (Alerts & Telegram)",
            "desc": "Можливість відійти від комп'ютера і отримувати сетапи прямо на смартфон.",
            "items": [
                ("[ ]", "2.1. Telegram-бот сповіщень (aiogram 3.x)", "Приватний бот із захистом за Chat ID. Надсилання повідомлень: монета, таймфрейм, тип формації, ціна, напрямок (LONG/SHORT)."),
                ("[ ]", "2.2. Генерація міні-графіка до алерту", "Формування компактного знімка графіка з нанесеними рівнями прямо в Telegram повідомлення."),
                ("[ ]", "2.3. Звукові алерти у веб-інтерфейсі", "Нативні приємні звукові сигнали (Web Audio API) при виявленні сигналу або підході ціни до рівня на < 0.2%."),
                ("[ ]", "2.4. Фільтр чутливості сповіщень", "Можливість налаштувати: отримувати сповіщення тільки для 1D та 1h, або тільки з ≥ 3 дотиками."),
            ]
        },
        {
            "title": "ЕТАП 3: Open Interest (OI) та ліквідаційний аналіз (Hyperliquid Edge)",
            "desc": "Використання ексклюзивних даних децентралізованого ордербука Hyperliquid для фільтрації хибних пробоїв.",
            "items": [
                ("[ ]", "3.1. Детекція дельти відкритого інтересу (OI Delta)", "Розрахунок зміни OI під час тесту рівня: пробій на зростанні OI = вхід великих гравців; пробій на скиданні OI = закриття стопів."),
                ("[ ]", "3.2. Фільтр хибних пробоїв за скиданням OI", "Підтвердження сигналу 'Хибний пробій' лише тоді, коли відкритого інтересу поменшало (відбувся виніс ліквідацій)."),
                ("[ ]", "3.3. Відображення пулів ліквідності (EQH / EQL)", "Виділення на графіку рівних хаїв (Buy-side Liquidity) та лоїв (Sell-side Liquidity) як зон для фіксації Take Profit."),
            ]
        },
        {
            "title": "ЕТАП 4: Скрінер ринку, об'єми та арбітражні модулі",
            "desc": "Інструменти для швидкого відбору найволатильніших та найприбутковіших інструментів.",
            "items": [
                ("[ ]", "4.1. Детектор сплесків об'єму (Volume Spike Tracker)", "Автоматичний пошук монет, де поточний об'єм у 3х - 5х разів перевищує середній за 20 свічок (вхід маркетмейкера)."),
                ("[ ]", "4.2. Фандинг-арбітраж (Funding Rate Scanner)", "Моніторинг аномальних ставок фінансування (Funding Rates) на Hyperliquid для отримання безризикової премії."),
                ("[ ]", "4.3. Віджет гарячих монет у терміналі", "Міні-панель праворуч або знизу зі списком топ-5 монет, що прямо зараз торгуються біля ключових зон."),
            ]
        },
        {
            "title": "ЕТАП 5: Автоматизація та торгівля в 1 клік (Execution via Agent Wallet)",
            "desc": "Перетворення скрінера у повноцінний торговий термінал з виконанням ордерів.",
            "items": [
                ("[ ]", "5.1. Інтеграція суб-ключа Hyperliquid Agent Wallet", "Безпечний API-гаманець без прав виведення коштів (тільки торгові операції)."),
                ("[ ]", "5.2. Автоматичний калькулятор ризику (Position Sizing)", "Розрахунок об'єму входу під фіксований ризик (наприклад 1% від балансу) з урахуванням стоп-лосу за межу зони."),
                ("[ ]", "5.3. Швидкі кнопки 'BUY' / 'SELL' прямо біля графіка", "Виставлення лімітного або ринкового ордера з автоматичним Take Profit на протилежну зону."),
                ("[ ]", "5.4. Журнал торгівлі та статистика вінрейту", "Автоматична статистика відпрацювання кожної формації (каскад, хибний пробій, FVG)."),
            ]
        }
    ]

    for section in sections:
        story.append(KeepTogether([
            Paragraph(section["title"], h1_style),
            Paragraph(section["desc"], item_desc_style),
            Spacer(1, 4)
        ]))

        table_data = []
        for box, name, desc in section["items"]:
            cell_box = Paragraph(f"<font color='#0ecb81' size='11'><b>{box}</b></font>", status_style)
            cell_text = [
                Paragraph(name, item_title_style),
                Paragraph(desc, item_desc_style)
            ]
            table_data.append([cell_box, cell_text])

        t = Table(table_data, colWidths=[35, 480])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#ffffff")),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor("#f1f5f9")),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    # Notes section at the end
    notes_data = [
        [
            Paragraph("<b>Як користуватися цим чеклистом:</b><br/>1. Роздрукуйте або відкрийте у переглядачі PDF.<br/>2. Виконуйте етапи послідовно: спочатку стабільний сокет і сповіщення, потім аналітика OI, далі автоматизація.<br/>3. Позначайте галочками завершені пункти для контролю прогресу розробки.", body_style)
        ]
    ]
    notes_table = Table(notes_data, colWidths=[515])
    notes_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f0fdf4")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#bbf7d0")),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(KeepTogether([
        Spacer(1, 6),
        notes_table
    ]))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"PDF successfully generated at: {output_path}")

if __name__ == "__main__":
    out = "/Users/stepanbezhuk/work/hyperscreener/HYPERSCREENER_ROADMAP.pdf"
    build_pdf(out)
