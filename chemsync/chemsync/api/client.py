"""eLabFTW REST API v2 client."""

from __future__ import annotations

import logging
import time
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, message: str, status_code: int = 0, response: requests.Response | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class ElabFtwClient:
    """Client for eLabFTW API v2."""

    def __init__(self, url: str, api_key: str, timeout: int = 30):
        self.base = url.rstrip("/") + "/api/v2/"
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": api_key,
            "Content-Type": "application/json",
        })

    def _url(self, path: str) -> str:
        return urljoin(self.base, path.lstrip("/"))

    def _request(self, method: str, path: str, retries: int = 3, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = self.session.request(method, self._url(path), **kwargs)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                    logger.warning("Rate limited, waiting %ds", wait)
                    time.sleep(wait)
                    continue
                if resp.status_code >= 400:
                    raise ApiError(
                        f"{method} {path} -> {resp.status_code}: {resp.text[:200]}",
                        status_code=resp.status_code,
                        response=resp,
                    )
                return resp
            except requests.ConnectionError as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(2 ** attempt)
        raise ApiError(f"Connection failed after {retries + 1} attempts: {last_exc}")

    def _get(self, path: str, **params) -> dict | list:
        resp = self._request("GET", path, params=params)
        return resp.json()

    def _post(self, path: str, data: dict | None = None) -> requests.Response:
        return self._request("POST", path, json=data or {})

    def _patch(self, path: str, data: dict) -> requests.Response:
        return self._request("PATCH", path, json=data)

    @staticmethod
    def _extract_id_from_location(resp: requests.Response) -> int:
        """Extract entity ID from Location header (e.g. '.../items/123')."""
        loc = resp.headers.get("Location", "")
        if loc:
            return int(loc.rstrip("/").rsplit("/", 1)[-1])
        raise ApiError("No Location header in response")

    # --- Connection ---

    def test_connection(self) -> dict:
        """GET /api/v2/info - returns server info."""
        return self._get("info")

    def get_items_types(self) -> list[dict]:
        """GET /api/v2/items_types - list all item categories."""
        return self._get("items_types")

    # --- Items ---

    def get_items(self, cat: int, limit: int = 999) -> list[dict]:
        """GET /api/v2/items - list items by category."""
        return self._get("items", cat=cat, limit=limit, scope=2)

    def get_item(self, item_id: int) -> dict:
        """GET /api/v2/items/{id} - get single item with full details."""
        return self._get(f"items/{item_id}")

    def create_item(self, payload: dict) -> int:
        """POST /api/v2/items - create item, returns new ID."""
        resp = self._post("items", payload)
        return self._extract_id_from_location(resp)

    def patch_item(self, item_id: int, payload: dict) -> None:
        """PATCH /api/v2/items/{id} - update item fields."""
        self._patch(f"items/{item_id}", payload)

    # --- Compounds ---

    def get_compounds(self) -> list[dict]:
        """GET /api/v2/compounds - list all compounds."""
        return self._get("compounds")

    def create_compound(self, data: dict) -> int:
        """POST /api/v2/compounds - create/upsert compound.

        Server handles duplicate CAS via upsert (returns existing ID).
        """
        resp = self._post("compounds", data)
        return self._extract_id_from_location(resp)

    def link_compound(self, item_id: int, compound_id: int) -> None:
        """POST /items/{id}/compounds_links/{cid} - link compound to item.

        INSERT IGNORE - idempotent, safe to call multiple times.
        """
        try:
            self._post(f"items/{item_id}/compounds_links/{compound_id}")
        except ApiError as e:
            # 409 Conflict means link already exists - that's fine
            if e.status_code != 409:
                raise

    # --- Storage ---

    def get_storage_units(self) -> list[dict]:
        """GET /api/v2/storage_units - list all storage units."""
        return self._get("storage_units")

    def create_storage_unit(self, name: str, parent_id: int | None = None) -> int:
        """POST /api/v2/storage_units - create storage unit."""
        data: dict = {"name": name}
        if parent_id is not None:
            data["parent_id"] = parent_id
        resp = self._post("storage_units", data)
        return self._extract_id_from_location(resp)

    def resolve_storage_path(self, path: list[str]) -> int:
        """Resolve a hierarchical storage path, creating units as needed.

        E.g. ["WIN-2.202", "Chemikalienschrank"] -> creates/finds both levels.
        Returns the ID of the innermost (leaf) storage unit.
        """
        units = self.get_storage_units()
        parent_id: int | None = None

        for level_name in path:
            found = None
            for u in units:
                if u["name"] == level_name and u.get("parent_id") == parent_id:
                    found = u
                    break
            if found:
                parent_id = found["id"]
            else:
                parent_id = self.create_storage_unit(level_name, parent_id)
                # Refresh units list for next level lookup
                units = self.get_storage_units()

        if parent_id is None:
            raise ApiError(f"Could not resolve storage path: {path}")
        return parent_id

    # --- Containers ---

    def get_containers(self, item_id: int) -> list[dict]:
        """GET /api/v2/items/{id}/containers - list container links for item."""
        return self._get(f"items/{item_id}/containers")

    def create_container(self, item_id: int, storage_id: int, qty: float, unit: str) -> int:
        """POST /api/v2/items/{id}/containers - assign item to storage location."""
        data = {
            "storage_id": storage_id,
            "qty_stored": qty,
            "qty_unit": unit,
        }
        resp = self._post(f"items/{item_id}/containers", data)
        return self._extract_id_from_location(resp)

    def patch_container(self, item_id: int, link_id: int, qty: float, unit: str) -> None:
        """PATCH /api/v2/items/{id}/containers/{link_id} - update container qty."""
        self._patch(f"items/{item_id}/containers/{link_id}", {
            "qty_stored": qty,
            "qty_unit": unit,
        })
