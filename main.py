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

# 📥 Téléchargement et extraction des députés et organes
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
                    if "acteur" in data:  # 📌 Députés
                        uid = data["acteur"]["uid"]["#text"]
                        deputes_data[uid] = data["acteur"]
                    elif "uid" in data and "refActeur" in data:  # 📌 Déports
                        deports_data.append(data)
                    elif "organe" in data and "uid" in data["organe"]:  # 📌 Organes
                        organe_id = data["organe"]["uid"]
                        organes_data[organe_id] = data["organe"].get("libelle", "Inconnu")
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
            return deputes_data[matching_deputes[0]["id"]]
        else:
            return {"error": "Plusieurs députés trouvés, précisez l'identifiant", "options": matching_deputes}

    if depute_id:
        depute = deputes_data.get(depute_id, {"error": "Député non trouvé"})
        if isinstance(depute, dict) and "mandats" in depute and "mandat" in depute["mandats"]:
            for mandat in depute["mandats"]["mandat"]:
                organe_ref = mandat.get("organes", {}).get("organeRef")
                if organe_ref in organes_data:
                    mandat["nomOrgane"] = organes_data[organe_ref]  # 🔄 Remplace l'ID par le libellé

        return depute

    return {"error": "Veuillez fournir un identifiant (`depute_id`) ou un nom (`nom`)"}

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
                if bloc and isinstance(bloc, dict):
                    votants = bloc.get("votant", [])
                    if isinstance(votants, dict):
                        votants = [votants]
                else:
                    votants = []

                for v in votants:
                    if v.get("acteurRef") == depute_id:
                        position = cle_vote[:-1].capitalize()

        results.append({
            "numero": numero,
            "date": date,
            "titre": titre,
            "position": position
        })

    if not results:
        return {"error": "Aucun vote trouvé pour ce député."}

    return results

@app.get("/deports")
def get_deports(depute_id: str = Query(...)):
    deports = [d for d in deports_data if d.get("refActeur") == depute_id]
    return deports if deports else {"message": "Aucun déport trouvé pour ce député."}

@app.get("/organes")
def get_organes(organe_id: str = Query(...)):
    return organes_data.get(organe_id, {"error": "Aucun organe trouvé"})

@app.get("/deputes_par_organe")
def get_deputes_par_organe(organe_id: str = Query(...)):
    deputes = []
    for uid, data in deputes_data.items():
        mandats = data.get("mandats", {}).get("mandat", [])
        if isinstance(mandats, dict):
            mandats = [mandats]
        for mandat in mandats:
            if mandat.get("organes", {}).get("organeRef") == organe_id:
                deputes.append({
                    "id": uid,
                    "nom": data.get("etatCivil", {}).get("ident", {}).get("nom"),
                    "prenom": data.get("etatCivil", {}).get("ident", {}).get("prenom")
                })
                break

    if not deputes:
        return {"error": "Aucun député trouvé pour cet organe."}

    return deputes
    
@app.get("/organes_liste")
def get_organes_liste():
    return [
        {"id": organe_id, "libelle": libelle}
        for organe_id, libelle in organes_data.items()
    ]
