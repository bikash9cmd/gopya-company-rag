"""Access control: the guarantees that matter most."""

import pytest

from gopya.index import Index

RESTRICTED = [
    ("bishal", "What is the dry season tariff this year?", "9.16"),
    ("pemba", "What is Pemba Sherpa's monthly gross salary?", "1,12,000"),
    ("kabita", "What price did the board discuss for the acquisition?", "64 crore"),
    ("sarita", "What is the budget for the annual overhaul?", "2.9 crore"),
    ("bishal", "Is the company planning to buy another hydropower project?", "Upper Kanchan"),
]


@pytest.mark.parametrize("user,question,secret", RESTRICTED)
def test_restricted_facts_never_appear(gopya, user, question, secret):
    r = gopya.ask(user, question)
    assert secret not in r.render()
    allowed = gopya.directory.user(user).role.collections
    assert all(cid.split("/")[0] in allowed for cid in r.trace["retrieved"])


def test_refusal_does_not_reveal_that_a_document_exists(gopya):
    restricted = gopya.ask("kabita", "What price did the board discuss for the acquisition?")
    nonexistent = gopya.ask("kabita", "What is our carbon credit revenue?")
    assert restricted.decision == nonexistent.decision == "not_found"
    assert restricted.answer == nonexistent.answer


def test_same_question_different_roles(gopya):
    assert "9.16" in gopya.ask("kabita", "What is the dry season tariff in FY 2082/83?").answer
    assert "9.16" in gopya.ask("sabina", "What is the dry season tariff in FY 2082/83?").answer
    assert gopya.ask("bishal", "What is the dry season tariff in FY 2082/83?").decision == "not_found"


def test_search_filters_inside_the_store(index):
    hits = index.search("acquisition price Upper Kanchan Khola", frozenset({"general"}), k=10)
    assert hits and all(h.chunk.collection == "general" for h in hits)
    assert index.search("anything", frozenset(), k=4) == []


def test_store_returning_a_restricted_chunk_is_an_error(index, monkeypatch):
    real = index.col.query

    def leaky(**kw):
        kw.pop("where")
        return real(**kw)

    monkeypatch.setattr(index.col, "query", leaky)
    with pytest.raises(AssertionError, match="outside the role"):
        index.search("acquisition price", frozenset({"general"}), k=4)


def test_hr_sees_personal_data_but_executive_does_not(gopya):
    q = "Show the employee record for Pemba Sherpa."
    hr = gopya.ask("sarita", q).answer
    ceo = gopya.ask("sabina", q).answer
    assert "69-06-74-42561" in hr
    assert "69-06-74-42561" not in ceo and "[redacted]" in ceo
    assert "1,12,000" in ceo  # salary is visible to the executive, identity numbers are not


def test_counterfactual_restricted_docs_change_nothing(chunks, directory, cfg, tmp_path, gopya):
    from gopya.answer import ExtractiveAnswerer
    from gopya.pipeline import Gopya
    from gopya.trace import TraceLog

    only_general = Index.build([c for c in chunks if c.collection == "general"], tmp_path / "g")
    g2 = Gopya(only_general, directory, cfg, answerer=ExtractiveAnswerer(cfg.min_coverage), traces=TraceLog(None))
    for _, q, _ in RESTRICTED:
        assert gopya.ask("bishal", q).render() == g2.ask("bishal", q).render()
