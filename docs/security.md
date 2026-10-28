# Threat model

Gopya's job is to be useful with documents that most of its users must not see. This page lists
what it defends against, how, and what it does not cover.

## Assets

- Restricted documents: finance, engineering, HR and board collections.
- Personal data in HR records: citizenship numbers, mobile numbers, bank accounts.
- The fact that a restricted document exists (an acquisition, a pending dismissal).

## Who attacks

An authenticated employee asking questions outside their role, by accident or on purpose. They
control the question text and nothing else. Gopya does not defend against someone who can edit
`data/docs`, the index, or the role configuration; those are deployment controls.

## Controls

| Threat | Control | Where | Tested by |
|---|---|---|---|
| Retrieving a restricted chunk | Collection filter inside the Chroma query and inside BM25 scoring | `index.py` | `test_search_filters_inside_the_store`, attack set (`restricted_retrieved`) |
| Vector store bug or misconfiguration returns one anyway | Every returned chunk's collection is re-checked; a mismatch raises | `index.py` | `test_store_returning_a_restricted_chunk_is_an_error` |
| Refusal reveals existence | All decisions use the role's chunks only; BM25 IDF per role; one "not found" message | `index.py`, `pipeline.py` | `test_refusal_does_not_reveal_that_a_document_exists`, counterfactual test |
| Role escalation through the prompt | Role comes from the bearer token; role claims are refused | `api.py`, `guards.py` | `test_api_uses_the_token_role`, injection attacks |
| Model leaks PII it was given | PII is redacted before the prompt for roles without clearance | `pipeline.py` | `test_model_never_sees_restricted_or_personal_data` |
| Model invents facts | Grounding gate on numbers and citations, extractive fallback | `answer.py` | `test_model_answer_with_invented_number_falls_back` |
| Instructions hidden in a document | The prompt tells the model to ignore instructions in context, and the gate still applies | `answer.py` | not tested (needs a live model) |
| Cost abuse | Per-user daily token budget | `pipeline.py`, `trace.py` | `test_budget_switches_to_offline` |

## The counterfactual test

For each user, `eval/run.py` builds a second index containing only the collections that user's
role may read, asks every question in the eval set again, and compares the full rendered output.
If any restricted document influenced anything the user sees (an answer, a refusal, which sources
are cited, the order of sentences), the two outputs would differ. This catches leaks that a list
of forbidden strings would miss, such as a refusal worded differently when a restricted document
matched.

## Known gaps

- **Corpus-fitted embeddings.** The local LSA embedder learns its vocabulary from every
  collection. Allowed-only decisions make this unobservable in the tests, but it is a theoretical
  side channel. Use a pretrained embedding model in production.
- **Timing.** Chroma's filtered search time depends slightly on the index as a whole. With 77
  chunks it is not measurable; at scale, one index per sensitivity tier removes the question.
- **Regex guards.** Cheap and explainable, but bypassable by rephrasing. They are a usability
  feature (a clear refusal instead of a "not found"), not the access boundary.
- **Traces contain questions.** `var/traces.jsonl` keeps question text for monitoring. In
  production, set a retention period and restrict who can read it, or hash the text.
