"""A stand-in for the OpenAI client so tests never touch the network."""

from types import SimpleNamespace


class FakeOpenAI:
    """Scripted replies: each item is reply text (str) or an exception to raise."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = []  # the kwargs of each request
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._script:
            raise AssertionError("FakeOpenAI script exhausted: unexpected extra request")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=item))])
