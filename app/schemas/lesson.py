from pydantic import BaseModel


class VocabularyWordResponse(BaseModel):
    word: str
    meaning: str
    example: str


class QuizQuestionResponse(BaseModel):
    id: str
    question: str
    options: list[str]
    answer: str


class PracticeExerciseResponse(BaseModel):
    id: str
    title: str
    prompt: str


class CourseResponse(BaseModel):
    id: str
    title: str
    description: str
    category: str
    difficulty: str
    duration: str
    lesson_count: int
    progress: int
    thumbnail_tone: str


class LessonDetailResponse(CourseResponse):
    overview: str
    content: list[str]
    vocabulary: list[VocabularyWordResponse]
    exercises: list[PracticeExerciseResponse]
    quiz: list[QuizQuestionResponse]
    xp_reward: int
    badge: str
