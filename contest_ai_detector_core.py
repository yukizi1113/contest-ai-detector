"""
Core heuristics for the contest code AI detector.
"""

import ast
import re


THRESHOLD = 40

_ALGORITHMIC_COMMENT_PATTERN = re.compile(
    r'#\s+(?:Initialize|Compute|Calculate|Process|Handle|Check\s+if|Find\s+the|'
    r'Sort\s+the|Build\s+the|Create\s+the|Update\s+the|Read\s+the|Parse\s+the|'
    r'Store\s+the|Iterate|Traverse|Use\s+a|Get\s+the|Set\s+the|Add\s+the|'
    r'Remove\s+the|Return\s+the|Time\s+[Cc]omplexity|Space\s+[Cc]omplexity)'
    r'[\w\s,.:]*'
)


def _parse_tree(source_code):
    try:
        return ast.parse(source_code), None
    except SyntaxError as exc:
        return None, str(exc)


def _imported_modules(tree):
    modules = set()
    if tree is None:
        return modules

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split('.')[0])
    return modules


def _attribute_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _attribute_name(node.value)
        if base:
            return f'{base}.{node.attr}'
        return node.attr
    return ''


def _has_dataclass_decorator(tree):
    if tree is None:
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for decorator in node.decorator_list:
                name = _attribute_name(decorator)
                if name == 'dataclass' or name.endswith('.dataclass'):
                    return True
    return False


def _is_main_guard_compare(node):
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
        return False
    if len(node.comparators) != 1:
        return False

    left = node.left
    right = node.comparators[0]
    left_value = left.value if isinstance(left, ast.Constant) else None
    right_value = right.value if isinstance(right, ast.Constant) else None

    return (
        (isinstance(left, ast.Name) and left.id == '__name__' and right_value == '__main__')
        or (isinstance(right, ast.Name) and right.id == '__name__' and left_value == '__main__')
    )


def _has_main_guard(tree):
    if tree is None:
        return False
    return any(
        isinstance(node, ast.If) and _is_main_guard_compare(node.test)
        for node in ast.walk(tree)
    )


def _has_zero_arg_main_def(tree):
    if tree is None:
        return False

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'main':
            args = node.args
            arg_count = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
            if arg_count == 0 and args.vararg is None and args.kwarg is None:
                return True
    return False


def _has_zero_arg_main_call(tree):
    if tree is None:
        return False

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == 'main'
            and not node.args
            and not node.keywords
        ):
            return True
    return False


def _has_dunder_all_assignment(tree):
    if tree is None:
        return False

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == '__all__':
                    return True
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == '__all__':
                return True
    return False


def _module_imported_by_regex(source_code, module_name):
    pattern = (
        rf'^\s*(?:from\s+{re.escape(module_name)}(?:\.|\s+import)'
        rf'|import\s+{re.escape(module_name)}\b)'
    )
    return bool(re.search(pattern, source_code, re.MULTILINE))


def analyze_contest_code(source_code: str) -> dict:
    """
    競技プログラミング提出物が AI 生成か人間記述かを判定する。

    スコアが THRESHOLD 以上 → AI 生成と判定
    スコアが THRESHOLD 未満 → 人間記述と判定
    """

    signals = []
    total_score = 0
    lines = source_code.splitlines()

    tree, parse_error = _parse_tree(source_code)
    modules = _imported_modules(tree)

    has_main_guard = _has_main_guard(tree) or (
        tree is None
        and bool(re.search(r'if\s+__name__\s*==\s*["\']__main__["\']', source_code))
    )
    if has_main_guard:
        score = 60
        total_score += score
        signals.append({
            'level': '強',
            'score': score,
            'title': '`if __name__ == "__main__":` ガード',
            'detail': (
                'スクリプト末尾の `if __name__ == "__main__":` ブロックが検出されました。'
                '競技プログラミングの提出物は単一スクリプトとして直接実行されるため、'
                'このガードは不要であり、AI 生成コードや本番向けモジュールに典型的なパターンです。'
            ),
        })

    if tree is not None:
        docstring_locs = []
        if ast.get_docstring(tree):
            docstring_locs.append('モジュールレベル')
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if ast.get_docstring(node):
                    docstring_locs.append(f'`{node.name}`')
        if docstring_locs:
            score = min(50 + (len(docstring_locs) - 1) * 10, 80)
            total_score += score
            signals.append({
                'level': '強',
                'score': score,
                'title': f'ドキュメント文字列 (docstring) × {len(docstring_locs)} 箇所',
                'detail': (
                    f'{", ".join(docstring_locs[:4])} にて三重引用符による docstring が検出されました。'
                    '競技プログラミングの提出物では関数・クラスに説明文字列を付けることは極めて稀です。'
                ),
            })

    has_typing = ('typing' in modules) or (
        tree is None and _module_imported_by_regex(source_code, 'typing')
    )
    if has_typing:
        score = 50
        total_score += score
        signals.append({
            'level': '強',
            'score': score,
            'title': '`typing` モジュールのインポート',
            'detail': (
                '型ヒント管理のための `typing` モジュールがインポートされています。'
                '競技プログラミングでは型注釈の厳密な管理は必要とされず、このインポートは見られません。'
            ),
        })

    has_try_except = (
        any(isinstance(node, ast.Try) for node in ast.walk(tree))
        if tree is not None
        else bool(re.search(r'^\s*try\s*:', source_code, re.MULTILINE))
    )
    if has_try_except:
        score = 40
        total_score += score
        signals.append({
            'level': '強',
            'score': score,
            'title': '`try-except` ブロック',
            'detail': (
                '例外処理ブロックが検出されました。'
                '競技プログラミングではジャッジの入力は問題の制約を満たすことが保証されているため、'
                '例外処理は通常記述しません。'
            ),
        })

    has_logging = ('logging' in modules) or (
        tree is None and _module_imported_by_regex(source_code, 'logging')
    )
    if has_logging:
        score = 55
        total_score += score
        signals.append({
            'level': '強',
            'score': score,
            'title': '`logging` モジュールのインポート',
            'detail': 'ログ出力管理モジュールがインポートされています。競技プログラミングでは使用しません。',
        })

    has_argparse = ('argparse' in modules) or (
        tree is None and _module_imported_by_regex(source_code, 'argparse')
    )
    if has_argparse:
        score = 60
        total_score += score
        signals.append({
            'level': '強',
            'score': score,
            'title': '`argparse` モジュールのインポート',
            'detail': 'コマンドライン引数解析モジュールがインポートされています。競技プログラミングでは使用しません。',
        })

    has_dataclass = (
        'dataclasses' in modules
        or _has_dataclass_decorator(tree)
        or (tree is None and (
            _module_imported_by_regex(source_code, 'dataclasses')
            or bool(re.search(r'@dataclass\b', source_code))
        ))
    )
    if has_dataclass:
        score = 45
        total_score += score
        signals.append({
            'level': '強',
            'score': score,
            'title': '`dataclasses` / `@dataclass` の使用',
            'detail': 'データクラスモジュールまたはデコレータが検出されました。競技プログラミングでは使用しません。',
        })

    has_abc = ('abc' in modules) or (
        tree is None and _module_imported_by_regex(source_code, 'abc')
    )
    if has_abc:
        score = 40
        total_score += score
        signals.append({
            'level': '強',
            'score': score,
            'title': '`abc` (抽象基底クラス) のインポート',
            'detail': '抽象基底クラスモジュールがインポートされています。競技プログラミングでは使用しません。',
        })

    has_main_pattern = (
        (_has_zero_arg_main_def(tree) and _has_zero_arg_main_call(tree))
        if tree is not None
        else bool(re.search(r'^\s*def\s+main\s*\(\s*\)\s*:', source_code, re.MULTILINE))
        and bool(re.search(r'^\s*main\s*\(\s*\)', source_code, re.MULTILINE))
    )
    if has_main_pattern:
        score = 35
        total_score += score
        signals.append({
            'level': '中',
            'score': score,
            'title': '`def main():` + `main()` 呼び出しパターン',
            'detail': (
                '`def main()` 関数の定義と明示的な呼び出しが検出されました。'
                'AI 生成コードに非常に多い構造ですが、競技プログラミングでは不要です。'
            ),
        })

    has_dunder_all = _has_dunder_all_assignment(tree) or (
        tree is None and bool(re.search(r'^__all__\s*=', source_code, re.MULTILINE))
    )
    if has_dunder_all:
        score = 25
        total_score += score
        signals.append({
            'level': '中',
            'score': score,
            'title': '`__all__` の定義',
            'detail': 'モジュール公開 API を定義する `__all__` が検出されました。競技プログラミングでは使用しません。',
        })

    has_pathlib = ('pathlib' in modules) or (
        tree is None and _module_imported_by_regex(source_code, 'pathlib')
    )
    if has_pathlib:
        score = 30
        total_score += score
        signals.append({
            'level': '中',
            'score': score,
            'title': '`pathlib` モジュールのインポート',
            'detail': (
                'パス操作モジュールがインポートされています。'
                '競技プログラミングでは標準入力を使用するためファイルパス操作は不要です。'
            ),
        })

    has_json = ('json' in modules) or (
        tree is None and _module_imported_by_regex(source_code, 'json')
    )
    if has_json:
        score = 25
        total_score += score
        signals.append({
            'level': '中',
            'score': score,
            'title': '`json` モジュールのインポート',
            'detail': (
                'JSON 処理モジュールがインポートされています。'
                '競技プログラミングの入出力は通常テキスト形式であり、JSON は使用しません。'
            ),
        })

    algorithmic_comments = _ALGORITHMIC_COMMENT_PATTERN.findall(source_code)
    if len(algorithmic_comments) >= 3:
        score = min(len(algorithmic_comments) * 6, 24)
        total_score += score
        examples = [comment.strip()[:60] for comment in algorithmic_comments[:2]]
        signals.append({
            'level': '弱',
            'score': score,
            'title': f'英語の説明的アルゴリズムコメント × {len(algorithmic_comments)} 箇所',
            'detail': (
                f'アルゴリズムの手順を英語で説明するコメントが {len(algorithmic_comments)} 箇所検出されました。'
                f'例: {examples}。競技プログラミングの人間提出物では稀なパターンです。'
            ),
        })

    if tree is not None:
        assert_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.Assert))
        if assert_count >= 2:
            score = 15
            total_score += score
            signals.append({
                'level': '弱',
                'score': score,
                'title': f'`assert` 文 × {assert_count} 個',
                'detail': '複数のデバッグ用 `assert` 文が検出されました。競技プログラミングでは通常使用しません。',
            })

    blank_count = sum(1 for line in lines if not line.strip())
    if len(lines) >= 20:
        blank_ratio = blank_count / len(lines)
        if blank_ratio > 0.38:
            score = 12
            total_score += score
            signals.append({
                'level': '弱',
                'score': score,
                'title': f'高い空行密度 ({blank_ratio:.0%})',
                'detail': (
                    f'全 {len(lines)} 行のうち {blank_count} 行（{blank_ratio:.0%}）が空行です。'
                    'AI は可読性向上のために多くの空行を挿入する傾向があります。'
                ),
            })

    return {
        'is_ai': total_score >= THRESHOLD,
        'score': total_score,
        'threshold': THRESHOLD,
        'signals': signals,
        'parse_error': parse_error,
        'stats': {
            'total_lines': len(lines),
            'blank_lines': blank_count,
            'non_blank_lines': len(lines) - blank_count,
        },
    }


def decode_uploaded_text(content: bytes) -> str:
    for encoding in ['utf-8-sig', 'utf-8', 'shift-jis', 'cp932']:
        try:
            return content.decode(encoding)
        except (UnicodeDecodeError, ValueError):
            pass
    return content.decode('utf-8', errors='replace')
