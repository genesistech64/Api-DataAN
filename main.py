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

# 📥 Téléchargement et extraction des députés, déports et organes
def download_and_parse_deputes():
    global deputes_data, deports_data, organes_data
    print("📥 Téléchargement des données des députés et organes...")
    r = requests.get(DEPUTE_URL)
    
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        json_files = [name for name in z.namelist()]
        print(f"📂 {len(json_files)} fichiers JSON trouvés dans le ZIP des députés et organes.")

        deputes_data.clear()
        deports_data.clear()
        organes_data.clear()

        for json_file in json_files:
            with z.open(json_file) as f:
                try:
                    data = json.load(f)
                    
                    # 📌 Chargement des députés
                    if "acteur" in data:
                        uid = data["acteur"]["uid"]["#text"]
                        deputes_data[uid] = data["acteur"]

                    # 📌 Chargement des déports
                    elif "uid" in data and "refActeur" in data:
                        deports_data.append(data)

                    # 📌 Chargement des organes
                    elif "organe" in data:
                        uid = data["organe"]["uid"]
                        libelle = data["organe"]["libelle"]["text"] if "libelle" in data["organe"] else "Inconnu"
                        organes_data[uid] = libelle
                
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

@app.get("/depute")
def get_depute(
    depute_id: str = Query(None, description="Identifiant du député, ex: PA1592"),
    nom: str = Query(None, description="Nom du député, ex: Habib")
):
    if nom:
        matching_deputes = [
            {
                "id": uid,
                "prenom": info.get("etatCivil", {}).get("ident", {}).get("prenom", ""),
                "nom": info.get("etatCivil", {}).get("ident", {}).get("nom", "")
            }
            for uid, info in deputes_data.items()
            if info.get("etatCivil", {}).get("ident", {}).get("nom", "").lower() == nom.lower()
        ]
        
        if len(matching_deputes) == 0:
            return {"error": "Député non trouvé"}
        elif len(matching_deputes) == 1:
            depute_id = matching_deputes[0]["id"]
        else:
            return {"error": "Plusieurs députés trouvés, précisez l'identifiant", "options": matching_deputes}

    if depute_id:
        depute = deputes_data.get(depute_id, {"error": "Député non trouvé"})
        
        # 🔄 Remplacement des ID des organes par leurs noms
        if isinstance(depute, dict) and "mandats" in depute and "mandat" in depute["mandats"]:
            for mandat in depute["mandats"]["mandat"]:
                organe_ref = mandat.get("organes", {}).get("organeRef")
                if organe_ref:
                    mandat["nomOrgane"] = organes_data.get(organe_ref, f"Organisme inconnu ({organe_ref})")

        return depute

    return {"error": "Veuillez fournir un identifiant (`depute_id`) ou un nom (`nom`)"}

@app.get("/organes")
def get_organes(organe_id: str = Query(...)):
    return organes_data.get(organe_id, {"error": "Aucun organe trouvé"})

@app.get("/votes")
def get_votes(depute_id: str = Query(...)):
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
                votants = bloc.get("votant", []) if isinstance(bloc, dict) else []

                for v in (votants if isinstance(votants, list) else [votants]):
                    if v.get("acteurRef") == depute_id:
                        position = cle_vote[:-1].capitalize()

        results.append({
            "numero": numero,
            "date": date,
            "titre": titre,
            "position": position
        })

    return results if results else {"error": "Aucun vote trouvé pour ce député."}
