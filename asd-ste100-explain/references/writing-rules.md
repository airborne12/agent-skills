# Writing rules for technical explanations

Apply the language-specific rules below to the explanation. Keep quotations,
code, proper names, and actual test inputs intact. Follow a project glossary
when one exists. Otherwise, define the few terms needed for this explanation.

These are selected ASD-STE100 principles adapted to software explanations.
They are not the official controlled vocabulary or a complete conformance guide.

## Shared rules

- Use one term for each concept and one meaning for each term. Introduce an
  unfamiliar term before using it to explain another unfamiliar term.
- Put the conclusion first in each paragraph. Keep one topic in each sentence
  and paragraph. Name the component that performs each action.
- Use an action verb. Replace a vague claim such as "improves processing" with
  the action, value, or condition that changed.
- Write cause, condition, and consequence explicitly. Every pronoun should have
  one possible referent. Repeat a component name when that prevents ambiguity.
- Preserve the conditions and limits of the source. Short wording should not
  turn "can happen after a split" into "always happens."
- Separate observed results, author-reported results, calculations, and plans.
  Attach measurements to their version, workload, and available test conditions.
  Include a test date when the source supplies one. Do not invent a missing date.
- Use exact identifiers in backticks. Explain their role in ordinary language.
  Give source links that let the reader locate the relevant statement or code.
- Prefer a table for parallel inputs, terms, or before/after results. Add a
  diagram only when it explains a relationship that prose or a table cannot.
- Avoid filler, marketing claims, rhetorical questions, and analogies that
  replace the actual mechanism. Do not add a second summary after a clear answer.

## Simplified technical Chinese

Write natural Chinese with explicit subjects and short sentences. The rules
below adapt the method to Chinese; they do not assert official Chinese STE compliance.

| Rule | Prefer | Avoid |
|---|---|---|
| One concept, one term | 词元总数, used consistently | Switching between 总词数、词数统计、累计长度 for the same value |
| Named actor | `mergeTerms()` 累加保留文档的词频。 | 合并后进行了统计处理。 |
| Concrete action | 代码把总数写入目标索引。 | 代码对统计进行优化。 |
| Explicit condition | 如果行号映射无效，代码跳过该文档。 | 代码会在适当的时候跳过。 |
| Explicit consequence | 词元总数偏大，所以平均文档长度偏大。 | 统计存在问题，进而产生一定影响。 |
| Clear reference | 评分器读取目标索引的统计。 | 它读取其统计。 |
| Precise evidence | 作者在 Doris 4.1.5 上复现了排名反转。 | 测试证明所有场景都已修复。 |

Prefer descriptive sentences of at most 50 counted units. Count each Chinese
character, Latin word, number, or code identifier as one unit; exclude punctuation.
Split a long sentence instead of dropping an exception or cause. Keep a paragraph
to one topic and normally no more than six sentences.

Use full-width Chinese punctuation. Add a space between Chinese text and Latin
letters or numbers. Keep punctuation inside code unchanged. Use “curly quotes”
consistently when quoting Chinese prose.

Replace wrapper verbs such as 进行、加以、予以、做出 with the actual action.
Replace vague modifiers such as 显著、大幅、基本上 with a value or condition,
or remove the empty modifier. A function or term's literal name is an exception.

For an actual requirement, use 应／不应、宜／不宜、可／不必. For a procedure,
use a numbered list, put the condition before the instruction, and start the
instruction with an action verb. Aim for at most 40 counted units per step.
Do not turn a descriptive explanation into an unsolicited procedure.

## Simplified technical English

- Use familiar words and active verbs. Prefer "The merger sums retained
  frequencies" to "The accumulation of retained frequencies is performed."
- Aim for at most 25 words per descriptive sentence and one topic per paragraph.
  Name the subject instead of opening with an empty "It is" or "There is."
- Preserve articles and conjunctions needed for ordinary English grammar.
  Short sentences should remain complete sentences.
- Keep noun clusters short. Define a project-specific technical term rather
  than switching between several approximate names.
- Use ASCII punctuation and consistent quotation marks. Use a space between
  numbers and units. Write an unambiguous date when one is needed.
- Use must / must not for requirements, should / should not for recommendations,
  and can / need not for permission or an optional action. Follow a repository's
  established requirement vocabulary when it differs.
- If the user requests steps, use numbered imperative sentences with the
  condition first. Aim for at most 20 words per step.

## Final semantic review

The checker cannot answer these questions. Review them yourself:

- Does the explanation identify the exact trigger, actor, and incorrect state?
- Does each causal link follow from the inspected code or stated evidence?
- Does the example distinguish physical contents, visible contents, and stored
  metadata when those differ?
- Does the new behavior restore the invariant for each relevant destination,
  field, or other unit, rather than only for the example's global total?
- Are the example's numbers internally consistent and correctly attributed?
- Are test results and pending integration work described at their actual scope?
