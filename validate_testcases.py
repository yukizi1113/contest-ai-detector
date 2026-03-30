#!/usr/bin/env python3
"""
Validates the detector against all 41 human-written test cases and a few
obvious AI-like smoke cases.
"""

import ast
import sys
from pathlib import Path

from contest_ai_detector_core import analyze_contest_code, decode_uploaded_text


TEST_DIR = Path(r"C:\Users\hp\Documents\Investment\test case")
POSITIVE_CASES = [
    (
        'typing_and_main_guard',
        '''from typing import List

def solve() -> int:
    values: List[int] = [1, 2, 3]
    return sum(values)

if __name__ == "__main__":
    print(solve())
''',
    ),
    (
        'dataclass_usage',
        '''from dataclasses import dataclass

@dataclass
class Edge:
    to: int
    cost: int
''',
    ),
    (
        'pathlib_json_and_main',
        '''import json
from pathlib import Path

def main():
    payload = json.loads(Path("input.json").read_text())
    print(payload)

main()
''',
    ),
]


def validate_human_cases():
    files = sorted(
        path for path in TEST_DIR.iterdir()
        if path.name.startswith('test') and path.suffix == '.txt'
    )

    print(f'Validating {len(files)} human-written test cases...\n')
    false_positives = []

    for path in files:
        source_code = path.read_text(encoding='utf-8', errors='replace')
        result = analyze_contest_code(source_code)
        status = 'PASS' if not result['is_ai'] else 'FAIL (FALSE POSITIVE!)'
        if result['is_ai']:
            false_positives.append((path.name, result['score'], result['signals']))
        print(
            f'  {status:30s} {path.name:15s} score={result["score"]:3d}  '
            f'signals={[signal["title"] for signal in result["signals"]]}'
        )

    return len(files), false_positives


def validate_positive_cases():
    print('\nValidating obvious AI-like smoke cases...\n')
    misses = []

    for name, source_code in POSITIVE_CASES:
        result = analyze_contest_code(source_code)
        status = 'PASS' if result['is_ai'] else 'FAIL (MISSED AI SIGNAL!)'
        if not result['is_ai']:
            misses.append((name, result['score'], result['signals']))
        print(
            f'  {status:30s} {name:24s} score={result["score"]:3d}  '
            f'signals={[signal["title"] for signal in result["signals"]]}'
        )

    return misses


def validate_bom_handling():
    print('\nValidating UTF-8 BOM decoding...\n')

    decoded = decode_uploaded_text(b'\xef\xbb\xbfprint(1)\n')
    if decoded.startswith('\ufeff'):
        return 'decoded text still contains BOM'

    try:
        ast.parse(decoded)
    except SyntaxError as exc:
        return f'BOM-decoded text is not parseable: {exc}'

    print('  PASS                           utf8_bom_input            decoded and parsed successfully')
    return None


def main():
    total_files, false_positives = validate_human_cases()
    positive_misses = validate_positive_cases()
    bom_failure = validate_bom_handling()

    print()
    if false_positives or positive_misses or bom_failure:
        if false_positives:
            print(f'FAILED: {len(false_positives)} false positives detected!')
            for name, score, signals in false_positives:
                print(f'  {name}: score={score}, signals={[signal["title"] for signal in signals]}')
        if positive_misses:
            print(f'FAILED: {len(positive_misses)} obvious AI-like cases were missed!')
            for name, score, signals in positive_misses:
                print(f'  {name}: score={score}, signals={[signal["title"] for signal in signals]}')
        if bom_failure:
            print(f'FAILED: UTF-8 BOM handling check failed: {bom_failure}')
        sys.exit(1)

    print(f'ALL {total_files} HUMAN TEST CASES PASSED (zero false positives)')
    print(f'ALL {len(POSITIVE_CASES)} OBVIOUS AI-LIKE SMOKE CASES WERE DETECTED')
    print('UTF-8 BOM INPUT IS HANDLED CORRECTLY')


if __name__ == '__main__':
    main()
