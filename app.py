"""Streamlit chat UI: pick a demo user and see how the same question is answered per role.

    streamlit run app.py
"""

import streamlit as st

from gopya.config import settings
from gopya.corpus import load
from gopya.index import Index
from gopya.pipeline import Gopya

st.set_page_config(page_title="Gopya", page_icon="🔒", layout="centered")


@st.cache_resource
def engine() -> Gopya:
    cfg = settings()
    if not (cfg.index_dir / "manifest.json").exists():  # fresh deploy: build the index once (a few seconds)
        Index.build(load(cfg.docs_dir), cfg.index_dir)
    return Gopya.open(cfg)


g = engine()
users = g.directory.users
with st.sidebar:
    st.header("Signed in as")
    uid = st.radio(
        "Demo user", list(users), format_func=lambda u: f"{users[u].name} ({users[u].role.name})", label_visibility="collapsed"
    )
    user = users[uid]
    st.caption("Can read: " + ", ".join(sorted(user.role.collections)))
    st.caption("Personal data: " + ("shown" if user.role.pii else "redacted"))
    st.divider()
    st.caption("Try: *What is the dry season tariff this year?* as Kabita and then as Bishal.")

st.title("Gopya")
st.caption("Kanchan Hydro's internal assistant. Answers only from documents your role can read.")

key = f"history-{uid}"
st.session_state.setdefault(key, [])
for role, text in st.session_state[key]:
    st.chat_message(role).markdown(text)

if q := st.chat_input("Ask about policies, operations or records"):
    st.chat_message("user").markdown(q)
    r = g.ask(user, q)
    body = r.answer
    if r.sources:
        body += "\n\n" + "\n".join(f"- {s}" for s in r.sources)
    st.chat_message("assistant").markdown(body)
    st.session_state[key] += [("user", q), ("assistant", body)]
