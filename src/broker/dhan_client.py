"""Dhan broker client wrapper."""

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()


class DhanClient:
    """Connect to DhanHQ API using client_id and access_token."""

    def __init__(
        self,
        client_id: str | None = None,
        access_token: str | None = None,
    ):
        self.client_id = client_id or os.getenv("DHAN_CLIENT_ID", "")
        self.access_token = access_token or os.getenv("DHAN_ACCESS_TOKEN", "")
        self._dhan = None

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.access_token)

    @property
    def dhan(self):
        if not self.is_configured:
            raise RuntimeError(
                "Dhan credentials missing. Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN in .env file. "
                "Get token from web.dhan.co -> My Profile -> Access DhanHQ APIs"
            )
        if self._dhan is None:
            from dhanhq import DhanContext, dhanhq

            ctx = DhanContext(self.client_id, self.access_token)
            self._dhan = dhanhq(ctx)
        return self._dhan

    def test_connection(self) -> dict[str, Any]:
        try:
            funds = self.dhan.get_fund_limits()
            return {"connected": True, "funds": funds}
        except Exception as e:
            return {"connected": False, "error": str(e)}
