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

import io
import zipfile

from contest_ai_detector_core import analyze_contest_code, decode_uploaded_text

try:
    from IPython.display import HTML, display
    HAS_IPYTHON_DISPLAY = True
except ImportError:
    HAS_IPYTHON_DISPLAY = False

    class HTML(str):
        pass

    def display(obj):
        print(str(obj))


def display_result(result: dict, filename: str = '') -> None:
    """判定結果を表示する。"""

    if not HAS_IPYTHON_DISPLAY:
        verdict = 'AI 生成の可能性が高い' if result['is_ai'] else '人間が記述した可能性が高い'
        print(f'{verdict} | score={result["score"]}/{result["threshold"]}')
        if filename:
            print(f'ファイル: {filename}')
        if result['signals']:
            print('根拠:')
            for signal in result['signals']:
                print(f'  - [{signal["level"]}] +{signal["score"]} {signal["title"]}')
        else:
            print('根拠: AI 生成を示すシグナルは検出されませんでした。')
        if result['parse_error']:
            print(f'構文エラーのため AST 解析をスキップしました: {result["parse_error"]}')
        return

    if result['is_ai']:
        verdict_ja = 'AI 生成の可能性が高い'
        verdict_en = 'Likely AI-generated'
        main_color = '#c62828'
        main_bg = '#ffebee'
        icon = '&#x1F916;'
    else:
        verdict_ja = '人間が記述した可能性が高い'
        verdict_en = 'Likely human-written'
        main_color = '#2e7d32'
        main_bg = '#e8f5e9'
        icon = '&#x1F464;'

    level_colors = {'強': '#c62828', '中': '#e65100', '弱': '#f57f17'}
    bar_pct = min(result['score'] / max(result['threshold'] * 2, 1) * 100, 100)

    if result['signals']:
        signal_items = ''
        for signal in result['signals']:
            color = level_colors.get(signal['level'], '#555')
            signal_items += (
                f'<div style="margin:8px 0;padding:10px 14px;border-left:4px solid {color};'
                f'background:#fafafa;border-radius:0 6px 6px 0;">'
                f'<div style="margin-bottom:4px;">'
                f'<span style="background:{color};color:#fff;padding:2px 7px;'
                f'border-radius:3px;font-size:12px;font-weight:bold;">'
                f'{signal["level"]}シグナル &nbsp;+{signal["score"]}</span>'
                f'<strong style="margin-left:8px;font-size:14px;">{signal["title"]}</strong></div>'
                f'<div style="color:#444;font-size:13px;line-height:1.6;">{signal["detail"]}</div>'
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


def _get_colab_files_module():
    try:
        from google.colab import files as colab_files
    except ImportError as exc:
        raise RuntimeError(
            'この関数は Google Colaboratory 上で実行してください。'
        ) from exc
    return colab_files


def run_single() -> None:
    """単体 .txt ファイルをアップロードして判定する。"""

    try:
        colab_files = _get_colab_files_module()
    except RuntimeError as exc:
        print(exc)
        return

    print('Python コードの .txt ファイルをアップロードしてください')
    print('（複数ファイルを同時にアップロード可能です）\n')

    uploaded = colab_files.upload()
    if not uploaded:
        print('ファイルがアップロードされませんでした。')
        return

    for filename, content in uploaded.items():
        source_code = decode_uploaded_text(content)
        print(f"\n{'=' * 60}\nファイル: {filename}\n{'=' * 60}")
        result = analyze_contest_code(source_code)
        display_result(result, filename)
        preview = '\n'.join(source_code.splitlines()[:30])
        if len(source_code.splitlines()) > 30:
            preview += f'\n... (以下 {len(source_code.splitlines()) - 30} 行省略)'
        print('\n--- コード内容 (先頭30行) ---')
        print(preview)


def run_batch_zip() -> None:
    """ZIP ファイル内の複数 .txt を一括判定する。"""

    try:
        colab_files = _get_colab_files_module()
    except RuntimeError as exc:
        print(exc)
        return

    print('ZIP ファイル（.txt ファイルを複数含む）をアップロードしてください\n')

    uploaded_zip = colab_files.upload()
    for zip_filename, zip_content in uploaded_zip.items():
        if not zip_filename.endswith('.zip'):
            print(f'  ⚠ {zip_filename} は ZIP ではありません。スキップします。')
            continue

        with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_file:
            txt_files = sorted(
                name for name in zip_file.namelist()
                if name.endswith('.txt') and not name.startswith('__')
            )
            print(f'ZIP 内の .txt ファイル数: {len(txt_files)}\n')
            ai_count = 0
            human_count = 0

            for name in txt_files:
                source_code = decode_uploaded_text(zip_file.read(name))
                result = analyze_contest_code(source_code)
                label = '🤖 AI  ' if result['is_ai'] else '👤 人間'
                signal_summary = ', '.join(signal['title'] for signal in result['signals']) or 'なし'
                print(
                    f'  {label}  {name:<40}  score={result["score"]:<4}  '
                    f'シグナル: {signal_summary}'
                )
                if result['is_ai']:
                    ai_count += 1
                else:
                    human_count += 1

            print(f'\n判定結果: 人間={human_count} 件  AI={ai_count} 件  合計={len(txt_files)} 件')


def launch() -> None:
    """Colab 向けのイントロを表示し、単体判定を開始する。"""

    if HAS_IPYTHON_DISPLAY:
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
    else:
        print('競技プログラミング AI生成コード判定ツール')
        print('利用可能な関数: run_single(), run_batch_zip()')

    run_single()


if __name__ == '__main__':
    launch()
