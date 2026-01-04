import os
import sys
import json
import argparse
import threading
from typing import List, Dict

import pandas as pd
import numpy as np
from playwright.sync_api import sync_playwright, Page, ConsoleMessage, Playwright

def _run_contrast_script_on_page(page: Page) -> List[Dict]:
    js_script = """
    () => {
        function getEffectiveBackgroundColor(element, skipSelf = false) {
            function alphaBlend(sourceColor, destinationColor) {
                const [r_s, g_s, b_s, a_s] = sourceColor;
                const [r_d, g_d, b_d] = destinationColor; 
                const r_out = Math.round(r_s * a_s + r_d * (1 - a_s));
                const g_out = Math.round(g_s * a_s + g_d * (1 - a_s));
                const b_out = Math.round(b_s * a_s + b_d * (1 - a_s));
                return [r_out, g_out, b_out, 1.0];
            }
            function getAverageGradientColor(gradientColors, startWeight = 0.3) {
                if (!gradientColors || gradientColors.length === 0) return null;
                const startColor = parseRgba(gradientColors[0]);
                const endColor = parseRgba(gradientColors[gradientColors.length - 1]);
                if (startColor && endColor) {
                    const endWeight = 1 - startWeight;
                    return [
                        Math.round(startColor[0] * startWeight + endColor[0] * endWeight),
                        Math.round(startColor[1] * startWeight + endColor[1] * endWeight),
                        Math.round(startColor[2] * startWeight + endColor[2] * endWeight),
                        startColor[3] * startWeight + endColor[3] * endWeight
                    ];
                }
                return startColor || endColor;
            }
            function parseRgba(colorStr) {
                if (!colorStr || colorStr === 'transparent' || colorStr === 'none') return null;
                let match = colorStr.match(/rgba?\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\)/);
                if (match) return [parseInt(match[1]), parseInt(match[2]), parseInt(match[3]), match[4] !== undefined ? parseFloat(match[4]) : 1.0];
                match = colorStr.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})?$/i);
                if (match) return [parseInt(match[1], 16), parseInt(match[2], 16), parseInt(match[3], 16), match[4] ? parseInt(match[4], 16) / 255 : 1.0];
                match = colorStr.match(/^#([0-9a-f])([0-9a-f])([0-9a-f])([0-9a-f])?$/i);
                if (match) return [parseInt(match[1] + match[1], 16), parseInt(match[2] + match[2], 16), parseInt(match[3] + match[3], 16), match[4] ? parseInt(match[4] + match[4], 16) / 255 : 1.0];
                if (colorStr.includes('gradient')) {
                    const gradientColors = colorStr.match(/rgba?\([^)]+\)|#[0-9a-fA-F]{3,8}/gi);
                    return getAverageGradientColor(gradientColors);
                }
                return null;
            }
            let layers = [];
            let current = skipSelf ? element.parentElement : element;
            while (current) {
                const style = window.getComputedStyle(current);
                const bgColor = style.backgroundColor;
                const bgImage = style.backgroundImage;
                const colorFromBg = parseRgba(bgColor);
                let colorFromImg = null;
                if (bgImage && bgImage !== 'none' && bgImage.includes('gradient')) {
                    const gradientColors = bgImage.match(/rgba?\([^)]+\)|#[0-9a-fA-F]{3,8}/gi);
                    colorFromImg = getAverageGradientColor(gradientColors);
                }
                if (colorFromBg) {
                    layers.push(colorFromBg);
                    if (colorFromBg[3] === 1.0) break;
                }
                if (colorFromImg) {
                    layers.push(colorFromImg);
                    if (colorFromImg[3] === 1.0) break;
                }
                if (current.parentElement === null) break;
                current = current.parentElement;
            }
            if (layers.length === 0) return 'rgb(255, 255, 255)';
            let blendedColor = layers.pop(); 
            if (blendedColor[3] < 1.0) {
                blendedColor = alphaBlend(blendedColor, [255, 255, 255]);
            }
            while (layers.length > 0) {
                let currentLayer = layers.pop();
                blendedColor = alphaBlend(currentLayer, [blendedColor[0], blendedColor[1], blendedColor[2]]);
            }
            return `rgb(${blendedColor[0]}, ${blendedColor[1]}, ${blendedColor[2]})`;
        }
        function parseRgb(rgbString) {
            if (!rgbString) return null;
            const match = rgbString.match(/rgba?\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
            if (match) return [parseInt(match[1], 10), parseInt(match[2], 10), parseInt(match[3], 10)];
            return null;
        }
        function getLuminance(rgb) {
            const [r, g, b] = rgb.map(c => {
                const s = c / 255;
                return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
            });
            return 0.2126 * r + 0.7152 * g + 0.0722 * b;
        }
        function getContrastRatio(rgb1, rgb2) {
            const lum1 = getLuminance(rgb1);
            const lum2 = getLuminance(rgb2);
            const brightest = Math.max(lum1, lum2);
            const darkest = Math.min(lum1, lum2);
            return (brightest + 0.05) / (darkest + 0.05);
        }
        function isLargeText(fontSize, fontWeight) {
            const size = parseFloat(fontSize);
            const weight = parseInt(fontWeight, 10);
            return (size >= 24) || (size >= 18.7 && (weight >= 700 || fontWeight === 'bold'));
        }
        const results = [];
        const elements = document.querySelectorAll('body *:not(script):not(style):not(meta):not(link):not(svg):not(path):not(img):not(:empty)');
        for (const el of Array.from(elements)) {
            const hasTextContent = Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim().length > 0);
            if (el.offsetParent === null || !hasTextContent || window.getComputedStyle(el).display === 'none') continue;
            const text = el.textContent.trim();
            if (!text || /^[\\p{Emoji}\\p{Symbol}]+$/u.test(text)) continue;
            const style = window.getComputedStyle(el);
            const fontSize = style.fontSize;
            const fontWeight = style.fontWeight;
            let foregroundColorStr, backgroundColorStr, fgLabel, bgLabel;
            const isGradientText = style.backgroundClip === 'text' || style.webkitBackgroundClip === 'text';
            if (isGradientText) {
                const bgImage = style.backgroundImage;
                const gradientColors = bgImage.match(/rgba?\([^)]+\)|#[0-9a-fA-F]{3,8}/gi);
                foregroundColorStr = (gradientColors && gradientColors.length > 0) ? gradientColors[0] : style.color;
                fgLabel = `[Gradient Approx.] ${foregroundColorStr}`;
                backgroundColorStr = getEffectiveBackgroundColor(el, true);
                bgLabel = backgroundColorStr;
            } else {
                foregroundColorStr = style.color;
                fgLabel = foregroundColorStr;
                backgroundColorStr = getEffectiveBackgroundColor(el, false);
                bgLabel = backgroundColorStr;
            }
            const foregroundRgb = parseRgb(foregroundColorStr);
            const backgroundRgb = parseRgb(backgroundColorStr);
            if (!foregroundRgb || !backgroundRgb) continue;
            const contrastRatio = getContrastRatio(foregroundRgb, backgroundRgb);
            const largeText = isLargeText(fontSize, fontWeight);
            const requiredRatio = 1.5;
            if (contrastRatio < requiredRatio) {
                results.push({
                    tagName: el.tagName,
                    text: el.textContent.trim().substring(0, 150),
                    foregroundColor: fgLabel,
                    backgroundColor: bgLabel,
                    contrastRatio: contrastRatio,
                    requiredRatio: requiredRatio,
                    isLarge: largeText
                });
            }
        }
        return results;
    }
    """
    return page.evaluate(js_script)

def check_html_contrast(html_doc_or_url: str, page: Page) -> List[Dict]:
    page.goto(html_doc_or_url, wait_until="domcontentloaded", timeout=600000)
    raw_results = _run_contrast_script_on_page(page)
    formatted_results = []
    for issue in raw_results:
        formatted_results.append({
            "tag": issue['tagName'],
            "text_sample": issue['text'],
            "text_color": issue['foregroundColor'],
            "background_color": issue['backgroundColor'],
            "contrast_ratio": f"{issue['contrastRatio']:.2f}",
            "threshold": issue['requiredRatio'],
            "is_large_text": issue['isLarge']
        })
    return formatted_results

def worker(worker_id: int, data_chunk: pd.DataFrame, config: Dict, results_list: List):
    
    thread_name = f"Worker-{worker_id}"
    threading.current_thread().name = thread_name

    batch_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()

        def handle_console_message(msg: ConsoleMessage):
            if "DEBUG:" in msg.text:
                print(f"[{thread_name}] BROWSER CONSOLE: {msg.text}")

        page.on("console", handle_console_message)

        for _, row in data_chunk.iterrows():
            current_id = row['id']
            if 'result' in row and row.get('result') != -1:
                batch_results.append((current_id, row['result'], row.get('reason', ''), None))
                continue
            
            target_url = None
            if 'url' in row and row['url']:
                target_url = row['url'] if row['url'].startswith('file://') else f"file://{row['url']}"
            elif 'html' in row and row['html']:
                temp_html_path = os.path.join(config['html_dir'], f"temp_{worker_id}_{current_id}.html")
                try:
                    with open(temp_html_path, 'w', encoding='utf-8') as f:
                        f.write(row['html'])
                    target_url = f"file://{os.path.abspath(temp_html_path)}"
                except Exception as e:
                    print(f"[{thread_name}] Unable to create temporary HTML file for ID {current_id}: {e}")
                    batch_results.append((current_id, -1, json.dumps({"error": f"File creation failed: {e}"}), None))
                    continue
            else:
                print(f"[{thread_name}] ID {current_id} has neither 'url' nor 'html' field, skipping.")
                batch_results.append((current_id, -1, json.dumps({"error": "Missing 'url' or 'html' field"}), None))
                continue
            
            print(f"[{thread_name}] Checking ID: {current_id}")

            try:
                problem_elements = check_html_contrast(target_url, page)
                if problem_elements:
                    min_contrast_ratio = min(float(p['contrast_ratio']) for p in problem_elements)
                    reason_json = json.dumps(problem_elements, ensure_ascii=False, indent=2)
                    batch_results.append((current_id, 0, reason_json, min_contrast_ratio))
                else:
                    batch_results.append((current_id, 1, json.dumps([], ensure_ascii=False), None))
            
            except Exception as e:
                print(f"[{thread_name}] A critical error occurred while processing ID={current_id}: {e}")
                error_json = json.dumps({"error": str(e)}, ensure_ascii=False)
                batch_results.append((current_id, -1, error_json, None))
            
            finally:
                if 'html' in row and row['html']:
                    temp_html_path = os.path.join(config['html_dir'], f"temp_{worker_id}_{current_id}.html")
                    if os.path.exists(temp_html_path):
                        try:
                            os.remove(temp_html_path)
                        except:
                            pass
        
        browser.close()

    results_list[worker_id] = batch_results
    print(f"[{thread_name}] All tasks have been completed.")

def main(input_path: str, output_dir: str, html_dir: str, num_threads: int):
   
    try:
        df = pd.read_json(input_path, lines=True)
        if 'id' not in df.columns:
            df['id'] = list(df.index)
    except Exception as e:
        print(f"Error reading JSON input file {input_path}: {e}")
        exit(1)
    
    df_chunks = np.array_split(df, num_threads) if len(df) > 0 else []

    threads = []
    thread_results = [None] * num_threads
    
    config = {'html_dir': html_dir}

    for i, chunk in enumerate(df_chunks):
        if not chunk.empty:
            thread = threading.Thread(
                target=worker,
                args=(i, chunk, config, thread_results)
            )
            threads.append(thread)
            thread.start()

    for thread in threads:
        thread.join()

    all_results_tuples = [item for sublist in thread_results if sublist is not None for item in sublist]
    
    results_dict = {id_val: (res, reason, ratio) for id_val, res, reason, ratio in all_results_tuples}

    df['result'] = df['id'].map(lambda x: results_dict.get(x, (-1, '{"error": "Result not found"}', None))[0])
    df['reason'] = df['id'].map(lambda x: results_dict.get(x, (-1, '{"error": "Result not found"}', None))[1])
   
    issue_ids = df[df['result'] == 1]['id'].tolist()
    contrast_ratio_list = [results_dict[id_val][2] for id_val in issue_ids if id_val in results_dict]
    
    print(f"Check complete. List of problematic file IDs: {issue_ids}.")
    if contrast_ratio_list:
        print(f"Minimum contrast ratios for problematic files: {contrast_ratio_list}.")
    
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, 'color_detect.json')

    if args.save_detailed:
        detail_output_path = os.path.join(args.output, "color_detect_detailed.jsonl")
        df.to_json(detail_output_path, orient='records', lines=True, force_ascii=False)

    status_results = {}
    no_issue_count = 0
    issue_count = 0
    
    for idx, row in df.iterrows():
        file_id = row['id']
        status_results[file_id] = row['result']
        if row['result'] == 1:
            no_issue_count += 1
        else:
            issue_count += 1
    
    sorted_results = dict(sorted(status_results.items(), 
                                key=lambda x: int(x[0]) if isinstance(x, str) and x[0].isdigit() else x[0]))
    
    complete_results = {
        "total_right": no_issue_count,
        "total_wrong": issue_count,
        "results": sorted_results
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(complete_results, f, ensure_ascii=False, indent=2)
    
    print(f"Results saved to: {output_path}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Color Detect")
    parser.add_argument("--input_jsonl", type=str, required=True)
    parser.add_argument("--output_dir", type=str, required=True)
    parser.add_argument("--num_threads", type=int, default=os.cpu_count() or 4)
    parser.add_argument('--save_detailed', action='store_true', default=False)
    args = parser.parse_args()

    if not os.path.exists(args.input_jsonl):
        print(f"Error: Input file not found at {args.input_jsonl}.")
        exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    html_dir = os.path.join(args.output_dir, 'html')
    os.makedirs(html_dir, exist_ok=True)

    try:
        main(args.input_jsonl, args.output_dir, html_dir, args.num_threads)
    except Exception as e:
        print(f"An uncaught exception occurred during script execution: {e}")
            
    print("----Done!----")
