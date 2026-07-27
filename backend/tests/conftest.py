"""Fixtures partagées des tests."""
import pytest

from app.core.chatbot import ANSDChatbot


@pytest.fixture(scope="session")
def chatbot():
    """Une instance de chatbot réutilisée par la session (l'initialisation —
    ingestion RAG, routeur — est coûteuse). Les voies testées ici (GEO, SQL)
    sont déterministes et n'appellent pas le LLM."""
    return ANSDChatbot()
