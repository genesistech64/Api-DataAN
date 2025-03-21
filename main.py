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

# URL officielle du fichier ZIP contenant les scrutins
SCRUTIN_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip"
scrutins_data = []

def download_and_parse():
    global scrutins_data
    print("Téléchargement des scrutins...")
    r = requests.get(SCRUTIN_URL)
    
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        json_files = [name for name in z.namelist() if name.endswith(".json")]
        print(f"{len(json_files)} fichiers JSON trouvés dans le zip.")
        
        # Charger chaque scrutin et les fusionner
        scrutins_data.clear()
        for json_file in json_files:
            with z.open(json_file) as f:
                try:
                    data = json.load(f)
                    if isinstance(data, dict) and "scrutin" in data:
                        scrutins_data.append(data)  # Ajoute uniquement les scrutins valides
                except json.JSONDecodeError:
                    print(f"Erreur de parsing JSON dans le fichier : {json_file}")
    
    print(f"{len(scrutins_data)} scrutins chargés.")

@app.on_event("startup")
def startup_event():
    download_and_parse()
    # Lancer la mise à jour automatique toutes les 48h (172800 secondes)
    threading.Thread(target=periodic_update, daemon=True).start()

def periodic_update():
    while True:
        time.sleep(172800)  # Attendre 48 heures
        print("⏳ Mise à jour automatique des scrutins...")
        download_and_parse()
        print("✅ Mise à jour terminée.")

@app.get("/votes")
def get_votes(depute_id: str = Query(..., description="Identifiant du député, ex: PA1592")):
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
                if isinstance(votants, dict):  # Cas où il n'y a qu'un seul votant
                    votants = [votants]
                if votants:
                    for v in votants:
                        if v.get("acteurRef") == depute_id:
                            position = cle_vote[:-1].capitalize()  # pours → Pour
        results.append({
            "numero": numero,
            "date": date,
            "titre": titre,
            "position": position
        })
    return results
