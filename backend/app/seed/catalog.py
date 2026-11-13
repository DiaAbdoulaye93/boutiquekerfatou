"""Catalogue of the fictional shop: everyday products of a Senegalese neighbourhood shop.

Prices are plausible but invented (FCFA). `weight` is the relative chance that a receipt
contains the product, `qty` the (min, max, step) quantity bought at once.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogItem:
    name: str
    category: str
    unit: str
    price_xof: int
    cost_xof: int
    weight: float
    qty: tuple[float, float, float]
    reorder_level: float


def _item(
    name: str,
    category: str,
    unit: str,
    price: int,
    cost: int,
    weight: float,
    qty: tuple[float, float, float] = (1, 3, 1),
    reorder: float = 10,
) -> CatalogItem:
    return CatalogItem(name, category, unit, price, cost, weight, qty, reorder)


CATALOG: tuple[CatalogItem, ...] = (
    # Céréales et féculents
    _item("Riz brisé", "Céréales", "kg", 450, 400, 30, (1, 5, 0.5), 50),
    _item("Riz brisé (sac de 50 kg)", "Céréales", "sac de 50 kg", 21500, 20000, 1.5, reorder=3),
    _item("Mil", "Céréales", "kg", 400, 330, 6, (1, 3, 0.5), 20),
    _item("Farine de blé", "Céréales", "kg", 600, 520, 4, (1, 2, 0.5), 15),
    _item("Couscous de mil", "Céréales", "sachet de 1 kg", 900, 760, 3),
    _item("Pâtes alimentaires", "Céréales", "paquet de 500 g", 350, 290, 8, (1, 4, 1), 20),
    _item("Pain", "Céréales", "baguette", 150, 125, 26, (1, 6, 1), 30),
    # Épicerie
    _item("Sucre en poudre", "Épicerie", "kg", 700, 620, 22, (0.5, 3, 0.5), 30),
    _item("Sucre en morceaux", "Épicerie", "boîte", 750, 640, 5),
    _item("Huile", "Épicerie", "litre", 1300, 1150, 16, (0.5, 2, 0.5), 20),
    _item("Huile (bidon de 5 L)", "Épicerie", "bidon de 5 L", 6000, 5500, 1.5, reorder=4),
    _item("Oignons", "Épicerie", "kg", 600, 480, 18, (0.5, 3, 0.5), 25),
    _item("Pommes de terre", "Épicerie", "kg", 500, 400, 9, (0.5, 3, 0.5), 20),
    _item("Concentré de tomate", "Épicerie", "boîte de 400 g", 650, 550, 9, reorder=12),
    _item("Bouillon cube", "Épicerie", "boîte", 1000, 850, 10, reorder=12),
    _item("Sel", "Épicerie", "sachet", 100, 70, 6, (1, 2, 1), 15),
    _item("Poivre", "Épicerie", "sachet", 100, 70, 5, (1, 2, 1), 15),
    _item("Ail", "Épicerie", "sachet", 200, 150, 6, (1, 2, 1), 15),
    _item("Vinaigre", "Épicerie", "bouteille", 400, 320, 3),
    _item("Mayonnaise", "Épicerie", "pot", 1500, 1250, 3, reorder=5),
    _item("Moutarde", "Épicerie", "pot", 1000, 830, 2, reorder=5),
    _item("Sardines", "Épicerie", "boîte", 450, 380, 5, (1, 3, 1), 12),
    # Petit-déjeuner
    _item("Lait en poudre", "Petit-déjeuner", "sachet de 400 g", 1900, 1650, 9, reorder=10),
    _item("Café Touba", "Petit-déjeuner", "sachet de 250 g", 1000, 830, 9, reorder=10),
    _item("Thé vert", "Petit-déjeuner", "paquet", 400, 320, 12, (1, 3, 1), 15),
    _item("Chocolat à tartiner", "Petit-déjeuner", "pot", 1200, 1000, 4, reorder=6),
    _item("Beurre", "Petit-déjeuner", "boîte", 700, 590, 4, reorder=6),
    _item("Œufs", "Petit-déjeuner", "pièce", 100, 80, 10, (2, 10, 1), 30),
    _item("Biscuits", "Petit-déjeuner", "paquet", 100, 75, 10, (1, 5, 1), 30),
    # Hygiène et entretien
    _item("Savon de Marseille", "Hygiène", "morceau", 300, 240, 8, (1, 3, 1), 15),
    _item("Savon de toilette", "Hygiène", "pièce", 350, 280, 5),
    _item("Lessive en poudre", "Hygiène", "sachet", 500, 410, 7, (1, 2, 1), 12),
    _item("Eau de Javel", "Hygiène", "bouteille", 400, 320, 4),
    _item("Papier hygiénique", "Hygiène", "rouleau", 250, 200, 4, (1, 4, 1), 12),
    _item("Dentifrice", "Hygiène", "tube", 500, 400, 3, reorder=6),
    # Boissons
    _item("Eau minérale", "Boissons", "bouteille de 1,5 L", 400, 320, 8, (1, 4, 1), 24),
    _item("Boisson gazeuse", "Boissons", "bouteille", 500, 400, 6, (1, 3, 1), 24),
    _item("Bissap", "Boissons", "sachet", 200, 150, 3, (1, 3, 1), 10),
    # Divers
    _item("Charbon", "Divers", "sac", 3500, 3000, 2, reorder=4),
    _item("Bougies", "Divers", "paquet", 500, 400, 2, reorder=5),
    _item("Allumettes", "Divers", "paquet", 100, 75, 4, (1, 3, 1), 15),
    _item("Piles", "Divers", "paire", 300, 230, 2, (1, 2, 1), 8),
)

# Fictional regular customers (common Senegalese names, no real person intended).
CUSTOMERS: tuple[str, ...] = (
    "Modou Diop",
    "Fatou Ndiaye",
    "Aminata Sow",
    "Ousmane Ba",
    "Mariama Diallo",
    "Cheikh Fall",
    "Awa Sarr",
    "Ibrahima Gueye",
    "Khady Faye",
    "Mamadou Sy",
    "Ndèye Mbaye",
    "Abdou Cissé",
    "Coumba Kane",
    "Babacar Thiam",
    "Seynabou Diouf",
    "Pape Ndiaye",
    "Aïssatou Barry",
    "Moussa Camara",
    "Rokhaya Seck",
    "Alioune Ka",
    "Adja Touré",
    "Samba Dieng",
    "Bineta Lo",
    "Lamine Sané",
    "Yacine Mendy",
    "Daouda Sall",
    "Marème Niang",
    "Saliou Wade",
    "Astou Diagne",
    "Oumar Sow",
)
