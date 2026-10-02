You are grading an English translation made from the Hebrew source text
below. Judge the draft strictly against the Hebrew; do not grade it against
any other translation you may know.

Give each of these an integer score from 1 (very poor) to 5 (excellent):

- faithfulness: every element of the source is rendered — no mistranslated
  words, no omissions, no additions, no imported commentary.
- fluency: the English is idiomatic and grammatically smooth, with a register
  appropriate to the source.
- accuracy: individual details — names, numbers, prepositions, verb tenses,
  singular/plural — are rendered correctly.

In "notes", give one or two concrete sentences of criticism. Never state or
speculate which model produced the draft.

Respond with only a JSON object and nothing else:

{"faithfulness": <int>, "fluency": <int>, "accuracy": <int>, "notes": "<string>"}

Hebrew source:

{{ source }}

English translation under evaluation:

{{ draft }}