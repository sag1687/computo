from dataclasses import dataclass


@dataclass(frozen=True)
class BundledDataset:
    key: str
    label: str
    region: str
    relative_path: str
    source_page: str
    update_url: str
    notes: str = ""


BUNDLED_DATASETS = [
    BundledDataset(
        key="basilicata-2026-lavorazioni",
        label="Basilicata 2026 - Lavorazioni",
        region="Basilicata",
        relative_path="data/bundled/basilicata_2026_lavorazioni.csv",
        source_page="https://www.regione.basilicata.it/?temi-im=ufficio-edilizia-pubblica-sociale-e-opere-pubbliche/prezzario-regionale-2026",
        update_url="https://www.regione.basilicata.it/wp-content/uploads/2026/07/INFRA_Allegato-C_Tassonomie.zip",
        notes="Dataset ufficiale pre-scaricato e normalizzato dal file tassonomia_lavorazioni.",
    ),
]
