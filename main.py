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

# 📥 Téléchargement et extraction des scrutins
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

    # 🔎 Vérification du stockage des scrutins
    if scrutins_data:
        for scr in scrutins_data[:5]:  # Afficher les 5 premiers scrutins
            print(f"📊 Scrutin {scr.get('scrutin', {}).get('numero')} - {scr.get('scrutin', {}).get('titre')}")

# 📥 Téléchargement et extraction des députés, déports et organes
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
                except json.JSONDecodeError as e:
                    print(f"❌ Erreur JSON dans {json_file}: {e}")

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

@app.get("/votes")
def get_votes(depute_id: str = Query(...)):
    print(f"🔍 Recherche des votes pour {depute_id}...")

    found = False
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
                votants = votes.get(cle_vote, {}).get("votant", [])
                if isinstance(votants, dict):
                    votants = [votants]
                for v in votants:
                    if v.get("acteurRef") == depute_id:
                        position = cle_vote[:-1].capitalize()
                        found = True

        results.append({
            "numero": numero,
            "date": date,
            "titre": titre,
            "position": position
        })

    if not found:
        print(f"⚠️ Aucun vote trouvé pour {depute_id} !")
        return {"error": "Aucun vote trouvé pour ce député."}

    return results

@app.get("/depute")
def get_depute(depute_id: str = Query(...)):
    return deputes_data.get(depute_id, {"error": "Député non trouvé"})

@app.get("/deports")
def get_deports(depute_id: str = Query(...)):
    deports = [d for d in deports_data if d.get("refActeur") == depute_id]
    if not deports:
        print(f"⚠️ Aucun déport trouvé pour {depute_id}.")
        return {"message": "Ce député n'a aucun déport enregistré."}
    return deports

@app.get("/organes")
def get_organes(organe_id: str = Query(...)):
    return organes_data.get(organe_id, {"error": "Aucun organe trouvé"})
