import json
from datetime import datetime,timezone
from pathlib import Path

from sqlalchemy import select

from app.core.config import Settings,get_settings
from app.db.models import JobSourceRecord
from app.models.profile import JobPreferences


class DiscoveryCatalogService:
    """Select a bounded, candidate-relevant mix of user and starter sources."""
    def __init__(self,settings:Settings|None=None):self.settings=settings or get_settings()
    def catalog(self)->list[dict]:
        path=Path(self.settings.starter_discovery_catalog_path)
        if not path.is_absolute():path=(Path(__file__).resolve().parents[2]/path).resolve()
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    @staticmethod
    def _relevance(item:dict,preferences:JobPreferences)->int:
        wanted=" ".join(preferences.preferred_domains+preferences.preferred_titles+preferences.locations).lower()
        signals=" ".join(item.get("domains",[])+item.get("locations",[])).lower()
        return sum(token in signals for token in {x for x in wanted.replace("/"," ").split() if len(x)>2})
    def select(self,db,preferences:JobPreferences)->list[JobSourceRecord]:
        cap=max(1,self.settings.discovery_max_sources_per_run)
        existing=list(db.scalars(select(JobSourceRecord).where(JobSourceRecord.enabled.is_(True))).all())
        user=[row for row in existing if (row.configuration or {}).get("origin")!="starter_catalog"]
        starter_existing={(row.ats_type,row.board_identifier):row for row in existing if (row.configuration or {}).get("origin")=="starter_catalog"}
        catalog=sorted(self.catalog(),key=lambda item:(-self._relevance(item,preferences),item["company"]))
        selected=user[:cap]
        keys={(row.ats_type,row.board_identifier) for row in selected}
        for item in catalog:
            if len(selected)>=cap:break
            key=(item["ats_type"],item["board_identifier"])
            if key in keys:continue
            row=starter_existing.get(key)
            if row is None:
                row=JobSourceRecord(company=item["company"],ats_type=item["ats_type"],board_identifier=item["board_identifier"],careers_url=item.get("website_url"),enabled=True,scan_frequency="scheduled",priority="NORMAL",configuration={"origin":"starter_catalog","domains":item.get("domains",[]),"locations":item.get("locations",[]),"website_url":item.get("website_url")})
                db.add(row);db.flush()
            selected.append(row);keys.add(key)
        db.commit()
        return selected
