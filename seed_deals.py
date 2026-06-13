# seed_deals.py — cria deals de teste na HubSpot
from hubspot_client import _post

deals = [
    {"dealname": "Projeto Site Loja A",    "amount": "3500",  "dealstage": "appointmentscheduled", "pipeline": "default"},
    {"dealname": "Integração CRM Empresa B","amount": "8000",  "dealstage": "qualifiedtobuy",       "pipeline": "default"},
    {"dealname": "Chatbot E-commerce C",   "amount": "5500",  "dealstage": "closedwon",            "pipeline": "default"},
    {"dealname": "Dashboard Analytics D",  "amount": "12000", "dealstage": "closedwon",            "pipeline": "default"},
    {"dealname": "RAG Jurídico E",         "amount": "9000",  "dealstage": "presentationscheduled","pipeline": "default"},
]

for d in deals:
    resultado = _post("/crm/v3/objects/deals", {"properties": d})
    print(f"✅ Deal criado: {d['dealname']} — id: {resultado['id']}")