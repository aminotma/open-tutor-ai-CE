# Scénarios d'évaluation — OpenTutorAI

---

## Scénario 1 : Acquisition d'une notion

**Session 1**

> **Utilisateur :** Je débute en Python. Explique-moi les boucles `for`.

### Attendu

- Le système récupère les documents pédagogiques liés aux boucles.
- Une explication adaptée à un débutant est produite.
- Le niveau de l'utilisateur est enregistré dans la mémoire.

### Métriques

| Métrique | Description |
|---|---|
| `Recall@k` | Les bons documents sont-ils récupérés ? |
| `Faithfulness` | La réponse est-elle ancrée dans les documents ? (détection hallucinations) |
| `Learning Gain` | Progression entre pré-test et post-test |
| Latence end-to-end | Temps de réponse total |

---

## Scénario 2 : Vérification de la mémoire

**Session 2 (nouvelle session)**

> **Utilisateur :** Continue le cours précédent et propose-moi un exercice.

### Attendu

Le système doit se souvenir que :

- le sujet était **Python** ;
- le concept étudié était les **boucles for** ;
- le niveau était **débutant**.

### Métriques — Mémoire

| Mémoire attendue | Récupérée ? |
|---|:---:|
| Python | ✅ Oui |
| Boucles for | ✅ Oui |
| Débutant | ✅ Oui |

$$\text{Memory Retrieval Accuracy} = \frac{3}{3} = 100\%$$

| Métrique | Description | Cible |
|---|---|---|
| `Memory Retrieval Accuracy` | Tous les champs attendus sont-ils récupérés ? | 100% |

---

## Scénario 3 : Adaptation pédagogique

> **Utilisateur :** Les boucles `for` sont encore difficiles pour moi.

### Attendu

Le système doit :

- détecter une difficulté ;
- diminuer la complexité ;
- proposer un nouvel exemple.

### Vérification

Comparer la réponse avec celle générée pour un utilisateur **avancé**.

---

## Scénario 4 : Test du RAG

### Base de documents

| ID | Contenu |
|---|---|
| Doc1 | Boucles for |
| Doc2 | Boucles while |
| Doc3 | Fonctions Python |
| Doc4 | Listes Python |

> **Utilisateur :** Quelle est la différence entre une boucle `for` et une boucle `while` ?

### Résultats

| | Documents |
|---|---|
| **Attendus** | Doc1, Doc2 |
| **Retournés** | Doc1, Doc2, Doc4 |

### Calcul des métriques

$$\text{Precision@3} = \frac{2}{3} \approx 0.67$$

$$\text{Recall@3} = \frac{2}{2} = 1$$

$$\text{MRR} = 1 \quad \text{(le premier document pertinent est en position 1)}$$

| Métrique | Valeur | Cible |
|---|---|---|
| `Recall@3` | 1.0 | ≥ 0.80 |
| `Faithfulness` | à mesurer | ≥ 0.85 |

---

## Scénario 5 : Compression de contexte

Après plusieurs échanges :

| | Taille |
|---|---|
| Contexte brut | 10 000 tokens |
| Résumé généré | 2 500 tokens |

$$\text{Compression Ratio} = \frac{2500}{10000} = 0.25$$

> Le système conserve **25 %** de la taille initiale.

---

## Scénario 6 : Apprentissage longitudinal ⭐

> *Le scénario le plus représentatif de la mémoire long terme*

### Déroulé des sessions

| Session | Message utilisateur |
|---|---|
| Session 1 | Je veux apprendre les fonctions Python. |
| Session 2 | Je comprends les fonctions simples mais pas les paramètres. |
| Session 3 | Fais-moi un quiz. |
| Session 4 | Continue avec un niveau plus avancé. |

### Attendu

OpenTutorAI doit récupérer :

- les notions déjà étudiées ;
- les difficultés détectées ;
- le niveau de maîtrise estimé.

### Ce scénario évalue

| Dimension | Description | Métrique |
|---|---|---|
| Mémoire | Rappel des sessions passées | `Memory Retrieval Accuracy` |
| Agentique | La tâche est-elle menée à terme ? | `Task Completion Rate` |
| Pédagogie | L'apprenant a-t-il progressé ? | `Learning Gain` |

$$\text{Learning Gain} = \frac{\text{score post-test} - \text{score pré-test}}{100 - \text{score pré-test}}$$

---

## Scénario 7 : Routage agentique

> **Utilisateur :** Donne-moi un exercice sur les listes Python.

### Attendu — séquence d'agents

```
1. Router Agent        → identifie l'intention : "exercice"
2. RAG Agent           → récupère Doc4 (Listes Python)
3. Memory Agent        → lit le profil : niveau débutant
4. Exercise Generator  → produit un exercice adapté au niveau
5. BKT Agent           → enregistre la tentative
```

### Métriques

| Métrique | Description | Cible |
|---|---|---|
| `Task Completion Rate` | La tâche est-elle menée à terme sans blocage ? | 100% |
| Tool Call Order | La séquence d'agents est-elle correcte ? | Exacte |
| Latence end-to-end | Temps total de traitement | < 3s |

### Vérification

Comparer la séquence réelle (logs) avec la séquence attendue. Toute déviation indique un défaut de routage.

---

## Scénario 8 : Conflit mémoire

### Déroulé

| Session | Message utilisateur |
|---|---|
| Session 1 | Je débute en Python, je n'ai jamais codé. |
| Session 4 | En fait je fais du Python depuis 2 ans, je veux aller plus vite. |

### Attendu

Le système doit :

- détecter la contradiction avec le profil enregistré ;
- mettre à jour le niveau dans la mémoire (débutant → avancé) ;
- adapter immédiatement le contenu proposé.

### Métriques

| Test | Résultat attendu |
|---|---|
| Profil mis à jour ? | Oui |
| Ancien profil écrasé ou versionné ? | Versionné (historique conservé) |
| Contenu adapté dès la session 4 ? | Oui |

### Vérification

Interroger directement la mémoire après la session 4 et vérifier que le champ `niveau` contient `avancé` et que l'historique conserve `débutant` avec horodatage.

---

## Scénario 9 : Résistance à la perte de contexte

### Mise en place

Simuler une longue session générant **~12 000 tokens** de contexte brut (dépassement de la fenêtre).

### Déroulé

| Étape | Action |
|---|---|
| 1 | 15 échanges sur les listes et fonctions Python |
| 2 | Compression automatique déclenchée |
| 3 | Nouvelle question : "Rappelle-moi ce qu'on a vu sur les listes." |

### Attendu

Le résumé compressé doit contenir :

- les concepts abordés (listes, fonctions) ;
- les difficultés détectées ;
- le niveau estimé.

### Métriques

| Métrique | Formule | Cible |
|---|---|---|
| Compression Ratio | tokens_résumé / tokens_brut | ≤ 0.30 |
| Information Retention | infos_clés_conservées / infos_clés_totales | ≥ 0.80 |
| Cohérence réponse post-compression | Évaluation manuelle 1–5 | ≥ 4 |

$$\text{Information Retention} = \frac{\text{infos clés conservées}}{\text{infos clés totales}} \geq 80\%$$

---

## Scénario 10 : Mise à jour BKT (Bayesian Knowledge Tracing)

### Déroulé

| Exercice | Résultat | P(maîtrise) attendu |
|---|---|---|
| Exercice 1 — Boucles for | ✅ Correct | Augmente |
| Exercice 2 — Boucles for | ✅ Correct | Augmente |
| Exercice 3 — Boucles for | ❌ Incorrect | Diminue légèrement |
| Exercice 4 — Boucles for | ✅ Correct | Augmente |

### Attendu

- `P(maîtrise)` progresse de manière cohérente avec les résultats.
- Après 3 réponses correctes consécutives, le système propose automatiquement un concept plus avancé.
- Un résultat incorrect ne réinitialise pas la progression — il la ralentit seulement.

### Métriques

| Métrique | Description |
|---|---|
| BKT Calibration | Écart entre `P(maîtrise)` estimé et performance réelle |
| Threshold Detection | Le seuil de promotion vers le niveau suivant est-il franchi au bon moment ? |
| Régression correcte | Une erreur diminue-t-elle `P(maîtrise)` sans tout réinitialiser ? |

### Vérification

```
P(maîtrise) initial        : 0.10
Après exercice 1 (✅)      : ~0.35
Après exercice 2 (✅)      : ~0.60
Après exercice 3 (❌)      : ~0.45
Après exercice 4 (✅)      : ~0.65 → promotion déclenchée si seuil = 0.65
```
