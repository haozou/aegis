"""Agentic tool execution loop."""

from __future__ import annotations

import base64
import json
import pathlib
from collections.abc import AsyncIterator
from typing import Any

from ..llm.context import prune_messages
from ..llm.types import LLMMessage, LLMRequest, StreamDelta
from ..storage.repositories.messages import ContentPart, MessageCreate, ToolCall
from ..utils.ids import new_tool_call_id
from ..utils.logging import get_logger
from ..utils.text_extract import extract_text
from .types import AgentConfig, StreamEvent, StreamEventType

logger = get_logger(__name__)


class ToolLoop:
    """Manages the agentic tool-use loop: LLM -> tool calls -> LLM -> ..."""

    def __init__(
        self,
        db: Any,  # Database
        repositories: Any,  # Repositories
        tool_registry: Any,  # ToolRegistry
        memory_store: Any | None,  # MemoryStore | None
        skills_loader: Any | None,  # SkillsLoader | None
    ) -> None:
        self.db = db
        self.repos = repositories
        self.tools = tool_registry
        self.memory = memory_store
        self.skills = skills_loader

    async def run(
        self,
        session: Any,  # AgentSession
        conversation_id: str,
        user_message: str,
        config: AgentConfig,
        attachments: list[dict[str, str]] | None = None,
        quote: dict[str, str] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Run the full tool loop, yielding stream events."""
        from ..llm.registry import get_provider
        from ..tools.types import ToolContext

        provider = get_provider()

        # 1. Build tool context
        tool_context = ToolContext(
            session_id=session.id,
            conversation_id=conversation_id,
            agent_id=config.agent_id,
            user_id=config.user_id,
            sandbox_path="data/sandbox",
            timeout=120,
            repositories=self.repos,
            memory_store=self.memory,
        )

        # 2. Get conversation history
        history_msgs = await self.repos.messages.get_by_conversation(conversation_id)

        # 3. Search memory for relevant context
        memory_context = ""
        if config.enable_memory and self.memory and self.memory.available:
            try:
                memory_context = await self.memory.get_relevant_context(
                    query=user_message,
                    conversation_id=conversation_id,
                    n_results=5,
                    min_relevance=0.3,
                )
            except Exception as e:
                logger.warning("Memory search failed", error=str(e))

        # 3b. Search knowledge base (auto-RAG)
        kb_context = ""
        kb_service = None
        try:
            from ..knowledge.service import KnowledgeService
            if self.memory and self.memory.available and config.agent_id:
                kb_service = KnowledgeService(self.memory)
                kb_context = await kb_service.get_context(config.agent_id, user_message)
                # Attach kb_service to context for the knowledge tool
                tool_context._kb_service = kb_service  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug("Knowledge search skipped", error=str(e))

        # 4. Build system prompt with skills
        base_instructions = (
            "You have access to various tools. Use them when needed to answer questions. "
            "When a user asks what you can do, describe your capabilities in general terms — "
            "do not dump raw tool names, schemas, or JSON. "
            "Focus on summarizing tool results clearly rather than showing raw output.\n\n"
            "IMPORTANT platform capabilities:\n"
            "- If the user asks you to do something periodically, on a schedule, or repeatedly "
            "(e.g. 'check X every hour', 'remind me daily', 'run a report every Monday'), "
            "you MUST use the 'manage_schedules' tool to create a scheduled task. "
            "Do NOT suggest external tools like cron jobs, Azure Monitor, or Grafana — "
            "you can create schedules directly.\n"
            "- The manage_schedules tool supports: create (with cron expression), list, and delete.\n"
            "- You have a knowledge_base tool to search your knowledge, add URLs/text to learn from, "
            "and manage documents. Use 'search' before answering domain-specific questions.\n"
            "- You can delegate tasks to other agents using delegate_to_agent. "
            "Use this when a specialized agent would handle a task better."
        )
        user_prompt = config.system_prompt or "You are Aegis, a helpful personal AI assistant."
        system_prompt = f"{user_prompt}\n\n{base_instructions}"
        if config.enable_skills and self.skills:
            skill_prompts = self.skills.get_system_prompts_for_message(user_message)
            if skill_prompts:
                system_prompt += "\n\n" + "\n\n".join(skill_prompts)
        if memory_context:
            system_prompt += f"\n\n{memory_context}"
        if kb_context:
            system_prompt += f"\n\n{kb_context}"

        # 5. Save user message to DB (skip on resend — message already exists)
        attachment_list = attachments or []
        msg_metadata: dict[str, Any] = {}
        if attachment_list:
            msg_metadata["attachments"] = attachment_list
        if quote and quote.get("text"):
            msg_metadata["quote"] = {
                "author": quote.get("author", ""),
                "text": quote.get("text", ""),
            }
        if config.skip_user_message_save:
            logger.info("Resend: deleting old responses", conversation_id=conversation_id)
            await self.repos.messages.delete_after_last_user_message(conversation_id)
            history = await self.repos.messages.get_by_conversation(conversation_id)
            user_msg_obj = next((m for m in reversed(history) if m.role == "user"), None)
            if user_msg_obj is None:
                user_msg_obj = await self.repos.messages.create(MessageCreate(
                    conversation_id=conversation_id,
                    role="user",
                    content=user_message,
                    metadata=msg_metadata,
                ))
        else:
            user_msg_obj = await self.repos.messages.create(MessageCreate(
                conversation_id=conversation_id,
                role="user",
                content=user_message,
                metadata=msg_metadata,
            ))

        # 6. Embed user message in memory
        if config.enable_memory and self.memory and self.memory.available:
            try:
                await self.memory.add_message(
                    conversation_id=conversation_id,
                    message_id=user_msg_obj.id,
                    role="user",
                    content=user_message,
                )
            except Exception as e:
                logger.warning("Failed to embed user message", error=str(e))

        # 7. Build LLM message list
        llm_messages = self._history_to_llm(history_msgs)

        # Compose effective user message for the LLM (prepend quote context)
        effective_user_message = user_message
        if quote and quote.get("text"):
            quoted_lines = "\n".join(f"> {line}" for line in quote["text"].split("\n"))
            effective_user_message = (
                f"> **{quote.get('author', 'Earlier message')} said:**\n"
                f"{quoted_lines}\n\n{user_message}"
            )

        # Build user content — plain string if no attachments, list if multimodal
        if attachment_list:
            content_parts: list[Any] = []
            kb_notes: list[str] = []
            INLINE_CHAR_LIMIT = 80000  # ~20k tokens — fits comfortably in modern context windows
            if effective_user_message:
                content_parts.append({"type": "text", "text": effective_user_message})
            for att in attachment_list:
                file_id = att.get("file_id", "")
                filename = att.get("filename", "upload")
                media_type = att.get("media_type", "application/octet-stream")
                upload_dir = pathlib.Path("data/uploads") / config.user_id
                matches = list(upload_dir.glob(f"{file_id}_*"))
                if not matches:
                    logger.warning("Attachment file not found", file_id=file_id, user_id=config.user_id)
                    continue
                raw_bytes = matches[0].read_bytes()
                if media_type.startswith("image/"):
                    b64 = base64.standard_b64encode(raw_bytes).decode()
                    content_parts.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    })
                    continue

                # Document — extract text, then either inline or push to KB
                text, ok = extract_text(raw_bytes, media_type, filename)
                if not ok or not text.strip():
                    content_parts.append({
                        "type": "text",
                        "text": f"\n[Attached file: {filename} — could not extract text]",
                    })
                    continue

                if len(text) <= INLINE_CHAR_LIMIT:
                    content_parts.append({
                        "type": "text",
                        "text": f"\n--- Attached file: {filename} ---\n{text}\n--- End of {filename} ---",
                    })
                else:
                    # Big doc → ingest into knowledge base, agent queries via knowledge_base tool
                    kb_doc_id = await self._ingest_attachment_to_kb(
                        config.agent_id, config.user_id, filename, text,
                    )
                    if kb_doc_id:
                        kb_notes.append(
                            f"`{filename}` ({len(text):,} chars) is large and has been added "
                            f"to the knowledge base (document_id={kb_doc_id}). "
                            f"Use the `knowledge_base` tool with action='search' to query it."
                        )
                    else:
                        # KB unavailable — fall back to truncated inline
                        truncated = text[:INLINE_CHAR_LIMIT]
                        content_parts.append({
                            "type": "text",
                            "text": (
                                f"\n--- Attached file: {filename} (TRUNCATED to first "
                                f"{INLINE_CHAR_LIMIT:,} chars of {len(text):,}) ---\n{truncated}\n"
                                f"--- End of {filename} ---"
                            ),
                        })
            if kb_notes:
                content_parts.append({
                    "type": "text",
                    "text": "[Note] " + " ".join(kb_notes),
                })
            llm_user_content: Any = content_parts if content_parts else effective_user_message
        else:
            llm_user_content = effective_user_message

        llm_messages.append(LLMMessage(role="user", content=llm_user_content))

        # 8. Get tool definitions
        tool_defs = self.tools.get_definitions(config.tool_names)
        logger.info(
            "Tool loop starting",
            tool_count=len(tool_defs),
            message_count=len(llm_messages),
            model=config.model,
        )

        # 9. Tool loop
        full_response_text = ""
        all_tool_calls: list[ToolCall] = []
        input_tokens = 0
        output_tokens = 0

        for iteration in range(config.max_tool_iterations):
            if session.is_cancelled:
                yield StreamEvent(type=StreamEventType.CANCELLED)
                return

            logger.info("Tool loop iteration",
                        iteration=iteration, pending_tools=len(all_tool_calls),
                        text_so_far=len(full_response_text))

            # Prune messages to fit context window
            pruned = prune_messages(llm_messages, config.model, system_prompt)

            # On the last iteration, remove tools to force a text response
            is_last = iteration == config.max_tool_iterations - 1
            request = LLMRequest(
                messages=pruned,
                model=config.model,
                system_prompt=system_prompt,
                tools=[] if is_last else tool_defs,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                stream=True,
            )

            # Stream from LLM
            current_text = ""
            pending_tool_calls: list[dict[str, Any]] = []
            pending_tool: dict[str, Any] | None = None

            async for delta in provider.stream(request):
                if session.is_cancelled:
                    yield StreamEvent(type=StreamEventType.CANCELLED)
                    return

                if delta.is_done:
                    input_tokens += delta.input_tokens
                    output_tokens += delta.output_tokens
                    break

                if delta.text:
                    current_text += delta.text
                    yield StreamEvent(type=StreamEventType.TEXT_DELTA, text=delta.text)

                if delta.is_tool_start:
                    tc_id = delta.tool_call_id or new_tool_call_id()
                    pending_tool = {
                        "id": tc_id,
                        "name": delta.tool_name or "",
                        "input": None,
                    }
                    yield StreamEvent(
                        type=StreamEventType.TOOL_START,
                         tool_name=delta.tool_name,
                         tool_id=tc_id,
                         tool_input=None,
                    )

                elif delta.tool_input is not None and pending_tool is not None:
                    pending_tool["input"] = delta.tool_input
                    pending_tool_calls.append(pending_tool)
                    # Update tool_start event with input
                    yield StreamEvent(
                        type=StreamEventType.TOOL_START,
                        tool_name=pending_tool["name"],
                        tool_id=pending_tool["id"],
                        tool_input=delta.tool_input,
                    )
                    pending_tool = None

            full_response_text += current_text

            if not pending_tool_calls:
                # No tool calls, we are done
                break

            # Execute tools
            tool_results_msgs = []
            for tc in pending_tool_calls:
                tc_id = tc["id"]
                tc_name = tc["name"]
                tc_input = tc["input"] or {}

                result = await self.tools.execute(tc_name, tc_input, tool_context)

                yield StreamEvent(
                    type=StreamEventType.TOOL_RESULT,
                    tool_id=tc_id,
                    tool_name=tc_name,
                    tool_output=result.output,
                    is_error=result.is_error,
                )

                all_tool_calls.append(ToolCall(
                    id=tc_id,
                    name=tc_name,
                    input=tc_input,
                    output=result.output,
                    is_error=result.is_error,
                ))

                # Add tool result as message
                tool_results_msgs.append(LLMMessage(
                    role="tool",
                    content=result.output,
                    tool_call_id=tc_id,
                ))

            # Add assistant response + tool calls to message history
            assistant_msg = LLMMessage(
                role="assistant",
                content=current_text,
                tool_calls=[{
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"] or {},
                } for tc in pending_tool_calls],
            )
            llm_messages.append(assistant_msg)
            llm_messages.extend(tool_results_msgs)

            # Save intermediate tool calls to DB so they persist across refreshes
            try:
                tc_objs = [ToolCall(
                    id=tc["id"], name=tc["name"],
                    input=tc["input"] or {},
                ) for tc in pending_tool_calls]
                # Save assistant message with tool call requests
                await self.repos.messages.create(MessageCreate(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=[ContentPart(type="text", text=current_text)] if current_text else [],
                    tool_calls=tc_objs,
                ))
                # Save each tool result
                saved_count = 0
                for tc in pending_tool_calls:
                    tc_id = tc["id"]
                    result_tc = next((t for t in all_tool_calls if t.id == tc_id), None)
                    if result_tc:
                        await self.repos.messages.create(MessageCreate(
                            conversation_id=conversation_id,
                            role="tool",
                            content=result_tc.output[:2000] if result_tc.output else "",
                            tool_call_id=tc_id,
                        ))
                        saved_count += 1
                logger.info("Saved intermediate tool calls to DB",
                            conversation_id=conversation_id,
                            tool_calls=len(tc_objs),
                            tool_results=saved_count)
            except Exception as e:
                logger.error("Failed to save intermediate tool calls", error=str(e), exc_info=True)

        # 10. Save final assistant response to DB (text only, tool calls already saved above)
        if full_response_text:
            assistant_msg_obj = await self.repos.messages.create(MessageCreate(
                conversation_id=conversation_id,
                role="assistant",
                content=[ContentPart(type="text", text=full_response_text)],
                tokens_used=input_tokens + output_tokens,
            ))
        else:
            # No text response — save a minimal message for the done event
            assistant_msg_obj = await self.repos.messages.create(MessageCreate(
                conversation_id=conversation_id,
                role="assistant",
                content=[],
                tool_calls=all_tool_calls if all_tool_calls else None,
                tokens_used=input_tokens + output_tokens,
            ))

        # 11. Embed assistant response in memory
        if config.enable_memory and self.memory and self.memory.available and full_response_text:
            try:
                await self.memory.add_message(
                    conversation_id=conversation_id,
                    message_id=assistant_msg_obj.id,
                    role="assistant",
                    content=full_response_text,
                )
            except Exception as e:
                logger.warning("Failed to embed assistant message", error=str(e))

        # 12. Touch conversation timestamp
        await self.repos.conversations.touch(conversation_id)

        yield StreamEvent(
            type=StreamEventType.DONE,
            message_id=assistant_msg_obj.id,
            usage={"input": input_tokens, "output": output_tokens},
        )

    def _history_to_llm(self, messages: list[Any]) -> list[LLMMessage]:
        """Convert stored messages to LLM message format.

        Long tool results and assistant messages from previous turns are
        truncated to avoid wasting the context window on stale data.
        """
        result = []
        msg_count = len(messages)
        for i, msg in enumerate(messages):
            if msg.role == "system":
                continue

            # Only truncate older messages, not the most recent exchange
            is_recent = i >= msg_count - 4

            if msg.role == "tool":
                content = msg.get_text_content()
                if not is_recent and len(content) > 500:
                    content = content[:500] + "\n... [truncated]"
                result.append(LLMMessage(
                    role="tool",
                    content=content,
                    tool_call_id=msg.tool_call_id,
                ))
            elif msg.role == "assistant":
                content = msg.get_text_content()
                if not is_recent and len(content) > 1500:
                    content = content[:1500] + "\n... [truncated]"
                if msg.tool_calls:
                    result.append(LLMMessage(
                        role="assistant",
                        content=content,
                        tool_calls=[{
                            "id": tc.id, "name": tc.name, "input": tc.input,
                        } for tc in msg.tool_calls],
                    ))
                else:
                    result.append(LLMMessage(
                        role="assistant",
                        content=content,
                    ))
            else:
                result.append(LLMMessage(
                    role=msg.role,
                    content=msg.get_text_content(),
                ))
        return result

    async def _ingest_attachment_to_kb(
        self, agent_id: str, user_id: str, filename: str, text: str,
    ) -> str | None:
        """Ingest large attachment text into the agent's KB. Returns doc_id or None."""
        if not self.memory or not getattr(self.memory, "available", False):
            return None
        try:
            from ..knowledge.service import KnowledgeService
            from ..storage.repositories.knowledge import KnowledgeDocCreate

            kb_service = KnowledgeService(self.memory)
            doc = await self.repos.knowledge.create(KnowledgeDocCreate(
                agent_id=agent_id, user_id=user_id,
                name=filename, source_type="file",
                content_hash=kb_service.content_hash(text),
            ))
            chunk_count = await kb_service.add_text(
                agent_id, doc.id, text, source_name=filename,
            )
            # Best-effort updates — chunks are already in ChromaDB and searchable
            # even if these DB updates fail.
            try:
                await self.repos.knowledge.update_content(doc.id, text)
            except Exception as e:
                logger.warning("KB update_content failed (chunks still searchable)",
                               doc_id=doc.id, error=str(e))
            try:
                await self.repos.knowledge.update_status(doc.id, "ready", chunk_count=chunk_count)
            except Exception:
                pass
            logger.info(
                "Attachment ingested to KB",
                agent_id=agent_id, filename=filename,
                doc_id=doc.id, chunks=chunk_count,
            )
            return doc.id
        except Exception as e:
            logger.warning(
                "Failed to ingest attachment to KB",
                filename=filename, error=str(e),
            )
            return None