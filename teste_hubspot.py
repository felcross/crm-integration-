# teste_hubspot.py
from hubspot_client import health_check, get_contacts, get_deals

print("=== Health Check ===")
print(health_check())

print("\n=== Contatos ===")
contatos = get_contacts(limit=5)
for c in contatos:
    print(c)

print("\n=== Deals ===")
deals = get_deals(limit=5)
for d in deals:
    print(d)