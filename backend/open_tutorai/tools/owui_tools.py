"""Source code strings for the 5 OTAI tools registered in Open WebUI.

Each constant is a self-contained Python module (class Tools) that Open WebUI
exec-s dynamically when the LLM invokes the corresponding tool.
"""

# ── generate_chart ─────────────────────────────────────────────────────────────

GENERATE_CHART_CODE = r'''"""
title: OpenTutorAI — Graphique
description: Trace des fonctions mathématiques (f(x)) et des chronologies historiques.
"""
import json


class Tools:
    async def plot_function(
        self,
        expr: str,
        x_min: float = -5.0,
        x_max: float = 5.0,
        title: str = "",
        __event_emitter__=None,
    ) -> str:
        """
        Trace la courbe d'une fonction mathématique f(x) et affiche l'image dans le chat.

        Utilise cet outil quand l'utilisateur demande de :
        - Tracer / représenter / visualiser une fonction ou une courbe
          (ex: "trace y = x² - 8", "représente f(x) = sin(x)", "dessine la parabole")
        - Montrer l'allure d'une fonction (polynôme, trigonométrique, exponentielle...)

        :param expr: Expression de la fonction, ex: "x**2 - 8" ou "sin(x)" ou "x**3 - 3*x"
        :param x_min: Borne inférieure de l'axe x (défaut -5)
        :param x_max: Borne supérieure de l'axe x (défaut 5)
        :param title: Titre du graphique (optionnel)
        :return: Confirmation de génération ou message d'erreur
        """
        from open_tutorai.tools.generate_chart import generate_chart
        payload = json.dumps({
            "expr": expr,
            "x_min": x_min,
            "x_max": x_max,
            "title": title if title else "f(x) = " + expr,
            "xlabel": "x",
            "ylabel": "f(x)",
        })
        result = generate_chart.invoke({"chart_type": "function", "payload": payload})
        if result.get("success") and result.get("image_b64"):
            mime = result.get("mime_type", "image/png")
            b64 = result["image_b64"]
            img_md = "![f(x) = " + expr + "](data:" + mime + ";base64," + b64 + ")\n"
            if __event_emitter__:
                await __event_emitter__({"type": "message", "data": {"content": img_md}})
                return "Graphique de f(x) = " + expr + " généré avec succès."
            return img_md
        return "Erreur lors de la génération du graphique : " + result.get("error", "inconnue")

    async def plot_timeline(
        self,
        events_json: str,
        title: str = "",
        __event_emitter__=None,
    ) -> str:
        """
        Trace une chronologie historique à partir d'une liste d'événements JSON.

        Utilise cet outil quand l'utilisateur demande de :
        - Afficher une timeline / chronologie d'événements historiques
        - Visualiser des faits historiques sur un axe temporel
          (ex: "montre la chronologie de la Révolution française")

        :param events_json: JSON array [{year: int, label: str}, ...], ex:
                            '[{"year": 1789, "label": "Révolution"}, {"year": 1815, "label": "Waterloo"}]'
        :param title: Titre de la chronologie (optionnel)
        :return: Confirmation de génération ou message d'erreur
        """
        from open_tutorai.tools.generate_chart import generate_chart
        try:
            events = json.loads(events_json)
        except Exception:
            return "Format invalide : events_json doit être un tableau JSON [{year, label}, ...]"
        payload = json.dumps({"events": events, "title": title if title else "Chronologie"})
        result = generate_chart.invoke({"chart_type": "timeline", "payload": payload})
        if result.get("success") and result.get("image_b64"):
            mime = result.get("mime_type", "image/png")
            b64 = result["image_b64"]
            img_md = "![Chronologie](data:" + mime + ";base64," + b64 + ")\n"
            if __event_emitter__:
                await __event_emitter__({"type": "message", "data": {"content": img_md}})
                return "Chronologie générée avec succès."
            return img_md
        return "Erreur : " + result.get("error", "inconnue")
'''


# ── math_evaluator ─────────────────────────────────────────────────────────────

MATH_EVALUATOR_CODE = r'''"""
title: OpenTutorAI — Calcul symbolique
description: Évalue des expressions mathématiques sympy (dérivées, intégrales, équations...).
"""


class Tools:
    def evaluate_expression(self, expression: str, expected: str = "") -> str:
        """
        Évalue ou résout une expression mathématique symbolique avec sympy.

        Utilise cet outil quand l'utilisateur demande de :
        - Calculer une expression (ex: "2**8", "factorial(10)", "sqrt(144)")
        - Résoudre une équation (ex: "solve(x**2 - 4*x + 3, x)")
        - Calculer une dérivée (ex: "diff(x**3 - 2*x, x)")
        - Calculer une intégrale (ex: "integrate(x**2 + 1, x)")
        - Évaluer une limite (ex: "limit(sin(x)/x, x, 0)")
        - Vérifier si un résultat attendu est correct

        :param expression: Expression sympy à évaluer
        :param expected: Résultat attendu pour vérification (optionnel, laisse vide si absent)
        :return: Résultat formaté en markdown
        """
        from open_tutorai.tools.math_evaluator import math_evaluator
        result = math_evaluator.invoke({"expression": expression, "expected": expected})
        if not result.get("success"):
            return "Erreur de calcul : " + result.get("error", "inconnue")
        res_str = str(result.get("result", ""))
        output = "**Résultat :** `" + res_str + "`"
        if result.get("matched") is True:
            output += "\n\nRéponse correcte."
        elif result.get("matched") is False:
            output += "\n\nRéponse incorrecte (attendu : `" + str(expected) + "`)."
        return output
'''


# ── live_code_evaluation ───────────────────────────────────────────────────────

LIVE_CODE_CODE = r'''"""
title: OpenTutorAI — Exécution de code
description: Exécute du code Python dans un sandbox isolé et retourne stdout/stderr.
"""


class Tools:
    def run_python(self, code: str) -> str:
        """
        Exécute du code Python et retourne la sortie (stdout/stderr).

        Utilise cet outil quand l'utilisateur demande de :
        - Exécuter / tester du code Python
        - Vérifier le résultat d'un script
        - Déboguer une erreur d'exécution
        - Compléter ou corriger un programme Python

        :param code: Code Python à exécuter (timeout 5 secondes)
        :return: Sortie du programme en markdown (stdout + stderr)
        """
        from open_tutorai.tools.live_code_evaluation import live_code_evaluation
        result = live_code_evaluation.invoke({"code": code, "language": "python"})
        stdout = result.get("stdout", "").strip()
        stderr = result.get("stderr", "").strip()
        if not result.get("success"):
            msg = stderr if stderr else result.get("error", "inconnue")
            return "**Erreur d'exécution :**\n```\n" + msg + "\n```"
        parts = ["**Sortie :**", "```", stdout if stdout else "(aucune sortie)", "```"]
        output = "\n".join(parts)
        if stderr:
            output += "\n\n**Warnings :**\n```\n" + stderr + "\n```"
        return output
'''


# ── search_web ─────────────────────────────────────────────────────────────────

SEARCH_WEB_CODE = r'''"""
title: OpenTutorAI — Recherche web
description: Recherche des informations sur le web via DuckDuckGo.
"""


class Tools:
    def search(self, query: str, max_results: int = 5) -> str:
        """
        Recherche des informations sur le web et retourne les résultats pertinents.

        Utilise cet outil quand l'utilisateur demande de :
        - Chercher / trouver des informations sur un sujet
        - Vérifier des faits historiques, scientifiques ou d'actualité
        - Obtenir des sources ou références pour répondre à une question
        - Répondre à des QCM ou questions factuelles nécessitant des données externes

        :param query: Requête de recherche en langage naturel
        :param max_results: Nombre maximum de résultats (1-10, défaut 5)
        :return: Liste des résultats formatée en markdown
        """
        from open_tutorai.tools.search_web import search_web
        result = search_web.invoke({"query": query, "max_results": max_results})
        if not result.get("success"):
            return "Erreur de recherche : " + result.get("error", "inconnue")
        results = result.get("results", [])
        if not results:
            return "Aucun résultat trouvé pour : " + query
        lines = ["**Résultats pour :** " + query, ""]
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            lines.append(str(i) + ". **" + title + "**")
            if body:
                lines.append("   " + body[:200])
            if href:
                lines.append("   [Lien](" + href + ")")
            lines.append("")
        return "\n".join(lines)
'''


# ── sql_evaluator ──────────────────────────────────────────────────────────────

SQL_EVALUATOR_CODE = r'''"""
title: OpenTutorAI — Requêtes SQL
description: Exécute des requêtes SQL SELECT sur une base SQLite en mémoire avec des tables d'exemple (Customers, Products, Orders, Employees).
"""


class Tools:
    def run_sql(self, query: str) -> str:
        """
        Exécute une requête SQL SELECT sur une base de données SQLite en mémoire
        et retourne les résultats sous forme de tableau markdown.

        Tables disponibles (données W3Schools) :
        - Customers(CustomerID, CustomerName, ContactName, Country, City)
        - Products(ProductID, ProductName, Category, Price, Stock)
        - Orders(OrderID, CustomerID, ProductID, Quantity, OrderDate)
        - Employees(EmployeeID, LastName, FirstName, Title, Country)

        Utilise cet outil quand l'utilisateur demande de :
        - Tester / exécuter une requête SQL (SELECT, JOIN, WHERE, GROUP BY...)
        - Vérifier le résultat d'une requête SQL
        - Apprendre SQL en pratiquant sur des données réelles
        - Corriger ou déboguer une requête SQL

        Seules les requêtes SELECT, WITH et EXPLAIN sont autorisées.

        :param query: Requête SQL à exécuter (SELECT uniquement)
        :return: Résultats formatés en tableau markdown ou message d'erreur
        """
        from open_tutorai.tools.sql_evaluator import sql_evaluator
        result = sql_evaluator.invoke({"query": query})
        if not result.get("success"):
            return "**Erreur SQL :**\n```\n" + result.get("error", "inconnue") + "\n```"
        rows = result.get("rows", [])
        columns = result.get("columns", [])
        row_count = result.get("row_count", 0)
        if not rows:
            return "La requête s'est exécutée sans erreur mais n'a retourné aucune ligne."
        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join("---" for _ in columns) + " |"
        lines = [
            "**Résultat (" + str(row_count) + " ligne(s)) :**\n",
            header,
            separator,
        ]
        for row in rows:
            lines.append("| " + " | ".join(str(row.get(c, "")) for c in columns) + " |")
        return "\n".join(lines)
'''


# ── Registry manifest ──────────────────────────────────────────────────────────

TOOLS_MANIFEST = [
    {
        "id":   "otai_generate_chart",
        "name": "OpenTutorAI — Graphique",
        "code": GENERATE_CHART_CODE,
        "description": "Trace des fonctions mathématiques et des chronologies historiques.",
    },
    {
        "id":   "otai_math_evaluator",
        "name": "OpenTutorAI — Calcul symbolique",
        "code": MATH_EVALUATOR_CODE,
        "description": "Évalue des expressions sympy (dérivées, intégrales, équations...).",
    },
    {
        "id":   "otai_live_code",
        "name": "OpenTutorAI — Exécution de code",
        "code": LIVE_CODE_CODE,
        "description": "Exécute du code Python dans un sandbox isolé.",
    },
    {
        "id":   "otai_search_web",
        "name": "OpenTutorAI — Recherche web",
        "code": SEARCH_WEB_CODE,
        "description": "Recherche des informations sur le web via DuckDuckGo.",
    },
    {
        "id":   "otai_sql_evaluator",
        "name": "OpenTutorAI — Requêtes SQL",
        "code": SQL_EVALUATOR_CODE,
        "description": "Exécute des requêtes SQL SELECT sur une base SQLite avec tables d'exemple.",
    },
]
