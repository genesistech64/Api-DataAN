from fastapi import FastAPI, Query, BackgroundTasks
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

# URL des fichiers de scrutins et des députés
SCRUTIN_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip"
DEPUTE_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/amo/deputes_actifs_mandats_actifs_organes/AMO10_deputes_actifs_mandats_actifs_organes.json.zip"

scrutins_data = []
deputes_data = {}

# Fonction pour télécharger et traiter les scrutins
def download_and_parse_scrutins():
    global scrutins_data
    print("Téléchargement des scrutins...")
    r = requests.get(SCRUTIN_URL)
    
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        json_files = [name for name in z.namelist() if name.endswith(".json")]
        print(f"{len(json_files)} fichiers JSON trouvés dans le zip.")
        
        scrutins_data.clear()
        for json_file in json_files:
            with z.open(json_file) as f:
                try:
                    data = json.load(f)
                    if isinstance(data, dict) and "scrutin" in data:
                        scrutins_data.append(data)
                except json.JSONDecodeError:
                    print(f"Erreur de parsing JSON dans le fichier : {json_file}")
    
    print(f"{len(scrutins_data)} scrutins chargés.")

# Fonction pour télécharger et traiter les informations des députés
def download_and_parse_deputes():
    global deputes_data
    print("Téléchargement des données des députés...")
    r = requests.get(DEPUTE_URL)
    
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        json_files = [name for name in z.namelist() if name.startswith("acteur/") and name.endswith(".json")]
        print(f"{len(json_files)} fichiers JSON trouvés dans le zip.")
        
        deputes_data.clear()
        for json_file in json_files:
            with z.open(json_file) as f:
                try:
                    data = json.load(f)
                    acteur = data.get("acteur", {})
                    uid = acteur.get("uid", {}).get("#text")
                    if uid:
                        deputes_data[uid] = acteur  # Stocker toutes les informations de l'acteur
                except json.JSONDecodeError:
                    print(f"Erreur de parsing JSON dans le fichier : {json_file}")
    
    print(f"{len(deputes_data)} députés chargés.")

@app.on_event("startup")
def startup_event():
    download_and_parse_scrutins()
    download_and_parse_deputes()
    threading.Thread(target=periodic_update, daemon=True).start()

def periodic_update():
    while True:
        time.sleep(172800)  # Attendre 48 heures
        print("⏳ Mise à jour automatique des données...")
        download_and_parse_scrutins()
        download_and_parse_deputes()
        print("✅ Mise à jour terminée.")

@app.get("/votes")
def get_votes(depute_id: str = Query(None, description="Identifiant du député, ex: PA1592"), nom: str = Query(None, description="Nom du député")):
    if nom:
        matching_deputes = [uid for uid, info in deputes_data.items() if info.get("etatCivil", {}).get("ident", {}).get("nom", "").lower() == nom.lower()]
        
        if len(matching_deputes) == 0:
            return {"error": "Député non trouvé"}
        elif len(matching_deputes) > 1:
            return {"error": "Plusieurs députés trouvés, veuillez préciser l'identifiant", "options": matching_deputes}
        else:
            depute_id = matching_deputes[0]
    
    if not depute_id:
        return {"error": "Veuillez fournir un identifiant ou un nom de député"}
    
    results = []
    for entry in scrutins_data:
        scr = entry.get("scrutin", {})
        numero = scr.get("numero")
        date = scr.get("dateScrutin")
        titre = scr.get("objet", {}).get("libelle") or scr.get("titre", "")
        position = "Absent"

        groupes = scr.get("ventilationVotes", {}).get("organe", {}).get("groupes", {}).get("groupe", [])
        for groupe in groupes:
            votes = groupe.get("vote", {}).get("decompteNominatif", {})
            for cle_vote in ["pours", "contres", "abstentions", "nonVotants"]:
                bloc = votes.get(cle_vote)
                if not bloc:
                    continue
                votants = bloc.get("votant")
                if isinstance(votants, dict):
                    votants = [votants]
                if votants:
                    for v in votants:
                        if v.get("acteurRef") == depute_id:
                            position = cle_vote[:-1].capitalize()
        results.append({
            "numero": numero,
            "date": date,
            "titre": titre,
            "position": position
        })
    return results

@app.get("/depute")
def get_depute(depute_id: str = Query(..., description="Identifiant du député, ex: PA1592")):
    if depute_id not in deputes_data:
        return {"error": "Député non trouvé"}
    return deputes_data[depute_id]
