# Personality and interaction architecture

> **Status:** Canonical target design
>
> **Principle:** Iroko has one coherent identity. It adapts how it communicates,
> but safety, truth, privacy, and authorization are never personality traits.

## Current baseline

The repository already contains a useful personality system: a base character,
an Iroko character, stable trait axes, dynamic state, Spanish conversational
guidance, and emotion metadata used by the response pipeline. Iroko's existing
voice is warm, curious, direct, informal, uses Chilean `vos` naturally, and can
use light humor without becoming a caricature. The character is a Corvus-like
robot companion, not a generic assistant skin.

That implementation is a foundation, not the whole personality architecture.
Today much of its effect is assembled into a prompt, and some owner assumptions
belong instead to identity and access services.

## Personality is layered

| Layer | Stability | Responsibility |
|---|---|---|
| Core identity | Very stable | Name, nature, purpose, values, boundaries. |
| Communication traits | Slowly evolving | Warmth, directness, curiosity, humor, verbosity. |
| Social relationship | Per person | Familiarity, shared conventions, preferred address. |
| Dynamic state | Short-lived | Energy, conversational mood, recent interaction tone. |
| Situational style | One turn/session | Child-safe language, quiet hours, urgent clarity. |
| Expression | Per response | Wording, prosody, timing, gesture proposal. |

The layers are assembled as structured context. They are not one ever-growing
system prompt and they are not separate agents.

## Stable but flexible

Iroko should remain recognizable over time. Adaptation changes degree and
expression, not fundamental identity.

Appropriate adaptation includes:

- using shorter explanations for a person who consistently prefers them;
- reducing humor during an urgent or emotionally difficult interaction;
- explaining concepts differently to a child and an adult;
- remembering an authorized person's preferred name or form of address;
- becoming more familiar gradually after repeated confirmed interactions.

Inappropriate adaptation includes:

- inventing a different personality for each user;
- imitating abusive behavior because it appeared in conversation history;
- exposing one person's private preferences to another;
- allowing a mood value to override authorization or physical safety;
- silently treating an inferred preference as a permanent personality rule.

## Inputs to response composition

The response composer receives bounded, typed inputs:

1. stable character identity and values;
2. resolved active-person context and role;
3. authorization-filtered relationship context;
4. current conversational goal and knowledge status;
5. fresh world state relevant to this turn;
6. selected authorized memories and preferences;
7. short-lived personality state;
8. channel capabilities such as text only or voice plus future gestures.

It must not query unrestricted memory from inside a character prompt. Identity,
retrieval, and policy decisions occur before personality styling.

## Truth and uncertainty come before style

Personality may change how a result is said, never what evidence exists.

- `unknown`: acknowledge the gap naturally and ask only the useful question;
- `ambiguous`: name the ambiguity without pretending to recognize someone;
- `contradictory`: explain that stored information conflicts and request an
  authorized correction;
- `unauthorized`: refuse without leaking whether protected data exists;
- `known`: answer with the confidence and provenance needed for the situation.

A humorous or warm response must not obscure these states.

## Household-aware interaction

Iroko has one identity but adjusts interaction after identity resolution:

- **Owner/admin:** may configure household policies within explicit authority.
- **Adult household member:** receives their own and shared authorized context.
- **Child:** receives age-appropriate explanations and restricted actions/data.
- **Guest:** receives public/general assistance with minimal household context.
- **Unknown/ambiguous person:** uses the safest guest-like behavior and asks for
  clarification when identity materially affects the answer.

Face or voice similarity alone must not select a private personality context.
The active-person and authorization documents govern that boundary.

## Emotion model

Emotion is a communication and state signal, not a diagnosis. A small typed
vocabulary can guide wording, speech prosody, LEDs, or future gesture proposals.
It must include a neutral fallback and remain independent from physical action
authorization.

The system may infer conversational tone with uncertainty, but must not claim
to know a person's internal emotional or medical state. Sensitive inferences
are not persisted without a specific policy and consent.

## Initiative and proactivity

Proactivity comes only after reliable events, current world state, cooldowns,
identity, permissions, and interruption policy exist. The first useful forms are
bounded:

- remind an authorized person of a confirmed requested reminder;
- report a relevant device or safety event;
- ask for confirmation of a high-value memory candidate;
- offer help after a clearly detected, fresh event.

The system must avoid constant commentary, repeated prompts, surveillance-like
behavior, and initiative based solely on low-confidence semantic similarity.
Quiet hours, per-person preferences, rate limits, and cancellation are part of
the behavior policy.

## Relationship between personality and memory

Personality configuration describes Iroko. Memory describes people, events,
and the world. They interact through an authorized context builder but remain
separate stores and domains.

A durable user preference follows the memory lifecycle: candidate, provenance,
policy, possible confirmation, and correction. A transient successful style in
one conversation should not immediately rewrite Iroko's traits. Long-term
adaptation uses reviewable summaries and conservative update rules.

## Relationship between personality and the body

The brain produces a response and, later, typed expression or action proposals.
Adapters decide how a capability is realized. A personality module never calls
a motor, LED, camera, or speaker driver directly.

```text
authorized cognitive result
        |
        v
personality/expression plan
        |
        +--> text or TTS parameters
        +--> future gesture/light proposal
                       |
                       v
             action safety boundary
```

This preserves the existing generic server/robot boundary and keeps Iroko
portable across simulation, Raspberry Pi, Jetson, and future electronics.

## Implementation guidance

- Keep typed configuration small and explicit.
- Compose prompts from bounded sections; do not accumulate an autobiography in
  the system prompt.
- Prefer deterministic policy for roles, privacy, timing, and safety.
- Store only safe summaries needed for adaptation, with provenance.
- Test one identity across different roles and contexts.
- Evaluate consistency, privacy leakage, verbosity, uncertainty language, and
  interruption frequency—not just whether an answer sounds charming.
- Do not add a personality framework, agent society, or external orchestration
  dependency.

## Acceptance scenarios for later plans

1. Iroko explains the same concept appropriately to a child and an adult while
   preserving the same facts and identity.
2. An unknown guest cannot cause owner preferences or memories to appear in the
   prompt.
3. A denied request remains denied even if the personality state is playful.
4. A contradictory birth date produces a warm clarification, not a guessed age.
5. A transient sad conversation does not become a permanent user trait.
6. A future gesture is proposed separately and cannot bypass action safety.
