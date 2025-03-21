from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
import requests, zipfile, io, json
import threading
import time

app = FastAPI()

# Activer le CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connexion à Supabase
SUPABASE_URL = "https://jjwpejhbwjbbkgxsfhnj.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Impqd3Blamhid2piYmtneHNmaG5qIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDI1ODE0OTIsImV4cCI6MjA1ODE1NzQ5Mn0.aKHWSXkuTmUCkpbgU5lJ-wg3ipq_-gFoC6YBJCXu9Tw"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# URLs des fichiers de l'Assemblée nationale
SCRUTIN_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip"
DEPUTE_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/amo/deputes_actifs_mandats_actifs_organes/AMO10_deputes_actifs_mandats_actifs_organes.json.zip"

# 📥 Mise à jour des données depuis l'Assemblée nationale

def update_data():
    """ Télécharge et met à jour la base Supabase avec les députés et organes """
    print("📥 Mise à jour des données...")
    r = requests.get(DEPUTE_URL)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        json_files = [name for name in z.namelist() if name.startswith("json/") and name.endswith(".json")]
        
        for json_file in json_files:
            with z.open(json_file) as f:
                try:
                    data = json.load(f)
                    if "acteur" in data:
                        uid = data["acteur"]["uid"]["#text"]
                        supabase.from_('deputies').upsert({
                            "id": uid,
                            "prenom": data["acteur"]["etatCivil"]["ident"].get("prenom", ""),
                            "nom": data["acteur"]["etatCivil"]["ident"].get("nom", ""),
                            "profession": data["acteur"].get("profession", "Non renseignée"),
                            "last_updated": "now()"
                        }).execute()
                    elif "organe" in data:
                        organe_id = data["organe"]["uid"]
                        supabase.from_('organes').upsert({
                            "uid": organe_id,
                            "nom": data["organe"].get("libelle", "Inconnu"),
                            "type": data["organe"].get("type", ""),
                            "date_debut": data["organe"].get("dateDebut", ""),
                            "date_fin": data["organe"].get("dateFin", "")
                        }).execute()
                except json.JSONDecodeError as e:
                    print(f"❌ Erreur JSON dans {json_file}: {e}")
    print("✅ Mise à jour terminée.")

@app.get("/update_data")
def trigger_update():
    threading.Thread(target=update_data).start()
    return {"message": "Mise à jour en cours..."}

# 🔍 Recherche des députés
@app.get("/depute")
def get_depute(depute_id: str = Query(None), nom: str = Query(None)):
    if depute_id:
        response = supabase.from_('deputies').select("*").eq("id", depute_id).execute()
        return response.data[0] if response.data else {"error": "Député non trouvé"}
    
    if nom:
        response = supabase.from_('deputies').select("*").eq("nom", nom).execute()
        return response.data if response.data else {"error": "Député non trouvé"}
    
    return {"error": "Veuillez fournir un identifiant (`depute_id`) ou un nom (`nom`)."}

# 📌 Récupération d'un organe et ses députés
@app.get("/organes")
def get_organes(organe_id: str = Query(...)):
    organe_info = supabase.from_('organes').select("*").eq("uid", organe_id).execute()
    if not organe_info.data:
        return {"error": "Aucun organe trouvé"}
    
    deputes = supabase.from_('deputy_organes').select("deputy_id").eq("organe_uid", organe_id).execute()
    return {
        "organe": organe_info.data[0],
        "deputes": [dep["deputy_id"] for dep in deputes.data]
    }

# 🗳 Récupération des votes d'un député
@app.get("/votes")
def get_votes(depute_id: str = Query(...)):
    response = supabase.from_('votes').select("*").eq("depute_id", depute_id).execute()
    return response.data if response.data else {"error": "Aucun vote trouvé pour ce député."}

# 🚫 Récupération des déports d'un député
@app.get("/deports")
def get_deports(depute_id: str = Query(...)):
    response = supabase.from_('deports').select("*").eq("depute_id", depute_id).execute()
    return response.data if response.data else {"message": "Aucun déport trouvé pour ce député."}

# 🏁 Démarrage de l'update périodique
@app.on_event("startup")
def startup_event():
    threading.Thread(target=update_data).start()
