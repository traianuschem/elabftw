"""Sync engine: orchestrates create/update operations against eLabFTW API."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from chemsync.api.client import ApiError, ElabFtwClient
from chemsync.config import AppConfig
from chemsync.engine.diff_engine import build_elab_records, compute_diffs, summarize_diffs
from chemsync.engine.metadata_builder import build_metadata, merge_metadata
from chemsync.models.chemical import ChemicalRecord
from chemsync.models.diff import MatchStatus, RecordDiff
from chemsync.models.mapping import MappingProfile
from chemsync.source.csv_reader import CsvReader

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    log: list[str] = field(default_factory=list)


class SyncEngine:
    """Orchestrates synchronization between CSV source and eLabFTW."""

    def __init__(self, client: ElabFtwClient, category_id: int = 17, dry_run: bool = True):
        self.client = client
        self.category_id = category_id
        self.dry_run = dry_run

    def sync_records(
        self,
        diffs: list[RecordDiff],
        on_progress: callable | None = None,
    ) -> SyncResult:
        """Execute sync for selected diffs.

        Args:
            diffs: List of RecordDiff to sync (only selected ones are processed).
            on_progress: Optional callback(current, total, message) for progress reporting.
        """
        result = SyncResult()
        selected = [d for d in diffs if d.selected and d.status in (MatchStatus.NEW, MatchStatus.CHANGED)]
        total = len(selected)

        for i, diff in enumerate(selected, 1):
            msg_prefix = f"[{i}/{total}]"
            try:
                if diff.status == MatchStatus.NEW:
                    self._create_record(diff, result, msg_prefix)
                elif diff.status == MatchStatus.CHANGED:
                    self._update_record(diff, result, msg_prefix)
            except ApiError as e:
                result.errors += 1
                err_msg = f"{msg_prefix} ERROR: {diff.display_name} - {e}"
                result.log.append(err_msg)
                logger.error(err_msg)
            except Exception as e:
                result.errors += 1
                err_msg = f"{msg_prefix} UNEXPECTED ERROR: {diff.display_name} - {e}"
                result.log.append(err_msg)
                logger.exception(err_msg)

            if on_progress:
                on_progress(i, total, result.log[-1] if result.log else "")

        summary = (
            f"Sync complete: {result.created} created, {result.updated} updated, "
            f"{result.skipped} skipped, {result.errors} errors"
        )
        result.log.append(summary)
        logger.info(summary)
        return result

    def _create_record(self, diff: RecordDiff, result: SyncResult, prefix: str) -> None:
        """Create a new item in eLabFTW."""
        src = diff.source_record
        if not src:
            return

        result.log.append(f"{prefix} CREATE: {src.title} (CAS {src.compound.cas_number if src.compound else 'N/A'})")

        if self.dry_run:
            result.log.append(f"  [DRY-RUN] Would create compound, item, links, storage")
            result.created += 1
            return

        # 1. Create/upsert compound
        compound_id = None
        if src.compound and src.compound.cas_number:
            compound_id = self.client.create_compound(src.compound.to_api_dict())
            result.log.append(f"  -> Compound #{compound_id} (upsert)")

        # 2. Create item
        metadata = build_metadata(src)
        item_payload = {
            "category": self.category_id,
            "title": src.title,
            "metadata": metadata,
            "canread_base": src.canread_base,
            "canwrite_base": src.canwrite_base,
        }
        if src.tags:
            item_payload["tags"] = src.tags

        item_id = self.client.create_item(item_payload)
        result.log.append(f"  -> Item #{item_id} created")

        # 3. Link compound
        if compound_id:
            self.client.link_compound(item_id, compound_id)
            result.log.append(f"  -> Compound linked")

        # 4. Storage + Container
        if src.container and src.container.storage_path:
            storage_id = self.client.resolve_storage_path(src.container.storage_path)
            storage_display = " > ".join(src.container.storage_path)
            result.log.append(f"  -> Storage: {storage_display} (#{storage_id})")

            self.client.create_container(
                item_id, storage_id,
                src.container.qty_stored, src.container.qty_unit,
            )
            result.log.append(
                f"  -> Container assigned ({src.container.qty_stored} {src.container.qty_unit})"
            )

        result.created += 1

    def _update_record(self, diff: RecordDiff, result: SyncResult, prefix: str) -> None:
        """Update an existing item in eLabFTW."""
        src = diff.source_record
        target = diff.target_record
        if not src or not target or not target.elabftw_item_id:
            return

        item_id = target.elabftw_item_id
        changed_fields = [d.field_name for d in diff.field_diffs if d.is_different]
        result.log.append(
            f"{prefix} UPDATE: {src.title} (CAS {src.compound.cas_number if src.compound else 'N/A'}) "
            f"[{len(changed_fields)} fields: {', '.join(changed_fields[:5])}]"
        )

        if self.dry_run:
            result.log.append(f"  [DRY-RUN] Would update item #{item_id}")
            result.updated += 1
            return

        # 1. Patch item (metadata + title + hide_main_text)
        # Use merge to preserve existing extra_fields not in CSV
        existing_item = self.client.get_item(item_id)
        metadata = merge_metadata(existing_item.get("metadata"), src)

        patch_payload: dict = {
            "metadata": metadata,
            "title": src.title,
            "hide_main_text": 1 if src.hide_main_text else 0,
        }
        self.client.patch_item(item_id, patch_payload)
        result.log.append(f"  -> PATCH items/{item_id}: metadata, title")

        # 2. Compound upsert + link
        if src.compound and src.compound.cas_number:
            compound_id = self.client.create_compound(src.compound.to_api_dict())
            self.client.link_compound(item_id, compound_id)
            result.log.append(f"  -> Compound #{compound_id} linked")

        # 3. Container update
        if src.container and src.container.storage_path:
            # Check if container assignment changed
            container_changed = any(
                d.field_name in ("qty_stored", "qty_unit") and d.is_different
                for d in diff.field_diffs
            )
            if container_changed and target.container and target.container.container_link_id:
                self.client.patch_container(
                    item_id, target.container.container_link_id,
                    src.container.qty_stored, src.container.qty_unit,
                )
                result.log.append(f"  -> Container updated")
            elif not target.container:
                storage_id = self.client.resolve_storage_path(src.container.storage_path)
                self.client.create_container(
                    item_id, storage_id,
                    src.container.qty_stored, src.container.qty_unit,
                )
                result.log.append(f"  -> Container created")

        result.updated += 1


def run_cli_sync(
    csv_path: str,
    mapping_path: str | None,
    url: str | None,
    api_key: str | None,
    category: int = 17,
    dry_run: bool = True,
) -> None:
    """Run sync from CLI (non-GUI mode)."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Load config
    config = AppConfig.load()
    url = url or config.api_url
    api_key = api_key or config.api_key

    if not url or not api_key:
        print("ERROR: API URL and key required. Use --url and --api-key or configure in ~/.chemsync/config.json",
              file=sys.stderr)
        sys.exit(1)

    # Load mapping profile
    if mapping_path:
        profile = MappingProfile.load(mapping_path)
    else:
        # Try default
        default_path = Path(__file__).parent.parent.parent / "mappings" / "default_chemdb.json"
        if default_path.exists():
            profile = MappingProfile.load(default_path)
        else:
            print("ERROR: No mapping profile specified. Use --mapping or create mappings/default_chemdb.json",
                  file=sys.stderr)
            sys.exit(1)

    # Load CSV
    reader = CsvReader()
    records, room = reader.load(csv_path, profile)
    print(f"Loaded {len(records)} records from CSV (room: {room})")

    # Connect to eLabFTW
    client = ElabFtwClient(url, api_key)
    info = client.test_connection()
    print(f"Connected to eLabFTW {info.get('elabftw_version', '?')}")

    # Load existing items
    print(f"Loading existing items (category={category})...")
    elab_items = client.get_items(category)
    elab_records = build_elab_records(elab_items)
    print(f"Found {len(elab_records)} existing items")

    # Compute diffs
    diffs = compute_diffs(records, elab_records)
    summary = summarize_diffs(diffs)
    print(f"\nDiff: {summary['new']} new | {summary['changed']} changed | "
          f"{summary['unchanged']} unchanged | {summary['missing']} missing in source")

    if dry_run:
        print("\n--- DRY RUN MODE ---")

    # Sync
    engine = SyncEngine(client, category, dry_run=dry_run)
    result = engine.sync_records(diffs, on_progress=lambda cur, tot, msg: print(msg))

    print(f"\n{'='*60}")
    print(f"Result: {result.created} created, {result.updated} updated, "
          f"{result.skipped} skipped, {result.errors} errors")
