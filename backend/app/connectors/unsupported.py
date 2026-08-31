from app.connectors.base import JobConnector,ConnectorError
class UnsupportedConnector(JobConnector):
    connector_name="unsupported"
    def fetch_jobs(self,identifier,company): raise ConnectorError(f"connector_not_implemented: {self.connector_name}")
class ICIMSConnector(UnsupportedConnector): source="icims"; connector_name="icims"
class JobviteConnector(UnsupportedConnector): source="jobvite"; connector_name="jobvite"
class SuccessFactorsConnector(UnsupportedConnector): source="successfactors"; connector_name="successfactors"
