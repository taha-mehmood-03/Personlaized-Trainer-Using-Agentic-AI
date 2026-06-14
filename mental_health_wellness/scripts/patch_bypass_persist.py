"""
Patches graph.py to add _background_persist call to the bypass early-return
path in chat_with_agent_streaming, so that memory_query / chitchat / etc.
turns are saved to the DB just like full-pipeline turns.
"""

import sys
import pathlib

graph_path = pathlib.Path(
    r"e:\FYP\mental_health_wellness\src\mental_health_wellness\agent\graph.py"
)
src = graph_path.read_bytes()

OLD = (
    b'                bypass_result["latency_trace"] = latency_trace\r\n'
    b'                bypass_result["latency_summary"] = _latency_summary(latency_trace, start_time)\r\n'
    b'                reply = bypass_result["response"]\r\n'
    b'                # Stream the bypass reply word-by-word (uniform UX across all routes)\r\n'
    b'                words = reply.split(" ") if reply else []\r\n'
    b'                for i, word in enumerate(words):\r\n'
    b'                    await token_queue.put({"type": "token", "content": word if i == 0 else " " + word})\r\n'
    b'                    await asyncio.sleep(0.01)\r\n'
    b'                await token_queue.put({"type": "done", "metadata": bypass_result})\r\n'
    b'                return\r\n'
)

NEW = (
    b'                bypass_result["latency_trace"] = latency_trace\r\n'
    b'                bypass_result["latency_summary"] = _latency_summary(latency_trace, start_time)\r\n'
    b'                reply = bypass_result["response"]\r\n'
    b'                # Stream the bypass reply word-by-word (uniform UX across all routes)\r\n'
    b'                words = reply.split(" ") if reply else []\r\n'
    b'                for i, word in enumerate(words):\r\n'
    b'                    await token_queue.put({"type": "token", "content": word if i == 0 else " " + word})\r\n'
    b'                    await asyncio.sleep(0.01)\r\n'
    b'                await token_queue.put({"type": "done", "metadata": bypass_result})\r\n'
    b'                # Persist gate-bypass turn to DB (memory_query, chitchat, accept/reject, etc.)\r\n'
    b'                if not _env_flag("SENTIMIND_DISABLE_BACKGROUND_PERSIST_FOR_TESTS"):\r\n'
    b'                    _persist_state = {\r\n'
    b'                        **bypass_result,\r\n'
    b'                        "messages": list(prev_messages) + [\r\n'
    b'                            HumanMessage(content=message),\r\n'
    b'                            AIMessage(content=reply),\r\n'
    b'                        ],\r\n'
    b'                        "user_id": user_id,\r\n'
    b'                        "session_id": actual_session_id,\r\n'
    b'                        "final_response": reply,\r\n'
    b'                    }\r\n'
    b'                    asyncio.create_task(_background_persist(_persist_state))\r\n'
    b'                    print(f"[PERSIST] [BYPASS] Scheduled DB persist for route={gate_route}")\r\n'
    b'                return\r\n'
)

count = src.count(OLD)
if count == 0:
    print("[PATCH] ERROR: target pattern not found", file=sys.stderr)
    sys.exit(1)
if count > 1:
    print(f"[PATCH] ERROR: {count} occurrences found – ambiguous", file=sys.stderr)
    sys.exit(1)

patched = src.replace(OLD, NEW, 1)
graph_path.write_bytes(patched)
print("[PATCH] OK — gate-bypass persist fix applied to graph.py")
