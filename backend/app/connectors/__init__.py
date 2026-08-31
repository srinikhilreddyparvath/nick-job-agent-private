from app.connectors.ashby import AshbyConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.lever import LeverConnector
from app.connectors.smartrecruiters import SmartRecruitersConnector
from app.connectors.generic_site import GenericCompanySiteConnector
from app.connectors.workday import WorkdayConnector
from app.connectors.unsupported import ICIMSConnector,JobviteConnector,SuccessFactorsConnector

CONNECTORS = {"greenhouse": GreenhouseConnector, "lever": LeverConnector, "ashby": AshbyConnector,"smartrecruiters":SmartRecruitersConnector,"workday":WorkdayConnector,"generic_company_site":GenericCompanySiteConnector,"icims":ICIMSConnector,"jobvite":JobviteConnector,"successfactors":SuccessFactorsConnector}
