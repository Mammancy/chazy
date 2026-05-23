from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.conversation_scenario import ConversationScenarioSession, ConversationScenarioTurn
from app.models.learning_analytics import LearningIssue
from app.models.message import Message
from app.schemas.conversation_scenario import (
    ConversationScenarioListResponse,
    ConversationScenarioResponse,
    ScenarioSessionCreate,
    ScenarioSessionResponse,
    ScenarioTurnRequest,
    ScenarioTurnResponse,
)


@dataclass(frozen=True)
class ScenarioTemplate:
    scenario_key: str
    category: str
    title: str
    description: str
    role: str
    user_role: str
    starter_prompt: str
    goals: list[str]
    useful_phrases: list[str]
    steps: list[str]


SCENARIOS = [
    ScenarioTemplate(
        scenario_key="job_interview",
        category="job_interviews",
        title="Job Interview",
        description="Practice answering interview questions with clear examples and confident professional language.",
        role="Interviewer",
        user_role="Job candidate",
        starter_prompt="Tell me about yourself and why you are interested in this role.",
        goals=["Introduce yourself", "Explain experience", "Ask one professional question"],
        useful_phrases=["I have experience in...", "One example is...", "I would like to ask about..."],
        steps=["background", "experience", "strengths", "challenge", "candidate question"],
    ),
    ScenarioTemplate(
        scenario_key="airport_travel",
        category="travel_situations",
        title="Airport Travel",
        description="Practice asking for help at an airport, checking details, and solving travel problems.",
        role="Airport staff",
        user_role="Traveler",
        starter_prompt="Hello. How can I help you with your flight today?",
        goals=["Explain travel need", "Ask for directions", "Confirm time or gate"],
        useful_phrases=["Could you help me find...", "My flight number is...", "What time should I...?"],
        steps=["request help", "share flight detail", "ask direction", "confirm instruction", "thank staff"],
    ),
    ScenarioTemplate(
        scenario_key="restaurant_order",
        category="restaurants",
        title="Restaurant Order",
        description="Practice ordering food, asking questions, and handling a simple restaurant conversation.",
        role="Server",
        user_role="Customer",
        starter_prompt="Welcome. Are you ready to order, or would you like a recommendation?",
        goals=["Order clearly", "Ask about ingredients", "Make a polite request"],
        useful_phrases=["I would like...", "Does this include...?", "Could I have...?"],
        steps=["greeting", "order food", "ask ingredient", "special request", "close politely"],
    ),
    ScenarioTemplate(
        scenario_key="business_meeting",
        category="business_meetings",
        title="Business Meeting",
        description="Practice sharing updates, giving opinions, and agreeing on next steps.",
        role="Meeting lead",
        user_role="Team member",
        starter_prompt="Let's start with your update. What progress did you make this week?",
        goals=["Give update", "State blocker", "Suggest next step"],
        useful_phrases=["This week I completed...", "The main blocker is...", "I suggest that we..."],
        steps=["progress update", "blocker", "opinion", "next step", "confirm action"],
    ),
    ScenarioTemplate(
        scenario_key="academic_discussion",
        category="academic_discussions",
        title="Academic Discussion",
        description="Practice explaining ideas, supporting opinions, and responding to another viewpoint.",
        role="Class discussion partner",
        user_role="Student",
        starter_prompt="What is your opinion on today's topic, and what evidence supports it?",
        goals=["State opinion", "Give reason", "Respond to follow-up"],
        useful_phrases=["In my opinion...", "The evidence suggests...", "I agree partly because..."],
        steps=["opinion", "evidence", "example", "counterpoint", "summary"],
    ),
    ScenarioTemplate(
        scenario_key="social_introduction",
        category="social_interactions",
        title="Social Introduction",
        description="Practice casual introductions, small talk, and friendly follow-up questions.",
        role="New acquaintance",
        user_role="Conversation partner",
        starter_prompt="Hi, I don't think we've met before. What's your name?",
        goals=["Introduce yourself", "Share one detail", "Ask a follow-up question"],
        useful_phrases=["Nice to meet you.", "I enjoy...", "What about you?"],
        steps=["name", "background", "interest", "follow-up question", "friendly close"],
    ),
]


class ConversationScenarioService:
    def __init__(self, db: Session):
        self.db = db

    def list_scenarios(self) -> ConversationScenarioListResponse:
        return ConversationScenarioListResponse(scenarios=[self._template_response(template) for template in SCENARIOS])

    def start_session(self, payload: ScenarioSessionCreate) -> ScenarioSessionResponse:
        template = self._template(payload.scenario_key)
        difficulty = payload.difficulty or self.adapt_difficulty(session_id=payload.session_id, user_id=payload.user_id)
        scenario_session = ConversationScenarioSession(
            session_id=payload.session_id,
            user_id=payload.user_id,
            conversation_id=payload.conversation_id,
            scenario_key=template.scenario_key,
            category=template.category,
            difficulty=difficulty,
            target_steps=self._target_steps(difficulty),
            scenario_context={
                "title": template.title,
                "role": template.role,
                "user_role": template.user_role,
                "goals": template.goals,
                "useful_phrases": template.useful_phrases,
            },
        )
        self.db.add(scenario_session)
        self.db.commit()
        self.db.refresh(scenario_session)
        return self._session_response(scenario_session, template)

    def respond(self, scenario_session_id: int, payload: ScenarioTurnRequest) -> ScenarioTurnResponse:
        scenario_session = self.db.get(ConversationScenarioSession, scenario_session_id)
        if scenario_session is None:
            raise ValueError("Conversation scenario session not found.")
        template = self._template(scenario_session.scenario_key)
        step_number = scenario_session.current_step + 1
        feedback = self._feedback(payload.message, scenario_session.difficulty)
        assistant_reply = self._assistant_reply(template, scenario_session, payload.message, step_number)

        scenario_session.current_step = step_number
        completed = scenario_session.current_step >= scenario_session.target_steps
        if completed:
            scenario_session.status = "completed"
            scenario_session.completed_at = datetime.now(timezone.utc)

        self.db.add(
            ConversationScenarioTurn(
                scenario_session_id=scenario_session.id,
                user_message_id=payload.user_message_id,
                assistant_message_id=payload.assistant_message_id,
                user_text=payload.message,
                assistant_text=assistant_reply,
                feedback=feedback,
                step_number=step_number,
            )
        )
        self.db.commit()
        self.db.refresh(scenario_session)
        return ScenarioTurnResponse(
            scenario_session_id=scenario_session.id,
            status=scenario_session.status,
            step_number=step_number,
            assistant_reply=assistant_reply,
            feedback=feedback,
            next_prompt=self._next_prompt(template, scenario_session),
            coaching_tip=self._coaching_tip(scenario_session.difficulty),
            difficulty=scenario_session.difficulty,
            completed=completed,
        )

    def active_session(self, *, session_id: str, user_id: int | None = None) -> ConversationScenarioSession | None:
        query = select(ConversationScenarioSession).where(
            ConversationScenarioSession.session_id == session_id,
            ConversationScenarioSession.status == "active",
        )
        if user_id is not None:
            query = query.where(
                or_(
                    ConversationScenarioSession.user_id == user_id,
                    ConversationScenarioSession.user_id.is_(None),
                )
            )
        return self.db.scalar(query.order_by(ConversationScenarioSession.updated_at.desc()).limit(1))

    def chat_mode_reply(
        self,
        *,
        session_id: str,
        user_id: int | None,
        conversation_id: int | None,
        message: str,
        user_message_id: int | None = None,
        assistant_message_id: int | None = None,
    ) -> ScenarioTurnResponse:
        scenario_session = self.active_session(session_id=session_id, user_id=user_id)
        if scenario_session is None:
            scenario_session = self.start_session(
                ScenarioSessionCreate(
                    session_id=session_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    scenario_key="social_introduction",
                )
            )
            scenario_session_id = scenario_session.scenario_session_id
        else:
            scenario_session_id = scenario_session.id
        return self.respond(
            scenario_session_id,
            ScenarioTurnRequest(
                message=message,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
            ),
        )

    def adapt_difficulty(self, *, session_id: str, user_id: int | None = None) -> str:
        scores = []
        query = select(Message).where(Message.role == "user")
        if user_id is not None:
            query = query.where(Message.user_id == user_id)
        else:
            query = query.where(Message.metadata_json["session_id"].as_string() == session_id)
        for message in self.db.scalars(query.order_by(Message.created_at.desc()).limit(20)).all():
            score = (message.metadata_json or {}).get("fluency_score")
            if isinstance(score, int):
                scores.append(score)
        issue_count = self.db.query(LearningIssue).filter(LearningIssue.session_id == session_id).count()
        average = round(sum(scores) / len(scores)) if scores else 55
        if average >= 78 and issue_count <= 4:
            return "advanced"
        if average >= 58:
            return "intermediate"
        return "beginner"

    def _template(self, scenario_key: str) -> ScenarioTemplate:
        for template in SCENARIOS:
            if template.scenario_key == scenario_key:
                return template
        raise ValueError("Conversation scenario not found.")

    def _template_response(self, template: ScenarioTemplate) -> ConversationScenarioResponse:
        return ConversationScenarioResponse(
            scenario_key=template.scenario_key,
            category=template.category,
            title=template.title,
            description=template.description,
            role=template.role,
            user_role=template.user_role,
            difficulty_levels=["beginner", "intermediate", "advanced"],
            starter_prompt=template.starter_prompt,
            goals=template.goals,
            useful_phrases=template.useful_phrases,
        )

    def _session_response(
        self,
        scenario_session: ConversationScenarioSession,
        template: ScenarioTemplate,
    ) -> ScenarioSessionResponse:
        return ScenarioSessionResponse(
            scenario_session_id=scenario_session.id,
            session_id=scenario_session.session_id,
            user_id=scenario_session.user_id,
            conversation_id=scenario_session.conversation_id,
            scenario=self._template_response(template),
            difficulty=scenario_session.difficulty,
            status=scenario_session.status,
            current_step=scenario_session.current_step,
            target_steps=scenario_session.target_steps,
            next_prompt=template.starter_prompt,
            coaching_tip=self._coaching_tip(scenario_session.difficulty),
            useful_phrases=template.useful_phrases,
            context=scenario_session.scenario_context or {},
            created_at=scenario_session.created_at,
        )

    def _assistant_reply(
        self,
        template: ScenarioTemplate,
        scenario_session: ConversationScenarioSession,
        message: str,
        step_number: int,
    ) -> str:
        next_prompt = self._next_prompt(template, scenario_session)
        role_prefix = f"{template.role}:"
        if scenario_session.difficulty == "beginner":
            return f"{role_prefix} Good. I understood you. {next_prompt}"
        if scenario_session.difficulty == "advanced":
            return f"{role_prefix} Thanks for that detail. Let me challenge you further: {next_prompt}"
        return f"{role_prefix} That is clear. {next_prompt}"

    def _next_prompt(self, template: ScenarioTemplate, scenario_session: ConversationScenarioSession) -> str:
        index = min(scenario_session.current_step, len(template.steps) - 1)
        focus = template.steps[index]
        prompts = {
            "beginner": f"Please answer with one clear sentence about {focus}.",
            "intermediate": f"Please explain {focus} in two or three connected sentences.",
            "advanced": f"Please discuss {focus} with a specific example and a follow-up question.",
        }
        return prompts.get(scenario_session.difficulty, prompts["intermediate"])

    def _feedback(self, message: str, difficulty: str) -> str:
        word_count = len(message.split())
        if difficulty == "beginner" and word_count < 4:
            return "Try to answer with a complete sentence, not only one or two words."
        if difficulty == "advanced" and word_count < 12:
            return "Add a concrete example or reason to make your answer sound more advanced."
        if any(word in message.lower() for word in ("because", "so", "but", "although")):
            return "Good use of connecting words. Keep linking your ideas clearly."
        return "Good attempt. Try adding because, so, or but to connect your next idea."

    def _coaching_tip(self, difficulty: str) -> str:
        if difficulty == "beginner":
            return "Use short complete sentences and repeat the role-play answer aloud."
        if difficulty == "advanced":
            return "Use examples, reasons, and professional follow-up questions."
        return "Use two connected sentences and include one specific detail."

    def _target_steps(self, difficulty: str) -> int:
        if difficulty == "beginner":
            return 4
        if difficulty == "advanced":
            return 7
        return 5
