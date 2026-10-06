import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import engine
from conftest import golden

# inferior-stemi answer key: correct dx 10, NSTEMI 3; management +5 +5 +5 +3, two harmful -5.
MAX_SCORE = 10 + 5 + 5 + 5 + 3


def submit(client, case_id, diagnosis, management=(), participant="dr-house"):
    return client.post(
        f"/cases/{case_id}/submissions",
        json={"participant": participant, "diagnosis_option_id": diagnosis, "management_option_ids": list(management)},
    )


def test_perfect_answer(client, stemi):
    opt = stemi["opt"]
    r = submit(
        client,
        stemi["id"],
        opt("Acute inferior STEMI"),
        [opt("Aspirin"), opt("Immediate transfer"), opt("IV fluid"), opt("P2Y12")],
    )
    assert r.status_code == 201
    result = r.json()
    assert result["score"] == result["max_score"] == MAX_SCORE
    assert result["diagnosis_correct"] is True


def test_partial_credit_and_penalty_for_harmful_action(client, stemi):
    opt = stemi["opt"]
    result = submit(client, stemi["id"], opt("NSTEMI"), [opt("Aspirin"), opt("Sublingual nitroglycerin")]).json()
    assert result["score"] == 3 + 5 - 5
    assert result["diagnosis_correct"] is False
    chosen = {o["label"] for o in result["options"] if o["chosen"]}
    assert chosen == {"NSTEMI", "Aspirin 300 mg loading dose", "Sublingual nitroglycerin"}
    # The result reveals the full key, including what was missed and why.
    nitro = next(o for o in result["options"] if o["label"] == "Sublingual nitroglycerin")
    assert nitro["points"] == -5 and "hypotension" in nitro["explanation"]


def test_score_is_floored_at_zero(client, stemi):
    opt = stemi["opt"]
    result = submit(client, stemi["id"], opt("Aortic dissection"), [opt("Sublingual"), opt("Morphine")]).json()
    assert result["score"] == 0
    assert result["max_score"] == MAX_SCORE


def test_duplicate_management_ids_count_once(client, stemi):
    opt = stemi["opt"]
    result = submit(client, stemi["id"], opt("Acute"), [opt("Aspirin")] * 3).json()
    assert result["score"] == 15


def test_one_attempt_per_participant(client, stemi):
    dx = stemi["opt"]("Acute")
    assert submit(client, stemi["id"], dx).status_code == 201
    assert submit(client, stemi["id"], dx).status_code == 409
    assert submit(client, stemi["id"], dx, participant="  dr-house ").status_code == 409
    assert submit(client, stemi["id"], dx, participant="   ").status_code == 422
    assert submit(client, stemi["id"], dx, participant="dr-cameron").status_code == 201


@pytest.mark.parametrize("field", ["diagnosis", "management"])
def test_options_from_another_case_are_rejected(client, stemi, field):
    other = client.post("/cases", json=golden("dka")).json()
    foreign = other["diagnosis_options"][0]["id"] if field == "diagnosis" else other["management_options"][0]["id"]
    dx = foreign if field == "diagnosis" else stemi["opt"]("Acute")
    r = submit(client, stemi["id"], dx, [foreign] if field == "management" else [])
    assert r.status_code == 422


def test_management_option_cannot_be_the_diagnosis(client, stemi):
    r = submit(client, stemi["id"], stemi["opt"]("Aspirin"))
    assert r.status_code == 422


def test_submission_to_unknown_case_is_404(client):
    assert submit(client, 999, 1).status_code == 404


def test_get_submission(client, stemi):
    created = submit(client, stemi["id"], stemi["opt"]("Acute"), [stemi["opt"]("Aspirin")]).json()
    assert client.get(f"/submissions/{created['submission_id']}").json() == created
    assert client.get("/submissions/999").status_code == 404


def test_leaderboard_ranks_by_score(client, stemi):
    opt = stemi["opt"]
    submit(client, stemi["id"], opt("NSTEMI"), participant="b")  # 3
    submit(client, stemi["id"], opt("Acute"), [opt("Aspirin")], participant="a")  # 15
    submit(client, stemi["id"], opt("NSTEMI"), participant="c")  # 3
    board = client.get(f"/cases/{stemi['id']}/leaderboard").json()
    assert [(e["rank"], e["participant"], e["score"]) for e in board] == [(1, "a", 15), (2, "b", 3), (2, "c", 3)]


def test_database_enforces_one_diagnosis_per_submission(client, stemi):
    """Integrity does not depend on the API: a second diagnosis row is rejected by Postgres."""
    opt = stemi["opt"]
    sub = submit(client, stemi["id"], opt("Acute")).json()
    with pytest.raises(IntegrityError, match="uq_submission_answers_one_diagnosis"), engine.begin() as conn:
        conn.execute(
            text("INSERT INTO submission_answers VALUES (:s, :o, :c, 'diagnosis')"),
            {"s": sub["submission_id"], "o": opt("NSTEMI"), "c": stemi["id"]},
        )


def test_database_rejects_option_of_another_case(client, stemi):
    other = client.post("/cases", json=golden("dka")).json()
    sub = submit(client, stemi["id"], stemi["opt"]("Acute")).json()
    with pytest.raises(IntegrityError, match="fk_submission_answers_option"), engine.begin() as conn:
        conn.execute(
            text("INSERT INTO submission_answers VALUES (:s, :o, :c, 'management')"),
            {"s": sub["submission_id"], "o": other["management_options"][0]["id"], "c": stemi["id"]},
        )
