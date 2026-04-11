**SentiMind**

**ChatGPT-Style Memory System**

Implementation Plan & Antigravity Prompt

────────────────────────────────────

*Replacing ChromaDB with a 3-Layer Memory Architecture*

**📋 Executive Summary**

This document defines the complete implementation plan for replacing
SentiMind\'s ChromaDB semantic search memory with a ChatGPT-style
3-layer memory architecture. The new system eliminates the vector
database entirely, using Prisma (already in the stack) for all memory
storage --- resulting in faster retrieval, more accurate context, and
significantly less complexity.

  ----------------------- ----------------------- -----------------------
  **Metric**              **Before**              **After**

  Memory approach         ChromaDB vector search  3-layer: Facts +
                                                  Summaries + Window

  Storage                 ChromaDB (separate      Prisma only (already in
                          service)                stack)

  Retrieval latency       \~200ms                 \~50ms

  Accuracy                \~60%                   \~90%

  Context quality         Raw similar messages    Structured grounded
                                                  context

  Max facts stored        Unlimited (noisy)       33 explicit facts (like
                                                  ChatGPT)

  Session history         All messages raw        15 smart summaries
                                                  (like ChatGPT)

  ChromaDB dependency     Required                Optional / removable
  ----------------------- ----------------------- -----------------------

**🏗️ Architecture Overview**

The new memory system mirrors exactly how ChatGPT manages memory --- 3
layers injected into every LLM prompt:

> **Layer 1: Explicit Facts** *(Like ChatGPT\'s \'Remember this\')*
>
> • Max 33 facts stored in Prisma UserFact table
>
> • Auto-extracted from user messages using LLM
>
> • Categories: identity, preference, goal, clinical, context
>
> • Examples: \'User name is Taha\', \'User is anxious about deadlines\'
>
> • Always injected --- no search needed, instant retrieval
>
> **Layer 2: Session Summaries** *(Like ChatGPT\'s conversation
> history)*
>
> • Max 15 summaries stored in Prisma SessionSummary table
>
> • Generated automatically at end of each session
>
> • Only user messages summarized --- not assistant responses
>
> • Format: Title + 2 sentence digest + emotion + techniques + outcome
>
> • Rolling window --- oldest deleted when limit reached
>
> **Layer 3: Sliding Window** *(Current session messages)*
>
> • Current session messages in memory --- no DB needed
>
> • Max 20 messages kept within token budget
>
> • Keeps first message (context) + most recent messages
>
> • Truncated to fit LLM context window
>
> • Cleared at session end

**🗄️ Database Changes (Prisma Schema)**

Add these two models to your existing schema.prisma file:

> model UserFact { id String \@id \@default(cuid()) userId String fact
> String category String //
> identity\|preference\|goal\|clinical\|context createdAt DateTime
> \@default(now()) updatedAt DateTime \@updatedAt user User
> \@relation(fields: \[userId\], references: \[id\]) } model
> SessionSummary { id String \@id \@default(cuid()) userId String
> sessionId String title String summary String emotion String techniques
> String\[\] outcome String createdAt DateTime \@default(now()) user
> User \@relation(fields: \[userId\], references: \[id\]) }

**Migration command to run after schema changes:**

> npx prisma migrate dev \--name add_chatgpt_memory_layers npx prisma
> generate

**📁 Files To Create**

  ------------------------------ ----------------------- -----------------------
  **File**                       **Purpose**             **Action**

  memory/explicit_facts.py       Layer 1 --- extract &   **CREATE NEW**
                                 retrieve facts          

  memory/session_summarizer.py   Layer 2 --- generate &  **CREATE NEW**
                                 retrieve summaries      

  memory/sliding_window.py       Layer 3 --- current     **CREATE NEW**
                                 session window          

  memory/memory_builder.py       Combines all 3 layers   **CREATE NEW**
                                 into prompt             

  nodes/intake_node.py           Wire new memory into    **MODIFY**
                                 pipeline                

  nodes/session_saver_node.py    Trigger summary         **MODIFY**
                                 generation              

  memory/memory_tools.py         Fix threshold bug (0.8  **MODIFY**
                                 → 1.2)                  

  memory/memory_tools.py         Remove assistant        **MODIFY**
                                 message storage         

  schema.prisma                  Add UserFact +          **MODIFY**
                                 SessionSummary models   
  ------------------------------ ----------------------- -----------------------

**🔢 Implementation Steps**

**Step 1: Prisma Schema Migration** *\[15 min\]* **🔴 DO FIRST**

> 1\. Open schema.prisma
>
> 2\. Add UserFact model with fields: id, userId, fact, category,
> createdAt, updatedAt
>
> 3\. Add SessionSummary model with fields: id, userId, sessionId,
> title, summary, emotion, techniques\[\], outcome, createdAt
>
> 4\. Add relations to User model for both new models
>
> 5\. Run: npx prisma migrate dev \--name add_chatgpt_memory_layers
>
> 6\. Run: npx prisma generate
>
> 7\. Verify migration succeeded in Supabase dashboard

**Step 2: Create explicit_facts.py** *\[30 min\]* **🔴 CRITICAL**

> 1\. Create memory/explicit_facts.py
>
> 2\. Import Groq client and Prisma client
>
> 3\. Define MAX_FACTS = 33 constant
>
> 4\. Implement extract_and_save_facts(user_id, message, session_id) ---
> calls Groq LLM to extract facts, saves new ones to UserFact table,
> skips duplicates, respects 33 limit
>
> 5\. Implement get_user_facts(user_id) --- retrieves all facts grouped
> by category, formatted for prompt injection
>
> 6\. Implement classify_fact_category(fact) --- rule-based categorizer
>
> 7\. Add proper try/except --- never crash the pipeline

**Step 3: Create session_summarizer.py** *\[30 min\]* **🔴 CRITICAL**

> 1\. Create memory/session_summarizer.py
>
> 2\. Import Groq client and Prisma client
>
> 3\. Define MAX_SUMMARIES = 15 constant
>
> 4\. Implement summarize_session(user_id, session_id, messages,
> emotion, techniques, outcome) --- extracts user messages only, calls
> Groq for title + 2 sentence summary, checks limit, deletes oldest if
> at limit, saves new summary
>
> 5\. Implement get_session_summaries(user_id) --- retrieves recent
> summaries ordered by date, formatted with date + title + summary +
> emotion + techniques + outcome
>
> 6\. Add proper try/except --- always use asyncio.create_task() so it
> never blocks the pipeline

**Step 4: Create sliding_window.py** *\[15 min\]* **🟠 IMPORTANT**

> 1\. Create memory/sliding_window.py
>
> 2\. Define MAX_MESSAGES = 20 constant
>
> 3\. Implement build_sliding_window(messages, max_messages) --- keeps
> first message + most recent up to limit
>
> 4\. Implement format_window_for_prompt(messages) --- formats as \'You:
> \...\' and \'SentiMind: \...\' alternating, truncates each message to
> 200 chars

**Step 5: Create memory_builder.py** *\[20 min\]* **🟠 IMPORTANT**

> 1\. Create memory/memory_builder.py
>
> 2\. Import all three layer modules
>
> 3\. Implement build_full_memory_context(user_id, current_messages,
> include_window=True)
>
> 4\. Call get_user_facts() --- Layer 1
>
> 5\. Call get_session_summaries() --- Layer 2
>
> 6\. Call build_sliding_window() + format_window_for_prompt() --- Layer
> 3
>
> 7\. Join all non-empty sections with double newline
>
> 8\. Append instruction: \'Use above as context. Do not repeat
> verbatim. Only reference if directly relevant.\'

**Step 6: Modify intake_node.py** *\[20 min\]* **🟠 IMPORTANT**

> 1\. Import build_full_memory_context from memory.memory_builder
>
> 2\. Import extract_and_save_facts from memory.explicit_facts
>
> 3\. Replace existing ChromaDB memory retrieval call with:
> memory_context = await build_full_memory_context(user_id, messages)
>
> 4\. Add asyncio.create_task(extract_and_save_facts(user_id, message,
> session_id)) --- runs async, doesnt block
>
> 5\. Set state\[\'memory_context\'\] = memory_context
>
> 6\. Keep existing Prisma profile/trend loading --- it feeds into Layer
> 1 naturally

**Step 7: Modify session_saver_node.py** *\[15 min\]* **🟠 IMPORTANT**

> 1\. Import summarize_session from memory.session_summarizer
>
> 2\. After existing save logic, add: if message_count % 5 == 0 or
> session_ending:
>
> 3\. asyncio.create_task(summarize_session(user_id, session_id,
> messages, emotion, techniques, outcome))
>
> 4\. This generates summaries every 5 messages and at session end
>
> 5\. Never await it directly --- always use create_task so pipeline is
> not blocked

**Step 8: Fix existing memory_tools.py bugs** *\[10 min\]* **🟢 QUICK
WIN**

> 1\. Change score threshold from 0.8 to 1.2 (L2 distance fix)
>
> 2\. Remove assistant message storage --- only store user messages
>
> 3\. Remove \'User said:\' prefix --- store clean text only
>
> 4\. Change bare \'raise\' in except to \'return \[\]\'
>
> 5\. Add vectorstore cache dict to avoid re-instantiation

**Step 9: Test & Verify** *\[30 min\]* **🟢 VERIFY**

> 1\. Start server: python -m api_server
>
> 2\. Send message with your name: \'My name is \[your name\]\'
>
> 3\. Check Prisma UserFact table --- should have new fact
>
> 4\. Send 5+ messages in one session
>
> 5\. Check Prisma SessionSummary table --- should have summary
>
> 6\. Send new message next session --- verify name is remembered
>
> 7\. Run full 75 test suite --- pass rate should stay at 86.7%+
>
> 8\. Check response quality --- should reference past context correctly

**🤖 Antigravity Implementation Prompt**

*Copy and paste this entire prompt into Antigravity to begin
implementation:*

> **── ANTIGRAVITY PROMPT --- COPY EVERYTHING BELOW THIS LINE ──**
>
> You are implementing a ChatGPT-style memory system for SentiMind, a
> mental health AI chatbot built with Python (FastAPI + LangGraph) and
> Next.js 14 App Router.
>
> ── PROJECT CONTEXT ──────────────────────────────────────────
>
> Project: SentiMind --- AI mental health wellness chatbot
>
> Backend: Python, FastAPI, LangGraph (14-node pipeline), Groq LLM
> (llama-3.3-70b-versatile), ChromaDB, Prisma ORM
>
> Database: Supabase (PostgreSQL) via Prisma
>
> Current memory: ChromaDB semantic search (being replaced)
>
> Embedding model: sentence-transformers/all-MiniLM-L6-v2
>
> ── WHAT YOU ARE BUILDING ────────────────────────────────────
>
> Replace ChromaDB semantic search memory with a 3-layer ChatGPT-style
> memory system:
>
> LAYER 1 --- Explicit Facts (memory/explicit_facts.py)
>
> • Max 33 facts stored in Prisma UserFact table
>
> • Auto-extracted from user messages using Groq LLM
>
> • Categories: identity, preference, goal, clinical, context
>
> • Always injected into prompt --- no search needed
>
> • extract_and_save_facts(user_id, message, session_id) --- LLM
> extracts new facts, saves to DB, skips duplicates
>
> • get_user_facts(user_id) → formatted string for prompt
>
> LAYER 2 --- Session Summaries (memory/session_summarizer.py)
>
> • Max 15 summaries in Prisma SessionSummary table
>
> • Auto-generated every 5 messages and at session end
>
> • Only user messages summarized (not assistant responses)
>
> • Format: title (5 words) + 2 sentence digest + emotion + techniques +
> outcome
>
> • Rolling window --- oldest deleted when at limit
>
> • summarize_session(user_id, session_id, messages, emotion,
> techniques, outcome)
>
> • get_session_summaries(user_id) → formatted string for prompt
>
> LAYER 3 --- Sliding Window (memory/sliding_window.py)
>
> • Current session messages in memory --- no DB needed
>
> • Max 20 messages, keeps first + most recent
>
> • build_sliding_window(messages) → trimmed list
>
> • format_window_for_prompt(messages) → formatted string
>
> COMBINER --- Memory Builder (memory/memory_builder.py)
>
> • build_full_memory_context(user_id, current_messages) → single
> context string
>
> • Calls all 3 layers, joins non-empty sections
>
> • Final string injected into state\[\'memory_context\'\] in intake
> node
>
> ── PRISMA SCHEMA --- ADD THESE TWO MODELS ─────────────────────
>
> model UserFact {
>
> id String \@id \@default(cuid())
>
> userId String
>
> fact String
>
> category String
>
> createdAt DateTime \@default(now())
>
> updatedAt DateTime \@updatedAt
>
> user User \@relation(fields: \[userId\], references: \[id\])
>
> }
>
> model SessionSummary {
>
> id String \@id \@default(cuid())
>
> userId String
>
> sessionId String
>
> title String
>
> summary String
>
> emotion String
>
> techniques String\[\]
>
> outcome String
>
> createdAt DateTime \@default(now())
>
> user User \@relation(fields: \[userId\], references: \[id\])
>
> }
>
> ── FILES TO MODIFY ───────────────────────────────────────────
>
> 1\. nodes/intake_node.py
>
> • Replace ChromaDB memory retrieval with: memory_context = await
> build_full_memory_context(user_id, messages)
>
> • Add asyncio.create_task(extract_and_save_facts(\...)) --- must NOT
> await, runs in background
>
> • Set state\[\'memory_context\'\] = memory_context
>
> 2\. nodes/session_saver_node.py
>
> • After existing save logic add:
> asyncio.create_task(summarize_session(\...))
>
> • Trigger every 5 messages AND when session ends
>
> • Never await --- always background task
>
> 3\. memory/memory_tools.py (existing ChromaDB file --- fix bugs)
>
> • Change score threshold from 0.8 → 1.2 (L2 distance fix)
>
> • Remove assistant message storage --- user messages only
>
> • Remove \'User said:\' prefix from stored text
>
> • Change bare \'raise\' in except blocks → return \[\]
>
> • Add vectorstore cache dict \_vectorstore_cache = {}
>
> ── CRITICAL RULES ────────────────────────────────────────────
>
> • All new memory functions must have try/except --- NEVER crash the
> pipeline
>
> • summarize_session and extract_and_save_facts must use
> asyncio.create_task() --- never block
>
> • Groq model to use for memory LLM calls: llama-3.3-70b-versatile
>
> • Use existing Prisma client import pattern from the project
>
> • Use existing Groq client import pattern from the project
>
> • MAX_FACTS = 33, MAX_SUMMARIES = 15, MAX_MESSAGES = 20
>
> • After Prisma schema changes run: npx prisma migrate dev \--name
> add_chatgpt_memory_layers
>
> ── FINAL PROMPT STRUCTURE AFTER IMPLEMENTATION ──────────────
>
> The memory_context injected into the LLM should look like:
>
> WHAT I KNOW ABOUT YOU:
>
> • User name is Taha Khan
>
> • User is doing FYP in mental health AI
>
> • User gets anxious about deadlines
>
> RECENT SESSION HISTORY:
>
> • Mar 12 --- FYP Deadline Anxiety
>
> User was stressed about pipeline testing. Used box breathing. Outcome:
> helped
>
> Emotion: anxiety \| Techniques: Box Breathing \| Outcome: helped
>
> CURRENT SESSION:
>
> You: I feel really anxious today
>
> SentiMind: I hear you, anxiety can feel heavy\...
>
> ── IMPLEMENTATION ORDER ──────────────────────────────────────
>
> 1\. schema.prisma --- add UserFact and SessionSummary models
>
> 2\. Run prisma migrate
>
> 3\. Create memory/explicit_facts.py
>
> 4\. Create memory/session_summarizer.py
>
> 5\. Create memory/sliding_window.py
>
> 6\. Create memory/memory_builder.py
>
> 7\. Modify nodes/intake_node.py
>
> 8\. Modify nodes/session_saver_node.py
>
> 9\. Fix bugs in memory/memory_tools.py
>
> 10\. Restart server and verify facts + summaries appear in Prisma
>
> ── VERIFICATION ──────────────────────────────────────────────
>
> After implementation verify:
>
> • Send \"My name is \[name\]\" → check UserFact table has new fact
>
> • Send 5+ messages → check SessionSummary table has summary
>
> • New session → verify name is remembered in response
>
> • Run 75 test suite → pass rate must stay at 86.7% or higher
>
> • Check no pipeline crashes from memory errors
>
> **── END OF ANTIGRAVITY PROMPT ──**

**✅ Verification Checklist**

  ----------------------- ----------------------- -----------------------
  **Check**               **Test**                **Expected**

  ☐                       Send \'My name is       UserFact table has new
                          Taha\'                  identity fact

  ☐                       Send 5+ messages in one SessionSummary table
                          session                 has new summary

  ☐                       Start new session ---   Bot correctly recalls
                          say \'what\'s my        name from facts
                          name?\'                 

  ☐                       Check memory_context in Shows 3 sections:
                          logs                    facts + summaries +
                                                  window

  ☐                       Run 75 test suite       Pass rate stays 86.7%
                                                  or higher

  ☐                       Force a memory error    Pipeline continues ---
                          (stop Prisma)           returns empty context

  ☐                       Send 6th session        Oldest summary deleted,
                          summary                 new one saved

  ☐                       Send 34th fact          Fact not saved ---
                                                  respects 33 limit

  ☐                       Check no \'User said:\' Clean text stored
                          in ChromaDB             without prefix

  ☐                       Check no assistant      Only user messages
                          messages in ChromaDB    stored
  ----------------------- ----------------------- -----------------------

*SentiMind Memory Implementation Plan • Generated for Antigravity*
