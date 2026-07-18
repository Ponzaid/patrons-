#!/usr/bin/env python3
# Lee la lista de mecenas activos desde la API de Patreon y escribe public/patrons.json,
# AGRUPADOS por tier y ordenados de mayor a menor aporte.
# - Renueva el access token en cada ejecución con el refresh token (así no caduca nunca).
# - Descubre el Campaign ID solo (no hace falta darlo a mano).
# - NO fusiona mecenas con el mismo nombre: cada miembro cuenta una vez.
# Solo usa la librería estándar (no hace falta pip install).
#
# Variables de entorno (se configuran como "Secrets" en GitHub):
#   PATREON_CLIENT_ID       -> Client ID del cliente creado en el portal de Patreon
#   PATREON_CLIENT_SECRET   -> Client Secret de ese mismo cliente
#   PATREON_REFRESH_TOKEN   -> Creator's Refresh Token (no caduca)

import json
import os
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from datetime import datetime, timezone

CLIENT_ID = os.environ["PATREON_CLIENT_ID"]
CLIENT_SECRET = os.environ["PATREON_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["PATREON_REFRESH_TOKEN"]

TOKEN_URL = "https://www.patreon.com/api/oauth2/token"
API = "https://www.patreon.com/api/oauth2/v2"


def refresh_access_token():
    # Cambia el refresh token por un access token nuevo y válido.
    body = urlencode({
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }).encode()
    req = Request(
        TOKEN_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data["access_token"]


def get(url, token):
    req = Request(url, headers={"Authorization": "Bearer " + token})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get_campaign_id(token):
    data = get(API + "/campaigns", token)
    campaigns = data.get("data", [])
    if not campaigns:
        raise SystemExit(
            "No se encontró ninguna campaña. Revisa que el cliente de Patreon "
            "sea el de tu cuenta de creador."
        )
    return campaigns[0]["id"]


def main():
    token = refresh_access_token()
    campaign_id = get_campaign_id(token)

    base = API + "/campaigns/{}/members".format(campaign_id)
    params = urlencode({
        "include": "currently_entitled_tiers",
        "fields[member]": "full_name,patron_status",
        "fields[tier]": "title,amount_cents",
        "page[count]": "1000",
    })
    url = base + "?" + params

    tiers_by_id = {}          # id -> {"title":..., "amount_cents":...}
    members = []              # lista de (nombre, tier_id o None)
    status_counts = {}        # para el log: cuántos miembros hay de cada estado

    while url:
        data = get(url, token)

        # Guarda la info de los tiers que aparecen en esta página
        for inc in data.get("included", []):
            if inc.get("type") == "tier":
                a = inc.get("attributes", {})
                tiers_by_id[inc["id"]] = {
                    "title": (a.get("title") or "Mecenas").strip(),
                    "amount_cents": a.get("amount_cents") or 0,
                }

        for m in data.get("data", []):
            attr = m.get("attributes", {})
            status = attr.get("patron_status")
            status_counts[status] = status_counts.get(status, 0) + 1
            if status != "active_patron":
                continue
            name = (attr.get("full_name") or "").strip() or "Mecenas anónimo"
            # De sus tiers activos, nos quedamos con el de mayor aporte
            rel = m.get("relationships", {}).get("currently_entitled_tiers", {}).get("data", [])
            tier_id, best = None, -1
            for t in rel:
                tid = t.get("id")
                amt = tiers_by_id.get(tid, {}).get("amount_cents", 0)
                if amt > best:
                    best, tier_id = amt, tid
            members.append((name, tier_id))

        url = data.get("links", {}).get("next")

    # Agrupa por tier (SIN quitar nombres repetidos: dos personas pueden llamarse igual)
    groups = {}
    for name, tid in members:
        groups.setdefault(tid, []).append(name)

    tiers_out = []
    for tid, names in groups.items():
        info = tiers_by_id.get(tid, {"title": "Mecenas", "amount_cents": 0})
        tiers_out.append({
            "title": info["title"],
            "amount_cents": info["amount_cents"],
            "patrons": sorted(names, key=lambda s: s.lower()),
        })

    # Del que más aporta al que menos (esto es lo "escalonado")
    tiers_out.sort(key=lambda t: t["amount_cents"], reverse=True)

    count = sum(len(t["patrons"]) for t in tiers_out)
    out = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "count": count,
        "tiers": tiers_out,
    }

    os.makedirs("public", exist_ok=True)
    with open("public/patrons.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("Escritos {} mecenas en {} tiers".format(count, len(tiers_out)))
    print("Estados de todos los miembros vistos en la API:", status_counts)


if __name__ == "__main__":
    main()
