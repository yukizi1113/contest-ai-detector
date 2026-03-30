"""
競技プログラミング提出物 AI生成コード判定ツール
Contest Code AI Detector

Google Colaboratory での実行方法:
  1. このファイルをアップロード後、以下のセルで実行してください:
       %run contest_ai_detector.py
  2. 判定したい .txt ファイルのアップロードダイアログが表示されます

設計方針:
  - 偽陽性（人間 → AI 誤判定）は絶対に許容しない
  - 偽陰性（AI → 人間 誤判定）は許容する
  - 最小限の変数名・コメント無し・汎用的命名はシグナルとして使用しない
"""

import ast
import re
import zipfile
import io
from IPython.display import HTML, display


# ════════════════════════════════════════════════════════
#  コア分析関数
# ════════════════════════════════════════════════════════

def analyze_contest_code(source_code: str) -> dict:
    """
    競技プログラミング提出物が AI 生成か人間記述かを判定する。

    スコアが THRESHOLD(40) 以上 → AI 生成と判定
    スコアが THRESHOLD 未満    → 人間記述と判定
    """

    signals = []
    total_score = 0
    THRESHOLD = 40

    lines = source_code.splitlines()

    # AST 解析（パースできない場合は None）
    tree = None
    parse_error = None
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        parse_error = str(e)

    # ── 強シグナル（単独でしきい値到達 >= 40） ──────────────

    # 1. if __name__ == "__main__" ガード
    if re.search(r'if\s+__name__\s*==\s*["\']__main__["\']', source_code):
        score = 60
        total_score += score
        signals.append(dict(
            level='強', score=score,
            title='`if __name__ == "__main__":` ガード',
            detail=(
                'スクリプト末尾の `if __name__ == "__main__":` ブロックが検出されました。'
                '競技プログラミングの提出物は単一スクリプトとして直接実行されるため、'
                'このガードは不要であり、AI 生成コードや本番向けモジュールに典型的なパターンです。'
            )
        ))

    # 2. ドキュメント文字列 (docstring)
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
            loc_str = ', '.join(docstring_locs[:4])
            signals.append(dict(
                level='強', score=score,
                title=f'ドキュメント文字列 (docstring) × {len(docstring_locs)} 箇所',
                detail=(
                    f'{loc_str} にて三重引用符による docstring が検出されました。'
                    '競技プログラミングの提出物では関数・クラスに説明文字列を付けることは極めて稀です。'
                )
            ))

    # 3. typing モジュールのインポート
    if re.search(r'^\s*(from\s+typing\s+import|import\s+typing\b)', source_code, re.MULTILINE):
        score = 50
        total_score += score
        signals.append(dict(
            level='強', score=score,
            title='`typing` モジュールのインポート',
            detail=(
                '型ヒント管理のための `typing` モジュールがインポートされています。'
                '競技プログラミングでは型注釈の厳密な管理は必要とされず、このインポートは見られません。'
            )
        ))

    # 4. try-except ブロック
    if tree is not None and any(isinstance(n, ast.Try) for n in ast.walk(tree)):
        score = 40
        total_score += score
        signals.append(dict(
            level='強', score=score,
            title='`try-except` ブロック',
            detail=(
                '例外処理ブロックが検出されました。'
                '競技プログラミングではジャッジの入力は問題の制約を満たすことが保証されているため、'
                '例外処理は通常記述しません。'
            )
        ))

    # 5. logging モジュール
    if re.search(r'^\s*(import\s+logging\b|from\s+logging\s+import)', source_code, re.MULTILINE):
        score = 55
        total_score += score
        signals.append(dict(
            level='強', score=score,
            title='`logging` モジュールのインポート',
            detail='ログ出力管理モジュールがインポートされています。競技プログラミングでは使用しません。'
        ))

    # 6. argparse モジュール
    if re.search(r'^\s*(import\s+argparse\b|from\s+argparse\s+import)', source_code, re.MULTILINE):
        score = 60
        total_score += score
        signals.append(dict(
            level='強', score=score,
            title='`argparse` モジュールのインポート',
            detail='コマンドライン引数解析モジュールがインポートされています。競技プログラミングでは使用しません。'
        ))

    # 7. dataclasses モジュール / @dataclass デコレータ
    has_dataclass = (
        re.search(r'^\s*(from\s+dataclasses\s+import|import\s+dataclasses\b)', source_code, re.MULTILINE)
        or re.search(r'@dataclass\b', source_code)
    )
    if has_dataclass:
        score = 45
        total_score += score
        signals.append(dict(
            level='強', score=score,
            title='`dataclasses` / `@dataclass` の使用',
            detail='データクラスモジュールまたはデコレータが検出されました。競技プログラミングでは使用しません。'
        ))

    # 8. abc（抽象基底クラス）
    if re.search(r'from\s+abc\s+import|import\s+abc\b', source_code):
        score = 40
        total_score += score
        signals.append(dict(
            level='強', score=score,
            title='`abc` (抽象基底クラス) のインポート',
            detail='抽象基底クラスモジュールがインポートされています。競技プログラミングでは使用しません。'
        ))

    # ── 中シグナル（複数の組み合わせでしきい値到達） ─────────

    # 9. def main(): + main() 呼び出しパターン
    has_main_def  = bool(re.search(r'^\s*def\s+main\s*\(\s*\)\s*:', source_code, re.MULTILINE))
    has_main_call = bool(re.search(r'^\s*main\s*\(\s*\)', source_code, re.MULTILINE))
    if has_main_def and has_main_call:
        score = 35
        total_score += score
        signals.append(dict(
            level='中', score=score,
            title='`def main():` + `main()` 呼び出しパターン',
            detail=(
                '`def main()` 関数の定義と明示的な呼び出しが検出されました。'
                'AI 生成コードに非常に多い構造ですが、競技プログラミングでは不要です。'
            )
        ))

    # 10. __all__ 定義
    if re.search(r'^__all__\s*=', source_code, re.MULTILINE):
        score = 25
        total_score += score
        signals.append(dict(
            level='中', score=score,
            title='`__all__` の定義',
            detail='モジュール公開 API を定義する `__all__` が検出されました。競技プログラミングでは使用しません。'
        ))

    # 11. pathlib のインポート
    if re.search(r'^\s*(from\s+pathlib\s+import|import\s+pathlib\b)', source_code, re.MULTILINE):
        score = 30
        total_score += score
        signals.append(dict(
            level='中', score=score,
            title='`pathlib` モジュールのインポート',
            detail=(
                'パス操作モジュールがインポートされています。'
                '競技プログラミングでは標準入力を使用するためファイルパス操作は不要です。'
            )
        ))

    # 12. json モジュール（競技プログラミングでは極めて稀）
    if re.search(r'^\s*(import\s+json\b|from\s+json\s+import)', source_code, re.MULTILINE):
        score = 25
        total_score += score
        signals.append(dict(
            level='中', score=score,
            title='`json` モジュールのインポート',
            detail=(
                'JSON 処理モジュールがインポートされています。'
                '競技プログラミングの入出力は通常テキスト形式であり、JSON は使用しません。'
            )
        ))

    # ── 弱シグナル（補強材料） ────────────────────────────────

    # 13. 英語の説明的コメント
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
        examples = [c.strip()[:60] for c in algorithmic_comments[:2]]
        signals.append(dict(
            level='弱', score=score,
            title=f'英語の説明的アルゴリズムコメント × {len(algorithmic_comments)} 箇所',
            detail=(
                f'アルゴリズムの手順を英語で説明するコメントが {len(algorithmic_comments)} 箇所検出されました。'
                f'例: {examples}。競技プログラミングの人間提出物では稀なパターンです。'
            )
        ))

    # 14. assert 文
    if tree is not None:
        assert_count = sum(1 for n in ast.walk(tree) if isinstance(n, ast.Assert))
        if assert_count >= 2:
            score = 15
            total_score += score
            signals.append(dict(
                level='弱', score=score,
                title=f'`assert` 文 × {assert_count} 個',
                detail='複数のデバッグ用 `assert` 文が検出されました。競技プログラミングでは通常使用しません。'
            ))

    # 15. 高い空行密度
    blank_count = sum(1 for l in lines if not l.strip())
    if len(lines) >= 20:
        blank_ratio = blank_count / len(lines)
        if blank_ratio > 0.38:
            score = 12
            total_score += score
            signals.append(dict(
                level='弱', score=score,
                title=f'高い空行密度 ({blank_ratio:.0%})',
                detail=(
                    f'全 {len(lines)} 行のうち {blank_count} 行（{blank_ratio:.0%}）が空行です。'
                    'AI は可読性向上のために多くの空行を挿入する傾向があります。'
                )
            ))

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
        }
    }


# ════════════════════════════════════════════════════════
#  表示関数
# ════════════════════════════════════════════════════════

def display_result(result: dict, filename: str = '') -> None:
    """判定結果を HTML でカラフルに表示する。"""

    if result['is_ai']:
        verdict_ja = 'AI 生成の可能性が高い'
        verdict_en = 'Likely AI-generated'
        main_color = '#c62828'
        main_bg    = '#ffebee'
        icon       = '&#x1F916;'
    else:
        verdict_ja = '人間が記述した可能性が高い'
        verdict_en = 'Likely human-written'
        main_color = '#2e7d32'
        main_bg    = '#e8f5e9'
        icon       = '&#x1F464;'

    level_colors = {'強': '#c62828', '中': '#e65100', '弱': '#f57f17'}
    bar_pct      = min(result['score'] / max(result['threshold'] * 2, 1) * 100, 100)

    if result['signals']:
        signal_items = ''
        for s in result['signals']:
            lc = level_colors.get(s['level'], '#555')
            signal_items += (
                f'<div style="margin:8px 0;padding:10px 14px;border-left:4px solid {lc};'
                f'background:#fafafa;border-radius:0 6px 6px 0;">'
                f'<div style="margin-bottom:4px;">'
                f'<span style="background:{lc};color:#fff;padding:2px 7px;'
                f'border-radius:3px;font-size:12px;font-weight:bold;">'
                f'{s["level"]}シグナル &nbsp;+{s["score"]}</span>'
                f'<strong style="margin-left:8px;font-size:14px;">{s["title"]}</strong></div>'
                f'<div style="color:#444;font-size:13px;line-height:1.6;">{s["detail"]}</div>'
                f'</div>'
            )
    else:
        signal_items = (
            '<div style="color:#555;font-style:italic;padding:8px;">'
            'AI 生成を示すシグナルは検出されませんでした。</div>'
        )

    parse_warning = ''
    if result['parse_error']:
        parse_warning = (
            f'<div style="background:#fff3e0;border:1px solid #ffb300;border-radius:6px;'
            f'padding:8px 12px;margin-bottom:12px;font-size:13px;color:#e65100;">'
            f'&#x26A0; 構文エラーのため AST 解析をスキップしました: {result["parse_error"]}'
            f'</div>'
        )

    fname_html = (
        f'<div style="margin-top:6px;font-size:13px;color:#888;">ファイル: {filename}</div>'
        if filename else ''
    )

    html = (
        '<div style="font-family:Helvetica Neue,Arial,sans-serif;max-width:780px;'
        'margin:10px 0;line-height:1.5;">'

        f'<div style="background:{main_bg};border:2px solid {main_color};border-radius:10px;'
        f'padding:18px 22px;margin-bottom:14px;">'
        f'<div style="font-size:26px;font-weight:bold;color:{main_color};">'
        f'{icon}&nbsp; {verdict_ja}</div>'
        f'<div style="color:#666;font-size:14px;margin-top:2px;">{verdict_en}</div>'
        f'{fname_html}</div>'

        f'<div style="background:#f5f5f5;border-radius:8px;padding:12px 16px;margin-bottom:14px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
        f'<span><strong>AI スコア:</strong> {result["score"]} 点</span>'
        f'<span style="color:#888;font-size:13px;">判定しきい値: {result["threshold"]} 点</span></div>'
        f'<div style="background:#e0e0e0;border-radius:4px;height:10px;overflow:hidden;">'
        f'<div style="background:{main_color};width:{bar_pct:.1f}%;height:100%;border-radius:4px;"></div></div>'
        f'<div style="display:flex;gap:20px;margin-top:8px;font-size:13px;color:#555;">'
        f'<span>総行数: {result["stats"]["total_lines"]}</span>'
        f'<span>有効行数: {result["stats"]["non_blank_lines"]}</span>'
        f'<span>空行: {result["stats"]["blank_lines"]}</span></div></div>'

        f'{parse_warning}'

        f'<div style="font-size:15px;font-weight:bold;margin-bottom:8px;">'
        f'検出されたシグナル ({len(result["signals"])} 件)</div>'
        f'{signal_items}'

        '<div style="margin-top:16px;padding:12px 14px;background:#e3f2fd;'
        'border-radius:8px;font-size:12px;color:#1565c0;line-height:1.6;">'
        '<strong>&#x1F4CC; 注意:</strong> '
        'このツールは競技プログラミング提出物向けに最適化されています。<br>'
        '最小限の変数名・コメント無し・汎用的命名・ビジネスコンテキストの欠如は'
        'AI 判定の根拠として<strong>使用していません</strong>。<br>'
        '偽陽性（人間&#x2192;AI 誤判定）を最小化する設計のため、'
        'AI コードを人間と誤判定することはあり得ますが、その逆はほぼ発生しません。'
        '</div></div>'
    )
    display(HTML(html))


# ════════════════════════════════════════════════════════
#  ファイルアップロード & 実行
# ════════════════════════════════════════════════════════

def _decode(content: bytes) -> str:
    for enc in ['utf-8', 'utf-8-sig', 'shift-jis', 'cp932']:
        try:
            return content.decode(enc)
        except (UnicodeDecodeError, ValueError):
            pass
    return content.decode('utf-8', errors='replace')


def run_single() -> None:
    """単体 .txt ファイルをアップロードして判定する。"""
    from google.colab import files as _cf
    print("Python コードの .txt ファイルをアップロードしてください")
    print("（複数ファイルを同時にアップロード可能です）\n")

    uploaded = _cf.upload()
    if not uploaded:
        print("ファイルがアップロードされませんでした。")
        return

    for filename, content in uploaded.items():
        src = _decode(content)
        print(f"\n{'='*60}\nファイル: {filename}\n{'='*60}")
        result = analyze_contest_code(src)
        display_result(result, filename)
        preview = '\n'.join(src.splitlines()[:30])
        if len(src.splitlines()) > 30:
            preview += f'\n... (以下 {len(src.splitlines())-30} 行省略)'
        print("\n--- コード内容 (先頭30行) ---")
        print(preview)


def run_batch_zip() -> None:
    """ZIP ファイル内の複数 .txt を一括判定する。"""
    from google.colab import files as _cf
    print("ZIP ファイル（.txt ファイルを複数含む）をアップロードしてください\n")

    uploaded_zip = _cf.upload()
    for zip_filename, zip_content in uploaded_zip.items():
        if not zip_filename.endswith('.zip'):
            print(f"  ⚠ {zip_filename} は ZIP ではありません。スキップします。")
            continue

        with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
            txt_files = sorted(n for n in zf.namelist()
                               if n.endswith('.txt') and not n.startswith('__'))
            print(f"ZIP 内の .txt ファイル数: {len(txt_files)}\n")
            ai_count = human_count = 0

            for name in txt_files:
                src   = _decode(zf.read(name))
                res   = analyze_contest_code(src)
                label = '🤖 AI  ' if res['is_ai'] else '👤 人間'
                sigs  = ', '.join(s['title'] for s in res['signals']) or 'なし'
                print(f"  {label}  {name:<40}  score={res['score']:<4}  シグナル: {sigs}")
                if res['is_ai']:
                    ai_count += 1
                else:
                    human_count += 1

            print(f"\n判定結果: 人間={human_count} 件  AI={ai_count} 件  合計={len(txt_files)} 件")


# ════════════════════════════════════════════════════════
#  エントリポイント（%run contest_ai_detector.py で実行）
# ════════════════════════════════════════════════════════

display(HTML(
    '<div style="font-family:Helvetica Neue,Arial,sans-serif;'
    'background:#e8eaf6;border-radius:10px;padding:18px 22px;max-width:680px;">'
    '<div style="font-size:20px;font-weight:bold;color:#1a237e;">'
    '&#x1F50D; 競技プログラミング AI生成コード判定ツール</div>'
    '<div style="margin-top:10px;font-size:14px;color:#333;line-height:1.8;">'
    '以下の関数が利用可能です:<br>'
    '<code style="background:#fff;padding:2px 6px;border-radius:3px;">run_single()</code>'
    '&nbsp;&mdash;&nbsp;単体 .txt ファイルを判定<br>'
    '<code style="background:#fff;padding:2px 6px;border-radius:3px;">run_batch_zip()</code>'
    '&nbsp;&mdash;&nbsp;ZIP 内の複数ファイルを一括判定'
    '</div></div>'
))

run_single()
