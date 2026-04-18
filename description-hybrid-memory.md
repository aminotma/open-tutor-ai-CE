# Description de la Hybrid Memory System

## Algorithme adopté

Le système de mémoire hybride implémenté dans Open TutorAI repose sur une architecture combinant :
- une organisation explicite des types de mémoire (`episodic`, `semantic`, `procedural`, `behavioral`),
- un stockage relationnel centralisé dans une table SQL dédiée,
- une recherche textuelle dans le contenu des mémoires pour l'accès par requête utilisateur.

Cette approche est dite hybride car elle mixe une taxonomie structurée de mémoire avec un mécanisme de récupération simple et efficace. En pratique, chaque mémoire est étiquetée par type et enregistrée avec son contenu, des métadonnées optionnelles et des horodatages. La récupération se fait par filtrage utilisateur + type, puis par recherche de sous-chaîne dans le champ `content`, ce qui permet de retrouver rapidement des souvenirs pertinents sans passer par un moteur vectoriel ou une indexation externe.

### Étapes principales de l'algorithme

1. Enregistrement de la mémoire
   - l'utilisateur envoie une mémoire via l'API `POST /api/v1/memories/add`
   - la mémoire est stockée dans la table SQL avec : `memory_type`, `content`, `memory_metadata`, `created_at`, `updated_at`

2. Lecture du contenu mémoire
   - l'utilisateur demande la liste des mémoires via `GET /api/v1/memories/`
   - l'API filtre par `user.id` et éventuellement par `memory_type`
   - les résultats sont ordonnés par date de mise à jour descendante, puis par date de création descendante

3. Recherche de mémoire
   - l'utilisateur envoie une requête à `POST /api/v1/memories/query`
   - l'API filtre les mémoires du même utilisateur et applique un `ilike('%query%')` sur le contenu
   - un filtre de type de mémoire peut aussi être ajouté pour restreindre la recherche

4. Mise à jour et suppression
   - modification via `POST /api/v1/memories/{memory_id}/update`
   - suppression d'une mémoire via `DELETE /api/v1/memories/{memory_id}`
   - suppression de toutes les mémoires de l'utilisateur via `DELETE /api/v1/memories/delete/user`

## Rôles des fichiers dans la gestion de la mémoire hybride

### `backend/open_tutorai/main.py`
- Rôle : point d'entrée principal de l'application backend, inclut le routeur `memories` pour exposer les endpoints API de gestion des mémoires.
- Modifications effectuées : ajout de l'import et de l'inclusion du routeur `memories` dans l'application FastAPI.

### `backend/open_tutorai/models/database.py`
- Rôle : définit le modèle de données SQLAlchemy pour la table `opentutorai_memory`, incluant la fonction `init_database()` pour créer la table automatiquement au démarrage.
- Modifications effectuées : ajout de la classe `Memory` héritant de `Base`, avec colonnes pour `id`, `user_id`, `memory_type`, `content`, `memory_metadata`, `created_at`, `updated_at`.

### `backend/open_tutorai/routers/memories.py`
- Rôle : implémente les endpoints REST API pour CRUD (Create, Read, Update, Delete) des mémoires, avec authentification utilisateur et validation des données.
- Modifications effectuées : définition des routes `GET /memories/`, `POST /memories/add`, `POST /memories/query`, `POST /memories/{memory_id}/update`, `DELETE /memories/{memory_id}`, `DELETE /memories/delete/user`.

### `src/lib/apis/memories/index.ts`
- Rôle : fournit les fonctions JavaScript/TypeScript côté client pour interagir avec l'API backend des mémoires, gérant les appels fetch et la gestion d'erreurs.
- Modifications effectuées : ajout des fonctions `getMemories`, `addNewMemory`, `updateMemoryById`, `queryMemory`, `deleteMemoryById`, `deleteMemoriesByUserId`.

### `src/lib/types/memory.ts`
- Rôle : définit les types TypeScript pour les mémoires, incluant `MemoryType` (énumération), `MemoryResponse` (interface de réponse API).
- Modifications effectuées : création des types pour typer les données de mémoire dans l'application frontend.

### `src/lib/components/chat/Settings/Personalization/AddMemoryModal.svelte`
- Rôle : composant modal Svelte pour ajouter une nouvelle mémoire, avec formulaire pour saisir le contenu et le type de mémoire.
- Modifications effectuées : implémentation du formulaire avec sélection de type, textarea pour le contenu, et appel à l'API pour sauvegarder.

### `src/lib/components/chat/Settings/Personalization/EditMemoryModal.svelte`
- Rôle : composant modal Svelte pour éditer une mémoire existante, pré-remplissant les champs avec les données actuelles.
- Modifications effectuées : formulaire d'édition avec liaison des valeurs existantes, et appel à l'API pour mettre à jour.

### `src/lib/components/chat/Settings/Personalization/ManageModal.svelte`
- Rôle : composant modal Svelte principal pour gérer les mémoires, affichant une liste filtrable, avec boutons pour ajouter, éditer, supprimer.
- Modifications effectuées : tableau des mémoires avec tri par date, filtres par type, intégration des modals enfants pour CRUD.

## Création de la table SQL dédiée

La table SQL dédiée aux mémoires est définie dans `backend/open_tutorai/models/database.py` sous le nom `opentutorai_memory`.

```python
class Memory(Base):
    """
    Table for storing user memories with explicit memory organization.
    """

    __tablename__ = f"{PREFIX}memory"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    memory_type = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    memory_metadata = Column(JSONField, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())
```

### Structure de la table

- `id` : identifiant unique de la mémoire, stocké en chaîne de caractères, indexé et utilisé comme clé primaire.
- `user_id` : identifiant de l'utilisateur propriétaire de la mémoire, indexé pour filtrer rapidement les mémoires par utilisateur.
- `memory_type` : catégorie de mémoire (`episodic`, `semantic`, `procedural`, `behavioral`), utilisée pour organiser et filtrer les souvenirs.
- `content` : texte principal de la mémoire, stocké dans un champ `Text` pour accepter des descriptions longues.
- `memory_metadata` : données JSON structurées optionnelles, permettant d'ajouter des informations complémentaires sans modifier le schéma.
- `created_at` : horodatage de création automatique, renseigné par la base de données.
- `updated_at` : horodatage de dernière mise à jour, géré automatiquement lors d'une modification.

### Initialisation de la table

La création physique de la table est effectuée à l'aide de SQLAlchemy via `Base.metadata.create_all(bind=engine, checkfirst=True)` dans la fonction `init_database()` :

```python
def init_database():
    """
    Initialize the database tables for OpenTutorAI.
    Call this function when your app starts to ensure all tables exist.

    This is safe to call even if tables already exist, as SQLAlchemy's
    create_all() only creates tables that don't exist yet.
    """
    from open_webui.internal.db import engine

    Base.metadata.create_all(bind=engine, checkfirst=True)
    print("OpenTutorAI database tables initialized successfully")

    return engine
```

Ce mécanisme garantit que la table SQL dédiée est créée automatiquement au démarrage de l'application si elle n'existe pas déjà.