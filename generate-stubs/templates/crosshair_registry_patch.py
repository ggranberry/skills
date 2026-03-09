"""
Minimal Django registry stubs for CrossHair.

No Django imports — safe to import before the registry is set up.
Imported by crosshair_django_setup.py (--extra_plugin) to patch the
Django app registry with lightweight stubs that let model files import
without calling django.setup().
"""


class _RegistryStubQuerySet:
    """Minimal QuerySet stand-in that supports method chaining."""
    def __getattr__(self, name):
        return lambda *a, **kw: self

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False


_registry_stub_qs = _RegistryStubQuerySet()


class _RegistryStubManager:
    """Minimal Manager stand-in that returns a stub QuerySet for any call."""
    def all(self):
        return _registry_stub_qs

    def filter(self, *args, **kwargs):
        return _registry_stub_qs

    def __getattr__(self, name):
        return lambda *a, **kw: _registry_stub_qs


class _RegistryStubModelsDict(dict):
    """A dict that creates stub model classes on-demand for any missing key."""
    def __init__(self, app_label):
        super().__init__()
        self._app_label = app_label

    def __missing__(self, key):
        model_name = key.capitalize()
        stub = type(model_name, (), {
            "_meta": type("Options", (), {
                "app_label": self._app_label,
                "model_name": key,
                "object_name": model_name,
            })(),
            "objects": _RegistryStubManager(),
        })
        self[key] = stub
        return stub


class _RegistryStubAppConfig:
    """Minimal AppConfig stand-in for apps not in app_configs."""
    def __init__(self, label, name=None):
        self.label = label
        self.name = name or label
        self.models = None  # matches real AppConfig before import_models()
        self._stub_models = _RegistryStubModelsDict(label)

    def import_models(self):
        # Mirror real AppConfig.import_models(): take a live reference to the
        # all_models[label] dict. register_model() populates it as models are
        # imported, so this reference sees real model classes as they appear.
        from django.apps import apps as _apps
        self.models = _apps.all_models[self.label]

    def get_model(self, model_name, require_ready=False):
        if self.models is None:
            self.import_models()
        # Fall back to stub class if model not yet registered
        return self.models.get(model_name.lower()) or self._stub_models[model_name.lower()]
