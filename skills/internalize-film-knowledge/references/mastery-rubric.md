# Mastery Rubric And Writeback Contract

## When to use this rubric

Use this rubric for an explicitly requested mastery check, not ordinary explanation or discussion. Diagnosis stays in the conversation unless the user explicitly asks to save this understanding or test result. An answer alone is not writeback authorization.

## State meaning

| 掌握状态 | Observable evidence |
|---|---|
| 未检验 | The user has not yet explained the concept without relying on the note. Missing mastery fields are interpreted this way. |
| 能复述 | The user can explain the core relationship or mechanism in their own words without changing its meaning. |
| 能辨析 | The user can additionally identify a boundary, counterexample, failure condition, or difference from a nearby concept. |
| 能迁移 | The user can correctly use the concept to analyze or make a decision in an unfamiliar work or new situation. |

Use the latest demonstrated ability, not the historical maximum. The state may rise or fall. Keep previous dated records so the change remains visible.

`能迁移` does not require a real personal project. A novel hypothetical or unfamiliar work is sufficient. Only an observed real project outcome can justify `证据状态: 实践验证`.

## Question ladder

Choose the ladder from the user's demonstrated mastery. A topic's `我的疑问` may be a broad research or application question; preserve it as background rather than automatically using it as the first test of an untested topic. Only the explicitly selected important source's actual pending current question may take precedence. `不适用` lessons do not own separate pending questions. A skip changes neither mastery nor the global task queue.

### 未检验 -> 能复述

Ask for the core causal relationship without looking at the note.

Pattern: `不看笔记，你会怎样用自己的话解释“X 为什么会导致 Y”？`

Pass when the answer preserves the main relationship, even if terminology is informal. Do not require memorized wording.

### 能复述 -> 能辨析

Ask for a boundary, counterexample, failure condition, or distinction.

Pattern: `什么情况下这个方法会失效，或者最容易被误用成什么？`

Pass when the answer gives a relevant condition and explains why it changes the judgment.

### 能辨析 -> 能迁移

Give one unfamiliar work, scene, or hypothetical situation and ask for a concrete decision.

Pattern: `换到这个新情境，你会怎样使用这条知识，第一步看什么，为什么？`

Pass when the user selects relevant information, applies the concept coherently, and avoids a known boundary violation.

## Diagnosis rules

- Ignore wording polish. Judge conceptual relation, boundary awareness, and application quality.
- A partial answer that identifies the right direction but misses a necessary link remains at the highest fully demonstrated level.
- A confident answer that reverses the core causal relationship may fall to a lower state.
- When source evidence is incomplete, contradictory, or too weak to settle the issue, describe the issue as `待核验` in the conversation (save it only with authorization) and avoid grading the disputed part as user error.
- Separate factual correction from taste. Different artistic priorities can both be valid if the tradeoff is understood.
- Never continue to a second question unless the user explicitly asks.

## Property updates

Only after explicit authorization to save an actual test result, topic notes may use:

```yaml
掌握状态: 未检验
最近检验:
```

Allowed mastery values are exactly `未检验`, `能复述`, `能辨析`, and `能迁移`. When saving an actual answer and diagnosis, set `最近检验` to the local date in `YYYY-MM-DD` format. Leave it blank while untested.

For compatible V2/V2.1 topic notes, missing fields are optional compatible extensions and may be added when an actual test result is explicitly authorized for saving. Do not batch-add them. Pre-V2 or contract-incomplete notes require a previewed compatibility upgrade only when necessary for the authorized writeback. Their format never prevents read-only explanation or discussion. Saving a user-owned understanding from ordinary discussion does not itself upgrade mastery.

For an actual test answer explicitly authorized for saving, source notes use:

| Outcome | 理解状态 | 关键问题状态 |
|---|---|---|
| 跳过或未回答 | unchanged | unchanged |
| 有意义但不完整 | 理解中 | 已回答 |
| 已说清核心关系或更高 | 已理解 | 已回答 |

## Concise record

Inside `## 我的理解、疑问与联想`, reuse one `### 内化检验记录` heading. Append entries, never duplicate the heading:

```markdown
### 内化检验记录

#### YYYY-MM-DD｜能辨析

- 问题：一句话保留本轮问题。
- 核心回答：用一到三句提炼用户真正表达的理解。
- 诊断：写清已抓住的关系和仍需修正的边界。
<!-- 如用户明确采用下一步行动，再记录；不是必填项。 -->
```

The record above is an example, not a mandatory four-field format. Preserve readable older records in their existing form; an empty heading or placeholder is not a test record. Structural validation can detect missing records, but cannot prove that an answer happened or that mastery is real.

Merge only a stable, user-owned conclusion explicitly requested for saving into the existing `我的理解` callout or paragraph. Preserve all existing content. Do not insert the assistant's explanation as the user's belief. An incomplete answer does not automatically create a review task; save an action only if the user explicitly adopts it.

If there is no topic note, place the authorized concise record in the source note's existing personal-understanding section. If none exists, add `## 我的理解、疑问与联想` at an appropriate location without requiring a review section. Never create a placeholder topic solely to store an internalization result.
