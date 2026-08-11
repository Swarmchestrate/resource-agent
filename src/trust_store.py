from optimusdb_client import OptimusDBClient


TRUST_STORE = "kbtrust"


class TrustStore:

    def __init__(self, client=None):
        self.client = client or OptimusDBClient()

    def get_trust_score(self, record_id, default=None):
        """
        Retrieve the trust_level for a trust record by its OptimusDB _id.

        Example:
            score = trust_store.get_trust_score("ra_aws_uk")
        """

        result = self.client.get(
            criteria=[{"_id": record_id}],
            dstype=TRUST_STORE,
        )

        data = result.get("data") or []

        if isinstance(data, dict):
            data = [data]

        if not data:
            return default

        return data[0].get("trust_level")