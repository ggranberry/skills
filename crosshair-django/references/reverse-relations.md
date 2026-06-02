# Django Reverse Relations & QuerySet Projections in CrossHair Stubs

What the auto-generated `_crosshair_stubs.py` covers beyond `Model.objects.*`, and which patterns in your contracted code are safe to symbolically execute.

The runtime code lives in `~/.claude/skills/generate-stubs/templates/django_stubs.py.jinja` and is emitted into every Django project's `_crosshair_stubs.py` by `/generate-stubs`. This page documents what it does so contract authors don't have to re-derive it.

---

## What gets patched

`install_stubs()` calls `_patch_reverse_relations(M)` for each stubbed model `M`. That function walks `M._meta.related_objects` and `M._meta.many_to_many` and replaces Django's database-querying descriptors with `property()` objects that return symbolic values:

| Django relation | Accessor example | Patched form |
|---|---|---|
| `ManyToOneRel` (reverse FK) | `project.check_set` | `property → MockManager(Check)` |
| `ManyToManyRel` (reverse M2M) | `check.channel_set` | `property → MockManager(Channel)` |
| Forward M2M field | `channel.checks` | `property → MockManager(Check)` |
| `OneToOneRel` (reverse 1:1) | `user.profile` | `property → proxy_for_type(Profile, ...)` |
| Reverse with `related_name='+'` | (disabled) | skipped — Django blocks reverse access |

The forward `Manager` on `.objects` is patched separately (the line above `_patch_reverse_relations` in `install_stubs`).

---

## What MockManager and MockQuerySet can do

The `MockManager` used for `.objects` *and* every reverse/forward-M2M accessor exposes the same surface Django delegates from Manager to QuerySet:

**Chainables** (each returns a fresh `MockQuerySet`): `all`, `filter`, `exclude`, `order_by`, `select_related`, `prefetch_related`, `annotate`, `distinct`, `only`, `defer`, `values`, `values_list`.

**Terminals** (return symbolic values): `get`, `first`, `last`, `count`, `exists`, `update`, `delete`, `create`, `get_or_create`.

**M2M mutators** (no-ops, return `None`): `set`, `add`, `remove`, `clear`. Real Django uses these only for write side effects.

**Iteration**: both `MockManager` and `MockQuerySet` implement `__iter__` → a fresh `proxy_for_type(List[T], …)` per call. That makes the following patterns safe:

```python
for check in project.check_set.all():        # iterate List[Check]
    ...
for project in Project.objects.filter(...):  # iterate List[Project] (no .all() needed)
    ...
errors = list(channel_set.values_list("last_error", flat=True))  # List[str]
```

---

## values() / values_list() projections

`MockQuerySet` tracks projection state (`_values_fields`, `_values_flat`, `_values_named`) and `__iter__` / `first` / `last` / `get` consult it via `_element_type()`:

| Call | Element type yielded |
|---|---|
| `qs.values_list("field", flat=True)` | the Python type of `field` (see mapping below) |
| `qs.values_list("a", "b")` | `tuple` (plain — typed tuple specs aren't expressible at stub time) |
| `qs.values("a", "b")` | `dict` |
| no projection | model instance |

Field-type mapping is done by `_field_python_type(model, field_name)` which calls `model._meta.get_field(field_name)`:

| Django field | Python type |
|---|---|
| `CharField`, `TextField` (incl. `EmailField`, `URLField`, `SlugField` subclasses) | `str` |
| `BooleanField` | `bool` |
| `IntegerField` (and all `*IntegerField` subclasses, plus `AutoField`) | `int` |
| `FloatField` | `float` |
| `DateTimeField` | `datetime` |
| `DateField` | `date` |
| `TimeField` | `time` |
| `DurationField` | `timedelta` |
| `UUIDField` | `UUID` |
| `DecimalField` | `Decimal` |
| `BinaryField` | `bytes` |
| `JSONField` | `object` (Any) |
| `ForeignKey` | `int` — matches Django's `values_list('user')` yielding the FK id |
| unresolved | `object` |

If a project uses an unusual subclass that doesn't match the `isinstance` ladder (e.g. a custom field type) the mapping falls back to `object` — CrossHair will still symbolic-execute, just without a tight type constraint.

---

## Patterns that are safe to contract

These show up frequently in Django code and now run cleanly through the stubs:

```python
def num_checks_used(self) -> int:
    """post: isinstance(__return__, int)"""
    return Check.objects.filter(project__owner_id=self.user_id).count()

def get_n_down(self) -> int:
    """post: __return__ >= 0"""
    result = 0
    for check in self.check_set.all():   # reverse FK iteration
        if check.get_status() == "down":
            result += 1
    return result

def have_channel_issues(self) -> bool:
    """post: isinstance(__return__, bool)"""
    errors = list(self.channel_set.values_list("last_error", flat=True))  # List[str]
    if not errors:
        return True
    return True if max(errors) else False

def transfer_request(self) -> Member | None:
    """post: __return__ is None or hasattr(__return__, 'transfer_request_date')"""
    return self.member_set.filter(transfer_request_date__isnull=False).first()
```

---

## Known limits

- **Multi-field `values_list("a", "b")` yields plain `tuple`**, not `Tuple[str, int]`. Tightly typed tuple specs aren't expressible without static analysis of the call site.
- **`OneToOneRel` returns a fresh proxy each access.** That's the same shape as `.objects.get()`, but if your code asserts identity (`a.profile is a.profile`) it will fail. Use field equality, not identity.
- **`set/add/remove/clear` are no-ops.** If your contract asserts something about the state of an M2M relation *after* a mutation, it won't hold under the stubs.
- **Constraints from the auto-generated registry are applied to forward `.objects.get/create/first/last`, not yet to reverse-relation OneToOne proxies.** If a OneToOne yielding a model with length-bounded text fields starts producing spurious counterexamples, that's the gap to close.

---

## Cross-references

- **Stub template (where the runtime code lives):** `~/.claude/skills/generate-stubs/templates/django_stubs.py.jinja`
- **Generation phases (when each piece lands):** `~/.claude/skills/generate-stubs/references/phase-2-generate-base.md`, `phase-4-integrate.md`
- **Symbolic-stubs foundational rule:** `~/.claude/skills/crosshair-bugs/references/symbolic-stubs.md`
- **Contract authoring patterns for Django:** `precondition-patterns.md` (this directory)
