from app.connectors.ashby import AshbyConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.lever import LeverConnector
from app.connectors.smartrecruiters import SmartRecruitersConnector
from app.connectors.generic_site import GenericCompanySiteConnector
from app.connectors.workday import WorkdayConnector
from app.connectors.bamboohr import BambooHRConnector
from app.connectors.recruitee import RecruiteeConnector
from app.connectors.teamtailor import TeamtailorConnector
from app.connectors.workable import WorkableConnector

CONNECTORS = {"greenhouse": GreenhouseConnector, "lever": LeverConnector, "ashby": AshbyConnector,"smartrecruiters":SmartRecruitersConnector,"workday":WorkdayConnector,"workable":WorkableConnector,"bamboohr":BambooHRConnector,"teamtailor":TeamtailorConnector,"recruitee":RecruiteeConnector,"generic_company_site":GenericCompanySiteConnector}
