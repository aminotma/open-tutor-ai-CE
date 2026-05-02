from typing import List, Optional, Dict, Any
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from open_webui.internal.db import get_db
from open_webui.utils.auth import get_verified_user
from open_tutorai.agents.adaptive_tutor_agent import AdaptiveTutorAgent
from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG
from open_tutorai.routers.context_retrieval import retrieve_pedagogical_documents

router = APIRouter(tags=["adaptive"])


class InteractionHistoryItem(BaseModel):
    content: str = Field(..., description="User interaction content")
    outcome: Optional[str] = Field(None, description="Outcome label, e.g. correct/incorrect")
    score: Optional[float] = Field(None, description="Performance score from 0 to 1")
    timestamp: Optional[float] = Field(None, description="Unix timestamp of the interaction")


class AdaptiveTutorRequest(BaseModel):
    topic: str = Field(..., description="Learning topic or concept")
    current_level: Optional[str] = Field(
        "intermediate",
        description="Current learner level: beginner, intermediate, advanced"
    )
    recent_interactions: Optional[List[InteractionHistoryItem]] = Field(
        None,
        description="Recent learner interactions with outcomes and scores"
    )
    feedback_comments: Optional[List[str]] = Field(
        None,
        description="Learner comments or feedback about difficulties"
    )
    learning_objectives: Optional[List[str]] = Field(
        None,
        description="Learning objectives that should shape the tutoring strategy"
    )
    preferred_exercise_types: Optional[List[str]] = Field(
        None,
        description="Preferred exercise types such as multiple-choice or worked examples"
    )
    use_langchain: Optional[bool] = Field(
        True,   
        description="Whether to use LangChain for orchestration (default: True)"
    )

class ExerciseSuggestion(BaseModel):
    id: str
    difficulty: str
    question: str
    hint: str
    answer: str
    skill_target: str


class VerificationSource(BaseModel):
    source_id: str
    title: Optional[str] = None
    preview: str
    relevance_score: float
    path: Optional[str] = None


class StrategyDecision(BaseModel):
    id: str
    action: str
    rationale: str
    priority: int
    dependencies: Optional[List[str]] = None


class VerificationReport(BaseModel):
    verified: bool
    support_score: float
    supported_items: List[str]
    unsupported_items: List[str]
    sources: List[VerificationSource]
    verdict: str
    note: Optional[str] = None


class AdaptiveTutorResponse(BaseModel):
    adjusted_level: str
    detected_difficulties: List[str]
    suggested_exercises: List[ExerciseSuggestion]
    strategy: List[str]
    strategy_decisions: Optional[List[StrategyDecision]] = None
    priority_focus: List[str]
    verification: Optional[VerificationReport] = None
    agent_trace: Optional[List[str]] = None
    notes: Optional[str] = None


NEGATIVE_FEEDBACK_KEYWORDS = [
    "confused",
    "hard",
    "difficult",
    "struggle",
    "mistake",
    "wrong",
    "lost",
    "unclear",
    "challenge",
    "stuck"
]

LEVEL_ORDER = ["beginner", "intermediate", "advanced"]


def normalize_level(level: Optional[str]) -> str:
    if not level:
        return "intermediate"
    lower = level.lower()
    return lower if lower in LEVEL_ORDER else "intermediate"


def parse_feedback_difficulties(feedback_comments: List[str]) -> List[str]:
    difficulties = []
    for comment in feedback_comments:
        text = comment.lower()
        if any(keyword in text for keyword in NEGATIVE_FEEDBACK_KEYWORDS):
            cleaned = text.replace("\n", " ").strip()
            if len(cleaned) > 0:
                difficulties.append(cleaned)
    return difficulties


def assess_current_level(
    current_level: str,
    interactions: Optional[List[InteractionHistoryItem]],
    feedback_comments: Optional[List[str]]
) -> str:
    level = normalize_level(current_level)
    if not interactions and not feedback_comments:
        return level

    total_score = 0.0
    scored_items = 0
    difficulty_flags = 0

    if interactions:
        for item in interactions:
            if item.score is not None:
                total_score += max(0.0, min(item.score, 1.0))
                scored_items += 1
                if item.score < 0.6:
                    difficulty_flags += 1
            if item.outcome and item.outcome.lower() in ["incorrect", "wrong", "failed"]:
                difficulty_flags += 1

    if feedback_comments:
        difficulty_flags += len(parse_feedback_difficulties(feedback_comments))

    average_score = total_score / scored_items if scored_items else 0.7

    if average_score >= 0.85 and difficulty_flags == 0:
        if level == "beginner":
            return "intermediate"
        if level == "intermediate":
            return "advanced"
    if average_score <= 0.55 or difficulty_flags >= 2:
        if level == "advanced":
            return "intermediate"
        if level == "intermediate":
            return "beginner"

    return level


def detect_difficulties(
    topic: str,
    interactions: Optional[List[InteractionHistoryItem]],
    feedback_comments: Optional[List[str]],
    learning_objectives: Optional[List[str]]
) -> List[str]:
    difficulties = []
    if feedback_comments:
        difficulties.extend(parse_feedback_difficulties(feedback_comments))

    if interactions:
        for item in interactions:
            if item.score is not None and item.score < 0.6:
                label = item.outcome or "low performance"
                difficulties.append(f"Difficulté avec l'interaction : {label}")
            if item.content and topic.lower() in item.content.lower():
                if item.score is not None and item.score < 0.6:
                    difficulties.append(f"Compréhension de {topic} insuffisante")

    if learning_objectives:
        for objective in learning_objectives:
            if any(keyword in objective.lower() for keyword in ["understand", "comprehend", "maîtriser"]):
                difficulties.append(f"Objectif à clarifier: {objective}")

    unique_difficulties = []
    for difficulty in difficulties:
        if difficulty not in unique_difficulties:
            unique_difficulties.append(difficulty)
    return unique_difficulties[:5]


def build_exercise_prompt(topic: str, level: str, objective: Optional[str], index: int) -> Dict[str, str]:
    base_topic = topic.capitalize()
    difficulty_descriptor = {
        "beginner": "simple",
        "intermediate": "standard",
        "advanced": "challenging"
    }[level]

    if objective:
        prompt = f"Propose un exercice {difficulty_descriptor} sur {base_topic} axé sur {objective}."
    else:
        prompt = f"Propose un exercice {difficulty_descriptor} sur {base_topic} avec une correction pas à pas."

    return {
        "question": f"Exercice {index}: {prompt}",
        "hint": f"Réfléchis aux éléments fondamentaux de {topic}.",
        "answer": f"Réponse attendue pour l'exercice {index} sur {topic}.",
        "skill_target": objective or f"Maîtrise de {topic}"
    }


def generate_exercises(
    topic: str,
    level: str,
    learning_objectives: Optional[List[str]],
    preferred_exercise_types: Optional[List[str]],
    count: int = 3
) -> List[Dict[str, Any]]:
    objectives = learning_objectives or []
    exercises = []
    for idx in range(1, count + 1):
        objective = objectives[idx - 1] if idx - 1 < len(objectives) else None
        exercise = build_exercise_prompt(topic, level, objective, idx)
        exercises.append({
            "id": f"exercise_{idx}",
            "difficulty": level,
            "question": exercise["question"],
            "hint": exercise["hint"],
            "answer": exercise["answer"],
            "skill_target": exercise["skill_target"]
        })
    return exercises


def plan_learning_strategy(
    topic: str,
    adjusted_level: str,
    difficulties: List[str],
    feedback_comments: Optional[List[str]]
) -> List[str]:
    strategy = []
    focus = []

    if difficulties:
        primary = difficulties[0]
        strategy.append(
            f"Se concentrer immédiatement sur la difficulté principale : {primary}."
        )
        focus.append(primary)
        strategy.append(
            f"Revoir le concept de base lié à {topic} avant de proposer de nouveaux exercices."
        )
        strategy.append(
            f"Proposer des exercices guidés adaptés au niveau {adjusted_level} et bâtir la confiance sur des points précis."
        )
        strategy.append(
            "Utiliser le feedback de l'apprenant pour ajuster la progression en temps réel, sans simplement offrir des options."
        )
    else:
        strategy.append(
            f"Le niveau actuel est stable ({adjusted_level}). Continuer avec des exercices progressifs sur {topic}."
        )
        strategy.append(
            "Renforcer les acquis avec une pratique ciblée, puis vérifier la compréhension par un court auto-test."
        )
        strategy.append(
            "Surveiller les retours de l'apprenant pour détecter toute difficulté émergente."
        )

    if feedback_comments:
        combined_feedback = " ".join(feedback_comments[:2])
        strategy.append(
            f"Prendre en compte les retours suivants : {combined_feedback}."
        )

    return strategy


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _tokenize(text: str) -> List[str]:
    return [token for token in re.findall(r"\w{4,}", text.lower())]


def _is_text_supported(candidate: str, source_corpus: str, threshold: float = 0.15) -> bool:
    candidate_tokens = _tokenize(candidate)
    if not candidate_tokens or not source_corpus:
        return False

    source_tokens = set(_tokenize(source_corpus))
    match_count = sum(1 for token in candidate_tokens if token in source_tokens)
    return (match_count / len(candidate_tokens)) >= threshold


def _build_verification_candidates(
    request: AdaptiveTutorRequest,
    exercises: List[Dict[str, Any]],
    strategy: List[str]
) -> List[str]:
    candidates = [request.topic]
    if request.learning_objectives:
        candidates.extend(request.learning_objectives)
    for exercise in exercises:
        candidates.append(exercise["question"])
        candidates.append(exercise["answer"])
    candidates.extend(strategy)
    return [c for c in candidates if c and c.strip()]


async def verify_adaptive_tutor_output(
    user_id: str,
    request: AdaptiveTutorRequest,
    exercises: List[Dict[str, Any]],
    strategy: List[str]
) -> VerificationReport:
    rag_config = CONTEXT_RETRIEVAL_CONFIG.get("rag", {})
    if not rag_config.get("verification_enabled", False):
        return VerificationReport(
            verified=False,
            support_score=0.0,
            supported_items=[],
            unsupported_items=[],
            sources=[],
            verdict="verification_disabled",
            note="La vérification RAG est désactivée dans la configuration."
        )

    query = request.topic
    if request.learning_objectives:
        query += " " + " ".join(request.learning_objectives)

    sources = await retrieve_pedagogical_documents(
        user_id,
        query,
        top_k=rag_config.get("top_k_documents", 5)
    )

    if not sources:
        return VerificationReport(
            verified=False,
            support_score=0.0,
            supported_items=[],
            unsupported_items=[],
            sources=[],
            verdict="no_sources_found",
            note=(
                "Aucune source vérifiée n'a été trouvée. "
                "La vérification nécessite un système RAG ou des documents locaux disponibles."
            )
        )

    source_corpus = " ".join([src.get("content", "") for src in sources])
    candidates = _build_verification_candidates(request, exercises, strategy)

    supported_items = []
    unsupported_items = []
    for candidate in candidates:
        if _is_text_supported(candidate, source_corpus):
            supported_items.append(candidate)
        else:
            unsupported_items.append(candidate)

    support_score = len(supported_items) / max(1, len(candidates))
    threshold = rag_config.get("verification_threshold", 0.65)
    verified = support_score >= threshold
    verdict = "supported" if verified else "needs_review"

    return VerificationReport(
        verified=verified,
        support_score=round(support_score, 3),
        supported_items=supported_items,
        unsupported_items=unsupported_items,
        sources=[
            VerificationSource(
                source_id=src.get("id", ""),
                title=src.get("metadata", {}).get("title"),
                preview=(src.get("content", "")[:280] + "...") if len(src.get("content", "")) > 280 else src.get("content", ""),
                relevance_score=round(src.get("relevance_score", 0.0), 3),
                path=src.get("metadata", {}).get("path")
            )
            for src in sources
        ],
        verdict=verdict,
        note=(
            "Vérification terminée à l'aide des sources RAG locales. "
            "Les éléments non appuyés doivent être relus ou enrichis."
            if verified else
            "Certains éléments n'ont pas pu être appuyés par les sources disponibles."
        )
    )


class AdaptiveTutorVerificationRequest(BaseModel):
    topic: str = Field(..., description="Sujet ou question du tutoriel à vérifier")
    generated_texts: List[str] = Field(..., description="Textes ou énoncés générés par le tutor à vérifier")
    learning_objectives: Optional[List[str]] = Field(
        None,
        description="Objectifs pédagogiques utilisés pour orienter la vérification"
    )


@router.post("/adaptive/verify", response_model=VerificationReport)
async def verify_adaptive_output(
    request: AdaptiveTutorVerificationRequest,
    user=Depends(get_verified_user)
):
    rag_config = CONTEXT_RETRIEVAL_CONFIG.get("rag", {})
    if not rag_config.get("verification_enabled", False):
        return VerificationReport(
            verified=False,
            support_score=0.0,
            supported_items=[],
            unsupported_items=[],
            sources=[],
            verdict="verification_disabled",
            note="La vérification RAG est désactivée dans la configuration."
        )

    query = request.topic
    if request.learning_objectives:
        query += " " + " ".join(request.learning_objectives)

    sources = await retrieve_pedagogical_documents(
        user.id,
        query,
        top_k=rag_config.get("top_k_documents", 5)
    )

    source_corpus = " ".join([src.get("content", "") for src in sources])
    supported_items = []
    unsupported_items = []
    for text in request.generated_texts:
        if _is_text_supported(text, source_corpus):
            supported_items.append(text)
        else:
            unsupported_items.append(text)

    support_score = len(supported_items) / max(1, len(request.generated_texts))
    verified = support_score >= rag_config.get("verification_threshold", 0.65)
    verdict = "supported" if verified else "needs_review"

    return VerificationReport(
        verified=verified,
        support_score=round(support_score, 3),
        supported_items=supported_items,
        unsupported_items=unsupported_items,
        sources=[
            VerificationSource(
                source_id=src.get("id", ""),
                title=src.get("metadata", {}).get("title"),
                preview=(src.get("content", "")[:280] + "...") if len(src.get("content", "")) > 280 else src.get("content", ""),
                relevance_score=round(src.get("relevance_score", 0.0), 3),
                path=src.get("metadata", {}).get("path")
            )
            for src in sources
        ],
        verdict=verdict,
        note=(
            "Vérification terminée à l'aide des sources RAG locales. "
            "Les éléments non appuyés doivent être relus ou enrichis."
            if verified else
            "Certains éléments n'ont pas pu être appuyés par les sources disponibles."
        )
    )


@router.post("/adaptive/plan", response_model=AdaptiveTutorResponse)
async def create_adaptive_plan(
    request: AdaptiveTutorRequest,
    user=Depends(get_verified_user),
    db=Depends(get_db)
):
    try:
        # use_langchain=True par défaut désormais
        agent = AdaptiveTutorAgent(
            user_id=user.id,
            request_data=request.dict(),
            db=db,
            use_langchain=True,  # LangChain est maintenant l'orchestrateur par défaut
        )
        state = await agent.run()
        
        return {
            "adjusted_level": state.adjusted_level,
            "detected_difficulties": state.difficulties,
            "suggested_exercises": [ExerciseSuggestion(**exercise) for exercise in state.suggested_exercises],
            "strategy": state.strategy,
            "strategy_decisions": state.strategy_decisions,
            "priority_focus": state.priority_focus or [f"Renforcer {request.topic}"],
            "verification": state.tool_results.get("verification"),
            "agent_trace": state.agent_trace,
            "notes": " ".join(state.reflection_notes) if state.reflection_notes else None,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Adaptive tutor plan failed: {str(exc)}")
