from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests, zipfile, io, json
import threading
import time

app = FastAPI()

# Activer le CORS pour autoriser les requêtes depuis Lovable ou d'autres frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# URLs des fichiers de données de l'Assemblée
SCRUTIN_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip"
DEPUTE_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/amo/deputes_actifs_mandats_actifs_organes/AMO10_deputes_actifs_mandats_actifs_organes.json.zip"

scrutins_data = []
deputes_data = {}
deports_data = []
organes_data = {}

# Téléchargement et extraction des scrutins
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
                except json.JSONDecodeError:
                    print(f"❌ Erreur de parsing JSON : {json_file}")
    
    print(f"✅ {len(scrutins_data)} scrutins chargés.")

# Téléchargement et extraction des députés, déports et organes
def download_and_parse_deputes():
    global deputes_data, deports_data, organes_data
    print("📥 Téléchargement des données des députés...")
    r = requests.get(DEPUTE_URL)
    
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        json_files = [name for name in z.namelist() if name.startswith("json/") and name.endswith(".json")]
        print(f"📂 {len(json_files)} fichiers JSON trouvés dans le ZIP des députés.")

        deputes_data.clear()
        deports_data.clear()
        organes_data.clear()

        for json_file in json_files:
            with z.open(json_file) as f:
                try:
                    data = json.load(f)
                    if "acteur" in data:  # Députés
                        uid = data["acteur"]["uid"]["#text"]
                        deputes_data[uid] = data["acteur"]
                    elif "uid" in data and "refActeur" in data:  # Déports
                        deports_data.append(data)
                    elif "uid" in data and "libelle" in data:  # Organes
                        organes_data[data["uid"]] = data
                except json.JSONDecodeError:
                    print(f"❌ Erreur de parsing JSON : {json_file}")
    
    print(f"✅ {len(deputes_data)} députés chargés.")
    print(f"✅ {len(deports_data)} déports chargés.")
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
def get_depute(depute_id: str = Query(None), nom: str = Query(None)):
    if nom:
        matching_deputes = [
            {"id": uid, "prenom": info.get("etatCivil", {}).get("ident", {}).get("prenom", ""), "nom": info.get("etatCivil", {}).get("ident", {}).get("nom", "")}
            for uid, info in deputes_data.items()
            if info.get("etatCivil", {}).get("ident", {}).get("nom", "").lower() == nom.lower()
        ]
        if len(matching_deputes) == 0:
            return {"error": "Député non trouvé"}
        elif len(matching_deputes) > 1:
            return {"error": "Plusieurs députés trouvés, veuillez préciser l'identifiant", "options": matching_deputes}
        else:
            depute_id = matching_deputes[0]["id"]
    
    if not depute_id or depute_id not in deputes_data:
        return {"error": "Député non trouvé"}

    depute_info = deputes_data[depute_id]
    
    # Recherche du groupe politique et des organes
    organes_depute = []
    for mandat in depute_info.get("mandats", {}).get("mandat", []):
        organe_id = mandat["organes"].get("organeRef")
        if organe_id in organes_data:
            organe_info = organes_data[organe_id]
            organes_depute.append({
                "type": organe_info.get("typeOrgane"),
                "nom": organe_info.get("libelle"),
                "date_debut": organe_info.get("dateDebut"),
                "date_fin": organe_info.get("dateFin"),
                "legislature": organe_info.get("legislature")
            })
    
    depute_info["organes"] = organes_depute
    return depute_info

@app.get("/organes")
def get_organes(organe_id: str = Query(...)):
    return organes_data.get(organe_id, {"error": "Aucun organe trouvé"})
