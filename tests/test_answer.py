from gopya.answer import LlmAnswerer, grounding_gate
from gopya.llm import Completion, LlmError


class FakeClient:
    def __init__(self, text=None, error=False):
        self.text, self.error, self.calls = text, error, []

    def complete(self, system, user, max_tokens=400):
        self.calls.append(user)
        if self.error:
            raise LlmError("timeout")
        return Completion(self.text, 900, 40, "llama-3.3-70b-versatile")


def test_gate_accepts_grounded_answer():
    ok, _ = grounding_gate("The tariff is Rs 9.16 per kWh [1].", "tariff?", ["Rs 9.16 per kWh in the dry season"])
    assert ok


def test_gate_rejects_invented_number():
    ok, why = grounding_gate("The tariff is Rs 9.50 per kWh [1].", "tariff?", ["Rs 9.16 per kWh"])
    assert not ok and why.startswith("ungrounded_number")


def test_gate_rejects_missing_or_bad_citation():
    assert grounding_gate("The tariff is Rs 9.16.", "q", ["Rs 9.16"])[1] == "no_citation"
    assert grounding_gate("Rs 9.16 [3].", "q", ["Rs 9.16"])[1] == "bad_citation"


def _llm_gopya(gopya, client):
    gopya.answerer = LlmAnswerer(client, gopya.extractive)
    return gopya


def test_model_answer_used_when_grounded(gopya):
    g = _llm_gopya(gopya, FakeClient("The dry season tariff for FY 2082/83 is Rs 9.16 per kWh [1]."))
    r = g.ask("kabita", "What is the dry season tariff in FY 2082/83?")
    assert r.trace["backend"] == "llm" and r.trace["gate"] == "pass"
    assert r.trace["tokens_in"] == 900 and r.trace["cost_usd"] > 0


def test_model_answer_with_invented_number_falls_back(gopya):
    g = _llm_gopya(gopya, FakeClient("The dry season tariff is Rs 10.20 per kWh [1]."))
    r = g.ask("kabita", "What is the dry season tariff in FY 2082/83?")
    assert r.trace["gate"].startswith("fail:ungrounded_number")
    assert "10.20" not in r.answer and "9.16" in r.answer


def test_model_error_falls_back(gopya):
    r = _llm_gopya(gopya, FakeClient(error=True)).ask("bishal", "How many days of sick leave do I get?")
    assert r.decision == "answered" and "12 days" in r.answer and r.trace["gate"] == "llm_error"


def test_model_never_sees_restricted_or_personal_data(gopya):
    client = FakeClient("NOT_FOUND")
    g = _llm_gopya(gopya, client)
    g.ask("sabina", "Show the employee record for Pemba Sherpa.")
    assert client.calls and "69-06-74-42561" not in client.calls[-1]
    g.ask("bishal", "How many days of sick leave do I get?")
    assert "finance/" not in client.calls[-1] and "64 crore" not in client.calls[-1]


def test_not_found_from_model(gopya):
    r = _llm_gopya(gopya, FakeClient("NOT_FOUND")).ask("bishal", "How many days of sick leave do I get?")
    assert r.decision == "not_found"


def test_budget_switches_to_offline(gopya):
    from gopya.trace import TraceLog

    g = _llm_gopya(gopya, FakeClient("Employees get 12 days of paid sick leave a year [1]."))
    g.traces = TraceLog(None)
    g.cfg = type(g.cfg)(daily_token_budget=1000)
    g.ask("bishal", "How many days of sick leave do I get?")  # spends 940 tokens
    g.ask("bishal", "How many days of sick leave do I get?")  # spends 940 more, now over budget
    r = g.ask("bishal", "How many days of sick leave do I get?")
    assert r.trace["gate"] == "budget" and r.trace["backend"] == "extractive"
