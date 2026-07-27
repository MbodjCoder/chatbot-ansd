"""
Test d'integration du client LLM de production (OpenAICompatClient).

Demontre que la voie API reelle fonctionne SANS dependre d'une cle ni du
reseau : un serveur local minimal implemente le contrat OpenAI
(/chat/completions, reponses completes ET flux SSE) et le client du systeme
est exerce contre lui. C'est le meme contrat que DeepSeek, OpenAI, Groq,
Mistral, OpenRouter et Ollama : si ce test passe, brancher une cle reelle
revient a changer deux variables d'environnement.

Verifie : completion, streaming SSE, nouvelles tentatives sur erreur 500.
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.client import FallbackLLM, OpenAICompatClient

PORT = 8765
FAIL_ONCE = {"n": 0}   # pour le test de retry


class FakeOpenAI(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencieux
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        # scenario retry : premiere requete du modele "flaky" echoue en 500
        if body["model"] == "flaky" and FAIL_ONCE["n"] == 0:
            FAIL_ONCE["n"] += 1
            self.send_response(500)
            self.end_headers()
            return
        content = f"echo:{body['messages'][-1]['content']}"
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for i in range(0, len(content), 5):
                chunk = {"choices": [{"delta": {"content": content[i:i+5]}}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            payload = {"model": body["model"], "usage": {"total_tokens": 42},
                       "choices": [{"message": {"content": content}}]}
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)


def test_completion():
    c = OpenAICompatClient(f"http://localhost:{PORT}", "cle-test", "test-model")
    r = c.complete("systeme", "bonjour", temperature=0.0)
    assert r.text == "echo:bonjour"
    assert r.usage["total_tokens"] == 42


def test_streaming():
    c = OpenAICompatClient(f"http://localhost:{PORT}", "cle-test", "test-model")
    morceaux = list(c.complete_stream("systeme", "flux sse"))
    assert "".join(morceaux) == "echo:flux sse"
    assert len(morceaux) > 1   # vrai decoupage en fragments


def test_retry_sur_erreur_500():
    FAIL_ONCE["n"] = 0
    c = OpenAICompatClient(f"http://localhost:{PORT}", "cle-test", "flaky",
                           max_retries=2)
    r = c.complete("systeme", "resilience")
    assert r.text == "echo:resilience"   # a reussi a la 2e tentative
    assert FAIL_ONCE["n"] == 1


def test_semaphore_concurrence_bornee():
    # S5 : le nb d'appels distants simultanes est borne par le semaphore ;
    # au-dela, l'exces attend (pas de tempete de requetes vers l'API).
    c = OpenAICompatClient(f"http://localhost:{PORT}", "cle", "test-model",
                           max_concurrency=2)
    # le faux serveur repond vite ; on verifie surtout l'absence d'erreur
    # et que le semaphore est bien relache (sinon un 3e appel bloquerait)
    for _ in range(6):
        assert c.complete("s", "ping").text == "echo:ping"
    # apres 6 appels sequentiels, 2 slots doivent etre libres
    assert c._sem.acquire(timeout=1) and c._sem.acquire(timeout=1)
    c._sem.release(); c._sem.release()


def test_reseau_faible_repli_rapide():
    # S3 : API injoignable + timeout court -> FallbackLLM bascule vite sur le
    # moteur local, pas de longue attente.
    import time as _t
    mort = OpenAICompatClient("http://localhost:59998", "cle", "modele",
                              timeout=2, max_retries=1)
    f = FallbackLLM(mort)
    t0 = _t.time()
    r = f.complete("GROUNDED_ANSWER", "<contexte>Le RGPH-5 est le recensement "
                   "de 2023.</contexte><question>RGPH-5 ?</question>")
    assert r.text and _t.time() - t0 < 12   # repli sans attente excessive


def test_fallback_si_api_morte():
    # API injoignable (mauvais port) : FallbackLLM ne leve JAMAIS, il
    # bascule sur le moteur local — le service reste disponible (regression
    # du plantage 402 Payment Required observe avec un compte sans credit)
    mort = OpenAICompatClient("http://localhost:59999", "cle", "modele",
                              timeout=2, max_retries=0)
    f = FallbackLLM(mort)
    r = f.complete("GROUNDED_ANSWER", "<contexte>Le RGPH-5 est le recensement "
                   "de 2023 au Senegal.</contexte><question>RGPH-5 ?</question>")
    assert r.text and f.last_error is not None
    morceaux = list(f.complete_stream("GROUNDED_ANSWER",
                    "<contexte>Le RGPH-5 est le recensement de 2023 au "
                    "Senegal.</contexte><question>RGPH-5 ?</question>"))
    assert "".join(morceaux)


if __name__ == "__main__":
    srv = HTTPServer(("localhost", PORT), FakeOpenAI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    fails = 0
    for name, fn in sorted({k: v for k, v in globals().items()
                            if k.startswith("test_")}.items()):
        try:
            fn()
            print(f"  [OK ] {name}")
        except Exception as e:
            fails += 1
            print(f"  [ECH] {name} : {e}")
    srv.shutdown()
    print(f"\n{'CLIENT LLM PRODUCTION VALIDE' if not fails else str(fails)+' echec(s)'}")
    sys.exit(1 if fails else 0)
