#!/usr/bin/env python3
"""
Validates the analyzer against all 41 human-written test cases.
ALL must return is_ai=False (zero false positives).
"""
import ast
import re
import os
import sys

# ── inline copy of analyze_contest_code ──────────────────────

def analyze_contest_code(source_code: str) -> dict:
    signals = []
    total_score = 0
    THRESHOLD = 40
    lines = source_code.splitlines()

    tree = None
    parse_error = None
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        parse_error = str(e)

    if re.search(r'if\s+__name__\s*==\s*["\']__main__["\']', source_code):
        total_score += 60
        signals.append(('強', 60, 'if __name__ == "__main__" ガード'))

    if tree is not None:
        docstring_locs = []
        if ast.get_docstring(tree):
            docstring_locs.append('module')
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if ast.get_docstring(node):
                    docstring_locs.append(node.name)
        if docstring_locs:
            score = min(50 + (len(docstring_locs) - 1) * 10, 80)
            total_score += score
            signals.append(('強', score, f'docstring × {len(docstring_locs)}'))

    if re.search(r'^\s*(from\s+typing\s+import|import\s+typing\b)', source_code, re.MULTILINE):
        total_score += 50
        signals.append(('強', 50, 'typing import'))

    if tree is not None and any(isinstance(n, ast.Try) for n in ast.walk(tree)):
        total_score += 40
        signals.append(('強', 40, 'try-except'))

    if re.search(r'^\s*(import\s+logging\b|from\s+logging\s+import)', source_code, re.MULTILINE):
        total_score += 55
        signals.append(('強', 55, 'logging'))

    if re.search(r'^\s*(import\s+argparse\b|from\s+argparse\s+import)', source_code, re.MULTILINE):
        total_score += 60
        signals.append(('強', 60, 'argparse'))

    has_dataclass = (
        re.search(r'^\s*(from\s+dataclasses\s+import|import\s+dataclasses\b)', source_code, re.MULTILINE)
        or re.search(r'@dataclass\b', source_code)
    )
    if has_dataclass:
        total_score += 45
        signals.append(('強', 45, 'dataclass'))

    if re.search(r'from\s+abc\s+import|import\s+abc\b', source_code):
        total_score += 40
        signals.append(('強', 40, 'abc'))

    has_main_def  = bool(re.search(r'^\s*def\s+main\s*\(\s*\)\s*:', source_code, re.MULTILINE))
    has_main_call = bool(re.search(r'^\s*main\s*\(\s*\)', source_code, re.MULTILINE))
    if has_main_def and has_main_call:
        total_score += 35
        signals.append(('中', 35, 'def main() + call'))

    if re.search(r'^__all__\s*=', source_code, re.MULTILINE):
        total_score += 25
        signals.append(('中', 25, '__all__'))

    if re.search(r'^\s*(from\s+pathlib\s+import|import\s+pathlib\b)', source_code, re.MULTILINE):
        total_score += 30
        signals.append(('中', 30, 'pathlib'))

    if re.search(r'^\s*(import\s+json\b|from\s+json\s+import)', source_code, re.MULTILINE):
        total_score += 25
        signals.append(('中', 25, 'json'))

    algorithmic_comments = re.findall(
        r'#\s+(?:Initialize|Compute|Calculate|Process|Handle|Check\s+if|Find\s+the|Sort\s+the|'
        r'Build\s+the|Create\s+the|Update\s+the|Read\s+the|Parse\s+the|Store\s+the|'
        r'Iterate|Traverse|Use\s+a|Get\s+the|Set\s+the|Add\s+the|Remove\s+the|'
        r'Return\s+the|Time\s+[Cc]omplexity|Space\s+[Cc]omplexity)[\w\s,.:]*',
        source_code
    )
    if len(algorithmic_comments) >= 3:
        score = min(len(algorithmic_comments) * 6, 24)
        total_score += score
        signals.append(('弱', score, f'verbose English comments × {len(algorithmic_comments)}'))

    if tree is not None:
        assert_count = sum(1 for n in ast.walk(tree) if isinstance(n, ast.Assert))
        if assert_count >= 2:
            total_score += 15
            signals.append(('弱', 15, f'assert × {assert_count}'))

    blank_count = sum(1 for l in lines if not l.strip())
    if len(lines) >= 20:
        blank_ratio = blank_count / len(lines)
        if blank_ratio > 0.38:
            total_score += 12
            signals.append(('弱', 12, f'blank ratio {blank_ratio:.0%}'))

    return {
        'is_ai': total_score >= THRESHOLD,
        'score': total_score,
        'signals': signals,
        'parse_error': parse_error,
    }


# ── run validation ───────────────────────────

TEST_DIR = r"C:\Users\hp\Documents\Investment\test case"

files = sorted(f for f in os.listdir(TEST_DIR)
               if f.startswith('test') and f.endswith('.txt'))

print(f"Validating {len(files)} test cases...\n")

false_positives = []
for fname in files:
    path = os.path.join(TEST_DIR, fname)
    with open(path, encoding='utf-8', errors='replace') as fh:
        src = fh.read()
    result = analyze_contest_code(src)
    status = 'PASS' if not result['is_ai'] else 'FAIL (FALSE POSITIVE!)'
    if result['is_ai']:
        false_positives.append((fname, result['score'], result['signals']))
    print(f"  {status:30s} {fname:15s} score={result['score']:3d}  "
          f"signals={[s[2] for s in result['signals']]}")

print()
if false_positives:
    print(f"FAILED: {len(false_positives)} false positives detected!")
    for fname, score, sigs in false_positives:
        print(f"  {fname}: score={score}, signals={[s[2] for s in sigs]}")
    sys.exit(1)
else:
    print(f"ALL {len(files)} TEST CASES PASSED (zero false positives)")
