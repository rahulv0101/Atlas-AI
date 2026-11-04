# Atlas Routing Contract

Atlas has one canonical informational answering route:

1. normalize question
2. detect intent candidates
3. detect answer domain
4. collect evidence
5. select answer plan
6. synthesize answer
7. run relevance validation

## Canonical Answer Routes

- UI typed questions: `/api/ask-atlas` calls `AskAtlasService.answer()`.
- Voice questions: `voice.wake_loop.run_voice_loop()` transcribes speech, then calls `AskAtlasService.answer(..., mode="voice")`.
- Conversation wrapper: `ConversationalAtlasInterface` defaults to `AskAtlasService`.
- Brain v2 observability: every canonical answer should expose `answer_trace`.

Specialist informational formatters are adapters to Brain v2 validation. Their
responses must pass the shared evidence, plan, and relevance checks before return
or conversational-memory storage. Direct-handler traces are not a substitute for
validation. Rejected drafts regenerate through the main answer engine; twice-rejected
drafts return an insufficient-evidence response.

The canonical structured knowledge directory is root `knowledge`. Readers and
macro writers use that same location, including in installed wheels. Cached reads
must refresh when files change and must not expose mutable cached objects to callers.

Voice and typed input share the same answer engine. Voice may shorten the response, but it must not use a separate brain.

## Trading And Execution Routes

- Trading decisions remain owned by `AtlasTrader`, `RiskManager`, execution guards, and broker adapters.
- Informational answers must not execute trades, alter risk policy, or mutate strategy parameters.
- Command execution must stay isolated behind explicit command routing.
- Trading observability should expose `decision_trace` without changing the decision.

## Legacy Compatibility

- `atlas_ai.operator_assistant.AtlasAssistant` is compatibility-only.
- `atlas_ai.operator_core` is compatibility-only.
- New typed, UI, conversation, or voice routes must not default to legacy operator modules.
- Legacy modules may remain importable for old tests, migration support, and read-only helper functions.

## Safety Boundaries

- Conversational memory may support continuity, but it must not alter trading decisions.
- Voice features may route explicit commands, but must not broaden system actions.
- Structured knowledge should be preferred over prompt blobs.
- Relevance failures must narrow evidence and regenerate instead of falling back to generic trading state.
