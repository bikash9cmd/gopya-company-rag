"""Build the board minutes PDF in data/docs/board from the text below.

The knowledge base keeps one PDF on purpose, so ingestion is tested on the format most company
documents arrive in. Run this only to change the minutes; the PDF is committed.
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).resolve().parents[1] / "data" / "docs" / "board" / "board-minutes-2082-asar.pdf"

SECTIONS = [
    ("Minutes of the 41st board meeting, 25 Asar 2082", None),
    ("Present", "Board chair Mohan Prasad Joshi, directors Sabina Shrestha (CEO), Gita Devi Koirala "
     "and Bikram Singh Thakuri. CFO Rajendra Adhikari attended as secretary."),
    ("1. Budget for FY 2082/83", "The board approved the budget for FY 2082/83 with operating "
     "expenses of Rs 25.9 crore and capital expenditure of Rs 4.5 crore. The board asked "
     "management to bring the dividend question back after the Q2 results."),
    ("2. Proposed acquisition of Upper Kanchan Khola", "Management presented a proposal to buy a 70% "
     "stake in the 12 MW Upper Kanchan Khola project, which is under construction in Dolakha. The "
     "indicative price is Rs 64 crore. The board approved a due diligence budget of Rs 45 lakh "
     "and asked for a final proposal by Poush 2082. This item is strictly confidential until the "
     "board decides."),
    ("3. Loan refinancing", "The CFO reported that two banks have offered to refinance the project "
     "loan at the base rate plus 1.5%, compared with plus 2% today. The board authorised the CFO "
     "to negotiate, with a final decision by the board."),
    ("4. CEO performance", "The board rated the CEO 4 (exceeds expectations) for FY 2081/82 and "
     "approved a 7% increment on basic salary from Shrawan 2082."),
    ("Next meeting", "The next board meeting will be held on 20 Ashwin 2082."),
]


def main() -> None:
    styles = getSampleStyleSheet()
    story = []
    for heading, body in SECTIONS:
        story.append(Paragraph(heading, styles["Title" if body is None else "Heading2"]))
        if body:
            story.append(Paragraph(body, styles["BodyText"]))
        story.append(Spacer(1, 8))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(OUT), pagesize=A4, title="Board minutes Asar 2082").build(story)
    print(OUT)


if __name__ == "__main__":
    main()
