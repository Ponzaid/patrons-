#!/usr/bin/env python3
# Lee la lista de mecenas activos desde la API de Patreon y escribe public/patrons.json.
# Renueva el access token en cada ejecución con el refresh token (así no caduca nunca).
# Solo usa la librería estándar (no hace falta pip install).
#
# Variables de entorno (se configuran como "Secrets" en GitHub):
#   PATREON_CLIENT_ID       -> Client ID del cliente creado en el portal de Patreon
#   PATREON_CLIENT_SECRET   -> Client Secret de ese mismo cliente
#   PATREON_REFRESH_TOKEN   -> Creator's Refresh Token (no caduca)
#   PATREON_CAMPAIGN_ID     -> el ID numérico de tu campaña

import json
import os
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from datetime import datetime, timezone

CLIENT_ID = os.environ["PATREON_CLIENT_ID"]
CLIENT_SECRET = os.environ["PATREON_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["PATREON_REFRESH_TOKEN"]
CAMPAIGN_ID = os.environ["PATREON_CAMPAIGN_ID"]

TOKEN_URL = "https://www.patreon.com/api/oauth2/token"


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


def main():
    token = refresh_access_token()

    base = "https://www.patreon.com/api/oauth2/v2/campaigns/{}/members".format(CAMPAIGN_ID)
    params = urlencode({
        "fields[member]": "full_name,patron_status",
        "page[count]": "1000",
    })
    url = base + "?" + params

    names = []
    while url:
        data = get(url, token)
        for m in data.get("data", []):
            attr = m.get("attributes", {})
            if attr.get("patron_status") == "active_patron":
                name = (attr.get("full_name") or "").strip()
                if name:
                    names.append(name)
        # Patreon devuelve la URL de la página siguiente en links.next (o nada al final)
        url = data.get("links", {}).get("next")

    # Quita duplicados y ordena alfabéticamente (sin distinguir mayúsculas)
    seen = set()
    uniq = []
    for n in sorted(names, key=lambda s: s.lower()):
        if n.lower() not in seen:
            seen.add(n.lower())
            uniq.append(n)

    out = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "count": len(uniq),
        "patrons": uniq,
    }

    os.makedirs("public", exist_ok=True)
    with open("public/patrons.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("Escritos {} mecenas en public/patrons.json".format(len(uniq)))


if __name__ == "__main__":
    main()
