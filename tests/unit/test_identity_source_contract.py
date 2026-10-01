"""`identity_source` has exactly one definition, shared by every place that types it (Plan 0055)."""

from typing import get_args, get_type_hints

from server.schemas import IdentitySource, TranscribeResponse
from server.schemas_streaming import StreamDoneEvent

from server import streaming


def test_identity_source_lists_the_three_evidence_sources() -> None:
    assert get_args(IdentitySource) == ("face", "face_voice", "local_unlock")


def test_every_identity_source_annotation_comes_from_that_definition() -> None:
    expected = IdentitySource | None
    for model in (TranscribeResponse, StreamDoneEvent):
        annotation = model.model_fields["identity_source"].annotation
        assert annotation == expected
    hint = get_type_hints(streaming.stream_response_plan)["identity_source"]
    assert hint == expected
