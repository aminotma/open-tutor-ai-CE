# AdaptiveTutorAgent: un agent de tutorat adaptatif avec routage dynamique et vérification RAG
from __future__ import annotations

import difflib
import io
import re
import sys
import requests
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG
from open_tutorai.models.database import Memory
from open_tutorai.routers.context_retrieval import (
    retrieve_internal_memory,
    retrieve_pedagogical_documents,
)

# LangChain imports
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import Tool, StructuredTool
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.documents import Document as LangChainDocument
from langchain.chains import RetrievalQA
from langchain_chroma import Chroma

from open_tutorai.routers.context_retrieval import (
    retrieve_internal_memory,
    retrieve_pedagogical_documents,
    retrieve_pedagogical_documents_as_langchain,
    get_vectorstore,
)
from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG
from open_tutorai.models.database import Memory

negative_feedback_keywords = [
    "confused",
    "hard",
    "difficult",
    "struggle",
    "mistake",
    "wrong",
    "lost",
    "unclear",
    "challenge",
    "stuck",
]

LEVEL_ORDER = ["beginner", "intermediate", "advanced"]

# ─── Routing constants ────────────────────────────────────────────────────────
# Maximum iterations the dynamic router is allowed to run before it stops.
MAX_ROUTING_ITERATIONS = 8
# Minimum RAG verification score required for the CollaborationAgent to
# declare consensus.  Below this threshold a corrective iteration is triggered.
CONSENSUS_THRESHOLD = 0.65


def _normalize_level(level: Optional[str]) -> str:
    if not level:
        return "intermediate"
    lower = level.lower()
    return lower if lower in LEVEL_ORDER else "intermediate"


def _parse_feedback_difficulties(feedback_comments: List[str]) -> List[str]:
    difficulties = []
    for comment in feedback_comments:
        text = comment.lower()
        if any(keyword in text for keyword in NEGATIVE_FEEDBACK_KEYWORDS):
            cleaned = text.replace("\n", " ").strip()
            if len(cleaned) > 0:
                difficulties.append(cleaned)
    return difficulties


def _assess_current_level(
    current_level: str,
    interactions: Optional[List[Dict[str, Any]]],
    feedback_comments: Optional[List[str]],
) -> str:
    level = _normalize_level(current_level)
    if not interactions and not feedback_comments:
        return level

    total_score = 0.0
    scored_items = 0
    difficulty_flags = 0

    if interactions:
        for item in interactions:
            if item.get("score") is not None:
                score = max(0.0, min(float(item.get("score", 0.0)), 1.0))
                total_score += score
                scored_items += 1
                if score < 0.6:
                    difficulty_flags += 1
            if item.get("outcome") and item.get("outcome").lower() in ["incorrect", "wrong", "failed"]:
                difficulty_flags += 1

    if feedback_comments:
        difficulty_flags += len(_parse_feedback_difficulties(feedback_comments))

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


def _tokenize_text(text: str) -> List[str]:
    return [token for token in re.findall(r"\w{3,}", text.lower())]


def _calculate_text_similarity(query: str, content: str) -> float:
    query_tokens = set(_tokenize_text(query))
    content_tokens = set(_tokenize_text(content))
    if not query_tokens or not content_tokens:
        return 0.0

    overlap = len(query_tokens & content_tokens) / max(1, len(query_tokens | content_tokens))
    sequence_ratio = difflib.SequenceMatcher(None, query.lower(), content.lower()).ratio()
    return min(1.0, 0.6 * overlap + 0.4 * sequence_ratio)


def _extract_memory_signals(topic: str, memory_context: List[Dict[str, Any]]) -> List[str]:
    if not memory_context:
        return []

    topic_lower = topic.lower()
    signals = []
    for memory in memory_context:
        content = str(memory.get("content", "")).lower()
        if topic_lower in content:
            preview = str(memory.get("content", ""))[:150].replace("\n", " ")
            signals.append(f"Mémoire pertinente : {preview}")
    return signals[:2]


def _detect_difficulties(
    topic: str,
    interactions: Optional[List[Dict[str, Any]]],
    feedback_comments: Optional[List[str]],
    learning_objectives: Optional[List[str]],
) -> List[str]:
    difficulties = []
    if feedback_comments:
        difficulties.extend(_parse_feedback_difficulties(feedback_comments))

    if interactions:
        for item in interactions:
            if item.get("score") is not None and float(item.get("score", 0.0)) < 0.6:
                label = item.get("outcome") or "low performance"
                difficulties.append(f"Difficulté avec l'interaction : {label}")
            if item.get("content") and topic.lower() in item.get("content", "").lower():
                if item.get("score") is not None and float(item.get("score", 0.0)) < 0.6:
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


def _build_exercise_prompt(topic: str, level: str, objective: Optional[str], index: int) -> Dict[str, str]:
    base_topic = topic.capitalize()
    difficulty_descriptor = {
        "beginner": "simple",
        "intermediate": "standard",
        "advanced": "challenging",
    }[level]

    if objective:
        prompt = f"Propose un exercice {difficulty_descriptor} sur {base_topic} axé sur {objective}."
    else:
        prompt = f"Propose un exercice {difficulty_descriptor} sur {base_topic} avec une correction pas à pas."

    return {
        "question": f"Exercice {index}: {prompt}",
        "hint": f"Réfléchis aux éléments fondamentaux de {topic}.",
        "answer": f"Réponse attendue pour l'exercice {index} sur {topic}.",
        "skill_target": objective or f"Maîtrise de {topic}",
    }


def _generate_exercises(
    topic: str,
    level: str,
    learning_objectives: Optional[List[str]],
    count: int = 3,
) -> List[Dict[str, Any]]:
    objectives = learning_objectives or []
    exercises = []
    for idx in range(1, count + 1):
        objective = objectives[idx - 1] if idx - 1 < len(objectives) else None
        exercise = _build_exercise_prompt(topic, level, objective, idx)
        exercises.append(
            {
                "id": f"exercise_{idx}",
                "difficulty": level,
                "question": exercise["question"],
                "hint": exercise["hint"],
                "answer": exercise["answer"],
                "skill_target": exercise["skill_target"],
            }
        )
    return exercises


def _plan_learning_strategy(
    topic: str,
    adjusted_level: str,
    difficulties: List[str],
    feedback_comments: Optional[List[str]],
    memory_context: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    decisions: List[Dict[str, Any]] = []
    priority = 1

    if difficulties:
        primary = difficulties[0]
        decisions.append(
            {
                "id": "focus_primary_difficulty",
                "action": f"Se concentrer immédiatement sur la difficulté principale : {primary}.",
                "rationale": f"La difficulté détectée en priorité est {primary}.",
                "priority": priority,
                "dependencies": [],
            }
        )
        priority += 1
        decisions.append(
            {
                "id": "review_concept",
                "action": f"Revoir le concept de base lié à {topic} avant de proposer de nouveaux exercices.",
                "rationale": "Un rappel conceptuel renforce la compréhension avant la pratique.",
                "priority": priority,
                "dependencies": ["focus_primary_difficulty"],
            }
        )
        priority += 1
        decisions.append(
            {
                "id": "generate_guided_exercises",
                "action": f"Proposer des exercices guidés adaptés au niveau {adjusted_level} et bâtir la confiance sur des points précis.",
                "rationale": "La pratique guidée aide à fixer les compétences tout en corrigeant les erreurs immédiatement.",
                "priority": priority,
                "dependencies": ["review_concept"],
            }
        )
        priority += 1
        decisions.append(
            {
                "id": "use_feedback",
                "action": "Utiliser le feedback de l'apprenant pour ajuster la progression en temps réel, sans simplement offrir des options.",
                "rationale": "L'adaptation continue maintient le plan aligné avec les besoins réels de l'apprenant.",
                "priority": priority,
                "dependencies": ["generate_guided_exercises"],
            }
        )
    else:
        decisions.append(
            {
                "id": "maintain_progress",
                "action": f"Le niveau actuel est stable ({adjusted_level}). Continuer avec des exercices progressifs sur {topic}.",
                "rationale": "Le maintien d'une progression régulière consolide les acquis.",
                "priority": priority,
                "dependencies": [],
            }
        )
        priority += 1
        decisions.append(
            {
                "id": "reinforce_acquis",
                "action": "Renforcer les acquis avec une pratique ciblée, puis vérifier la compréhension par un court auto-test.",
                "rationale": "La consolidation et l'évaluation rapide permettent de détecter toute faiblesse émergente.",
                "priority": priority,
                "dependencies": ["maintain_progress"],
            }
        )
        priority += 1
        decisions.append(
            {
                "id": "monitor_feedback",
                "action": "Surveiller les retours de l'apprenant pour détecter toute difficulté émergente.",
                "rationale": "La surveillance des retours permet d'ajuster le plan avant qu'une difficulté ne s'installe.",
                "priority": priority,
                "dependencies": ["reinforce_acquis"],
            }
        )

    if feedback_comments:
        combined_feedback = " ".join(feedback_comments[:2])
        decisions.append(
            {
                "id": "consider_feedback",
                "action": f"Prendre en compte les retours suivants : {combined_feedback}.",
                "rationale": "Les retours de l'apprenant fournissent un contexte précieux pour adapter le plan.",
                "priority": priority + 1,
                "dependencies": [],
            }
        )

    if memory_context:
        decisions.append(
            {
                "id": "leverage_memory",
                "action": "Exploiter les souvenirs pédagogiques et les mémoires antérieures pour ajuster le plan à l'historique de l'apprenant.",
                "rationale": "Les éléments mémorisés fournissent des indices sur les difficultés récurrentes et les points de progrès antérieurs.",
                "priority": priority + 2,
                "dependencies": ["consider_feedback"],
            }
        )

    return decisions


def _is_text_supported(candidate: str, source_corpus: str, threshold: float = 0.15) -> bool:
    candidate_tokens = re.findall(r"\w{4,}", candidate.lower())
    if not candidate_tokens or not source_corpus:
        return False

    source_tokens = set(re.findall(r"\w{4,}", source_corpus.lower()))
    match_count = sum(1 for token in candidate_tokens if token in source_tokens)
    return (match_count / len(candidate_tokens)) >= threshold


async def verify_agent_output(
    user_id: str,
    request: dict,
    exercises: List[Dict[str, Any]],
    strategy: List[str],
) -> Dict[str, Any]:
    rag_config = CONTEXT_RETRIEVAL_CONFIG.get("rag", {})
    if not rag_config.get("verification_enabled", False):
        return {
            "verified": False,
            "support_score": 0.0,
            "supported_items": [],
            "unsupported_items": [],
            "sources": [],
            "verdict": "verification_disabled",
            "note": "La vérification RAG est désactivée dans la configuration.",
        }

    query = request.get("topic", "")
    if request.get("learning_objectives"):
        query += " " + " ".join(request.get("learning_objectives", []))

    sources = await retrieve_pedagogical_documents(
        user_id,
        query,
        top_k=rag_config.get("top_k_documents", 5),
    )

    if not sources:
        return {
            "verified": False,
            "support_score": 0.0,
            "supported_items": [],
            "unsupported_items": [],
            "sources": [],
            "verdict": "no_sources_found",
            "note": "Aucune source vérifiée n'a été trouvée.",
        }

    source_corpus = " ".join([src.get("content", "") for src in sources])
    candidates = [request.get("topic", "")]
    if request.get("learning_objectives"):
        candidates.extend(request.get("learning_objectives", []))
    for exercise in exercises:
        candidates.append(exercise.get("question", ""))
        candidates.append(exercise.get("answer", ""))
    candidates.extend(strategy)

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

    return {
        "verified": verified,
        "support_score": round(support_score, 3),
        "supported_items": supported_items,
        "unsupported_items": unsupported_items,
        "sources": [
            {
                "source_id": src.get("id", ""),
                "title": src.get("metadata", {}).get("title"),
                "preview": (src.get("content", "")[:280] + "...") if len(src.get("content", "")) > 280 else src.get("content", ""),
                "relevance_score": round(src.get("relevance_score", 0.0), 3),
                "path": src.get("metadata", {}).get("path"),
            }
            for src in sources
        ],
        "verdict": verdict,
        "note": (
            "Vérification terminée à l'aide des sources RAG locales. "
            "Les éléments non appuyés doivent être relus ou enrichis."
            if verified
            else "Certains éléments n'ont pas pu être appuyés par les sources disponibles."
        ),
    }


@dataclass
class AdaptiveTutorState:
    """
    State partagé entre les noeuds LangChain.
    Chaque champ est mis à jour par un noeud de la chain.
    """
    user_id: str
    topic: str
    current_level: str
    recent_interactions: List[Dict[str, Any]] = field(default_factory=list)
    feedback_comments: List[str] = field(default_factory=list)
    learning_objectives: List[str] = field(default_factory=list)
    preferred_exercise_types: List[str] = field(default_factory=list)

    # Contexte récupéré
    memory_context: List[Dict[str, Any]] = field(default_factory=list)
    pedagogical_context: List[Dict[str, Any]] = field(default_factory=list)

    # Résultats produits par la chain
    adjusted_level: str = "intermediate"
    difficulties: List[str] = field(default_factory=list)
    strategy: List[str] = field(default_factory=list)
    strategy_decisions: List[Dict[str, Any]] = field(default_factory=list)
    suggested_exercises: List[Dict[str, Any]] = field(default_factory=list)
    priority_focus: List[str] = field(default_factory=list)

    # Vérification RAG
    tool_results: Dict[str, Any] = field(default_factory=dict)
    reflection_notes: List[str] = field(default_factory=list)

    # Trace de l'exécution LangChain
    agent_trace: List[str] = field(default_factory=list)
    langchain_messages: List[Any] = field(default_factory=list)

class BaseAgent:
    def __init__(self, state: AdaptiveTutorState):
        self.state = state

    async def act(self) -> None:
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
# LangChainOrchestrator: Utilise LangChain pour l'orchestration agentique
# ─────────────────────────────────────────────────────────────────────────────

class LangChainOrchestrator:
    def __init__(self, state: AdaptiveTutorState, tools: List[Tool]):
        self.state = state
        self.llm = ChatOpenAI(temperature=0)  # Adapter selon la config OpenAI
        self.tools = tools
        self.agent = initialize_agent(self.tools, self.llm, agent=AgentType.OPENAI_FUNCTIONS, verbose=True)

    async def run_orchestration(self, task: str) -> str:
        try:
            result = await self.agent.arun(task)
            return result
        except Exception as exc:
            self.state.agent_trace.append(f"LangChainOrchestrator: erreur - {exc}")
            return f"Erreur dans l'orchestration : {exc}"


# ─────────────────────────────────────────────────────────────────────────────
# ToolAgent  (real web search + API calls + sandboxed exec)
# ─────────────────────────────────────────────────────────────────────────────

class ToolAgent(BaseAgent):
    """
    Provides concrete tool capabilities to every other agent.

    web_search now performs a real HTTP call via the DuckDuckGo Instant
    Answer API (no API key required).  Results are returned as a concise
    plain-text summary so callers can embed them directly into prompts or
    use them to enrich the pedagogical context.
    """

    # DuckDuckGo Instant Answer endpoint – no auth required, CORS-friendly.
    _DDG_API = "https://api.duckduckgo.com/"

    def __init__(self, state: AdaptiveTutorState):
        super().__init__(state)
        self.search_tool = DuckDuckGoSearchRun()

    # ── Public tool interface ─────────────────────────────────────────────

    def web_search(self, query: str, max_results: int = 5) -> str:
        """
        Executes a web search using LangChain's DuckDuckGoSearchRun tool.

        Returns a human-readable summary for use in prompts or context enrichment.
        """
        self.state.agent_trace.append(f"ToolAgent (LangChain): recherche web pour '{query}'.")
        try:
            result = self.search_tool.run(query)
            self.state.tool_results["web_search"] = {"query": query, "summary": result}
            self.state.agent_trace.append("ToolAgent: recherche LangChain terminée.")
            return result
        except Exception as exc:
            error_msg = f"Recherche web échouée : {exc}"
            self.state.agent_trace.append(f"ToolAgent: {error_msg}")
            self.state.tool_results["web_search_error"] = str(exc)
            return error_msg

    def call_api(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        json_payload: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.state.agent_trace.append(f"ToolAgent: appel API {method} {endpoint}.")
        try:
            response = requests.request(
                method,
                endpoint,
                params=params,
                json=json_payload,
                headers=headers,
                timeout=10,
            )
            return {
                "status_code": response.status_code,
                "body": response.text,
                "headers": dict(response.headers),
            }
        except Exception as exc:
            return {"error": str(exc)}

    def execute_code(self, code: str) -> Dict[str, Any]:
        self.state.agent_trace.append("ToolAgent: exécution de code en environnement sécurisé.")
        safe_builtins = {
            "print": print,
            "len": len,
            "range": range,
            "min": min,
            "max": max,
            "sum": sum,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "dict": dict,
            "list": list,
            "set": set,
        }
        local_vars: Dict[str, Any] = {}
        stdout_buffer = io.StringIO()
        original_stdout = sys.stdout
        sys.stdout = stdout_buffer
        try:
            exec(code, {"__builtins__": safe_builtins}, local_vars)
            output = stdout_buffer.getvalue().strip()
            return {"output": output, "locals": local_vars}
        except Exception as exc:
            return {"error": str(exc), "traceback": traceback.format_exc()}
        finally:
            sys.stdout = original_stdout


# ─────────────────────────────────────────────────────────────────────────────
# Perception
# ─────────────────────────────────────────────────────────────────────────────

class PerceptionAgent(BaseAgent):
    def __init__(self, state: AdaptiveTutorState, db):
        super().__init__(state)
        self.db = db

    async def act(self) -> None:
        self.state.agent_trace.append("PerceptionAgent: collecte la mémoire et le contexte pédagogique.")
        query = self.state.topic
        if self.state.learning_objectives:
            query += " " + " ".join(self.state.learning_objectives)

        self.state.memory_context = await retrieve_internal_memory(
            self.state.user_id,
            query,
            memory_types=CONTEXT_RETRIEVAL_CONFIG["memory"]["memory_types"],
            limit=CONTEXT_RETRIEVAL_CONFIG["memory"]["top_k_memories"],
            db=self.db,
        )

        self.state.pedagogical_context = await retrieve_pedagogical_documents(
            self.state.user_id,
            query,
            top_k=CONTEXT_RETRIEVAL_CONFIG["rag"]["top_k_documents"],
        )
        self.state.agent_trace.append(
            f"PerceptionAgent: trouvé {len(self.state.memory_context)} items mémoire, "
            f"{len(self.state.pedagogical_context)} documents pédagogiques."
        )
        # Route → diagnosis
        self.state.next_agent = "diagnosis"


# ─────────────────────────────────────────────────────────────────────────────
# Diagnosis
# ─────────────────────────────────────────────────────────────────────────────

class DiagnosisAgent(BaseAgent):
    async def act(self) -> None:
        self.state.agent_trace.append("DiagnosisAgent: évalue le niveau et identifie les difficultés.")
        self.state.adjusted_level = _assess_current_level(
            self.state.current_level,
            self.state.recent_interactions,
            self.state.feedback_comments,
        )
        self.state.difficulties = _detect_difficulties(
            self.state.topic,
            self.state.recent_interactions,
            self.state.feedback_comments,
            self.state.learning_objectives,
        )
        self.state.difficulties.extend(_extract_memory_signals(self.state.topic, self.state.memory_context))
        if not self.state.difficulties:
            self.state.difficulties = [f"Aucun point critique détecté pour {self.state.topic}."]
        self.state.priority_focus = self.state.difficulties[:3]
        self.state.agent_trace.append(
            f"DiagnosisAgent: niveau ajusté à {self.state.adjusted_level}, difficultés évaluées."
        )
        # Route → planning
        self.state.next_agent = "planning"


# ─────────────────────────────────────────────────────────────────────────────
# Planning  (now emits dynamic next_agent based on context)
# ─────────────────────────────────────────────────────────────────────────────

class PlanningAgent(BaseAgent):
    """
    Builds the learning strategy *and* decides which agent should run next.

    Decision rules
    ──────────────
    1. If no pedagogical documents were retrieved → enrich with a web search
       first (routes to ToolAgent / web_search flow) then back to exercise.
    2. If this is a corrective cycle (state.corrective_cycles > 0) → skip
       straight to exercise regeneration with a narrower focus.
    3. Default → exercise generation.
    """

    async def act(self) -> None:
        self.state.agent_trace.append("PlanningAgent: décompose le plan en sous-tâches concrètes.")
        self.state.tasks = [
            "Analyser l'état de l'apprenant et récupérer le contexte disponible.",
            "Identifier les difficultés principales et le niveau adapté.",
            "Construire une stratégie pédagogique claire et priorisée.",
            "Générer des exercices ciblés et des indications.",
            "Vérifier les résultats par rapport aux sources RAG.",
            "Réviser le plan si la vérification révèle des écarts.",
        ]
        self.state.strategy_decisions = _plan_learning_strategy(
            self.state.topic,
            self.state.adjusted_level,
            self.state.difficulties,
            self.state.feedback_comments,
            self.state.memory_context,
        )
        self.state.strategy = [decision["action"] for decision in self.state.strategy_decisions]
        self.state.agent_trace.extend(
            [f"PlanningAgent: tâche ajoutée -> {task}" for task in self.state.tasks]
        )

        # ── Dynamic routing decision ──────────────────────────────────────
        if not self.state.pedagogical_context and self.state.corrective_cycles == 0:
            # No RAG sources available: enrich via web search before generating exercises.
            self.state.agent_trace.append(
                "PlanningAgent: aucun document RAG disponible → enrichissement web avant exercices."
            )
            self.state.next_agent = "web_enrichment"
        elif self.state.corrective_cycles > 0:
            # Corrective cycle: re-generate exercises with refined focus.
            self.state.agent_trace.append(
                f"PlanningAgent: cycle correctif #{self.state.corrective_cycles} → re-génération ciblée des exercices."
            )
            self.state.next_agent = "exercise"
        else:
            self.state.next_agent = "exercise"


# ─────────────────────────────────────────────────────────────────────────────
# Exercise
# ─────────────────────────────────────────────────────────────────────────────

class ExerciseAgent(BaseAgent):
    def __init__(self, state: AdaptiveTutorState, tool_agent: ToolAgent):
        super().__init__(state)
        self.tool_agent = tool_agent

    async def act(self) -> None:
        self.state.agent_trace.append("ExerciseAgent: génère des exercices correspondants à la stratégie.")

        # On corrective cycles narrow the focus to unsupported items only.
        objectives = self.state.learning_objectives
        if self.state.corrective_cycles > 0:
            unsupported = self.state.tool_results.get("verification", {}).get("unsupported_items", [])
            if unsupported:
                # Re-use unsupported exercise questions as new objectives.
                objectives = [item[:120] for item in unsupported[:3]]
                self.state.agent_trace.append(
                    "ExerciseAgent: re-génération ciblée sur les éléments non validés par RAG."
                )

        self.state.suggested_exercises = _generate_exercises(
            topic=self.state.topic,
            level=self.state.adjusted_level,
            learning_objectives=objectives,
            count=3,
        )
        self.state.agent_trace.append(
            f"ExerciseAgent: {len(self.state.suggested_exercises)} exercices générés."
        )
        self.state.tool_results["exercise_generation"] = {
            "exercise_count": len(self.state.suggested_exercises)
        }
        # Route → verification
        self.state.next_agent = "verification"


# ─────────────────────────────────────────────────────────────────────────────
# Verification
# ─────────────────────────────────────────────────────────────────────────────

class VerificationAgent(BaseAgent):
    async def act(self) -> None:
        self.state.agent_trace.append("VerificationAgent: vérifie les résultats générés avec le système RAG.")
        verification = await verify_agent_output(
            self.state.user_id,
            {
                "topic": self.state.topic,
                "learning_objectives": self.state.learning_objectives,
            },
            self.state.suggested_exercises,
            self.state.strategy,
        )
        self.state.tool_results["verification"] = verification
        self.state.agent_trace.append(
            f"VerificationAgent: verdict = {verification.get('verdict')}, "
            f"score = {verification.get('support_score')}"
        )
        # Route → reflection
        self.state.next_agent = "reflection"


# ─────────────────────────────────────────────────────────────────────────────
# Reflection
# ─────────────────────────────────────────────────────────────────────────────

class ReflectionAgent(BaseAgent):
    def __init__(self, state: AdaptiveTutorState, db):
        super().__init__(state)
        self.db = db

    async def act(self) -> None:
        self.state.agent_trace.append("ReflectionAgent: auto-corrige et enrichit la mémoire agentique.")
        verification = self.state.tool_results.get("verification", {})
        if verification.get("verified") is False:
            self.state.strategy.append(
                "Réviser la stratégie pour corriger les éléments non validés par la source pédagogique."
            )
            self.state.difficulties.append("Points à relire : contenu non soutenu par les sources RAG.")
            self.state.agent_trace.append(
                "ReflectionAgent: échec de vérification, ajustement de la stratégie et des difficultés."
            )
        else:
            self.state.agent_trace.append(
                "ReflectionAgent: vérification réussie, pas de correction majeure nécessaire."
            )

        self.state.reflection_notes.append(
            "Le système conserve les résultats et peut enregistrer une mémoire d'apprentissage si nécessaire."
        )
        await self._persist_reflection_memory()
        # Route → collaboration (consensus check)
        self.state.next_agent = "collaboration"

    async def _persist_reflection_memory(self) -> None:
        if not self.db:
            return

        verification = self.state.tool_results.get("verification", {})
        summary = (
            f"Agent reflection: niveau {self.state.adjusted_level}, "
            f"difficultés {', '.join(self.state.difficulties[:3])}. "
            f"Vérification : {verification.get('verdict', 'inconnu')}."
        )
        memory = Memory(
            id=uuid4().hex,
            user_id=self.state.user_id,
            memory_type="behavioral",
            content=summary,
            memory_metadata={
                "topic": self.state.topic,
                "agent_step": "reflection",
                "verification": verification.get("verdict"),
                "strategy_decisions": [d.get("id") for d in self.state.strategy_decisions],
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        try:
            self.db.add(memory)
            self.db.commit()
            self.db.refresh(memory)
            self.state.agent_trace.append("ReflectionAgent: mémoire de réflexion enregistrée.")
            await self._consolidate_memory()
        except Exception:
            self.db.rollback()
            self.state.agent_trace.append("ReflectionAgent: echec de l'enregistrement mémoire.")

    async def _consolidate_memory(self) -> None:
        try:
            memories = (
                self.db.query(Memory)
                .filter(Memory.user_id == self.state.user_id)
                .order_by(Memory.updated_at.desc().nullslast(), Memory.created_at.desc())
                .all()
            )
            if len(memories) <= 50:
                return

            for memory in memories[40:]:
                self.db.delete(memory)
            self.db.commit()
            self.state.agent_trace.append(
                f"ReflectionAgent: consolidation de mémoire effectuée, "
                f"{len(memories) - 40} éléments supprimés."
            )
        except Exception:
            self.db.rollback()
            self.state.agent_trace.append("ReflectionAgent: échec de la consolidation de la mémoire.")


# ─────────────────────────────────────────────────────────────────────────────
# Collaboration  (active consensus + corrective loop)
# ─────────────────────────────────────────────────────────────────────────────

class CollaborationAgent(BaseAgent):
    """
    Evaluates agent outputs and decides whether to:
      • declare consensus (stop the loop), or
      • trigger a corrective cycle (re-plan → re-generate → re-verify).

    Consensus criteria
    ──────────────────
    1. RAG verification score ≥ CONSENSUS_THRESHOLD, OR verification is
       disabled (score defaults to 0 but verdict is "verification_disabled").
    2. At least one exercise was generated.
    3. corrective_cycles has not exceeded MAX_CORRECTIVE_CYCLES (= 2) to
       prevent infinite loops.
    """

    MAX_CORRECTIVE_CYCLES = 2

    def __init__(self, state: AdaptiveTutorState, agents: List[BaseAgent]):
        super().__init__(state)
        self.agents = agents

    async def act(self) -> None:
        self.state.agent_trace.append(
            "CollaborationAgent: évalue le consensus entre les agents."
        )
        roles = [agent.__class__.__name__ for agent in self.agents]
        self.state.agent_trace.append(
            f"CollaborationAgent: agents impliqués = {', '.join(roles)}."
        )

        verification = self.state.tool_results.get("verification", {})
        support_score: float = verification.get("support_score", 0.0)
        verdict: str = verification.get("verdict", "unknown")
        exercise_count: int = self.state.tool_results.get(
            "exercise_generation", {}
        ).get("exercise_count", 0)

        # ── Consensus evaluation ──────────────────────────────────────────
        verification_ok = (
            support_score >= CONSENSUS_THRESHOLD
            or verdict == "verification_disabled"
            or verdict == "no_sources_found"   # No local RAG; we cannot block indefinitely.
        )
        exercises_ok = exercise_count > 0

        if verification_ok and exercises_ok:
            self.state.consensus_reached = True
            self.state.next_agent = None  # Signals the router to stop.
            self.state.agent_trace.append(
                f"CollaborationAgent: consensus atteint (score={support_score:.2f}, "
                f"exercices={exercise_count}). Boucle terminée."
            )
            return

        # ── No consensus: attempt a corrective cycle ──────────────────────
        if self.state.corrective_cycles >= self.MAX_CORRECTIVE_CYCLES:
            # Safety valve: too many corrections, stop anyway.
            self.state.consensus_reached = False
            self.state.next_agent = None
            self.state.agent_trace.append(
                f"CollaborationAgent: nombre maximum de cycles correctifs atteint "
                f"({self.MAX_CORRECTIVE_CYCLES}). Arrêt forcé."
            )
            return

        self.state.corrective_cycles += 1
        self.state.agent_trace.append(
            f"CollaborationAgent: consensus non atteint (score={support_score:.2f}, "
            f"exercices={exercise_count}). "
            f"Déclenchement du cycle correctif #{self.state.corrective_cycles}."
        )

        # Build a corrective rationale for the planning agent.
        issues: List[str] = []
        if not verification_ok:
            unsupported = verification.get("unsupported_items", [])
            issues.append(
                f"Score RAG insuffisant ({support_score:.0%}). "
                f"Éléments non validés : {', '.join(unsupported[:3])}."
            )
        if not exercises_ok:
            issues.append("Aucun exercice généré.")

        self.state.strategy.append(
            f"[Cycle correctif #{self.state.corrective_cycles}] {' | '.join(issues)} "
            "→ Re-planification et re-génération ciblée requises."
        )
        # Route back to planning for a corrective pass.
        self.state.next_agent = "planning"


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator  (dynamic router)
# ─────────────────────────────────────────────────────────────────────────────

class AdaptiveTutorAgent:
    """
    Orchestration LangChain remplaçant le système d'agents custom.
    Utilise une séquence de chains plutôt qu'un routeur dynamique manuel.
    """

    def __init__(self, user_id: str, request_data: Dict[str, Any], db, use_langchain: bool = True):
        self.state = AdaptiveTutorState(
            user_id=user_id,
            topic=request_data.get("topic", ""),
            current_level=request_data.get("current_level", "intermediate"),
            recent_interactions=request_data.get("recent_interactions", []) or [],
            feedback_comments=request_data.get("feedback_comments", []) or [],
            learning_objectives=request_data.get("learning_objectives", []) or [],
            preferred_exercise_types=request_data.get("preferred_exercise_types", []) or [],
        )
        self.db = db

        # LLM principal
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.2
        )

        # Vectorstore LangChain (ChromaDB adapté)
        self.vectorstore = get_vectorstore()
        self.retriever = self.vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": CONTEXT_RETRIEVAL_CONFIG["rag"]["top_k_documents"]}
        )

        # Outil de recherche web (DuckDuckGo — déjà présent avant)
        self.search_tool = DuckDuckGoSearchRun()

        # Construction des outils LangChain
        self.tools = self._build_tools()

    def _build_tools(self) -> List[Tool]:
        """Construit les outils disponibles pour l'agent LangChain."""

        def web_search_fn(query: str) -> str:
            self.state.agent_trace.append(f"Tool: web_search → '{query}'")
            try:
                result = self.search_tool.run(query)
                return result
            except Exception as e:
                return f"Recherche échouée : {e}"

        def retrieve_memory_fn(query: str) -> str:
            """Récupère les mémoires internes synchroniquement pour LangChain."""
            import asyncio
            self.state.agent_trace.append(f"Tool: retrieve_memory → '{query}'")
            try:
                loop = asyncio.get_event_loop()
                memories = loop.run_until_complete(
                    retrieve_internal_memory(
                        self.state.user_id,
                        query,
                        memory_types=CONTEXT_RETRIEVAL_CONFIG["memory"]["memory_types"],
                        limit=CONTEXT_RETRIEVAL_CONFIG["memory"]["top_k_memories"],
                        db=self.db
                    )
                )
                self.state.memory_context = memories
                return "\n".join([m.get("content", "") for m in memories[:5]])
            except Exception as e:
                return f"Mémoire non disponible : {e}"

        def rag_retrieve_fn(query: str) -> str:
            """Recherche dans ChromaDB via LangChain retriever."""
            self.state.agent_trace.append(f"Tool: rag_retrieve → '{query}'")
            try:
                docs = self.retriever.invoke(query)
                self.state.pedagogical_context = [
                    {"content": d.page_content, "metadata": d.metadata}
                    for d in docs
                ]
                return "\n\n".join([d.page_content[:500] for d in docs])
            except Exception as e:
                return f"RAG non disponible : {e}"

        return [
            Tool(
                name="web_search",
                func=web_search_fn,
                description=(
                    "Recherche des informations pédagogiques sur le web. "
                    "Utilise quand le contexte RAG est insuffisant."
                )
            ),
            Tool(
                name="retrieve_memory",
                func=retrieve_memory_fn,
                description=(
                    "Récupère les mémoires d'apprentissage passées de l'apprenant. "
                    "Utilise pour personnaliser la stratégie."
                )
            ),
            Tool(
                name="rag_retrieve",
                func=rag_retrieve_fn,
                description=(
                    "Recherche dans la base de documents pédagogiques vectoriels (ChromaDB). "
                    "Utilise en priorité avant web_search."
                )
            ),
        ]

    def _build_diagnosis_chain(self):
        """Chain de diagnostic du niveau et des difficultés."""
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=(
                "Tu es un tuteur adaptatif expert. Analyse les performances "
                "de l'apprenant et produis un diagnostic JSON strict."
            )),
            HumanMessage(content=(
                "Sujet : {topic}\n"
                "Niveau actuel : {current_level}\n"
                "Interactions récentes : {interactions}\n"
                "Commentaires : {feedback}\n"
                "Mémoires passées : {memory}\n\n"
                "Réponds UNIQUEMENT en JSON valide avec les clés : "
                "adjusted_level (beginner/intermediate/advanced), "
                "difficulties (liste de str), "
                "priority_focus (liste de str, max 3)."
            ))
        ])
        return prompt | self.llm | JsonOutputParser()

    def _build_planning_chain(self):
        """Chain de planification de la stratégie pédagogique."""
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=(
                "Tu es un planificateur pédagogique. Génère une stratégie "
                "d'apprentissage directive et concrète."
            )),
            HumanMessage(content=(
                "Sujet : {topic}\n"
                "Niveau ajusté : {adjusted_level}\n"
                "Difficultés détectées : {difficulties}\n"
                "Contexte pédagogique RAG : {rag_context}\n"
                "Objectifs : {objectives}\n\n"
                "Réponds UNIQUEMENT en JSON valide avec les clés : "
                "strategy (liste de str), "
                "strategy_decisions (liste de dict avec id/action/rationale/priority)."
            ))
        ])
        return prompt | self.llm | JsonOutputParser()

    def _build_exercise_chain(self):
        """Chain de génération d'exercices adaptés."""
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=(
                "Tu es un générateur d'exercices pédagogiques. "
                "Crée des exercices ciblés et progressifs."
            )),
            HumanMessage(content=(
                "Sujet : {topic}\n"
                "Niveau : {adjusted_level}\n"
                "Objectifs : {objectives}\n"
                "Difficultés à corriger : {difficulties}\n"
                "Contexte RAG disponible : {rag_context}\n\n"
                "Génère 3 exercices. Réponds UNIQUEMENT en JSON valide : "
                "liste de dict avec les clés "
                "id, difficulty, question, hint, answer, skill_target."
            ))
        ])
        return prompt | self.llm | JsonOutputParser()

    async def _run_verification(
        self,
        exercises: List[Dict],
        strategy: List[str]
    ) -> Dict:
        """Vérification RAG (réutilise la logique existante)."""
        from open_tutorai.routers.adaptive_tutor import verify_adaptive_tutor_output
        from open_tutorai.routers.adaptive_tutor import AdaptiveTutorRequest

        class _FakeRequest:
            topic = self.state.topic
            learning_objectives = self.state.learning_objectives

        result = await verify_adaptive_tutor_output(
            self.state.user_id,
            _FakeRequest(),
            exercises,
            strategy
        )
        return result.dict() if hasattr(result, "dict") else result

    async def _persist_memory(self, exercises: List[Dict], verification: Dict):
        """Persistance mémoire comportementale (logique conservée de ReflectionAgent)."""
        if not self.db:
            return
        from uuid import uuid4
        from datetime import datetime, timezone

        verdict = verification.get("verdict", "unknown")
        summary = (
            f"LangChain session: niveau {self.state.adjusted_level}, "
            f"difficultés {', '.join(self.state.difficulties[:3])}. "
            f"Vérification : {verdict}."
        )
        memory = Memory(
            id=uuid4().hex,
            user_id=self.state.user_id,
            memory_type="behavioral",
            content=summary,
            memory_metadata={
                "topic": self.state.topic,
                "agent_step": "langchain_reflection",
                "verification": verdict,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        try:
            self.db.add(memory)
            self.db.commit()
            self.db.refresh(memory)
            self.state.agent_trace.append("LangChain: mémoire comportementale persistée.")
        except Exception:
            self.db.rollback()
            self.state.agent_trace.append("LangChain: échec persistance mémoire.")

    async def run(self) -> AdaptiveTutorState:
        """
        Pipeline LangChain en 5 étapes séquentielles remplaçant
        la boucle de routage dynamique custom.
        """
        self.state.agent_trace.append("LangChain AdaptiveTutorAgent: démarrage.")

        # ── Étape 1 : Récupération du contexte (mémoire + RAG) ──────────────
        self.state.agent_trace.append("Étape 1: Récupération contexte.")

        # Mémoire interne
        self.state.memory_context = await retrieve_internal_memory(
            self.state.user_id,
            self.state.topic,
            memory_types=CONTEXT_RETRIEVAL_CONFIG["memory"]["memory_types"],
            limit=CONTEXT_RETRIEVAL_CONFIG["memory"]["top_k_memories"],
            db=self.db
        )

        # Documents RAG via LangChain retriever
        rag_docs = self.retriever.invoke(self.state.topic)
        self.state.pedagogical_context = [
            {"content": d.page_content, "metadata": d.metadata}
            for d in rag_docs
        ]
        rag_context_str = "\n\n".join([d.page_content[:400] for d in rag_docs])

        # Fallback web si RAG vide
        if not rag_docs:
            self.state.agent_trace.append("Étape 1: RAG vide → fallback web_search.")
            rag_context_str = self.search_tool.run(self.state.topic)

        memory_str = "\n".join([
            m.get("content", "")[:200]
            for m in self.state.memory_context[:5]
        ])

        # ── Étape 2 : Diagnostic ─────────────────────────────────────────────
        self.state.agent_trace.append("Étape 2: Diagnostic niveau et difficultés.")
        diagnosis_chain = self._build_diagnosis_chain()
        diagnosis_result = await diagnosis_chain.ainvoke({
            "topic": self.state.topic,
            "current_level": self.state.current_level,
            "interactions": str(self.state.recent_interactions[:3]),
            "feedback": str(self.state.feedback_comments),
            "memory": memory_str,
        })
        self.state.adjusted_level = diagnosis_result.get("adjusted_level", self.state.current_level)
        self.state.difficulties = diagnosis_result.get("difficulties", [])
        self.state.priority_focus = diagnosis_result.get("priority_focus", [])

        # ── Étape 3 : Planification ──────────────────────────────────────────
        self.state.agent_trace.append("Étape 3: Planification stratégique.")
        planning_chain = self._build_planning_chain()
        planning_result = await planning_chain.ainvoke({
            "topic": self.state.topic,
            "adjusted_level": self.state.adjusted_level,
            "difficulties": str(self.state.difficulties),
            "rag_context": rag_context_str[:1000],
            "objectives": str(self.state.learning_objectives),
        })
        self.state.strategy = planning_result.get("strategy", [])
        self.state.strategy_decisions = planning_result.get("strategy_decisions", [])

        # ── Étape 4 : Génération d'exercices ─────────────────────────────────
        self.state.agent_trace.append("Étape 4: Génération exercices.")
        exercise_chain = self._build_exercise_chain()
        exercise_result = await exercise_chain.ainvoke({
            "topic": self.state.topic,
            "adjusted_level": self.state.adjusted_level,
            "objectives": str(self.state.learning_objectives),
            "difficulties": str(self.state.difficulties),
            "rag_context": rag_context_str[:800],
        })
        # La chain peut retourner une liste directement ou un dict avec clé
        if isinstance(exercise_result, list):
            self.state.suggested_exercises = exercise_result
        elif isinstance(exercise_result, dict):
            self.state.suggested_exercises = exercise_result.get(
                "exercises", list(exercise_result.values())[0]
                if exercise_result else []
            )

        # ── Étape 5 : Vérification RAG + Persistance mémoire ─────────────────
        self.state.agent_trace.append("Étape 5: Vérification RAG.")
        verification = await self._run_verification(
            self.state.suggested_exercises,
            self.state.strategy
        )
        self.state.tool_results["verification"] = verification

        await self._persist_memory(self.state.suggested_exercises, verification)

        self.state.agent_trace.append(
            f"LangChain AdaptiveTutorAgent: terminé. "
            f"Vérification: {verification.get('verdict', 'unknown')}."
        )
        return self.state
