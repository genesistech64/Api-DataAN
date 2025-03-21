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
deports_data = []
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
    global deputes_data, deports_data, organes_data
    print("📥 Téléchargement des données des députés et organes...")
    r = requests.get(DEPUTE_URL)
    
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        json_files = [name for name in z.namelist() if name.startswith("json/") and name.endswith(".json")]
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
                    elif "organe" in data and "uid" in data["organe"]:
                        organes_data[data["organe"]["uid"]] = data["organe"].get("libelle", "Inconnu")
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
def get_depute(depute_id: str = Query(None), nom: str = Query(None), legislature: str = Query(None)):
    if nom:
        deputes = [info for uid, info in deputes_data.items()
                   if info.get("etatCivil", {}).get("ident", {}).get("nom", "").lower() == nom.lower()]
        return deputes if deputes else {"error": "Député non trouvé"}
    
    if depute_id:
        return deputes_data.get(depute_id, {"error": "Député non trouvé"})
    
    return {"error": "Veuillez fournir un identifiant (`depute_id`) ou un nom (`nom`)"}

@app.get("/votes")
def get_votes(depute_id: str = Query(...), legislature: str = Query(None)):
    results = []
    for entry in scrutins_data:
        scr = entry.get("scrutin", {})
        position = "Absent"
        
        groupes = scr.get("ventilationVotes", {}).get("organe", {}).get("groupes", {}).get("groupe", [])
        for groupe in groupes:
            votes = groupe.get("vote", {}).get("decompteNominatif", {})
            for cle_vote in ["pours", "contres", "abstentions", "nonVotants"]:
                bloc = votes.get(cle_vote, {})
                votants = bloc.get("votant", []) if isinstance(bloc, dict) else []
                for v in votants:
                    if v.get("acteurRef") == depute_id:
                        position = cle_vote[:-1].capitalize()
        results.append({
            "numero": scr.get("numero"),
            "date": scr.get("dateScrutin"),
            "titre": scr.get("objet", {}).get("libelle", scr.get("titre", "")),
            "position": position
        })
    return results if results else {"error": "Aucun vote trouvé"}

@app.get("/organes")
def get_organes(organe_id: str = Query(...)):
    return organes_data.get(organe_id, {"error": "Aucun organe trouvé"})
