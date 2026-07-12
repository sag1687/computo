from dataclasses import dataclass, field


@dataclass
class PriceItem:
    code: str
    description: str
    unit: str
    unit_price: float
    category: str = ""
    notes: str = ""


@dataclass
class ImportedPriceList:
    name: str
    source_type: str
    source_path: str = ""
    source_url: str = ""
    notes: str = ""
    items: list[PriceItem] = field(default_factory=list)


@dataclass
class MeasurementItem:
    layer_name: str
    feature_id: int
    geometry_type: str
    price_code: str
    description: str
    unit: str
    quantity: float
    unit_price: float
    total_price: float
    category: str = ""
    note: str = ""
    price_list_id: int | None = None


@dataclass
class ReportMetadata:
    run_id: int
    layer_name: str
    price_list_name: str
    crs_authid: str
    generated_at: str
    notes: str = ""


@dataclass
class ReportReference:
    label: str
    value: str


@dataclass
class ReportProfile:
    title: str = "Computo metrico estimativo"
    subtitle: str = ""
    organization: str = ""
    logo_path: str = ""
    footer_text: str = ""
    include_map: bool = True
    map_title: str = "Mappa di inquadramento"
    references: list[ReportReference] = field(default_factory=list)
