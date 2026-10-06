from copy import deepcopy

from conftest import golden


def test_create_and_read_case(client):
    body = golden("pe-pregnancy")
    created = client.post("/cases", json=body)
    assert created.status_code == 201
    case_id = created.json()["id"]

    case = client.get(f"/cases/{case_id}").json()
    assert case["title"] == body["title"]
    assert case["patient"] == {"age": 31, "sex": "female"}
    assert case["vitals"]["spo2"] == 91
    assert case["vitals"]["temperature_c"] == 37.1
    assert [f["name"] for f in case["findings"]] == [f["name"] for f in body["findings"]]
    assert [o["label"] for o in case["diagnosis_options"]] == [o["label"] for o in body["diagnosis_options"]]

    assert client.get("/cases").json() == [{k: case[k] for k in ("id", "title", "presenting_complaint", "patient")}]


def test_public_case_does_not_leak_answer_key(client):
    case_id = client.post("/cases", json=golden("sah")).json()["id"]
    raw = client.get(f"/cases/{case_id}").text
    assert "points" not in raw
    assert "explanation" not in raw
    assert "unsecured aneurysm" not in raw


def test_unknown_case_is_404(client):
    assert client.get("/cases/999").status_code == 404


def test_answer_key_must_have_exactly_one_correct_diagnosis(client):
    body = deepcopy(golden("dka"))
    body["diagnosis_options"][1]["points"] = 10
    response = client.post("/cases", json=body)
    assert response.status_code == 422
    assert "exactly one diagnosis option" in response.text


def test_option_labels_must_be_unique(client):
    body = deepcopy(golden("dka"))
    body["management_options"].append({**body["management_options"][0], "label": "iv 0.9% SALINE resuscitation "})
    assert client.post("/cases", json=body).status_code == 422


def test_vitals_out_of_range_rejected(client):
    body = deepcopy(golden("dka"))
    body["vitals"]["spo2"] = 140
    assert client.post("/cases", json=body).status_code == 422
