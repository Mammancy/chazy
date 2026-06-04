from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lesson_progress import LessonProgress
from app.schemas.lesson import CourseResponse, LessonCompleteResponse, LessonDetailResponse


LESSONS = [
    LessonDetailResponse(
        id="beginner-foundations",
        title="Speaking Confidence Foundations",
        description="Build simple sentences, greetings, and confident speaking basics.",
        category="Speaking Foundations",
        difficulty="Beginner",
        duration="2h 20m",
        lesson_count=12,
        progress=68,
        thumbnail_tone="cyan",
        overview="Learn the essential patterns needed for clear daily communication.",
        content=[
            "Introduce yourself with a simple structure.",
            "Use present tense for everyday routines.",
            "Ask and answer basic follow-up questions.",
        ],
        vocabulary=[
            {
                "word": "Introduce",
                "meaning": "To tell someone your name or basic information.",
                "example": "Let me introduce myself.",
            },
            {
                "word": "Routine",
                "meaning": "Something you do regularly.",
                "example": "My morning routine starts at 7 AM.",
            },
        ],
        exercises=[
            {
                "id": "ex-1",
                "title": "Self introduction",
                "prompt": "Record a 30-second introduction with your name and goal.",
            },
        ],
        quiz=[
            {
                "id": "q-1",
                "question": "Which sentence is correct?",
                "options": ["I am practice speaking.", "I am practicing speaking.", "I practicing speaking."],
                "answer": "I am practicing speaking.",
            },
        ],
        xp_reward=120,
        badge="Foundation Builder",
    ),
    LessonDetailResponse(
        id="daily-conversation-flow",
        title="Conversation Mastery Flow",
        description="Practice natural small talk, polite replies, and follow-ups.",
        category="Daily Conversation",
        difficulty="Beginner",
        duration="1h 45m",
        lesson_count=9,
        progress=42,
        thumbnail_tone="emerald",
        overview="Become smoother in everyday conversations.",
        content=[
            "Open a conversation with context.",
            "Ask natural follow-up questions.",
            "Close conversations politely.",
        ],
        vocabulary=[
            {
                "word": "Actually",
                "meaning": "Used to add or correct information.",
                "example": "Actually, I started learning last month.",
            },
            {
                "word": "Sounds good",
                "meaning": "A natural way to agree.",
                "example": "Sounds good, see you tomorrow.",
            },
        ],
        exercises=[
            {
                "id": "ex-2",
                "title": "Coffee shop chat",
                "prompt": "Practice ordering and asking one friendly question.",
            },
        ],
        quiz=[
            {
                "id": "q-2",
                "question": "Which phrase is most natural?",
                "options": ["How are you doing?", "How you doing are?", "How do you are?"],
                "answer": "How are you doing?",
            },
        ],
        xp_reward=140,
        badge="Conversation Starter",
    ),
    LessonDetailResponse(
        id="grammar-mastery-tenses",
        title="Grammar Mastery: Tenses",
        description="Use past, present, and future tenses with clarity.",
        category="Grammar Mastery",
        difficulty="Intermediate",
        duration="3h 10m",
        lesson_count=16,
        progress=35,
        thumbnail_tone="violet",
        overview="Improve grammar accuracy through practical speaking examples.",
        content=[
            "Choose the right tense for timelines.",
            "Fix common tense errors in spoken answers.",
            "Tell stories using past tense sequences.",
        ],
        vocabulary=[
            {
                "word": "Completed",
                "meaning": "Finished.",
                "example": "I completed the project yesterday.",
            },
            {
                "word": "Currently",
                "meaning": "Happening now.",
                "example": "I am currently improving my grammar.",
            },
        ],
        exercises=[
            {
                "id": "ex-3",
                "title": "Past tense story",
                "prompt": "Describe one problem you solved last week.",
            },
        ],
        quiz=[
            {
                "id": "q-3",
                "question": "Choose the correct past tense.",
                "options": ["I go yesterday.", "I went yesterday.", "I gone yesterday."],
                "answer": "I went yesterday.",
            },
        ],
        xp_reward=180,
        badge="Grammar Sharpener",
    ),
    LessonDetailResponse(
        id="business-english-meetings",
        title="Public Speaking for Meetings",
        description="Speak with structure in updates, presentations, and decisions.",
        category="Public Speaking",
        difficulty="Advanced",
        duration="2h 55m",
        lesson_count=14,
        progress=24,
        thumbnail_tone="blue",
        overview="Sound polished and concise in professional speaking settings.",
        content=[
            "Lead with outcomes before details.",
            "Use concise meeting phrases.",
            "Disagree politely and clearly.",
        ],
        vocabulary=[
            {
                "word": "Outcome",
                "meaning": "The result of an action.",
                "example": "The outcome was better than expected.",
            },
            {
                "word": "Priority",
                "meaning": "Something more important than other things.",
                "example": "Our priority is customer trust.",
            },
        ],
        exercises=[
            {
                "id": "ex-4",
                "title": "Project update",
                "prompt": "Give a 45-second update using result, reason, and next step.",
            },
        ],
        quiz=[
            {
                "id": "q-4",
                "question": "Which opening is strongest for a meeting update?",
                "options": [
                    "I want to talk many things.",
                    "The rollout is on track, and we resolved the blocker.",
                    "Yesterday maybe we did work.",
                ],
                "answer": "The rollout is on track, and we resolved the blocker.",
            },
        ],
        xp_reward=220,
        badge="Meeting Pro",
    ),
    LessonDetailResponse(
        id="pronunciation-rhythm",
        title="Pronunciation Rhythm",
        description="Improve stress, pacing, and final consonant clarity.",
        category="Pronunciation",
        difficulty="Intermediate",
        duration="1h 30m",
        lesson_count=8,
        progress=58,
        thumbnail_tone="amber",
        overview="Train your mouth and rhythm for clearer spoken communication.",
        content=[
            "Stress the important word in a sentence.",
            "Pause naturally between ideas.",
            "Finish final consonants clearly.",
        ],
        vocabulary=[
            {
                "word": "Rhythm",
                "meaning": "The pattern and speed of speech.",
                "example": "Your rhythm sounds more natural now.",
            },
            {
                "word": "Stress",
                "meaning": "Extra emphasis on a word or sound.",
                "example": "Stress the word responsible.",
            },
        ],
        exercises=[
            {
                "id": "ex-5",
                "title": "Final consonants",
                "prompt": "Repeat: project, worked, improved, helped.",
            },
        ],
        quiz=[
            {
                "id": "q-5",
                "question": "What should you do before an important idea?",
                "options": ["Rush", "Pause briefly", "Lower every sound"],
                "answer": "Pause briefly",
            },
        ],
        xp_reward=160,
        badge="Clear Speaker",
    ),
    LessonDetailResponse(
        id="interview-practice-star",
        title="Interview Practice: STAR Answers",
        description="Answer interview questions with confident structure.",
        category="Interview Practice",
        difficulty="Advanced",
        duration="2h 15m",
        lesson_count=10,
        progress=15,
        thumbnail_tone="rose",
        overview="Use clear examples to answer interview questions naturally.",
        content=[
            "Structure answers with situation, task, action, result.",
            "Avoid long introductions.",
            "End with a confident learning point.",
        ],
        vocabulary=[
            {
                "word": "Responsible",
                "meaning": "In charge of something.",
                "example": "I was responsible for leading the timeline.",
            },
            {
                "word": "Improved",
                "meaning": "Made better.",
                "example": "We improved the response time by 20%.",
            },
        ],
        exercises=[
            {
                "id": "ex-6",
                "title": "Behavioral answer",
                "prompt": "Answer: Tell me about a time you solved a difficult problem.",
            },
        ],
        quiz=[
            {
                "id": "q-6",
                "question": "What does the R in STAR mean?",
                "options": ["Reason", "Result", "Routine"],
                "answer": "Result",
            },
        ],
        xp_reward=240,
        badge="Interview Ready",
    ),
]


class LessonService:
    def __init__(self, db: Session):
        self.db = db

    def list_courses(
        self,
        *,
        user_id: int,
        category: str | None = None,
        difficulty: str | None = None,
        search: str | None = None,
    ) -> list[CourseResponse]:
        lessons = LESSONS
        if category and category != "All":
            lessons = [lesson for lesson in lessons if lesson.category == category]
        if difficulty and difficulty != "All":
            lessons = [lesson for lesson in lessons if lesson.difficulty == difficulty]
        if search:
            normalized_search = search.lower()
            lessons = [
                lesson
                for lesson in lessons
                if normalized_search in lesson.title.lower()
                or normalized_search in lesson.description.lower()
            ]

        progress_by_lesson = self._progress_by_lesson(user_id=user_id)
        return [
            CourseResponse(
                id=lesson.id,
                title=lesson.title,
                description=lesson.description,
                category=lesson.category,
                difficulty=lesson.difficulty,
                duration=lesson.duration,
                lesson_count=lesson.lesson_count,
                progress=progress_by_lesson.get(lesson.id, lesson.progress).progress
                if lesson.id in progress_by_lesson
                else lesson.progress,
                completed=lesson.id in progress_by_lesson and progress_by_lesson[lesson.id].completed_at is not None,
                completed_at=self._iso(progress_by_lesson[lesson.id].completed_at)
                if lesson.id in progress_by_lesson
                else None,
                thumbnail_tone=lesson.thumbnail_tone,
            )
            for lesson in lessons
        ]

    def get_lesson(self, lesson_id: str, *, user_id: int) -> LessonDetailResponse | None:
        lesson = next((item for item in LESSONS if item.id == lesson_id), None)
        if lesson is None:
            return None
        progress = self._progress(user_id=user_id, lesson_id=lesson_id)
        return lesson.model_copy(
            update={
                "progress": progress.progress if progress else lesson.progress,
                "completed": progress.completed_at is not None if progress else False,
                "completed_at": self._iso(progress.completed_at) if progress else None,
            },
        )

    def complete_lesson(self, lesson_id: str, *, user_id: int) -> LessonCompleteResponse | None:
        lesson = next((item for item in LESSONS if item.id == lesson_id), None)
        if lesson is None:
            return None

        progress = self._progress(user_id=user_id, lesson_id=lesson_id)
        already_completed = progress is not None and progress.completed_at is not None
        if progress is None:
            progress = LessonProgress(user_id=user_id, lesson_id=lesson_id)
            self.db.add(progress)

        if not already_completed:
            progress.progress = 100
            progress.xp_awarded = lesson.xp_reward
            progress.badge = lesson.badge
            progress.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(progress)

        detail = self.get_lesson(lesson_id, user_id=user_id)
        return LessonCompleteResponse(
            lesson=detail,
            xp_awarded=0 if already_completed else lesson.xp_reward,
            badge=lesson.badge,
            already_completed=already_completed,
        )

    def completed_count(self, *, user_id: int | None) -> int:
        if user_id is None:
            return 0
        return self.db.query(LessonProgress).filter(
            LessonProgress.user_id == user_id,
            LessonProgress.completed_at.is_not(None),
        ).count()

    def _progress(self, *, user_id: int, lesson_id: str) -> LessonProgress | None:
        return self.db.scalar(
            select(LessonProgress).where(
                LessonProgress.user_id == user_id,
                LessonProgress.lesson_id == lesson_id,
            ).limit(1),
        )

    def _progress_by_lesson(self, *, user_id: int) -> dict[str, LessonProgress]:
        rows = self.db.scalars(select(LessonProgress).where(LessonProgress.user_id == user_id)).all()
        return {row.lesson_id: row for row in rows}

    @staticmethod
    def _iso(value) -> str | None:
        return value.isoformat() if value else None
