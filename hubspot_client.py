"""
hubspot_client.py — Comunicação com a API REST da HubSpot.

Responsabilidades:
    • Puxar contatos e deals via API
    • Criar contatos novos
    • Cachear respostas com diskcache (TTL configurável)

Endpoints usados:
    GET  /crm/v3/objects/contacts   — lista contatos
    GET  /crm/v3/objects/deals      — lista deals
    POST /crm/v3/objects/contacts   — cria contato

Não usa SDK da HubSpot — apenas httpx direto, mais transparente e mais fácil
de entender para quem está aprendendo a integração.
"""

import hashlib
import logging
import os
from datetime import datetime

import diskcache
import httpx
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# ── Configuração ───────────────────────────────────────────────────────────────
HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")
BASE_URL      = "https://api.hubapi.com"
TTL_SEGUNDOS  = 5 * 60   # cache de 5 minutos

_cache = diskcache.Cache(".cache_hubspot")

HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type":  "application/json",
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════════════════════

def _cache_key(sufixo: str) -> str:
    return hashlib.sha256(sufixo.encode()).hexdigest()


def _get(endpoint: str, params: dict | None = None) -> dict:
    """Faz GET autenticado e lança exceção clara em caso de erro."""
    url = f"{BASE_URL}{endpoint}"
    try:
        resp = httpx.get(url, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        log.error(f"HubSpot API erro {e.response.status_code}: {e.response.text}")
        raise
    except httpx.RequestError as e:
        log.error(f"Erro de rede ao chamar HubSpot: {e}")
        raise


def _post(endpoint: str, payload: dict) -> dict:
    """Faz POST autenticado."""
    url = f"{BASE_URL}{endpoint}"
    try:
        resp = httpx.post(url, headers=HEADERS, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        log.error(f"HubSpot API erro {e.response.status_code}: {e.response.text}")
        raise


# ══════════════════════════════════════════════════════════════════════════════
# CONTATOS
# ══════════════════════════════════════════════════════════════════════════════

def get_contacts(limit: int = 100, force_refresh: bool = False) -> list[dict]:
    """
    Retorna lista de contatos da HubSpot.

    Campos retornados por contato:
        id, firstname, lastname, email, phone, createdate, hs_lead_status

    Usa cache de 5 minutos. Passe force_refresh=True para ignorar o cache.
    """
    key = _cache_key(f"contacts_{limit}")

    if not force_refresh:
        cached = _cache.get(key)
        if cached is not None:
            log.info(f"Cache HIT — contatos ({len(cached)} registros)")
            return cached

    log.info("Buscando contatos na HubSpot API...")

    data = _get(
        "/crm/v3/objects/contacts",
        params={
            "limit": limit,
            "properties": "firstname,lastname,email,phone,createdate,hs_lead_status",
        },
    )

    contatos = []
    for item in data.get("results", []):
        props = item.get("properties", {})
        contatos.append({
            "id":           item["id"],
            "nome":         f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
            "email":        props.get("email", ""),
            "telefone":     props.get("phone", ""),
            "status_lead":  props.get("hs_lead_status", ""),
            "criado_em":    props.get("createdate", ""),
        })

    _cache.set(key, contatos, expire=TTL_SEGUNDOS)
    log.info(f"Contatos carregados: {len(contatos)} registros — cache atualizado.")
    return contatos


# ══════════════════════════════════════════════════════════════════════════════
# DEALS
# ══════════════════════════════════════════════════════════════════════════════

def get_deals(limit: int = 100, force_refresh: bool = False) -> list[dict]:
    """
    Retorna lista de deals (oportunidades de venda) da HubSpot.

    Campos retornados por deal:
        id, dealname, amount, dealstage, closedate, createdate, pipeline

    Usa cache de 5 minutos.
    """
    key = _cache_key(f"deals_{limit}")

    if not force_refresh:
        cached = _cache.get(key)
        if cached is not None:
            log.info(f"Cache HIT — deals ({len(cached)} registros)")
            return cached

    log.info("Buscando deals na HubSpot API...")

    data = _get(
        "/crm/v3/objects/deals",
        params={
            "limit": limit,
            "properties": "dealname,amount,dealstage,closedate,createdate,pipeline",
        },
    )

    deals = []
    for item in data.get("results", []):
        props = item.get("properties", {})

        # Converte amount para float com segurança
        try:
            valor = float(props.get("amount") or 0)
        except (ValueError, TypeError):
            valor = 0.0

        deals.append({
            "id":         item["id"],
            "nome":       props.get("dealname", ""),
            "valor":      valor,
            "estagio":    props.get("dealstage", ""),
            "pipeline":   props.get("pipeline", ""),
            "data_close": props.get("closedate", ""),
            "criado_em":  props.get("createdate", ""),
        })

    _cache.set(key, deals, expire=TTL_SEGUNDOS)
    log.info(f"Deals carregados: {len(deals)} registros — cache atualizado.")
    return deals


# ══════════════════════════════════════════════════════════════════════════════
# CRIAR CONTATO
# ══════════════════════════════════════════════════════════════════════════════

def create_contact(
    nome: str,
    email: str,
    telefone: str = "",
    resumo_conversa: str = "",
) -> dict:
    """
    Cria um novo contato na HubSpot a partir dos dados extraídos pelo chat.

    Salva o resumo da conversa no campo 'hs_content_membership_notes' (notas).
    Invalida o cache de contatos após criar.

    Retorna o contato criado (com id gerado pela HubSpot).
    """
    # Separa nome em primeiro e último
    partes = nome.strip().split(" ", 1)
    firstname = partes[0]
    lastname  = partes[1] if len(partes) > 1 else ""

    payload = {
        "properties": {
            "firstname":  firstname,
            "lastname":   lastname,
            "email":      email,
            "phone":      telefone,
            "hs_lead_status": "NEW",
            # Notas visíveis no card do contato
            "hs_content_membership_notes": (
                f"[Chat IA — {datetime.now().strftime('%d/%m/%Y %H:%M')}]\n{resumo_conversa}"
                if resumo_conversa else ""
            ),
        }
    }

    log.info(f"Criando contato: {nome} <{email}>")
    resultado = _post("/crm/v3/objects/contacts", payload)

    # Invalida cache para que a próxima chamada traga o contato novo
    _invalidar_cache_contatos()

    log.info(f"Contato criado com id: {resultado.get('id')}")
    return resultado


# ══════════════════════════════════════════════════════════════════════════════
# UTILITÁRIOS
# ══════════════════════════════════════════════════════════════════════════════

def _invalidar_cache_contatos():
    """Remove entradas de contatos do cache após criação/atualização."""
    for limit in [10, 50, 100, 200]:
        key = _cache_key(f"contacts_{limit}")
        _cache.delete(key)
    log.info("Cache de contatos invalidado.")


def invalidar_tudo():
    """Limpa todo o cache — útil para forçar refresh completo."""
    _cache.clear()
    log.info("Cache HubSpot completamente invalidado.")


def health_check() -> dict:
    """
    Verifica conectividade com a HubSpot API.
    Retorna dict com status e contagem de contatos/deals.
    Útil para exibir na sidebar do Streamlit.
    """
    try:
        data = _get("/crm/v3/objects/contacts", params={"limit": 1})
        total = data.get("total", 0)
        return {"ok": True, "total_contatos": total, "erro": None}
    except Exception as e:
        return {"ok": False, "total_contatos": 0, "erro": str(e)}