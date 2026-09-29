"""Loopback-only local owner PIN unlock and face-enrollment endpoints.

Never trusts `X-Forwarded-For` or any other proxy header — the server does
not enable `proxy_headers`, and every route additionally checks the raw ASGI
connection origin before touching any downstream service.

Face enrollment/revocation are the ONLY way to register or purge biometric
authentication evidence: both require a fresh PIN-consumed token from
`POST /auth/owner/unlock`, enroll or revoke exclusively the token's own
owner, and route through the same deterministic authorization pipeline
(`evaluate_authorization`) every other protected action uses. This is
separate from — and never modifies — the quarantined public
`POST /vision/enroll`.
"""

from datetime import UTC, datetime
import io
from ipaddress import ip_address
import logging
from typing import Annotated
from uuid import uuid4
import wave

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)

from server import vision
from server.audio_contract import validate_wav_contract
from server.cognition.authorization import (
    AuthorizationRequest,
    DataSensitivity,
    DataVisibility,
    evaluate_authorization,
)
from server.cognition.identity import ActivePersonContext
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationStatus,
    CognitiveEvent,
)
from server.cognition.owner_authentication import (
    OwnerUnlockRateLimitedError,
    OwnerUnlockService,
)
from server.cognition.response_plan import TextTurnPayload
from server.dependencies import IdentityTokenDep, OwnerUnlockServiceDep
from server.exceptions import (
    AudioContractError,
    EnrollmentRejectedError,
    ImageContractError,
    UploadTooLargeError,
    VisionError,
)
from server.memory.biometric_consent import grant_face_consent, revoke_face_consent
from server.memory.household_authorization import record_authorization_decision
from server.memory.voice_consent import grant_voice_consent, revoke_voice_consent
from server.schemas import error_responses
from server.schemas_auth import (
    FaceEnrollResponse,
    OwnerUnlockRequest,
    OwnerUnlockResponse,
    VoiceEnrollResponse,
)
from server.settings import settings
from server.text_turn import new_interaction_scope
from server.uploads import read_limited_upload
from server.voice.speaker_embedding import (
    SpeakerBackendError,
    embed_wav,
    has_voiced_energy,
    model_id as _current_model_id,
)
from server.voice.voiceprints import count_voiceprints, enroll_voiceprint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/owner", tags=["Auth"])

_UNAUTHORIZED_DETAIL = "Owner authentication failed"
# Not the owner's name: the label is never read, so it must not duplicate a real name.
_VOICEPRINT_LABEL = "owner"


def _is_loopback(request: Request) -> bool:
    """Return whether the raw ASGI connection originates from loopback.

    Decided with IP-address semantics rather than string equality: the whole
    `127.0.0.0/8` range is loopback, and an IPv4-mapped IPv6 client arrives as
    `::ffff:127.0.0.1`. A comparison against two literals would refuse both.

    Args:
        request: Raw ASGI request; only its direct client address is read,
            never a forwarded header.

    Returns:
        `True` only when the direct peer address parses and is loopback. An
        absent or unparseable address is not local.
    """
    client = request.client
    if client is None:
        return False
    try:
        address = ip_address(client.host)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return bool((mapped or address).is_loopback)


@router.post(
    "/unlock",
    responses=error_responses(
        (401, "Wrong PIN or missing/non-owner profile"),
        (403, "Caller is not on loopback"),
        (429, "Local rate limit is blocking new attempts"),
    ),
)
async def unlock_owner(
    request: OwnerUnlockRequest,
    http_request: Request,
    response: Response,
    owner_unlock_service: OwnerUnlockServiceDep,
) -> OwnerUnlockResponse:
    """Verify the local owner PIN and issue one opaque one-use grant.

    Args:
        request: The candidate PIN — never logged or echoed.
        http_request: Raw ASGI request used only to check loopback origin.
        owner_unlock_service: Lifespan-owned unlock service (Plan 0040).

    Returns:
        The opaque token and its expiry on a successful local unlock.

    Raises:
        HTTPException: 403 for a non-loopback caller, 401 for a wrong PIN or
            missing/non-owner profile, 429 while the local rate limit blocks
            new attempts.
    """
    if not _is_loopback(http_request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local access only")
    try:
        result = await owner_unlock_service.unlock(request.pin.get_secret_value())
    except OwnerUnlockRateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHORIZED_DETAIL)
    # The body carries a usable grant; no cache may retain it.
    response.headers["Cache-Control"] = "no-store"
    return OwnerUnlockResponse(token=result.token, expires_at=result.expires_at)


def _face_event(event_type: str) -> CognitiveEvent[TextTurnPayload]:
    """Build a synthetic event envelope for one face-administration action.

    Only the event envelope (identity/correlation/timestamps) is used by the
    resolver and the authorization pipeline — the payload text itself is a
    placeholder, since no intent resolution runs for this action.

    Args:
        event_type: Synthetic event type — `"face.enroll"` or `"face.revoke"`.

    Returns:
        A fresh event scoped to exactly one face-administration request.
    """
    now = datetime.now(UTC)
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type=event_type,
        occurred_at=now,
        recorded_at=now,
        source="auth.face",
        correlation_id=uuid4(),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message=event_type, conversation_id=new_interaction_scope()),
    )


async def _authorize_biometric_action(
    owner_unlock_service: OwnerUnlockService, token: str | None, *, event_type: str
) -> tuple[ActivePersonContext, AuthorizationRequest, AuthorizationDecision]:
    """Resolve the request-scoped actor and evaluate the biometric-admin policy.

    Consumes the bound one-use token at most once via a fresh resolver, then
    evaluates `ENROLL_BIOMETRIC` through the same deterministic
    `evaluate_authorization` pipeline every other protected action uses —
    covering both the owner-role check and the explicit consent check for a
    sensitive biometric action.

    Args:
        owner_unlock_service: Lifespan-owned unlock service (Plan 0040).
        token: Optional one-use owner unlock token from the request header.
        event_type: Synthetic event type — `"face.enroll"`, `"face.revoke"`,
            `"voice.enroll"` (Plan 0053), or `"voice.revoke"` (Plan 0053).

    Returns:
        The resolved actor, the request that was evaluated, and its
        decision. The decision is `ALLOWED` only for a fresh, consumed
        owner grant.
    """
    resolver = owner_unlock_service.for_request(token)
    event = _face_event(event_type)
    actor = await resolver.resolve_actor(event)
    consent = await resolver.resolve_consent(event, actor)
    request = AuthorizationRequest(
        actor=actor,
        action=AuthorizationAction.ENROLL_BIOMETRIC,
        target_person_id=actor.person_id,
        visibility=frozenset({DataVisibility.PERSONAL}),
        sensitivity=frozenset({DataSensitivity.BIOMETRIC}),
        consent=consent,
        correlation_id=event.correlation_id,
        requested_at=event.recorded_at,
    )
    decision = evaluate_authorization(request)
    return actor, request, decision


async def _read_face_image(image: UploadFile) -> bytes:
    """Read and validate one face-enrollment image against the image contract.

    Duplicated minimally from `routers/vision.py`'s `_read_contract_image` —
    Plan 0029 Task 4 keeps `routers/vision.py` untouched, so this router
    cannot import from it.

    Image contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720 · ONE frame.

    Args:
        image: Multipart upload carrying the enrollment frame.

    Returns:
        The raw, validated image bytes.

    Raises:
        HTTPException 413: If the image exceeds MAX_UPLOAD_BYTES.
        HTTPException 422: If the image is empty, an unrecognized format,
            fails to decode, or exceeds the 1280x720 contract limit.
    """
    try:
        image_bytes = await read_limited_upload(image, limit=settings.max_image_upload_bytes)
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large — max {exc.limit // 1024 // 1024} MB",
        ) from exc
    if not image_bytes:
        raise HTTPException(status_code=422, detail="Image file is empty")
    if not vision.is_known_image_format(image_bytes):
        raise HTTPException(
            status_code=422,
            detail="Unsupported image format (contract: JPEG/PNG/WebP/GIF/BMP · max 1280x720)",
        )
    try:
        vision.decode_and_validate_image(image_bytes)
    except ImageContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return image_bytes


@router.post(
    "/face/enroll",
    responses=error_responses(
        (401, "Absent, expired, consumed, or otherwise unauthorized token"),
        (403, "Caller is not on loopback"),
        (413, "Image exceeds the upload size limit"),
        (503, "Face model unavailable"),
    ),
)
async def enroll_owner_face(
    http_request: Request,
    owner_unlock_service: OwnerUnlockServiceDep,
    image: Annotated[
        UploadFile, File(description="JPEG/PNG/WebP/GIF/BMP · max 1280x720 · one frame")
    ],
    x_iroko_identity_token: IdentityTokenDep = None,
) -> FaceEnrollResponse:
    """Enroll the token's own owner's face as local authentication evidence.

    The only way to register a face for owner authentication: loopback-only,
    requires a fresh PIN-consumed unlock token, and always enrolls the
    token's own owner — no `name` (or any other subject) field is accepted
    from the request.

    Args:
        http_request: Raw ASGI request used only to check loopback origin.
        owner_unlock_service: Lifespan-owned unlock service (Plan 0040).
        image: JPEG/PNG/WebP/GIF/BMP frame, max 1280x720 and upload limit.
        x_iroko_identity_token: One-use owner unlock token issued by
            `POST /auth/owner/unlock`.

    Returns:
        The new face profile id and the enrollment timestamp.

    Raises:
        HTTPException: 403 for a non-loopback caller; 401 for an absent,
            expired, consumed, or otherwise unauthorized token; 422 for an
            invalid image or a rejected frame (`no_face` / `multiple_faces`
            / `low_quality` / `face_too_small`); 503 if the face model
            itself fails.
    """
    if not _is_loopback(http_request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local access only")

    actor, request, decision = await _authorize_biometric_action(
        owner_unlock_service, x_iroko_identity_token, event_type="face.enroll"
    )
    await record_authorization_decision(request, decision)
    if (
        decision.decision is not AuthorizationStatus.ALLOWED
        or actor.person_id is None
        or actor.display_name is None
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHORIZED_DETAIL)

    image_bytes = await _read_face_image(image)
    try:
        outcome = await vision.enroll_person(name=actor.display_name, image=image_bytes)
    except EnrollmentRejectedError as exc:
        raise HTTPException(status_code=422, detail=f"{exc.code}: {exc}") from exc
    except VisionError as exc:
        logger.error("Face enrollment backend failed: %s", exc)
        raise HTTPException(status_code=503, detail="Face model unavailable") from exc

    await grant_face_consent(actor.person_id)
    return FaceEnrollResponse(profile_id=outcome.profile_id, enrolled_at=datetime.now(UTC))


@router.post(
    "/face/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        (401, "Absent, expired, consumed, or otherwise unauthorized token"),
        (403, "Caller is not on loopback"),
    ),
)
async def revoke_owner_face(
    http_request: Request,
    owner_unlock_service: OwnerUnlockServiceDep,
    x_iroko_identity_token: IdentityTokenDep = None,
) -> None:
    """Revoke the token's own owner's face consent and purge stored profiles.

    Args:
        http_request: Raw ASGI request used only to check loopback origin.
        owner_unlock_service: Lifespan-owned unlock service (Plan 0040).
        x_iroko_identity_token: One-use owner unlock token issued by
            `POST /auth/owner/unlock`.

    Raises:
        HTTPException: 403 for a non-loopback caller; 401 for an absent,
            expired, consumed, or otherwise unauthorized token.
    """
    if not _is_loopback(http_request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local access only")

    actor, request, decision = await _authorize_biometric_action(
        owner_unlock_service, x_iroko_identity_token, event_type="face.revoke"
    )
    await record_authorization_decision(request, decision)
    if decision.decision is not AuthorizationStatus.ALLOWED or actor.person_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHORIZED_DETAIL)

    await revoke_face_consent(actor.person_id)


def _enrollment_duration_s(audio_bytes: bytes) -> float:
    """Return a contract-passing WAV's duration in seconds.

    Call only after `validate_wav_contract` already accepted *audio_bytes* —
    this re-reads the same header without re-validating it.
    """
    with wave.open(io.BytesIO(audio_bytes), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


async def _read_enrollment_audio(audio: UploadFile) -> bytes:
    """Read and validate one voice-enrollment clip against the audio contract.

    Audio contract: WAV, 16 000 Hz, mono, signed int16. The returned bytes
    are embedded and discarded by the caller — never stored, never logged.

    Args:
        audio: Multipart upload carrying the enrollment clip.

    Returns:
        The raw, validated WAV bytes.

    Raises:
        HTTPException 413: If the upload exceeds MAX_UPLOAD_BYTES.
        HTTPException 422: If the WAV fails the audio contract, is shorter
            than `settings.speaker_min_enrollment_s`, or carries no voiced
            energy (Review Focus 1).
    """
    try:
        audio_bytes = await read_limited_upload(audio, limit=settings.max_audio_upload_bytes)
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=f"Audio too large — max {exc.limit // 1024 // 1024} MB",
        ) from exc
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="Audio file is empty")
    try:
        validate_wav_contract(audio_bytes, max_duration_s=settings.max_audio_duration_s)
    except AudioContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if _enrollment_duration_s(audio_bytes) < settings.speaker_min_enrollment_s:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Audio is shorter than the {settings.speaker_min_enrollment_s:.1f}s "
                "enrollment minimum"
            ),
        )
    if not has_voiced_energy(audio_bytes):
        raise HTTPException(status_code=422, detail="Audio is too quiet to enroll")
    return audio_bytes


@router.post(
    "/voice/enroll",
    responses=error_responses(
        (401, "Absent, expired, consumed, or otherwise unauthorized token"),
        (403, "Caller is not on loopback"),
        (413, "Audio exceeds the upload size limit"),
        (503, "Speaker authentication is disabled, or the speaker model is unavailable"),
    ),
)
async def enroll_owner_voice(
    http_request: Request,
    owner_unlock_service: OwnerUnlockServiceDep,
    audio: Annotated[UploadFile, File(description="WAV 16kHz mono int16 · one utterance")],
    x_iroko_identity_token: IdentityTokenDep = None,
) -> VoiceEnrollResponse:
    """Enroll one reference voiceprint for the token's own owner.

    Audio contract: WAV, 16 000 Hz, mono, signed int16. The audio is embedded
    and discarded — never stored, never logged, never transcribed. Several
    calls build the reference set the runtime compares a centroid against;
    `settings.speaker_min_reference_count` references are required before any
    verification is attempted.

    Disabled entirely while `settings.speaker_authentication_enabled` is
    `False` — no token is consumed and no audio is read, unlike face
    enrolment, which has no equivalent gate (Plan 0053's flag matrix is
    stricter on purpose: less voice data collected while the feature is off).

    ADR-0015 decision 1: this is `biometric_admin`, not
    `personal_protected_read`. Plan 0051 binds the grant's scope; until then
    it consumes the same unscoped one-use token the face routes consume.

    Args:
        http_request: Raw ASGI request used only to check loopback origin.
        owner_unlock_service: Lifespan-owned unlock service (Plan 0040).
        audio: WAV 16 000 Hz mono int16 clip, one utterance.
        x_iroko_identity_token: One-use owner unlock token issued by
            `POST /auth/owner/unlock`.

    Returns:
        The new voiceprint's row id, the enrollment timestamp, and how many
        references this person now has for the currently configured model.

    Raises:
        HTTPException: 403 for a non-loopback caller; 503 if speaker
            authentication is disabled, or if the speaker model itself
            fails; 401 for an absent, expired, consumed, or otherwise
            unauthorized token; 413 for an oversized upload; 422 for audio
            that fails the contract, is too short, or is too quiet.
    """
    if not _is_loopback(http_request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local access only")
    if not settings.speaker_authentication_enabled:
        raise HTTPException(status_code=503, detail="Speaker authentication is disabled")

    # Validate the clip BEFORE spending the one-use token: three references need
    # three PINs, and a too-short or silent clip is the likeliest operator error.
    audio_bytes = await _read_enrollment_audio(audio)
    actor, request, decision = await _authorize_biometric_action(
        owner_unlock_service, x_iroko_identity_token, event_type="voice.enroll"
    )
    await record_authorization_decision(request, decision)
    if (
        decision.decision is not AuthorizationStatus.ALLOWED
        or actor.person_id is None
        or actor.display_name is None
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHORIZED_DETAIL)

    current_model_id = _current_model_id()
    try:
        embedding = await embed_wav(audio_bytes)
    except SpeakerBackendError as exc:
        logger.error(
            "Voice enrollment backend failed: %s (cause: %s)",
            exc,
            type(exc.__cause__).__name__ if exc.__cause__ is not None else "none",
        )
        raise HTTPException(status_code=503, detail="Speaker model unavailable") from exc

    # Consent first: a voiceprint must never exist without an active grant.
    await grant_voice_consent(actor.person_id)
    profile_id = await enroll_voiceprint(
        actor.person_id, embedding, _VOICEPRINT_LABEL, current_model_id
    )
    reference_count = await count_voiceprints(actor.person_id, current_model_id)
    return VoiceEnrollResponse(
        profile_id=profile_id,
        enrolled_at=datetime.now(UTC),
        reference_count=reference_count,
    )


@router.post(
    "/voice/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        (401, "Absent, expired, consumed, or otherwise unauthorized token"),
        (403, "Caller is not on loopback"),
    ),
)
async def revoke_owner_voice(
    http_request: Request,
    owner_unlock_service: OwnerUnlockServiceDep,
    x_iroko_identity_token: IdentityTokenDep = None,
) -> None:
    """Revoke the token's own owner's voice consent and purge stored voiceprints.

    ADR-0015 decision 1: this is `biometric_admin`, not
    `personal_protected_read`. Plan 0051 binds the grant's scope; until then
    it consumes the same unscoped one-use token the face routes consume.

    Carries no `speaker_authentication_enabled` check — unlike enrolment,
    revocation must keep working even with the feature nominally off, so an
    owner can always purge whatever was captured before they turned it off.

    Args:
        http_request: Raw ASGI request used only to check loopback origin.
        owner_unlock_service: Lifespan-owned unlock service (Plan 0040).
        x_iroko_identity_token: One-use owner unlock token issued by
            `POST /auth/owner/unlock`.

    Raises:
        HTTPException: 403 for a non-loopback caller; 401 for an absent,
            expired, consumed, or otherwise unauthorized token.
    """
    if not _is_loopback(http_request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local access only")

    actor, request, decision = await _authorize_biometric_action(
        owner_unlock_service, x_iroko_identity_token, event_type="voice.revoke"
    )
    await record_authorization_decision(request, decision)
    if decision.decision is not AuthorizationStatus.ALLOWED or actor.person_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHORIZED_DETAIL)

    await revoke_voice_consent(actor.person_id)
