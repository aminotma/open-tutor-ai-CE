# Migration du RAG : De File-Walk à ChromaDB

## État Initial du RAG

**Avant les modifications :**
- **Méthode** : File-walk (traversée de fichiers)
- **Algorithme** : Recherche textuelle simple avec `os.walk()` sur les répertoires `docs/` et `backend/`
- **Scoring** : Similarité basée sur la présence de termes de requête dans le contenu
- **Limites** :
  - Pas de recherche sémantique
  - Dépendance aux termes exacts
  - Performance limitée
  - Pas d'indexation des documents uploadés

**Code original dans `retrieve_pedagogical_documents()` :**
```python
async def retrieve_pedagogical_documents(user_id: str, query: str, top_k: int = 5) -> List[Dict]:
    repo_root = Path(__file__).resolve().parents[4]
    search_paths = [repo_root / "docs", repo_root / "backend"]
    documents = []

    for base_path in search_paths:
        if not base_path.exists():
            continue
        for root, _, files in os.walk(base_path):  # FILE-WALK
            for file_name in files:
                if not file_name.lower().endswith((".md", ".txt", ".json")):
                    continue
                file_path = Path(root) / file_name
                text = _read_text_file(file_path)
                if not text:
                    continue

                relevance_score = _score_document_relevance(text, query)  # TEXT MATCHING
                if relevance_score <= 0:
                    continue

                documents.append({
                    "id": str(file_path.relative_to(repo_root)),
                    "content": text,
                    "relevance_score": relevance_score,
                })

    documents.sort(key=lambda x: x["relevance_score"], reverse=True)
    return documents[:top_k]
```

## Améliorations Implémentées

**Après les modifications :**
- **Méthode** : Indexation vectorielle avec ChromaDB
- **Algorithme** : Recherche sémantique par similarité cosinus des embeddings
- **Modèle d'embeddings** : `all-MiniLM-L6-v2` (via ChromaDB par défaut)
- **Indexation automatique** : Documents locaux et uploadés
- **Fallback** : Maintien de la compatibilité avec file-walk en cas d'échec

## Changements Techniques

### 1. Ajout de ChromaDB
```python
import chromadb
from chromadb.config import Settings

# Client ChromaDB persistant
chroma_client = chromadb.PersistentClient(
    path="data/vector_db",
    settings=Settings(anonymized_telemetry=False)
)

DOCUMENTS_COLLECTION = "pedagogical_documents"
```

### 2. Fonctions d'Indexation
```python
def index_document_to_chromadb(doc_id: str, content: str, metadata: Dict[str, Any]) -> bool:
    """Indexe un document dans ChromaDB pour la recherche vectorielle"""
    collection = get_or_create_collection(DOCUMENTS_COLLECTION)
    collection.add(
        documents=[content],
        metadatas=[metadata],
        ids=[doc_id]
    )
    return True

def index_local_documents_to_chromadb() -> int:
    """Indexe automatiquement les documents locaux"""
    # Traverse docs/ et backend/ et indexe les fichiers .md/.txt/.json
    # Vérifie si déjà indexé avant d'ajouter

def index_uploaded_document_to_chromadb(file_path: str, user_id: str, title: str) -> bool:
    """Indexe un document uploadé"""
    # Lit le fichier, génère un ID unique, indexe dans ChromaDB
```

### 3. Nouvelle Fonction de Récupération
```python
async def retrieve_pedagogical_documents(user_id: str, query: str, top_k: int = 5) -> List[Dict]:
    # Indexation automatique des documents locaux
    indexed_count = index_local_documents_to_chromadb()

    # Recherche vectorielle
    collection = get_or_create_collection(DOCUMENTS_COLLECTION)
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        include=['documents', 'metadatas', 'distances']
    )

    # Conversion distance → score de similarité
    for i, doc_id in enumerate(results['ids'][0]):
        distance = results['distances'][0][i]
        vector_score = max(0.0, 1.0 - distance)  # Similarité cosinus

        documents.append({
            "id": doc_id,
            "content": results['documents'][0][i],
            "metadata": results['metadatas'][0][i],
            "relevance_score": vector_score,
            "vector_score": vector_score
        })

    return documents
```

### 4. Intégration avec les Uploads
**Modification de `supports.py` :**
```python
# Après sauvegarde du fichier
index_success = index_uploaded_document_to_chromadb(
    file_path=save_path,
    user_id=user_id,
    title=file.filename
)

return {"id": file_id, "filename": file.filename, "status": "success", "indexed": index_success}
```

### 5. Nouveaux Endpoints API
```python
@router.post("/context/index-local-documents")
# Déclenche l'indexation manuelle des documents locaux

@router.delete("/context/reset-vector-db")
# Reset la base vectorielle

@router.get("/context/vector-db-stats")
# Statistiques de la collection ChromaDB
```

## Avantages de l'Amélioration

1. **Recherche Sémantique** : Compréhension du sens plutôt que mots-clés exacts
2. **Performance** : Indexation une fois, recherche rapide
3. **Évolutivité** : Supporte de gros volumes de documents
4. **Précision** : Scores de similarité plus fiables
5. **Flexibilité** : Indexation automatique des nouveaux documents

## Tests de Validation

**Indexation :**
```bash
# Test d'indexation d'un document
File length: 240
Index result: True
Collection count: 1
```

**Recherche Vectorielle :**
```bash
# Test de recherche
Found 1 documents
First result: Test
```

## Configuration et Déploiement

- **Modèle d'embeddings** : `all-MiniLM-L6-v2` (384 dimensions)
- **Persistance** : `backend/data/vector_db/chroma.sqlite3`
- **Téléchargement automatique** : Modèle ONNX téléchargé au premier usage
- **Fallback** : File-walk maintenu en cas d'échec ChromaDB

## État Final

✅ **ChromaDB intégré et fonctionnel**
✅ **Recherche vectorielle opérationnelle**
✅ **Indexation automatique des uploads**
✅ **API de gestion disponible**
✅ **Compatibilité descendante assurée**

Le RAG est maintenant basé sur une indexation vectorielle moderne avec ChromaDB, offrant des capacités de recherche sémantique avancées tout en maintenant la robustesse du système.