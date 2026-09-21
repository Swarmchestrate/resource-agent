from optimusdb_client import OptimusDBClient


TRUST_STORE = "kbtrust"


class TrustStore:

    def __init__(self, client=None):
        self.client = client or OptimusDBClient()

    def get_trust_score(self, cap_id, default=None):
        """
        Retrieve trust_level using the CAP ID as the record's OptimusDB _id.

        Example:
            score = trust_store.get_trust_score("cap_aws_uk")
        """

        if not cap_id:
            return default

        result = self.client.get(
            criteria=[{"_id": cap_id}],
            dstype=TRUST_STORE,
        )

        data = result.get("data") or []

        if isinstance(data, dict):
            data = [data]

        if not data:
            return default

        return data[0].get("trust_level", default)
