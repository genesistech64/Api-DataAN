from pathlib import Path
import zipfile

# Dossier projet
project_dir = Path("/mnt/data/votes_api_render_fixed")
project_dir.mkdir(parents=True, exist_ok=True)

# Nouveau main.py corrigé
main_py = project_dir / "main.py"
main_py.write_text('''from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests, zipfile, io, json
from typing import List

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SCRUTIN_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip"
scrutins_data = []

@app.on_event("startup")
def download_and_parse():
    global scrutins_data
    print("Téléchargement des scrutins...")
    r = requests.get(SCRUTIN_URL)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        filename = [name for name in z.namelist() if name.endswith(".json")][0]
        print(f"Fichier trouvé dans le zip : {filename}")
        with z.open(filename) as f:
            scrutins_data = json.load(f)
    print(f"{len(scrutins_data)} scrutins chargés.")

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
''')

# Copier les autres fichiers
(project_dir / "requirements.txt").write_text("fastapi\nuvicorn[standard]\nrequests\n")
(project_dir / "render.yaml").write_text('''services:
  - type: web
    name: votes-api
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port 10000
    plan: free
''')

# Créer le ZIP corrigé
zip_path = "/mnt/data/votes_api_render_fixed.zip"
with zipfile.ZipFile(zip_path, "w") as zipf:
    for file in project_dir.rglob("*"):
        zipf.write(file, arcname=file.relative_to(project_dir))

zip_path
