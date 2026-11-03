"""Fixtures partagées des tests."""
import os

# Mode démo forcé avant tout import de l'application : la configuration
# (pydantic-settings) est lue une seule fois, au premier import ; si .env
# active la production, les tests déterministes appelleraient le vrai LLM.
os.environ["ANSD_MODE"] = "demo"

import pytest  # noqa: E402

from app.core.chatbot import ANSDChatbot  # noqa: E402


@pytest.fixture(scope="session")
def chatbot():
    """Une instance de chatbot réutilisée par la session (l'initialisation —
    ingestion RAG, routeur — est coûteuse). Les voies testées ici (GEO, SQL)
    sont déterministes et n'appellent pas le LLM."""
    return ANSDChatbot()
