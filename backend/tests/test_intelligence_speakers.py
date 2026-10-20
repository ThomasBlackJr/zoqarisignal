from app.services.speaker_roles import enhance_roles


def turn(text, identity=None):
    return {
        "text": text,
        "speaker_id": identity,
        "speaker_role": "UNKNOWN",
        "role_source": "unknown",
        "source_start": 0,
        "source_end": len(text),
    }


def test_first_speaker_can_be_customer_and_unknown_is_preserved():
    turns = [
        turn("I'm calling because my delivery is missing.", "speaker_1"),
        turn("Let me pull that up for you.", "speaker_2"),
        turn("Okay."),
    ]
    original = [(t["source_start"], t["source_end"]) for t in turns]
    enhance_roles(turns)
    assert [t["speaker_role"] for t in turns] == ["CALLER", "DISPATCHER", "UNKNOWN"]
    assert [(t["source_start"], t["source_end"]) for t in turns] == original


def test_real_speaker_ids_propagate_but_conflicting_evidence_abstains():
    turns = [
        turn("Can I have your order number?", "a"),
        turn("One moment.", "a"),
        turn("I'm calling because it is missing. Let me pull that up for you.", "b"),
    ]
    enhance_roles(turns)
    assert turns[0]["speaker_role"] == turns[1]["speaker_role"] == "DISPATCHER"
    assert turns[2]["speaker_role"] == "UNKNOWN"


def test_new_conflicting_cue_demotes_old_inference_but_preserves_explicit_role():
    inferred = turn("Let me check. My order is late.", "a")
    inferred.update(speaker_role="DISPATCHER", role_source="text_cue")
    provided = turn("My order is late.", "b")
    provided.update(speaker_role="DISPATCHER", role_source="provided_role")
    enhance_roles([inferred, provided])
    assert inferred["speaker_role"] == "UNKNOWN"
    assert provided["speaker_role"] == "DISPATCHER"
