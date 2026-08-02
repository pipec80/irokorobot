"""Vision package — scene description (V0), dialogue triggers (V0.5),
face recognition (V1).

Public API re-exported here so callers keep using ``from server import
vision`` regardless of the internal module layout.
"""

from server.vision.describe import (
    PERCEPTION_FAILED,
    decode_and_validate_image,
    describe_image,
    is_known_image_format,
)
from server.vision.faces import (
    DetectedFace,
    EnrollOutcome,
    FaceMatch,
    detect_faces,
    enroll_face,
    enroll_person,
    extract_faces,
    match_face,
    recognize,
)
from server.vision.perception import enroll_from_frame, perceive
from server.vision.triggers import wants_enroll, wants_vision
