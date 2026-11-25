"""Read existing account-scoped closure proof; never infer it from learning rows."""
import hashlib
import json
from pathlib import Path


def load_confirmed_outcomes(base, settings=None):
    from atlas_ai.config.settings import load_settings
    from atlas_ai.learning.closed_position_ledger import SCHEMA
    settings = settings or load_settings()
    account = hashlib.sha256(f'{settings.hfm_server}:{settings.hfm_login}:{settings.symbol}'.encode()).hexdigest()
    path = Path(base)/'performance'/f'closed_positions_{account[:16]}.json'
    if not path.exists(): return []
    document = json.loads(path.read_text(encoding='utf-8'))
    if document.get('schema') != SCHEMA or document.get('account_fingerprint') != account:
        raise ValueError('closed_outcome_account_identity_mismatch')
    result = []
    for position in document.get('positions', {}).values():
        if (position.get('state') != 'closed' or not position.get('strict_strategy_evidence')
                or position.get('manual_test') or not position.get('closed_at')): continue
        fills = [document.get('fills', {}).get(str(ticket), {}) for ticket in position.get('fill_tickets', [])]
        entries = [row for row in fills if row.get('entry_type') == 0]
        if not entries: continue
        entry = entries[0]
        result.append({'ticket': str(position.get('closed_fill_ticket') or position['position_id']),
            'position_id': position['position_id'], 'decision_id': entry.get('decision_id'),
            'strategy': position['strategy'], 'side': 'buy' if entry.get('deal_type') == 0 else 'sell',
            'time': position['closed_at'], 'net_pnl_zar': position['net_profit'], 'outcome': position['outcome'],
            'currency': document.get('currency', 'unknown'), 'broker_confirmed_closed': True,
            'source': 'account_scoped_closed_position_ledger',
            'confirmation_scope': 'balanced closed position with decision links; not proof of protected autonomous lifecycle'})
    return sorted(result, key=lambda row: (row['time'], row['ticket']))
