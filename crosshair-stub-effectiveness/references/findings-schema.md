# Findings JSON Schema (Metric B)

Used by `attribute_findings.py` to merge a hand-curated finding list into `stub-effectiveness.json`.

## Format

A JSON array of objects. Each object must have:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | int or str | yes | Stable identifier — keep consistent across re-runs |
| `file` | str | yes | Source file path relative to project root |
| `function` | str | yes | Function name (with `Class.method` for methods) |
| `category` | enum | yes | One of `real_bug`, `contract_bug`, `precondition_gap`, `stub_gap` |
| `input_source` | enum | yes | One of `primitive`, `stubbed_model`, `stub_gap`, `contract_only` |
| `summary` | str | optional | One-line description (shown in report) |
| `reason` | str | optional | Why this `input_source` was chosen |

## Category meanings

- **`real_bug`** — actual bug in product code. The contract caught it.
- **`contract_bug`** — the bug was in the contract itself (typo, bad keyword, missing close paren).
- **`precondition_gap`** — the contract was too loose; the counterexample was technically valid but unrealistic.
- **`stub_gap`** — the bug was *caused* by an incomplete stub (e.g. HttpRequest fields missing). Not a real product bug.

## Input source meanings

`input_source` answers **"would the smart stubs being absent have prevented CrossHair from reaching this bug?"** — *not* "what type did CrossHair print in the counterexample." This is a reachability question, not a literal-value question.

- **`primitive`** — the function could be symbolically executed *without the smart stubs at all*. Its signature has no stubbed-model parameters, its body never touches `Model.objects.X()` / FK descriptors / M2M managers on the path to the bug, and any model-typed parameters default to None (or similar) on the failing branch. CrossHair generates the triggering value natively (int, str, datetime, None, list, …).

- **`stubbed_model`** — without the smart stubs CrossHair *could not have executed the function past the point where the bug fires*. The function takes a stubbed-model arg, OR its body calls `Model.objects.X(...)`, OR it walks a ForeignKey descriptor, OR it iterates a related manager (`<doc>.tags.all()`, `<doc>.notes_set.all()`), OR it reads a stub-installed attribute. The stubs are the enabler even if the literal value CrossHair generated to *trigger* the failing branch is a primitive str or int. **A pure-primitive-arg signature whose body calls `Model.objects.get(...)` is `stubbed_model`, not `primitive`.**

- **`stub_gap`** — the bug *was* a stub-shaped hole — set on the stub, not on product code.

- **`contract_only`** — the bug never reached symbolic execution because the contract itself failed to parse / type-check.

### Quick decision procedure

Ask in order:

1. Did the contract even parse? If no → `contract_only`.
2. Is the "bug" actually in the stub (Document.pk unconstrained, missing FK, etc.)? If yes → `stub_gap`.
3. Without the smart stubs, would CrossHair raise (e.g. `ImproperlyConfigured: settings.DATABASES`, `RelatedObjectDoesNotExist`, `ValueError: wrong parameter order` from signature intersection) *before* reaching the buggy code path? If yes → `stubbed_model`.
4. Otherwise → `primitive`.

A useful sanity check: if you removed the smart stubs and re-ran CrossHair, would the counterexample still appear? `primitive` says yes, `stubbed_model` says no.

## Examples

```json
[
  {
    "id": 1,
    "category": "real_bug",
    "file": "core/utils.py",
    "function": "duration_string",
    "summary": "duration_string(timedelta(days=-1))",
    "input_source": "primitive",
    "reason": "Argument is a timedelta CrossHair generates natively. Function body has no ORM access — would still reproduce with stubs disabled."
  },
  {
    "id": 4,
    "category": "real_bug",
    "file": "api/serializers.py",
    "function": "CoreModelWithDurationSerializer.validate",
    "summary": "validate(timer=<stubbed Timer>) where .child is None",
    "input_source": "stubbed_model",
    "reason": "Timer instance produced by MockManager. The triggering .child=None path is reachable only because the symbolic Timer mock has a symbolic Optional child."
  },
  {
    "id": 5,
    "category": "real_bug",
    "file": "documents/file_handling.py",
    "function": "generate_filename",
    "summary": "f-string formats doc.pk when doc.pk is None",
    "input_source": "stubbed_model",
    "reason": "Counterexample CrossHair printed shows `archive_filename='\\x00', use_format=''` (primitives), but the function takes a Document arg and reads doc.pk and doc.storage_path.path (FK). Without the smart stubs CrossHair cannot synthesize the Document parameter at all — signature intersection raises before the body runs. The stubs are the enabler; the primitives just steer which branch fires."
  }
]
```

The third example is the common gotcha: a counterexample whose printed values are all primitives can *still* be `stubbed_model`-attributable if the function's signature or body requires the stubs to be reachable in the first place.

## Computed metrics

After ingesting, the summary block gains:

- `real_bugs_count`
- `real_bugs_from_stubbed_models`
- `real_bugs_from_primitives`
- `real_bugs_smart_stub_attribution_ratio` = `stubbed / (stubbed + primitive)` over real_bugs
- `attributable_findings_count` (across all categories where `input_source` ∈ {`primitive`, `stubbed_model`})
- `all_findings_smart_stub_attribution_ratio` = same ratio but over all attributable findings
