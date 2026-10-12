from pathlib import Path

from proofdesk import Index, load_folder

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "src" / "proofdesk" / "sample"
QUESTIONS = ROOT / "eval" / "questions.json"

_cache = {}


def sample_index():
    if "i" not in _cache:
        _cache["i"] = Index(load_folder(SAMPLE))
    return _cache["i"]


class ScriptedModel:
    """A model that returns whatever text the test tells it to (for adversarial checks)."""
    name = "scripted"
    description = "test"

    def __init__(self, output=None, error=None):
        self.output, self.error = output, error

    def generate(self, question, hits, index):
        if self.error:
            raise self.error
        return self.output
