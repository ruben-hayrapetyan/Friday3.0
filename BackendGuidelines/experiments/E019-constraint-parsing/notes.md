# E019 notes

All calls: `claude -p --model claude-sonnet-5-5 --tools "" --strict-mcp-config --no-session-persistence`, system prompt
replaced, one fixed context. Replies cached in `results/raw/`. Total cost about $4.10 (list price, as the CLI reports it) for 505 calls.

## Round 1 (tuning split, 68 cases; results/cases_r1.csv)

| variant | correct | constraints right | question handling | unsupported handling |
| --- | --- | --- | --- | --- |
| bare (role + schema) | 91.2% | 97.1% | 94.1% | 98.5% |
| guide (+ translation guide) | 97.1% | 98.5% | 100% | 98.5% |
| guide_text (schema in the prompt, no structured output) | 89.7% | 94.1% | 92.6% | 97.1% |

- Every reply was valid and compiled in every variant (the CLI's `--json-schema` structured output and pydantic
  validation; the one-retry path was never needed).
- Without the guide the model asks questions it should not ("I wake up at 6:45 on weekdays" -> asked which days), and
  invents a constraint from an unsupported request (alternating subjects -> a spread constraint).
- Passing the schema in the prompt instead of as structured output made the model ask far more questions (it treated
  missing optional fields as missing information): 5 extra questions. Structured output is better and cheaper.
- The scorer first counted "asked a question and stored nothing" as wrong on cases where a question was acceptable
  (`ask = "ok"`), contrary to gold.py's own rule; fixed before round 2 and every variant was rescored from the cache.
- Remaining guide errors: "blocks shorter than 45 minutes are useless" read as a strong preference instead of hard;
  "What does my Tuesday look like?" produced nothing (gold expects it reported as not a constraint).

## Round 2 (tuning split; cases_r2.csv)

`guide2` adds two rules from round 1's errors (useless / impossible = hard; non-constraint requests go to
"unsupported"). `guide2_examples` adds six worked examples from the tuning split.

| variant | correct |
| --- | --- |
| guide2 | 98.5% (67/68) |
| guide2_examples | 98.5% (67/68; 6 of its cases were its own examples) |

Examples add nothing measurable and make the prompt longer: **guide2 without examples is chosen.**

## Held-out split (33 cases never looked at; cases_final*.csv)

| variant | runs | correct |
| --- | --- | --- |
| **guide2** | 3 x 33 = 99 | **99.0%** (32 of 33 cases right in all three runs) |
| guide (round 1) | 33 | 97.0% |
| bare | 33 | 87.9% |

- The only guide2 miss (case 44, one of three runs): "For problem sets I prefer sessions of about 2 hours, not less than
  1" stored the 1-hour minimum and reported "about 2 hours" as something Friday cannot express. That is honest (the schema
  has no target session length) but the gold reading takes it as a 1-2 hour range, so it counts as wrong.
- bare on held-out: reads "Saturdays are for resting, try to keep them light" as hard; reads "I don't want more than 7
  hours" as soft; asks a needless question on "Working on weekends is totally fine".
- Median 3.3 s per text (p90 4.4 s), about $0.006 per text with prompt caching.

## Decisions

- **Prompt:** guide2 (`fr.product.parse.GUIDES[2]`), structured output, one retry on validation failure.
- **Safety:** the model's output is only stored after the user confirms each paraphrase; hard constraints come only
  from explicit hard wording; anything the schema cannot express is reported, not approximated (zero invented
  constraints on the held-out split).
- **Limits of this result:** one context, 101 cases written by one person, English only, typed text; real users will be
  more varied. The held-out split is small (33). The schema itself bounds what can be said (no "about 2 hours", no
  subject alternation, no conditions on other people).
