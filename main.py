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
TABULAR_DEPUTE_BASE = "https://tabular-api.data.gouv.fr/api/resources/092bd7bb-1543-405b-b53c-932ebb49bb8e/data/"
TABULAR_DEPUTE_PROFILE = "https://tabular-api.data.gouv.fr/api/resources/092bd7bb-1543-405b-b53c-932ebb49bb8e/profile/"
TABULAR_GROUPE_BASE = "https://tabular-api.data.gouv.fr/api/resources/9d9b5dfb-6fbd-4c27-96fd-1c37a2456603/data/"
TABULAR_GROUPE_PROFILE = "https://tabular-api.data.gouv.fr/api/resources/9d9b5dfb-6fbd-4c27-96fd-1c37a2456603/profile/"

scrutins_data = []
deputes_data = {}
deports_data = []
organes_data = {}
tabular_column_name = None
tabular_group_column_name = None

def download_and_parse_scrutins():
    global scrutins_data
    print("📥 Téléchargement des scrutins...")
    r = requests.get(SCRUTIN_URL)

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        json_files = [name for name in z.namelist() if name.endswith(".json")]
        print(f"📂 {len(json_files)} fichiers JSON trouvés dans le ZIP des scrutins.")

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

def download_and_parse_deputes():
    global deputes_data, deports_data, organes_data
    print("📥 Téléchargement des données des députés et organes...")
    r = requests.get(DEPUTE_URL)

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        json_files = [name for name in z.namelist() if name.startswith("json/") and name.endswith(".json")]
        print(f"📂 {len(json_files)} fichiers JSON trouvés dans le ZIP des députés et organes.")

        deputes_data.clear()
        deports_data.clear()
        organes_data.clear()

        for json_file in json_files:
            with z.open(json_file) as f:
                try:
                    data = json.load(f)
                    if "acteur" in data:
                        uid = data["acteur"]["uid"]["#text"]
                        deputes_data[uid] = data["acteur"]
                    elif "uid" in data and "refActeur" in data:
                        deports_data.append(data)
                    elif "organe" in data and "uid" in data["organe"]:
                        organe_id = data["organe"]["uid"]
                        organes_data[organe_id] = data["organe"].get("libelle", "Inconnu")
                except json.JSONDecodeError as e:
                    print(f"❌ Erreur JSON dans {json_file}: {e}")

    print(f"✅ {len(deputes_data)} députés chargés.")
    print(f"✅ {len(deports_data)} déports chargés.")
    print(f"✅ {len(organes_data)} organes chargés.")

def detect_tabular_column():
    global tabular_column_name
    try:
        response = requests.get(TABULAR_DEPUTE_PROFILE)
        if response.status_code == 200:
            profile = response.json().get("profile", {})
            headers = profile.get("header", [])
            for h in headers:
                if h.lower() == "id":
                    tabular_column_name = h
                    print(f"✅ Colonne de liaison députés détectée : {h}")
                    return
            print("⚠️ Colonne 'ID' non trouvée dans la ressource députés.")
    except Exception as e:
        print(f"❌ Erreur lors de la détection de la colonne députés : {e}")

def detect_group_column():
    global tabular_group_column_name
    try:
        response = requests.get(TABULAR_GROUPE_PROFILE)
        if response.status_code == 200:
            profile = response.json().get("profile", {})
            headers = profile.get("header", [])
            for h in headers:
                if h.lower() == "id":
                    tabular_group_column_name = h
                    print(f"✅ Colonne de liaison groupes détectée : {h}")
                    return
            print("⚠️ Colonne 'ID' non trouvée dans la ressource groupes.")
    except Exception as e:
        print(f"❌ Erreur lors de la détection de la colonne groupes : {e}")

@app.on_event("startup")
def startup_event():
    download_and_parse_scrutins()
    download_and_parse_deputes()
    detect_tabular_column()
    detect_group_column()
    threading.Thread(target=periodic_update, daemon=True).start()

def periodic_update():
    while True:
        time.sleep(172800)
        print("🔄 Mise à jour automatique des données...")
        download_and_parse_scrutins()
        download_and_parse_deputes()
        detect_tabular_column()
        detect_group_column()
        print("✅ Mise à jour terminée.")

@app.get("/groupe_enrichi")
def get_groupe_enrichi(organe_id: str = Query(...)):
    if not tabular_group_column_name:
        return {"error": "Colonne tabulaire non détectée pour les groupes"}
    try:
        response = requests.get(f"{TABULAR_GROUPE_BASE}?{tabular_group_column_name}__exact={organe_id}&page_size=1")
        if response.status_code == 200:
            data = response.json()
            if "data" in data and len(data["data"]) > 0:
                return data["data"][0]
            else:
                return {"info": "Aucune donnée enrichie trouvée pour ce groupe"}
        else:
            return {"error": f"Erreur lors de la récupération des données enrichies du groupe (code {response.status_code})"}
    except Exception as e:
        return {"error": f"Exception levée : {str(e)}"}

@app.get("/deputes_par_organe")
def get_deputes_par_organe(organe_id: str = Query(...), enrichi: bool = Query(False)):
    results = []

    for uid, depute in deputes_data.items():
        mandats = depute.get("mandats", {}).get("mandat", [])
        for mandat in mandats:
            if isinstance(mandat, dict):
                org_ref = mandat.get("organes", {}).get("organeRef")
                if org_ref == organe_id:
                    item = {
                        "id": uid,
                        "prenom": depute.get("etatCivil", {}).get("ident", {}).get("prenom", ""),
                        "nom": depute.get("etatCivil", {}).get("ident", {}).get("nom", ""),
                        "nom_complet": f"{depute.get('etatCivil', {}).get('ident', {}).get('prenom', '')} {depute.get('etatCivil', {}).get('ident', {}).get('nom', '')}"
                    }
                    if enrichi and tabular_column_name:
                        try:
                            response = requests.get(f"{TABULAR_DEPUTE_BASE}?{tabular_column_name}__exact={uid}&page_size=1")
                            if response.status_code == 200:
                                json_data = response.json()
                                if json_data.get("data"):
                                    item["statistiques"] = json_data["data"][0]
                        except Exception as e:
                            item["statistiques"] = {"error": str(e)}
                    results.append(item)
                    break

    if not results:
        return {"info": "Aucun député trouvé pour cet organe."}

    return results

@app.get("/deputes_par_groupe")
def get_deputes_par_groupe(organe_id: str = Query(...), enrichi: bool = Query(False)):
    return get_deputes_par_organe(organe_id=organe_id, enrichi=enrichi)
