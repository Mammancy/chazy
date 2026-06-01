from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.speaking_partner import PracticeRequest, SpeakingPartnerProfile
from app.models.user import User
from app.schemas.speaking_partner import (
    PracticeRequestCreate,
    PracticeRequestListResponse,
    PracticeRequestResponse,
    PracticeRequestUpdate,
    PracticeRequestUserSummary,
    RecommendedSpeakingPartnerListResponse,
    RecommendedSpeakingPartnerResponse,
    SpeakingPartnerListResponse,
    SpeakingPartnerProfileResponse,
    SpeakingPartnerProfileUpdate,
)

LEVEL_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}


class SpeakingPartnerService:
    def __init__(self, db: Session):
        self.db = db

    def list_partners(
        self,
        *,
        current_user_id: int,
        speaking_level: str | None = None,
        native_language: str | None = None,
        target_language: str | None = None,
        interests: list[str] | None = None,
        timezone: str | None = None,
    ) -> SpeakingPartnerListResponse:
        query = (
            select(SpeakingPartnerProfile)
            .where(
                SpeakingPartnerProfile.is_public.is_(True),
                SpeakingPartnerProfile.user_id != current_user_id,
            )
            .order_by(SpeakingPartnerProfile.updated_at.desc())
        )
        if speaking_level:
            query = query.where(SpeakingPartnerProfile.speaking_level == speaking_level)
        if native_language:
            query = query.where(SpeakingPartnerProfile.native_language == native_language)
        if target_language:
            query = query.where(SpeakingPartnerProfile.target_language == target_language)
        if timezone:
            query = query.where(SpeakingPartnerProfile.timezone == timezone)

        profiles = self.db.scalars(query).all()
        if interests:
            normalized = {self._normalize_interest(interest) for interest in interests if interest.strip()}
            profiles = [
                profile
                for profile in profiles
                if normalized.intersection({self._normalize_interest(item) for item in (profile.interests or [])})
            ]

        return SpeakingPartnerListResponse(partners=[self._profile_response(profile) for profile in profiles])

    def recommended_partners(self, *, current_user: User) -> RecommendedSpeakingPartnerListResponse:
        my_profile = self._profile_for_user(current_user.id)
        if my_profile is None or not self._profile_has_matching_data(my_profile):
            return RecommendedSpeakingPartnerListResponse(partners=[])

        candidates = self.db.scalars(
            select(SpeakingPartnerProfile)
            .where(
                SpeakingPartnerProfile.is_public.is_(True),
                SpeakingPartnerProfile.user_id != current_user.id,
            )
            .order_by(SpeakingPartnerProfile.updated_at.desc())
        ).all()
        recommendations = [
            self._recommended_profile_response(candidate, my_profile)
            for candidate in candidates
        ]
        recommendations.sort(key=lambda partner: partner.match_score, reverse=True)
        return RecommendedSpeakingPartnerListResponse(partners=recommendations)

    def my_profile(self, user: User) -> SpeakingPartnerProfileResponse:
        return self._profile_response(self._get_or_create_profile(user))

    def update_my_profile(
        self,
        *,
        user: User,
        payload: SpeakingPartnerProfileUpdate,
    ) -> SpeakingPartnerProfileResponse:
        profile = self._get_or_create_profile(user)
        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            if field == "interests" and value is not None:
                value = [item.strip() for item in value if item.strip()]
            if field in {"native_language", "target_language", "timezone", "bio", "speaking_level"} and isinstance(value, str):
                value = value.strip()
            setattr(profile, field, value)
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return self._profile_response(profile)

    def create_request(self, *, sender: User, payload: PracticeRequestCreate) -> PracticeRequestResponse:
        if payload.receiver_user_id == sender.id:
            raise ValueError("Choose another learner for conversation practice.")

        receiver = self.db.get(User, payload.receiver_user_id)
        if receiver is None:
            raise ValueError("Speaking partner not found.")

        receiver_profile = self._profile_for_user(payload.receiver_user_id)
        if receiver_profile is None or not receiver_profile.is_public:
            raise ValueError("Speaking partner is not available for requests.")

        existing = self.db.scalar(
            select(PracticeRequest).where(
                PracticeRequest.sender_user_id == sender.id,
                PracticeRequest.receiver_user_id == payload.receiver_user_id,
                PracticeRequest.status == "pending",
            )
        )
        if existing is not None:
            raise ValueError("A pending practice request already exists for this learner.")

        request = PracticeRequest(
            sender_user_id=sender.id,
            receiver_user_id=payload.receiver_user_id,
            message=payload.message.strip(),
            status="pending",
        )
        self.db.add(request)
        self.db.commit()
        self.db.refresh(request)
        return self._request_response(request)

    def list_requests(self, *, user_id: int) -> PracticeRequestListResponse:
        requests = self.db.scalars(
            select(PracticeRequest)
            .where(or_(PracticeRequest.sender_user_id == user_id, PracticeRequest.receiver_user_id == user_id))
            .order_by(PracticeRequest.created_at.desc())
        ).all()
        incoming = [self._request_response(item) for item in requests if item.receiver_user_id == user_id]
        outgoing = [self._request_response(item) for item in requests if item.sender_user_id == user_id]
        return PracticeRequestListResponse(incoming=incoming, outgoing=outgoing)

    def update_request(
        self,
        *,
        request_id: int,
        user_id: int,
        payload: PracticeRequestUpdate,
    ) -> PracticeRequestResponse:
        request = self.db.get(PracticeRequest, request_id)
        if request is None:
            raise ValueError("Practice request not found.")

        if payload.status in {"accepted", "rejected"} and request.receiver_user_id != user_id:
            raise PermissionError("Only the receiving learner can accept or reject this request.")
        if payload.status == "completed" and user_id not in {request.sender_user_id, request.receiver_user_id}:
            raise PermissionError("Only request participants can complete this request.")
        if request.status != "pending" and payload.status in {"accepted", "rejected"}:
            raise ValueError("Only pending practice requests can be accepted or rejected.")
        if payload.status == "completed" and request.status != "accepted":
            raise ValueError("Only accepted practice requests can be completed.")

        request.status = payload.status
        self.db.add(request)
        self.db.commit()
        self.db.refresh(request)
        return self._request_response(request)

    def _get_or_create_profile(self, user: User) -> SpeakingPartnerProfile:
        profile = self._profile_for_user(user.id)
        if profile is not None:
            return profile

        profile = SpeakingPartnerProfile(
            user_id=user.id,
            speaking_level=self._level_from_preference(user.response_length_preference),
            native_language="",
            target_language="English",
            interests=[],
            timezone=user.timezone,
            availability={},
            bio=user.bio or "",
            is_public=False,
        )
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def _profile_for_user(self, user_id: int) -> SpeakingPartnerProfile | None:
        return self.db.scalar(select(SpeakingPartnerProfile).where(SpeakingPartnerProfile.user_id == user_id))

    def _profile_response(self, profile: SpeakingPartnerProfile) -> SpeakingPartnerProfileResponse:
        user = self.db.get(User, profile.user_id)
        display_name = user.full_name if user and user.full_name else "Confidence Learner"
        return SpeakingPartnerProfileResponse(
            id=profile.id,
            user_id=profile.user_id,
            display_name=display_name,
            initials=self._initials(display_name),
            speaking_level=profile.speaking_level,
            native_language=profile.native_language,
            target_language=profile.target_language,
            interests=profile.interests or [],
            timezone=profile.timezone,
            availability=profile.availability or {},
            bio=profile.bio or "",
            is_public=profile.is_public,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    def _recommended_profile_response(
        self,
        profile: SpeakingPartnerProfile,
        my_profile: SpeakingPartnerProfile,
    ) -> RecommendedSpeakingPartnerResponse:
        base = self._profile_response(profile).model_dump()
        score, shared_interests, reasons = self._match_details(my_profile, profile)
        return RecommendedSpeakingPartnerResponse(
            **base,
            match_score=score,
            shared_interests=shared_interests,
            match_reasons=reasons,
        )

    def _match_details(
        self,
        mine: SpeakingPartnerProfile,
        partner: SpeakingPartnerProfile,
    ) -> tuple[int, list[str], list[str]]:
        score = 0
        reasons: list[str] = []

        level_delta = self._level_delta(mine.speaking_level, partner.speaking_level)
        if level_delta == 0:
            score += 30
            reasons.append("Similar speaking level")
        elif level_delta == 1:
            score += 20
            reasons.append("Adjacent speaking level")

        if self._same_text(mine.target_language, partner.target_language):
            score += 25
            reasons.append("Same target language")

        if self._same_text(partner.native_language, mine.target_language):
            score += 15
            reasons.append("Partner can model your target language")

        shared_interests = self._shared_interests(mine.interests or [], partner.interests or [])
        if shared_interests:
            score += min(len(shared_interests) * 5, 20)
            reasons.append("Shared interests")

        if self._timezone_within_three_hours(mine.timezone, partner.timezone):
            score += 10
            reasons.append("Compatible timezone")

        if self._availability_overlap(mine.availability or {}, partner.availability or {}):
            score += 15
            reasons.append("Compatible schedule")

        return min(score, 100), shared_interests, reasons

    def _request_response(self, request: PracticeRequest) -> PracticeRequestResponse:
        return PracticeRequestResponse(
            id=request.id,
            sender_user_id=request.sender_user_id,
            receiver_user_id=request.receiver_user_id,
            status=request.status,
            message=request.message or "",
            sender=self._user_summary(request.sender_user_id),
            receiver=self._user_summary(request.receiver_user_id),
            created_at=request.created_at,
        )

    def _user_summary(self, user_id: int) -> PracticeRequestUserSummary:
        user = self.db.get(User, user_id)
        profile = self._profile_for_user(user_id)
        display_name = user.full_name if user and user.full_name else "Confidence Learner"
        return PracticeRequestUserSummary(
            id=user_id,
            display_name=display_name,
            initials=self._initials(display_name),
            speaking_level=profile.speaking_level if profile else None,
            timezone=profile.timezone if profile else None,
        )

    @staticmethod
    def _initials(name: str) -> str:
        parts = [part[0] for part in name.split() if part]
        return "".join(parts[:2]).upper() or "CL"

    @staticmethod
    def _normalize_interest(value: str) -> str:
        return value.strip().lower()

    @staticmethod
    def _same_text(first: str | None, second: str | None) -> bool:
        return bool(first and second and first.strip().lower() == second.strip().lower())

    @staticmethod
    def _level_delta(first: str | None, second: str | None) -> int | None:
        if first not in LEVEL_ORDER or second not in LEVEL_ORDER:
            return None
        return abs(LEVEL_ORDER[first] - LEVEL_ORDER[second])

    def _shared_interests(self, mine: list[str], partner: list[str]) -> list[str]:
        mine_by_key = {self._normalize_interest(interest): interest for interest in mine if interest.strip()}
        partner_keys = {self._normalize_interest(interest) for interest in partner if interest.strip()}
        return [label for key, label in mine_by_key.items() if key in partner_keys]

    @staticmethod
    def _timezone_within_three_hours(first: str | None, second: str | None) -> bool:
        offsets = {
            "UTC": 0,
            "Africa/Lagos": 1,
            "Africa/Accra": 0,
            "Africa/Nairobi": 3,
            "Europe/London": 0,
            "Europe/Paris": 1,
            "America/New_York": -5,
            "America/Chicago": -6,
            "America/Los_Angeles": -8,
            "Asia/Dubai": 4,
            "Asia/Kolkata": 5.5,
        }
        if first not in offsets or second not in offsets:
            return bool(first and second and first == second)
        return abs(offsets[first] - offsets[second]) <= 3

    @staticmethod
    def _availability_overlap(first: dict, second: dict) -> bool:
        first_notes = str(first.get("notes", "")).strip().lower()
        second_notes = str(second.get("notes", "")).strip().lower()
        if first_notes and second_notes:
            first_tokens = {token for token in first_notes.replace(",", " ").split() if len(token) > 2}
            second_tokens = {token for token in second_notes.replace(",", " ").split() if len(token) > 2}
            if first_tokens.intersection(second_tokens):
                return True

        for key, first_value in first.items():
            second_value = second.get(key)
            if second_value is None:
                continue
            if isinstance(first_value, list) and isinstance(second_value, list):
                if set(first_value).intersection(second_value):
                    return True
            elif first_value == second_value:
                return True
        return False

    @staticmethod
    def _profile_has_matching_data(profile: SpeakingPartnerProfile) -> bool:
        return bool(
            profile.speaking_level
            and profile.target_language
            and (profile.interests or profile.availability or profile.timezone)
        )

    @staticmethod
    def _level_from_preference(value: str | None) -> str:
        if value == "DETAILED":
            return "advanced"
        if value == "SHORT":
            return "beginner"
        return "intermediate"
