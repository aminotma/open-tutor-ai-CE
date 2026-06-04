"""Tool: execute a student SQL query against an in-memory SQLite database.

Subjects : informatique, bases de données, SQL
Exercise types : sql, coding (when code_language == 'sql')

Pre-loaded sample tables (W3Schools-compatible schema):
  Customers(CustomerID, CustomerName, ContactName, Country, City)
  Products(ProductID, ProductName, Category, Price, Stock)
  Orders(OrderID, CustomerID, ProductID, Quantity, OrderDate)
  Employees(EmployeeID, LastName, FirstName, Title, Country)
"""
from __future__ import annotations

import sqlite3
import textwrap
from typing import Any

from langchain_core.tools import tool

# ── Sample data ────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE Customers (
    CustomerID   INTEGER PRIMARY KEY,
    CustomerName TEXT,
    ContactName  TEXT,
    Country      TEXT,
    City         TEXT
);
CREATE TABLE Products (
    ProductID   INTEGER PRIMARY KEY,
    ProductName TEXT,
    Category    TEXT,
    Price       REAL,
    Stock       INTEGER
);
CREATE TABLE Orders (
    OrderID    INTEGER PRIMARY KEY,
    CustomerID INTEGER,
    ProductID  INTEGER,
    Quantity   INTEGER,
    OrderDate  TEXT,
    FOREIGN KEY (CustomerID) REFERENCES Customers(CustomerID),
    FOREIGN KEY (ProductID)  REFERENCES Products(ProductID)
);
CREATE TABLE Employees (
    EmployeeID INTEGER PRIMARY KEY,
    LastName   TEXT,
    FirstName  TEXT,
    Title      TEXT,
    Country    TEXT
);
"""

_DATA_SQL = """
INSERT INTO Customers VALUES
  (1,'Alfreds Futterkiste','Maria Anders','Germany','Berlin'),
  (2,'Ana Trujillo Emparedados','Ana Trujillo','Mexico','México D.F.'),
  (3,'Around the Horn','Thomas Hardy','UK','London'),
  (4,'Berglunds snabbköp','Christina Berglund','Sweden','Luleå'),
  (5,'Blondel père et fils','Frédérique Citeaux','France','Strasbourg');

INSERT INTO Products VALUES
  (1,'Chai','Beverages',18.0,39),
  (2,'Chang','Beverages',19.0,17),
  (3,'Aniseed Syrup','Condiments',10.0,13),
  (4,'Chef Anton Cajun Seasoning','Condiments',22.0,53),
  (5,'Grandma Boysenberry Spread','Condiments',25.0,120);

INSERT INTO Orders VALUES
  (10248,1,1,12,'1996-07-04'),
  (10249,2,2,10,'1996-07-05'),
  (10250,3,3,5,'1996-07-08'),
  (10251,4,4,6,'1996-07-08'),
  (10252,5,5,40,'1996-07-09');

INSERT INTO Employees VALUES
  (1,'Davolio','Nancy','Sales Representative','USA'),
  (2,'Fuller','Andrew','Vice President Sales','USA'),
  (3,'Leverling','Janet','Sales Representative','USA'),
  (4,'Peacock','Margaret','Sales Representative','USA'),
  (5,'Buchanan','Steven','Sales Manager','UK');
"""

_ALLOWED_PREFIXES = ("select", "with", "explain", "pragma table_info")


def _build_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL + _DATA_SQL)
    return conn


def _is_safe(query: str) -> bool:
    """Only allow read-only statements."""
    first = query.strip().lower().lstrip(";")
    return any(first.startswith(p) for p in _ALLOWED_PREFIXES)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


@tool
def sql_evaluator(query: str, expected_row_count: int = -1) -> dict:
    """
    Execute a SQL SELECT query against a pre-loaded in-memory SQLite database and
    return the result rows.

    Available tables: Customers, Products, Orders, Employees
    (W3Schools-compatible schema and sample data)

    Only SELECT / WITH / EXPLAIN statements are allowed.

    Args:
        query:              SQL query to execute (SELECT only).
        expected_row_count: Optional expected number of rows. When >= 0, the tool
                            checks whether the result matches this count.

    Returns:
        dict with keys:
            success      (bool)       — True if query ran without error
            rows         (list[dict]) — Result rows (max 50)
            row_count    (int)        — Number of rows returned
            matched      (bool|None)  — True if row_count == expected_row_count
            columns      (list[str])  — Column names
            error        (str)        — Error message if execution failed
    """
    query = textwrap.dedent(query).strip()

    if not _is_safe(query):
        return {
            "success":   False,
            "rows":      [],
            "row_count": 0,
            "matched":   None,
            "columns":   [],
            "error":     "Only SELECT / WITH / EXPLAIN statements are allowed.",
        }

    try:
        conn = _build_db()
        cursor = conn.execute(query)
        rows = cursor.fetchmany(50)
        columns = [d[0] for d in cursor.description] if cursor.description else []
        row_dicts = _rows_to_dicts(rows)
        row_count = len(row_dicts)

        matched: bool | None = None
        if expected_row_count >= 0:
            matched = row_count == expected_row_count

        conn.close()
        return {
            "success":   True,
            "rows":      row_dicts,
            "row_count": row_count,
            "matched":   matched,
            "columns":   columns,
            "error":     "",
        }

    except Exception as exc:
        return {
            "success":   False,
            "rows":      [],
            "row_count": 0,
            "matched":   None,
            "columns":   [],
            "error":     str(exc),
        }
