"""Async Monero wallet RPC client using httpx.

Note: `monero-wallet-rpc --rpc-login` uses HTTP Digest auth.
"""

from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx


class MoneroRPCError(Exception):
    """Raised when Monero RPC returns an error."""

    def __init__(self, message: str, code: int | None = None, method: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.method = method


class MoneroWalletRPC:
    """Async client for monero-wallet-rpc JSON-RPC API.

    This client provides methods for wallet operations needed by the
    cheque bot, including wallet creation, opening, and transaction monitoring.
    """

    def __init__(
        self,
        url: str = "http://localhost:18082/json_rpc",
        username: str = "",
        password: str = "",
        timeout: float = 60.0,
    ) -> None:
        """Initialize the RPC client.

        Args:
            url: Full URL to the monero-wallet-rpc endpoint
            username: HTTP Basic Auth username (if required)
            password: HTTP Basic Auth password (if required)
            timeout: Request timeout in seconds
        """
        # Support URLs with embedded credentials: http://user:pass@host:port/json_rpc
        parsed = urlsplit(url)
        if parsed.username or parsed.password:
            username = parsed.username or ""
            password = parsed.password or ""
            host = parsed.hostname or ""
            netloc = host
            if parsed.port:
                netloc = f"{host}:{parsed.port}"
            url = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

        self.url = url
        self.timeout = timeout

        # monero-wallet-rpc uses HTTP Digest auth when --rpc-login is enabled.
        auth = httpx.DigestAuth(username, password) if username or password else None
        self._client = httpx.AsyncClient(auth=auth, timeout=timeout)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "MoneroWalletRPC":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def _call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Make a JSON-RPC call to the wallet.

        Args:
            method: RPC method name
            params: Method parameters
            timeout: Override default timeout for this call

        Returns:
            RPC result dictionary

        Raises:
            MoneroRPCError: If RPC returns an error
            httpx.HTTPError: If HTTP request fails
        """
        payload = {
            "jsonrpc": "2.0",
            "id": "0",
            "method": method,
            "params": params or {},
        }

        try:
            response = await self._client.post(
                self.url,
                json=payload,
                timeout=timeout or self.timeout,
            )
            response.raise_for_status()
        except httpx.TimeoutException as e:
            raise MoneroRPCError(f"RPC timeout calling {method}", method=method) from e
        except httpx.HTTPError as e:
            raise MoneroRPCError(f"HTTP error calling {method}: {e}", method=method) from e

        data = response.json()

        if "error" in data:
            error = data["error"]
            raise MoneroRPCError(
                error.get("message", "Unknown RPC error"),
                code=error.get("code"),
                method=method,
            )

        return data.get("result", {})

    # ==========================================================================
    # Wallet Lifecycle Methods
    # ==========================================================================

    async def generate_from_keys(
        self,
        address: str,
        view_key: str,
        filename: str,
        spend_key: str | None = None,
        password: str = "",
        restore_height: int = 0,
        autosave_current: bool = True,
    ) -> dict[str, Any]:
        """Create a view-only wallet from address and view key.

        This creates a wallet file that can monitor incoming transactions
        but cannot spend funds (no spend key).

        Args:
            address: Monero address (starts with 4 or 8)
            view_key: Private view key (64 hex characters)
            filename: Name for the wallet file (without .keys extension)
            spend_key: Optional spend key (not used for view-only wallets)
            password: Wallet file password
            restore_height: Block height to start scanning from
            autosave_current: Whether to save current wallet before switching

        Returns:
            RPC result with wallet info
        """
        params: dict[str, Any] = {
            "address": address,
            "viewkey": view_key,
            "filename": filename,
            "password": password,
            "restore_height": restore_height,
            "autosave_current": autosave_current,
        }
        if spend_key:
            params["spendkey"] = spend_key

        return await self._call("generate_from_keys", params)

    async def open_wallet(
        self,
        filename: str,
        password: str = "",
    ) -> dict[str, Any]:
        """Open an existing wallet file.

        Args:
            filename: Name of the wallet file (without .keys extension)
            password: Wallet file password

        Returns:
            RPC result (typically empty on success)
        """
        params = {
            "filename": filename,
            "password": password,
        }
        return await self._call("open_wallet", params)

    async def close_wallet(self, autosave: bool = True) -> dict[str, Any]:
        """Close the currently open wallet.

        Args:
            autosave: Whether to save wallet before closing

        Returns:
            RPC result (typically empty on success)
        """
        params = {"autosave_current": autosave}
        return await self._call("close_wallet", params)

    # ==========================================================================
    # Wallet Operations
    # ==========================================================================

    async def refresh(self, start_height: int | None = None) -> dict[str, Any]:
        """Refresh the wallet by scanning for new transactions.

        Args:
            start_height: Optional block height to start scanning from

        Returns:
            RPC result with blocks fetched count
        """
        params: dict[str, Any] = {}
        if start_height is not None:
            params["start_height"] = start_height
        return await self._call("refresh", params)

    async def get_transfers(
        self,
        *,
        incoming: bool = False,
        outgoing: bool = False,
        pending: bool = False,
        failed: bool = False,
        pool: bool = False,
        min_height: int | None = None,
        max_height: int | None = None,
        account_index: int = 0,
    ) -> dict[str, Any]:
        """Get transfers matching specified criteria.

        Args:
            incoming: Include incoming transfers
            outgoing: Include outgoing transfers
            pending: Include pending transfers
            failed: Include failed transfers
            pool: Include transfers in mempool
            min_height: Minimum block height to filter
            max_height: Maximum block height to filter
            account_index: Account index to query

        Returns:
            RPC result with transfers grouped by type
            Format: {"in": [...], "out": [...], "pending": [...], "pool": [...], ...}
        """
        params: dict[str, Any] = {
            "in": incoming,
            "out": outgoing,
            "pending": pending,
            "failed": failed,
            "pool": pool,
            "account_index": account_index,
        }
        if min_height is not None:
            params["min_height"] = min_height
        if max_height is not None:
            params["max_height"] = max_height
        if min_height is not None or max_height is not None:
            params["filter_by_height"] = True

        return await self._call("get_transfers", params)

    async def get_height(self) -> dict[str, Any]:
        """Get current blockchain height.

        Returns:
            RPC result with height: {"height": 1234567}
        """
        return await self._call("get_height")

    # ==========================================================================
    # Utility Methods
    # ==========================================================================

    async def get_version(self) -> dict[str, Any]:
        """Get RPC version information.

        Returns:
            RPC result with version info
        """
        return await self._call("get_version")

    async def get_address(self, account_index: int = 0) -> dict[str, Any]:
        """Get wallet address.

        Args:
            account_index: Account index (default 0)

        Returns:
            RPC result with address: {"address": "..."}
        """
        params = {"account_index": account_index}
        return await self._call("get_address", params)

    # ==========================================================================
    # Convenience Methods for Cheque Bot
    # ==========================================================================

    async def get_incoming_transfers(
        self,
        min_height: int | None = None,
        include_pool: bool = True,
    ) -> list[dict[str, Any]]:
        """Get all incoming transfers including mempool.

        This is the primary method used by the payment monitor
        to find incoming payments to cheques.

        Args:
            min_height: Minimum block height to filter (from cheque.min_height)
            include_pool: Whether to include mempool transactions

        Returns:
            List of transfer dictionaries with fields:
            - txid: Transaction hash
            - amount: Amount in atomic units
            - height: Block height (0 if in pool)
            - timestamp: Unix timestamp
            - confirmations: Number of confirmations
        """
        result = await self.get_transfers(
            incoming=True,
            pool=include_pool,
            min_height=min_height,
        )

        transfers: list[dict[str, Any]] = []

        # Confirmed incoming transfers
        if "in" in result:
            transfers.extend(result["in"])

        # Pool (mempool) transfers
        if include_pool and "pool" in result:
            for tx in result["pool"]:
                # Mark pool transactions with height 0
                tx = dict(tx)
                if "height" not in tx:
                    tx["height"] = 0
                transfers.append(tx)

        return transfers

    async def get_current_height(self) -> int:
        """Get current blockchain height as integer.

        Returns:
            Current blockchain height
        """
        result = await self.get_height()
        return int(result.get("height", 0))

    async def check_health(self) -> bool:
        """Check if RPC is accessible and responsive.

        Returns:
            True if RPC is healthy, False otherwise
        """
        try:
            await self.get_version()
            return True
        except Exception:
            return False
