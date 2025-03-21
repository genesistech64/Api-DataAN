📌 Documentation de l'API des Votes et Députés de l'Assemblée Nationale
Version : 1.0
Dernière mise à jour : Mise à jour automatique toutes les 48h
Base URL : https://api-dataan.onrender.com

📖 Introduction
Cette API permet d'extraire, analyser et afficher les votes des députés français ainsi que leurs informations détaillées.
Elle s’appuie sur les données ouvertes de l'Assemblée Nationale et propose des endpoints REST simples et performants.

🏛 Données utilisées
Les données proviennent de :
📥 Votes et scrutins publics :

URL source : Scrutins.json.zip
Contient tous les scrutins et votes des députés depuis le début de la législature.
📥 Informations des députés & organes :

URL source : AMO10_deputes_actifs_mandats_actifs_organes.json.zip
Contient les détails des députés, leurs mandats, commissions, groupes politiques et organes liés.
📥 Déports (situations où un député ne peut pas voter)

📥 Organes parlementaires (Groupes politiques, commissions, fonctions…)

🚀 Utilisation de l'API
L'API expose plusieurs endpoints REST pour interagir avec les données.

1️⃣ /depute → Obtenir les informations d’un député
📌 Permet d'obtenir les informations détaillées d'un député, y compris :

Nom, prénom, date et lieu de naissance
Groupe politique et commissions parlementaires
Fonctions spécifiques et autres mandats
Contacts : emails, adresses et réseaux sociaux
🔹 Requête
bash
Copier
Modifier
GET /depute?depute_id=PA1592
GET /depute?nom=Habib
🔹 Réponse JSON
json
Copier
Modifier
{
  "id": "PA1592",
  "prenom": "David",
  "nom": "Habib",
  "civilite": "M.",
  "date_naissance": "1961-03-16",
  "lieu_naissance": "Paris (Paris), France",
  "profession": "Cadre",
  "groupe_politique": "Groupe Socialiste et apparentés",
  "organes": [
    {
      "type": "GP",
      "nom": "Groupe Socialiste et apparentés",
      "date_debut": "2024-07-19",
      "date_fin": null,
      "legislature": "17"
    },
    {
      "type": "COMNL",
      "nom": "Commission des Finances",
      "date_debut": "2024-09-20",
      "date_fin": null,
      "legislature": "17"
    }
  ],
  "contacts": [
    { "type": "Adresse officielle", "valeur": "126 Rue de l'Université" },
    { "type": "Mèl", "valeur": "David.Habib@assemblee-nationale.fr" },
    { "type": "Twitter", "valeur": "@DavidDhabib" }
  ]
}
🔍 Gère les homonymes :
Si plusieurs députés ont le même nom, une liste des ID disponibles est retournée pour choisir le bon.

2️⃣ /votes → Obtenir tous les votes d’un député
📌 Liste tous les scrutins dans lesquels un député a voté et indique sa position (Pour, Contre, Abstention, Absent).

🔹 Requête
bash
Copier
Modifier
GET /votes?depute_id=PA1592
GET /votes?nom=Habib
🔹 Réponse JSON
json
Copier
Modifier
[
  {
    "numero": "1080",
    "date": "2025-03-20",
    "titre": "Amendement n°301 sur le narcotrafic",
    "position": "Contre"
  },
  {
    "numero": "1079",
    "date": "2025-03-18",
    "titre": "Loi Climat et Résilience",
    "position": "Pour"
  }
]
📌 Gestion des absences → Si un député ne figure pas dans les votes d'un scrutin, il est considéré comme "Absent".

3️⃣ /organes → Obtenir les informations d’un organe
📌 Donne les détails d’un organe parlementaire (groupe politique, commission, organisme, etc.).

🔹 Requête
bash
Copier
Modifier
GET /organes?organe_id=PO845485
🔹 Réponse JSON
json
Copier
Modifier
{
  "uid": "PO845485",
  "libelle": "Groupe Socialiste et apparentés",
  "legislature": "17",
  "dateDebut": "2024-07-19",
  "dateFin": null,
  "typeOrgane": "GP",
  "membres": [
    { "uid": "PA1592", "etat": "Titulaire" },
    { "uid": "PA1234", "etat": "Titulaire" }
  ]
}
4️⃣ /deports → Obtenir les déports d’un député
📌 Affiche les situations où un député ne peut pas voter pour cause de conflit d’intérêts.

🔹 Requête
bash
Copier
Modifier
GET /deports?depute_id=PA1592
🔹 Réponse JSON
json
Copier
Modifier
[
  {
    "refActeur": "PA1592",
    "motif": "Conflit d'intérêts",
    "dateDebut": "2025-02-15",
    "dateFin": null
  }
]
🔄 Mise à jour des données
📌 Les données sont mises à jour toutes les 48h automatiquement
📌 Les données sont chargées en mémoire pour garantir des réponses rapides aux requêtes.

🎯 Cas d’usage pour un développeur
✅ 1. Afficher la fiche d’un député
Appeler /depute?nom=Nom
Vérifier si plusieurs résultats sont renvoyés (cas d’homonyme)
Récupérer son depute_id
Afficher la fiche complète avec ses mandats, fonctions et contacts.
✅ 2. Afficher les votes d’un député
Appeler /votes?depute_id=XXX
Récupérer tous les scrutins votés
Filtrer et afficher les résultats selon la date, la position (Pour/Contre)…
✅ 3. Vérifier le groupe politique d’un député
Appeler /depute?depute_id=XXX
Lire groupe_politique dans la réponse.
🚀 Prochaine amélioration
📌 Ajout d'un filtre par date pour les votes
📌 Permettre d'obtenir la liste des députés actifs via /deputes
📌 Optimisation de la gestion mémoire et de la rapidité d’accès aux données

📢 Besoin d'aide ?
📬 Contact : Ouvrez une issue sur GitHub ou posez vos questions directement.
👨‍💻 Contributions bienvenues pour améliorer l'API !
