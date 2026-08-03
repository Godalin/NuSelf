"""Delivery-record persistence and state transitions."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace

from nuself.config.settings import RuntimePaths
from nuself.delivery.model import AdapterResult, DeliveryRecord, DeliveryStatus
from nuself.runtime.clock import utc_now_iso
from nuself.runtime.context import RuntimeContext
from nuself.runtime.observability import decode_observed_record
from nuself.storage.contract import StorageBackend, validate_storage_key
from nuself.storage.filesystem import blocking_private_file_lock


class DeliveryStore:
    def __init__(self, paths: RuntimePaths, backend: StorageBackend) -> None:
        self._backend = backend
        self._collection = backend.collection("delivery_records")
        self._root = paths.authority_root
        self._locks = paths.authority_root / "delivery" / "locks"

    def lock(self, record_id: str) -> AbstractContextManager[None]:
        validate_storage_key(record_id)
        return blocking_private_file_lock(self._locks / f"{record_id}.lock")

    def list(self, status: DeliveryStatus | None = None) -> list[DeliveryRecord]:
        records: list[DeliveryRecord] = []
        for wire in self._collection.list():
            record = decode_observed_record(
                wire, DeliveryRecord.from_wire, component="delivery",
                collection="delivery_records", project_root=self._root,
            )
            if record is not None and (status is None or record.status == status):
                records.append(record)
        return records

    def get(self, record_id: str) -> DeliveryRecord:
        wire = self._collection.get(record_id)
        if wire is None:
            raise KeyError(record_id)
        return DeliveryRecord.from_wire(wire)

    def request(self, item_id: str, *, context: RuntimeContext) -> DeliveryRecord:
        record_id = f"delivery-{item_id}"
        with self._backend.transaction():
            wire = self._collection.get(record_id)
            if wire is not None:
                return DeliveryRecord.from_wire(wire)
            record = DeliveryRecord(id=record_id, item_id=item_id, context=context)
            self._collection.put(record.id, record.to_wire())
            return record

    def prepare(self, record_id: str, adapters: tuple[str, ...]) -> DeliveryRecord:
        with self._backend.transaction():
            record = self.get(record_id)
            if record.required_adapters:
                return record
            updated = replace(record, required_adapters=adapters,
                              results={key: AdapterResult() for key in adapters})
            self._save(updated)
            return updated

    def recover(self, record_id: str) -> DeliveryRecord:
        with self._backend.transaction():
            record = self.get(record_id)
            results = dict(record.results)
            changed = False
            for key, result in results.items():
                if result.status == "delivering":
                    results[key] = replace(result, status="uncertain")
                    changed = True
            updated = replace(record, results=results) if changed else record
            if changed:
                self._save(updated)
            return updated

    def begin(self, record_id: str, adapter: str) -> DeliveryRecord:
        with self._backend.transaction():
            record = self.get(record_id)
            result = record.results[adapter]
            if result.status != "pending":
                return record
            results = dict(record.results)
            results[adapter] = AdapterResult("delivering", result.attempts + 1)
            updated = replace(record, results=results)
            self._save(updated)
            return updated

    def finish_adapter(self, record_id: str, adapter: str, *, success: bool) -> DeliveryRecord:
        with self._backend.transaction():
            record = self.get(record_id)
            result = record.results[adapter]
            results = dict(record.results)
            results[adapter] = AdapterResult(
                "sent" if success else "failed", result.attempts,
                utc_now_iso() if success else None,
            )
            updated = replace(record, results=results)
            self._save(updated)
            return updated

    def finalize(self, record_id: str) -> DeliveryRecord:
        with self._backend.transaction():
            record = self.get(record_id)
            states = tuple(result.status for result in record.results.values())
            status: DeliveryStatus = (
                "pending" if not states or any(x in {"pending", "delivering"} for x in states)
                else "sent" if all(x == "sent" for x in states)
                else "failed"
            )
            updated = replace(record, status=status)
            self._save(updated)
            return updated

    def _save(self, record: DeliveryRecord) -> None:
        self._collection.put(record.id, record.to_wire())
