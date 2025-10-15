# NextPost - Full Stack Social Media Platform

Un projet full-stack utilisant Django pour le backend et Next.js pour le frontend.

## 🛠 Technologies

### Backend
- **Python 3.13.7**
- **Django 5.2.7**
- **Django REST Framework** (pour les APIs)

### Frontend
- **Next.js**
- **TypeScript**
- **React**

## 🚀 Installation et Configuration

### Prérequis
- Python 3.13+
- Node.js 18+
- Git

### Backend (Django)

1. Cloner le repository :
```bash
git clone https://github.com/votre-username/nextpost.git
cd nextpost
```

2. Créer et activer l'environnement virtuel :
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
```

3. Installer les dépendances :
```bash
cd backend
pip install -r requirements.txt
```

4. Appliquer les migrations :
```bash
python manage.py migrate
```

5. Lancer le serveur de développement :
```bash
python manage.py runserver
```

Le backend sera accessible sur `http://127.0.0.1:8000/`

### Frontend (Next.js)

1. Installer les dépendances :
```bash
cd frontend
npm install
```

2. Lancer le serveur de développement :
```bash
npm run dev
```

Le frontend sera accessible sur `http://localhost:3000/`

## 📁 Structure du projet

```
nextpost/
├── backend/                 # Application Django
│   ├── nextpost_backend/   # Configuration principale
│   ├── manage.py           # Script de gestion Django
│   └── requirements.txt    # Dépendances Python
├── frontend/               # Application Next.js
│   ├── src/               # Code source
│   ├── public/            # Fichiers statiques
│   └── package.json       # Dépendances Node.js
├── .venv/                 # Environnement virtuel Python
└── README.md              # Ce fichier
```

## 🔧 Développement

### Commandes utiles Django

```bash
# Créer une nouvelle app
python manage.py startapp nom_app

# Créer des migrations
python manage.py makemigrations

# Appliquer les migrations
python manage.py migrate

# Créer un superutilisateur
python manage.py createsuperuser

# Collecter les fichiers statiques
python manage.py collectstatic
```

### Commandes utiles Next.js

```bash
# Développement
npm run dev

# Build production
npm run build

# Lancer en production
npm start

# Linting
npm run lint
```

## 📝 Licence

Ce projet est sous licence MIT.

## 👥 Contributeurs

- Votre nom (@JuniorSEVERE-WEB)
