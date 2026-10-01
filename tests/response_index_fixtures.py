"""Explicit legacy history fixtures; never select JSON for normal runtime use."""
import json
from pathlib import Path

from fruth_services import response_frames as frames, response_index_sqlite as storage
from fruth_services.response_index_maintenance import _rollback_payload


def legacy_history(root, values):
    """Create old canonical rows/CAS and a derived JSON map in a temporary root.

    This deliberately writes a historical fixture rather than using the current
    runtime writer to enable a legacy backend. Production migration uses the
    existing maintenance owner.
    """
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    ledger=root/'responses.jsonl'
    previous=[]
    with ledger.open('wb') as handle:
        for value in values:
            enriched=frames.enrich_response_frame_metadata(value,previous_frames=previous,
                                                          force_append_sequence=True)
            same=[v for v in previous if v.get('response_id')==enriched.get('response_id')]
            compact=frames.compact_response_frame_for_ledger(
                enriched,frames_dir=root,parent_frame=same[-1] if same else None)
            handle.write(json.dumps(frames._json_safe(compact),ensure_ascii=False,sort_keys=True).encode()+b'\n')
            previous.append(enriched)
    scan=frames._scan_response_frame_ledger_index_truth(ledger,include_entries=True)
    assert scan['ok'],scan
    payload=_rollback_payload(ledger,scan)
    (root/storage.LEGACY_NAME).write_bytes(storage.encode(payload)+b'\n')
    return ledger
