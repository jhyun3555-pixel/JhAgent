"""Run any single agent: python3 -m backend.worker insight < input.json."""
import importlib
import json
import sys
from backend.catalog import AGENT_IDS


def main():
    try:
        agent_id = sys.argv[1]
        if agent_id not in AGENT_IDS:
            raise ValueError('Unknown agent')
        payload = json.load(sys.stdin)
        if payload.get('contract_version') != 1 or not isinstance(payload.get('request'), dict):
            raise ValueError('contract_version=1 및 request 객체가 필요합니다.')
        output = importlib.import_module('backend.agents.' + agent_id).run(payload)
        if not isinstance(output, dict) or not isinstance(output.get('summary'), str):
            raise ValueError('Agent output must contain summary')
        print(json.dumps({'ok': True, 'output': output}, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == '__main__':
    main()
