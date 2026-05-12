from __future__ import annotations

from uuid import uuid4

from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from open_tutorai.agents import state_registry as registry
from open_tutorai.agents.prompts import build_system_prompt
from open_tutorai.agents.state import AdaptiveTutorState, AgentStep
from open_tutorai.agents.tools import ALL_TOOLS, tool_persist_memory, tool_final_answer, _current_run_id
from open_tutorai.config import CONTEXT_RETRIEVAL_CONFIG, get_openai_api_key, get_openai_base_url


class AdaptiveTutorAgent:
    """
    Autonomous ReAct agent for adaptive tutoring.

    Lifecycle:
        agent = AdaptiveTutorAgent(user_id, request_data, db)
        state = await agent.run()
    """

    def __init__(self, user_id: str, request_data: dict):
        self.user_id = user_id
        self.config = CONTEXT_RETRIEVAL_CONFIG

        # Unique run identifier — isolates this invocation from all others
        self.run_id = uuid4().hex

        # Build initial state
        self.initial_state = AdaptiveTutorState(
            user_id=user_id,
            topic=request_data.get("topic", ""),
            current_level=request_data.get("current_level", "intermediate"),
            language=request_data.get("preferred_language", "fr"),
            recent_interactions=request_data.get("recent_interactions") or [],
            feedback_comments=request_data.get("feedback_comments") or [],
            learning_objectives=request_data.get("learning_objectives") or [],
            preferred_exercise_types=request_data.get("preferred_exercise_types") or [],
            max_iterations=self.config.get("react", {}).get("max_iterations", 10),
        )

        # LLM — clé et URL récupérées depuis la config admin (partagée)
        lc_cfg = self.config.get("langchain", {})
        self.llm = ChatOpenAI(
            model=lc_cfg.get("llm_model", "gpt-4o-mini"),
            temperature=lc_cfg.get("llm_temperature", 0.2),
            api_key=get_openai_api_key(),
            base_url=get_openai_base_url(),
        )

    async def run(self) -> AdaptiveTutorState:
        """Run the ReAct loop and return the final state."""

        # Register state in the thread-safe registry
        registry.register(self.run_id, self.initial_state, self.user_id)

        try:
            return await self._execute()
        finally:
            # Always clean up the registry entry to avoid memory leaks
            registry.deregister(self.run_id)

    async def _execute(self) -> AdaptiveTutorState:
        react_cfg = self.config.get("react", {})
        state = registry.get_state(self.run_id)

        # Build the open ReAct prompt (no mandatory sequence)
        system_content = build_system_prompt(state)

        react_template = (
            system_content
            + """

{tools}

Use the following format strictly:

Thought: think about what to do next
Action: one of [{tool_names}]
Action Input: the input to the action (JSON dict or string)
Observation: the result of the action
... (repeat as many times as needed)
Thought: diagnosis done and exercises generated — time to close the session
Action: tool_final_answer
Action Input: {{}}

WARNING: never write "Final Answer: ..." — always use "Action: tool_final_answer" to finish.

Begin!

Question: {input}
Thought:{agent_scratchpad}"""
        )

        prompt = PromptTemplate.from_template(react_template)
        agent = create_react_agent(self.llm, ALL_TOOLS, prompt)

        executor = AgentExecutor(
            agent=agent,
            tools=ALL_TOOLS,
            verbose=react_cfg.get("verbose", True),
            max_iterations=state.max_iterations,
            handle_parsing_errors=True,
            return_intermediate_steps=True,
            early_stopping_method="force",
        )

        # The run_id is passed through LangChain's configurable so every tool
        # can look up the correct state from the registry
        lc_config = {"configurable": {"run_id": self.run_id}}

        input_question = (
            f"Conduire une session d'apprentissage adaptative pour l'apprenant sur : "
            f"'{state.topic}'. Niveau déclaré : {state.current_level}. "
            f"Objectifs : {', '.join(state.learning_objectives[:3]) or 'non spécifiés'}."
        )

        state = registry.get_state(self.run_id)
        state = state.append_trace("ReAct AdaptiveTutorAgent: démarrage.")
        registry.update_state(self.run_id, state)

        # Définir le run_id dans le ContextVar pour que tous les outils y accèdent
        ctx_token = _current_run_id.set(self.run_id)
        try:
            result = await executor.ainvoke(
                {"input": input_question},
                config=lc_config,
            )

            # Sync intermediate steps back into state bookkeeping
            state = registry.get_state(self.run_id)
            for i, (action, observation) in enumerate(result.get("intermediate_steps", [])):
                step = AgentStep(
                    thought="",
                    action=action.tool,
                    action_input=action.tool_input if isinstance(action.tool_input, dict) else {"input": action.tool_input},
                    observation=str(observation),
                    iteration=i + 1,
                )
                state = state.with_updates(
                    react_steps=[*state.react_steps, step],
                    iteration_count=i + 1,
                )
            registry.update_state(self.run_id, state)

        except Exception as exc:
            _current_run_id.reset(ctx_token)
            state = registry.get_state(self.run_id)
            state = state.append_trace(f"ReAct: erreur — {exc}")

            # Graceful fallback: if we have at least exercises, mark complete
            if state.suggested_exercises:
                state = state.with_updates(
                    is_complete=True,
                    final_answer={
                        "adjusted_level": state.adjusted_level,
                        "detected_difficulties": state.difficulties,
                        "suggested_exercises": state.suggested_exercises,
                        "strategy": state.strategy,
                        "strategy_decisions": state.strategy_decisions,
                        "priority_focus": state.priority_focus,
                        "verification": state.verification,
                        "agent_trace": [*state.agent_trace, f"[fallback] erreur: {exc}"],
                        "react_iterations": state.iteration_count,
                        "tools_used": list(set(state.tools_called)),
                    },
                )
            registry.update_state(self.run_id, state)
        else:
            _current_run_id.reset(ctx_token)

        self._enforce_mandatory_tools()

        state = registry.get_state(self.run_id)
        state = state.append_trace(
            f"ReAct terminé. Itérations : {state.iteration_count}. "
            f"Outils : {', '.join(set(state.tools_called))}."
        )
        registry.update_state(self.run_id, state)

        return registry.get_state(self.run_id)

    def _enforce_mandatory_tools(self) -> None:
        """
        After the ReAct loop, call any mandatory tool the LLM skipped.

        - tool_persist_memory : always callable from state — generates summary inline.
        - tool_final_answer   : called only when is_complete is still False.
        - Other mandatory tools (diagnose, generate_exercises) cannot be run
          retroactively; a warning is written to the agent trace.
        """
        mandatory = self.config.get("react", {}).get("mandatory_tools", [])
        state = registry.get_state(self.run_id)
        called = set(state.tools_called)
        lc_config = {"configurable": {"run_id": self.run_id}}

        # Enforce in order: persist first, then finalize
        for tool_name in ["tool_persist_memory", "tool_final_answer"]:
            if tool_name not in mandatory or tool_name in called:
                continue

            if tool_name == "tool_persist_memory":
                state = registry.get_state(self.run_id)
                verification = state.verification or {}
                summary = (
                    f"Session ReAct (enforced): topic={state.topic}, "
                    f"niveau={state.adjusted_level}, "
                    f"difficultés={', '.join(state.difficulties[:3]) or 'aucune'}, "
                    f"vérification={verification.get('verdict', 'unknown')}, "
                    f"outils={', '.join(called)}."
                )
                tool_persist_memory.invoke({"summary": summary}, config=lc_config)
                state = registry.get_state(self.run_id)
                state = state.append_trace(
                    "[enforce] tool_persist_memory appelé automatiquement (non invoqué par le LLM)"
                )
                registry.update_state(self.run_id, state)

            elif tool_name == "tool_final_answer":
                state = registry.get_state(self.run_id)
                if not state.is_complete:
                    tool_final_answer.invoke({}, config=lc_config)
                    state = registry.get_state(self.run_id)
                    state = state.append_trace(
                        "[enforce] tool_final_answer appelé automatiquement (non invoqué par le LLM)"
                    )
                    registry.update_state(self.run_id, state)

        # Warn about mandatory tools that cannot be enforced retroactively
        state = registry.get_state(self.run_id)
        for tool_name in mandatory:
            if tool_name not in called and tool_name not in {"tool_persist_memory", "tool_final_answer"}:
                state = state.append_trace(
                    f"[enforce] WARNING: mandatory tool '{tool_name}' was not called"
                )
        registry.update_state(self.run_id, state)
