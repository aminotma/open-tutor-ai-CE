# Agentique — Utilisation d’outils (web, APIs, code)

Ce document décrit l’intégration d’un agent d’outils dans le système agentique.

## Objectif

Permettre aux agents de recourir à des outils spécialisés pour :
- chercher des informations externes,
- appeler des APIs,
- exécuter du code pour vérifier ou enrichir des réponses.

## Implémentation

Le code se trouve dans :
- `backend/open_tutorai/agents/adaptive_tutor_agent.py`
- `backend/open_tutorai/routers/context_retrieval.py` (pour les outils de recherche interne)

### Composants clés

- `ToolAgent` : interface pour les outils.
- `web_search()` : requête de recherche web simulée.
- `call_api()` : exécution d’appels HTTP vers une API donnée.
- `execute_code()` : exécution de scripts Python dans un environnement restreint.
- **Outils de recherche interne** : Améliorations dans `retrieve_internal_memory()` et `retrieve_pedagogical_documents()` pour une recherche sémantique plus robuste.

### Fonctionnement

1. Le gestionnaire d’outils expose des capacités clairement identifiées.
2. Les autres agents peuvent consommer ces services pour améliorer la qualité de la solution.
3. Les résultats des outils sont enregistrés dans la trace de l’agent.

### Améliorations récentes (Recherche sémantique et RAG)

- **Recherche mémoire enrichie** : `retrieve_internal_memory()` utilise désormais un scoring sémantique combinant correspondance de tokens et similarité de séquence, au lieu d'un simple `ILIKE`. Résultats triés par pertinence et récence.
- **RAG pédagogique amélioré** : `retrieve_pedagogical_documents()` applique le même scoring enrichi. Si aucun résumé en cache, génération de résumés légers à partir des documents/mémoires récupérés, passant d'un placeholder à une synthèse réelle.
- **Génération de résumés** : `retrieve_context()` génère des synthèses locales lorsque le cache est vide, utilisant `summarize_interactions()` pour créer des résumés concis limités à 300 tokens (au lieu de mots) pour éviter les dépassements de limites de modèles externes.

## Bénéfices

- plus grande flexibilité pour enrichir les décisions,
- possibilité de faire des vérifications dynamiques,
- ouverture vers des intégrations externes futures,
- recherche interne plus précise et pertinente pour une meilleure récupération de contexte.
