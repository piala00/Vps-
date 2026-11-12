from .base import (SageAdapter, SageClient, SageEntry, SagePurchaseOrder,  # noqa: F401
                   SolvencyComponents, SageIndisponible, SageExtractionIncomplete)


def creer_adaptateur(cfg: dict):
    mode = cfg["sage"]["mode"]
    if mode == "sql":
        from .sql_adapter import SqlSageAdapter
        return SqlSageAdapter(cfg["sage"])
    if mode == "demo":
        from .fake import FakeSageAdapter
        from pathlib import Path
        demo = Path(__file__).resolve().parents[2] / "demo" / "sage_demo.json"
        return FakeSageAdapter.depuis_json(demo) if demo.exists() else FakeSageAdapter()
    raise ValueError(f"Mode Sage inconnu : {mode}")
