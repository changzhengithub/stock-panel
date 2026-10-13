"""Read-only upstream checks; never publishes quotes or replaces production history."""
import asyncio
import json

from app.jobs.concepts_tdx import fetch_blocks
from app.providers.free import FreeProvider, free_cutoff

result = {}
provider = FreeProvider()
try:
    try:
        rows = provider.tencent_snapshot(['000001.SZ'])
        result['quote'] = {
            'ok': bool(rows),
            'requested_snapshot_date': free_cutoff(),
            'source_dates': sorted({r['date'] for r in rows}),
            'source_times': sorted({r['time'] for r in rows}),
        }
    except Exception as exc:
        result['quote'] = {'ok': False, 'error': str(exc)}
    try:
        end = free_cutoff()
        raw = provider.tencent_history('000001', '20251013', end)
        adjusted = provider.tencent_history('000001', '20251013', end, adjusted=True)
        result['history'] = {
            'ok': bool(raw) and {r['date'] for r in raw} == {r['date'] for r in adjusted},
            'raw_bars': len(raw),
            'adjusted_bars': len(adjusted),
            'last_date': max(r['date'] for r in raw),
        }
    except Exception as exc:
        result['history'] = {'ok': False, 'error': str(exc)}
    try:
        blocks = asyncio.run(fetch_blocks())
        result['concepts'] = {'ok': len(blocks) >= 200, 'blocks': len(blocks)}
    except Exception as exc:
        result['concepts'] = {'ok': False, 'error': str(exc)}
finally:
    provider.close()
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if all(r['ok'] for r in result.values()) else 1)
