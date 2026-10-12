"""ProofDesk: ask questions about your documents and check every answer against its source."""
from __future__ import annotations

from .answer import Answer, answer
from .corpus import CorpusError, Document, Passage, chunk, load_folder, make_document
from .models import AnthropicModel, MockModel, ModelError, get_model
from .retrieve import Index

__version__ = "0.1.0"
__all__ = ["Answer", "answer", "AnthropicModel", "MockModel", "ModelError", "get_model", "Index", "Document",
           "Passage", "chunk", "load_folder", "make_document", "CorpusError", "__version__"]
