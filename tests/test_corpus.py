from gopya.corpus import _tables_to_sentences
from gopya.text import npr, numbers, tokens


def test_every_collection_is_loaded(chunks):
    assert {c.collection for c in chunks} == {"general", "finance", "engineering", "hr", "board"}


def test_pdf_is_split_into_agenda_items(chunks):
    board = [c for c in chunks if c.collection == "board"]
    assert any("Upper Kanchan Khola" in c.section for c in board)
    assert all(c.text for c in board)


def test_csv_rows_are_flagged_as_personal_data(chunks):
    rows = [c for c in chunks if c.doc_id == "hr/employees"]
    assert len(rows) == 13 and all(c.has_pii for c in rows)
    assert "Rs 1,12,000" in next(c.text for c in rows if c.section == "Pemba Sherpa")


def test_tables_keep_their_headers():
    md = "| Amount | Who |\n|---|---|\n| Up to Rs 50,000 | Head of department |"
    assert _tables_to_sentences(md) == "Amount: Up to Rs 50,000; Who: Head of department."


def test_folder_and_front_matter_must_agree(tmp_path):
    from gopya.corpus import load
    import pytest

    (tmp_path / "general").mkdir()
    (tmp_path / "general" / "x.md").write_text("---\ntitle: X\ndept: finance\n---\n\nhello\n")
    with pytest.raises(ValueError, match="does not match folder"):
        load(tmp_path)


def test_text_helpers():
    assert npr(410000) == "Rs 4,10,000"
    assert npr(1500) == "Rs 1,500"
    assert numbers("Rs 1,25,000 and 9.16 [2]") == {"125000", "9.16", "2"}
    assert tokens("7,000 ppm") == tokens("7000 ppm")
    assert tokens("sick leave kati din pauchha") == tokens("sick leave day")
