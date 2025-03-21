from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests, zipfile, io, json
import threading
import time

app = FastAPI()

# Activer le CORS pour permettre les requêtes externes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# URLs des fichiers de l'Assemblée nationale
SCRUTIN_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip"
DEPUTE_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/amo/deputes_actifs_mandats_actifs_organes/AMO10_deputes_actifs_mandats_actifs_organes.json.zip"

scrutins_data = []
deputes_data = {}
organes_data = {}

# 📥 Téléchargement et extraction des scrutins
def download_and_parse_scrutins():
    global scrutins_data
    print("📥 Téléchargement des scrutins...")
    r = requests.get(SCRUTIN_URL)

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        json_files = [name for name in z.namelist() if name.endswith(".json")]
        scrutins_data.clear()
        for json_file in json_files:
            with z.open(json_file) as f:
                try:
                    data = json.load(f)
                    if isinstance(data, dict) and "scrutin" in data:
                        scrutins_data.append(data)
                except json.JSONDecodeError as e:
                    print(f"❌ Erreur JSON dans {json_file}: {e}")
    print(f"✅ {len(scrutins_data)} scrutins chargés.")

# 📥 Téléchargement et extraction des députés et organes
def download_and_parse_deputes():
    global deputes_data, organes_data
    print("📥 Téléchargement des données des députés et organes...")
    r = requests.get(DEPUTE_URL)

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        json_files = [name for name in z.namelist() if name.startswith("json/") and name.endswith(".json")]
        deputes_data.clear()
        organes_data.clear()

        for json_file in json_files:
            with z.open(json_file) as f:
                try:
                    data = json.load(f)
                    if "acteur" in data:
                        uid = data["acteur"]["uid"]["#text"]
                        deputes_data[uid] = data["acteur"]
                    elif "organe" in data and "uid" in data["organe"]:
                        organes_data[data["organe"]["uid"]] = {
                            "libelle": data["organe"].get("libelle", "Inconnu"),
                            "type": data["organe"].get("type", "Inconnu"),
                        }
                except json.JSONDecodeError as e:
                    print(f"❌ Erreur JSON dans {json_file}: {e}")
    print(f"✅ {len(deputes_data)} députés chargés.")
    print(f"✅ {len(organes_data)} organes chargés.")

@app.on_event("startup")
def startup_event():
    download_and_parse_scrutins()
    download_and_parse_deputes()
    threading.Thread(target=periodic_update, daemon=True).start()

def periodic_update():
    while True:
        time.sleep(172800)  # Attendre 48 heures
        print("🔄 Mise à jour automatique des données...")
        download_and_parse_scrutins()
        download_and_parse_deputes()
        print("✅ Mise à jour terminée.")

@app.get("/depute")
def get_depute(
    depute_id: str = Query(None, description="Identifiant du député, ex: PA1592"),
    nom: str = Query(None, description="Nom du député, ex: Habib"),
    organe_id: str = Query(None, description="Identifiant de l'organe, ex: PO845401")
):
    if organe_id:
        deputes_in_organe = [
            {
                "id": uid,
                "prenom": info.get("etatCivil", {}).get("ident", {}).get("prenom", ""),
                "nom": info.get("etatCivil", {}).get("ident", {}).get("nom", ""),
            }
            for uid, info in deputes_data.items()
            if "mandats" in info and "mandat" in info["mandats"]
            for mandat in info["mandats"]["mandat"]
            if isinstance(mandat, dict) and mandat.get("organes", {}).get("organeRef") == organe_id
        ]

        return deputes_in_organe if deputes_in_organe else {"error": "Aucun député trouvé pour cet organe."}

    if nom:
        matching_deputes = [
            {
                "id": uid,
                "prenom": info.get("etatCivil", {}).get("ident", {}).get("prenom", ""),
                "nom": info.get("etatCivil", {}).get("ident", {}).get("nom", ""),
                "organes": [
                    {"id": mandat.get("organes", {}).get("organeRef", ""), 
                     "nom": organes_data.get(mandat.get("organes", {}).get("organeRef", ""), {}).get("libelle", "Inconnu")}
                    for mandat in info.get("mandats", {}).get("mandat", [])
                    if isinstance(mandat, dict)
                ]
            }
            for uid, info in deputes_data.items()
            if info.get("etatCivil", {}).get("ident", {}).get("nom", "").lower() == nom.lower()
        ]

        return matching_deputes if matching_deputes else {"error": "Député non trouvé"}

    if depute_id:
        depute = deputes_data.get(depute_id, {"error": "Député non trouvé"})
        if isinstance(depute, dict) and "mandats" in depute and "mandat" in depute["mandats"]:
            for mandat in depute["mandats"]["mandat"]:
                organe_ref = mandat.get("organes", {}).get("organeRef")
                if organe_ref in organes_data:
                    mandat["nomOrgane"] = organes_data[organe_ref]["libelle"]  # 🔄 Remplace l'ID par le libellé
        
        return depute

    return {"error": "Veuillez fournir un identifiant (`depute_id`), un nom (`nom`) ou un organe (`organe_id`)"}

@app.get("/organes")
def get_organes(organe_id: str = Query(..., description="Identifiant de l'organe, ex: PO845401")):
    return organes_data.get(organe_id, {"error": "Aucun organe trouvé"})
