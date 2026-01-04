import argparse
import re
import os
import io
import json
import webcolors
import collections
from bs4 import BeautifulSoup
import logging
import pandas as pd
import asyncio
from playwright.async_api import async_playwright, Error as PlaywrightError
from PIL import Image
import concurrent.futures
import math
import threading

WCAG_CONTRAST_THRESHOLD_AA = 1.06
MAX_WORKERS = 1 #os.cpu_count() or 4

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: [Thread-%(thread)d] %(message)s'
)

# --- Browser Interaction (Playwright) ---

class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.browser = None

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch()
        logging.info("Playwright Start.")
        return self.browser

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logging.info("Playwright Close.")

async def get_global_background_from_edges(page):
    try:
        screenshot_bytes = await page.screenshot()
        img = Image.open(io.BytesIO(screenshot_bytes)).convert('RGB')
        width, height = img.size
        if width < 100 or height < 100:
            logging.warning("Global background sampling failed: viewport is too small.")
            return None
        x_margin = int(width * 0.05)
        y_points = [int(height * p) for p in [0.2, 0.4, 0.6, 0.8]]
        colors = []
        for y in y_points:
            colors.append(img.getpixel((x_margin, y)))
        for y in y_points:
            colors.append(img.getpixel((width - 1 - x_margin, y)))
        if not colors:
            logging.warning("Global background sampling failed: no colors could be collected from the edges.")
            return None
        num_colors = len(colors)
        avg_r = sum(c[0] for c in colors) // num_colors
        avg_g = sum(c[1] for c in colors) // num_colors
        avg_b = sum(c[2] for c in colors) // num_colors
        avg_color = (avg_r, avg_g, avg_b)
        logging.info(f"Global background sampling successful: {avg_color}")
        return avg_color
    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        return None

async def get_background_by_sampling(page, selector):
    try:
        try:
            await page.wait_for_selector(selector, state='attached', timeout=5000)
        except PlaywrightError:
            logging.error(f"Timeout Error: '{selector}'")
            return None
        element = await page.query_selector(selector)
        if not element:
            logging.warning(f"SampleError: Element not found for selector '{selector}'.")
            return None
        if not await element.is_visible():
            await element.scroll_into_view_if_needed(timeout=5000)
            await page.wait_for_timeout(200)
            if not await element.is_visible():
                logging.warning(f"SampleError: element '{selector}' is not visible.")
                return None
        screenshot_bytes = await element.screenshot()
        img = Image.open(io.BytesIO(screenshot_bytes)).convert('RGB')
        width, height = img.size
        if width < 20 or height < 20:
            logging.warning(f"SampleError: screenshot of element '{selector}' is too small ({width}x{height}).")
            return None
        edge_colors = []
        margin = min(3, width // 8, height // 8)
        num_samples_per_edge = 20
        if num_samples_per_edge > 1:
            step = (width - 1 - 2 * margin) / (num_samples_per_edge - 1)
            for i in range(num_samples_per_edge):
                x = int(margin + i * step)
                edge_colors.append(img.getpixel((x, margin)))
                edge_colors.append(img.getpixel((x, height - 1 - margin)))
        if num_samples_per_edge > 2:
            step = (height - 1 - 2 * margin) / (num_samples_per_edge - 2)
            for i in range(1, num_samples_per_edge - 1):
                y = int(margin + i * step)
                edge_colors.append(img.getpixel((margin, y)))
                edge_colors.append(img.getpixel((width - 1 - margin, y)))
        if not edge_colors:
            logging.error(f"No colors could be collected from '{selector}'.")
            return None
        most_common_color = collections.Counter(edge_colors).most_common(1)[0][0]
        logging.info(f"Successfully obtain the background color of '{selector}': {most_common_color}")
        return most_common_color
    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        return None

async def get_ultimate_opaque_background(page):
    bg_color_rgb = await get_global_background_from_edges(page)
    if not bg_color_rgb:
        default_color = (0, 0, 0)
        logging.error(f"SampleError: Use default color {default_color}。")
        return default_color
    return bg_color_rgb

def average_rgb(rgb1, rgb2):
    if not rgb1 or not rgb2: return None
    return (round((rgb1[0] + rgb2[0]) / 2), round((rgb1[1] + rgb2[1]) / 2), round((rgb1[2] + rgb2[2]) / 2))

def blend_color(fg_rgb, bg_rgb, alpha):
    if not fg_rgb or not bg_rgb: return None
    if alpha >= 1.0: return fg_rgb
    r = round(fg_rgb[0] * alpha + bg_rgb[0] * (1 - alpha))
    g = round(fg_rgb[1] * alpha + bg_rgb[1] * (1 - alpha))
    b = round(fg_rgb[2] * alpha + bg_rgb[2] * (1 - alpha))
    return (r, g, b)

def parse_color(color_string):
    if not isinstance(color_string, str):
        if isinstance(color_string, dict) and 'colorStops' in color_string:
            color_stops = color_string.get('colorStops', [])
            if len(color_stops) >= 2:
                start_rgb, _ = parse_color(color_stops[0]['color'])
                end_rgb, _ = parse_color(color_stops[-1]['color'])
                avg_rgb = average_rgb(start_rgb, end_rgb)
                if avg_rgb: return avg_rgb, 1.0
        return None, 1.0
    color_string = color_string.strip().lower()
    if color_string.startswith('#'):
        try: return tuple(webcolors.hex_to_rgb(color_string)), 1.0
        except ValueError: pass
    rgba_match = re.match(r'rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)', color_string)
    if rgba_match:
        rgb = tuple(int(c) for c in rgba_match.groups()[:3])
        alpha = float(rgba_match.group(4)) if rgba_match.group(4) is not None else 1.0
        return rgb, alpha
    try: return tuple(webcolors.name_to_rgb(color_string)), 1.0
    except ValueError: pass
    logging.warning(f"Unable to parse: '{color_string}'")
    return None, 1.0

def get_relative_luminance(rgb):
    if not rgb: return 0
    r, g, b = [x / 255.0 for x in rgb]
    def transform(c): return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * transform(r) + 0.7152 * transform(g) + 0.0722 * transform(b)

def calculate_contrast_ratio(rgb1, rgb2):
    if not rgb1 or not rgb2: return 1.0
    lum1, lum2 = get_relative_luminance(rgb1), get_relative_luminance(rgb2)
    return (lum1 + 0.05) / (lum2 + 0.05) if lum1 > lum2 else (lum2 + 0.05) / (lum1 + 0.05)

async def analyze_charts_via_browser_api(page, screenshots_dir, current_id):
    ultimate_bg_rgb = await get_ultimate_opaque_background(page)
    if not ultimate_bg_rgb:
        logging.error("Unable to determine the final page background color.")
        return [], 0
    charts_data = await page.evaluate("""
        () => {
            const allChartsDetails = [];
            if (typeof window.Chart !== 'undefined' && typeof window.Chart.instances === 'object') {
                for (const instanceId in window.Chart.instances) {
                    const chartInstance = window.Chart.instances[instanceId];
                    if (chartInstance && chartInstance.canvas) {
                        const canvas = chartInstance.canvas;
                        let canvasId = canvas.id || `chartjs-auto-id-${chartInstance.id}`;
                        if (!canvas.id) canvas.id = canvasId;
                        const chartType = chartInstance.config.type;
                        const chartDetails = { library: 'Chart.js', chartId: canvasId, elements: [] };
                        if (chartInstance.config.data && chartInstance.config.data.datasets) {
                            chartInstance.config.data.datasets.forEach(dataset => {
                                const addColor = (colorValue, sourceName) => {
                                    if (colorValue) {
                                        if (Array.isArray(colorValue)) {
                                            colorValue.forEach(c => chartDetails.elements.push({ color: c, source: sourceName, chartType: chartType }));
                                        } else {
                                            chartDetails.elements.push({ color: colorValue, source: sourceName, chartType: chartType });
                                        }
                                    }
                                };
                                addColor(dataset.backgroundColor, 'backgroundColor');
                                addColor(dataset.borderColor, 'borderColor');
                                addColor(dataset.pointBackgroundColor, 'pointBackgroundColor');
                            });
                        }
                        allChartsDetails.push(chartDetails);
                    }
                }
            }
            if (typeof window.echarts !== 'undefined' && typeof window.echarts.getInstanceByDom === 'function') {
                const chartDoms = document.querySelectorAll('[_echarts_instance_]');
                for (const dom of chartDoms) {
                    const chartInstance = window.echarts.getInstanceByDom(dom);
                    if (chartInstance && chartInstance.getOption) {
                        const option = chartInstance.getOption();
                        if (option) { 
                            let domId = dom.id || `echarts-auto-id-${Math.random().toString(36).substr(2, 9)}`;
                            if (!dom.id) dom.id = domId;
                            const chartDetails = { library: 'ECharts', chartId: domId, elements: [] };
                            const seenColors = new Set();
                            const processColor = (color, source, seriesType = 'unknown') => {
                                if (color && typeof color !== 'function' && !seenColors.has(JSON.stringify(color))) {
                                    chartDetails.elements.push({ color: color, source: source, chartType: seriesType });
                                    seenColors.add(JSON.stringify(color));
                                }
                            };
                            if (Array.isArray(option.color)) {
                                option.color.forEach(c => processColor(c, 'option.color (global palette)'));
                            }
                            if (option.series) {
                                option.series.forEach((series) => {
                                    const seriesType = series.type || 'unknown';
                                    processColor(series.color, 'series.color', seriesType);
                                    processColor(series.itemStyle?.color, 'series.itemStyle.color', seriesType);
                                    processColor(series.itemStyle?.borderColor, 'series.itemStyle.borderColor', seriesType);
                                    processColor(series.lineStyle?.color, 'series.lineStyle.color', seriesType);
                                    processColor(series.areaStyle?.color, 'series.areaStyle.color', seriesType);
                                    if (series.data) {
                                        series.data.forEach(item => {
                                            if (item && typeof item === 'object') {
                                                processColor(item?.itemStyle?.color, 'data.itemStyle.color', seriesType);
                                                processColor(item?.itemStyle?.borderColor, 'data.itemStyle.borderColor', seriesType);
                                                processColor(item?.lineStyle?.color, 'data.lineStyle.color', seriesType);
                                                processColor(item?.areaStyle?.color, 'data.areaStyle.color', seriesType);
                                            }
                                        });
                                    }
                                });
                            }
                            allChartsDetails.push(chartDetails);
                        }
                    }
                }
            }
            return allChartsDetails;
        }
    """)
    if not charts_data:
        logging.info("Browser API analysis complete: no Chart.js or ECharts instances found on the page.")
        return [], 0
    logging.info(f"Browser API analysis complete: found {len(charts_data)} chart instance(s).")
    found_issues = []
    for chart in charts_data:
        chart_id, library = chart['chartId'], chart['library']
        selector = f"#{chart_id}"
        try:
            chart_element = await page.query_selector(selector)
            if chart_element:
                if not await chart_element.is_visible():
                     await chart_element.scroll_into_view_if_needed(timeout=3000)
                     await page.wait_for_timeout(200)
                if await chart_element.is_visible():
                    screenshot_path = os.path.join(screenshots_dir, f"{current_id}_{chart_id}.png")
                    await chart_element.screenshot(path=screenshot_path)
                    logging.info(f"Chart screenshot saved to: {screenshot_path}")
                else:
                    logging.warning(f"Cannot capture screenshot for chart '{chart_id}' because it is still not visible after scrolling.")
            else:
                logging.warning(f"Cannot find chart element '{selector}' to capture a screenshot.")
        except Exception as e:
            logging.error(f" Error for '{chart_id}': {e}")
        final_bg_rgb = await get_background_by_sampling(page, selector)
        if not final_bg_rgb:
            final_bg_rgb = ultimate_bg_rgb
            logging.warning(f"Chart '{chart_id}' sampling failed; using page background {final_bg_rgb} as its background.")
        else:
            logging.info(f"Chart '{chart_id}' ({library}): final background color from sampling is RGB {final_bg_rgb}.")
        if not chart['elements']:
            logging.warning(f"Chart '{chart_id}' ({library}): API extraction succeeded, but no actually used data colors were found.")
            continue
        for element in chart['elements']:
            color_obj, source, chart_type = element.get('color'), element.get('source'), element.get('chartType')
            if library == 'Chart.js':
                if source == 'borderColor' and chart_type in ['doughnut', 'pie', 'bar','line']:
                    logging.info(f"Skipping detection: border color for Chart.js '{chart_type}' chart.")
                    continue
                if source == 'backgroundColor' and chart_type in ['line', 'radar']:
                    logging.info(f"Skipping detection: area fill color for Chart.js '{chart_type}' chart (usually semi-transparent).")
                    continue
                if source == 'pointBackgroundColor' and chart_type in ['line', 'radar']:
                    logging.info(f"Skipping detection: inner fill color of data points in Chart.js '{chart_type}' chart ('{source}').")
                    continue
            elif library == 'ECharts':
                if 'itemStyle.color' in source and chart_type in ['line', 'radar']:
                    logging.info(f"Skipping detection: inner fill color of data points in ECharts '{chart_type}' chart (source: '{source}').")
                    continue
                if 'areaStyle.color' in source:
                    logging.info(f"Skipping detection: area fill color of ECharts '{chart_type}' chart (source: '{source}').")
                    continue
                if 'itemStyle.borderColor' in source and chart_type in ['pie', 'bar','line']:
                    logging.info(f"Skipping detection: border color of ECharts '{chart_type}' chart (source: '{source}').")
                    continue
            data_color_rgb_source, data_alpha = parse_color(color_obj)
            color_str_for_log = json.dumps(color_obj) if isinstance(color_obj, dict) else str(color_obj)
            if not data_color_rgb_source:
                logging.warning(f"Unable to parse color: '{color_str_for_log}', skipping.")
                continue
            final_visual_rgb = blend_color(data_color_rgb_source, final_bg_rgb, data_alpha) if data_alpha < 1.0 else data_color_rgb_source
            if not final_visual_rgb: continue
            contrast_ratio = calculate_contrast_ratio(final_visual_rgb, final_bg_rgb)
            logging.info(f"Checking color: '{color_str_for_log}' (source: {source}) -> visual RGB: {final_visual_rgb}, contrast: {contrast_ratio:.2f}:1")
            if contrast_ratio < WCAG_CONTRAST_THRESHOLD_AA:
                issue_details = {
                    "library": library, "chart_id": chart_id, "data_color_str": color_str_for_log,
                    "color_source": source, "chart_type": chart_type, "final_visual_rgb": final_visual_rgb,
                    "background_color_rgb": final_bg_rgb, "contrast_ratio": f"{contrast_ratio:.2f}:1",
                    "threshold": f"{WCAG_CONTRAST_THRESHOLD_AA}:1",
                    "conclusion": f"The color '{color_str_for_log}' extracted via API has too low contrast against the background."
                }
                found_issues.append(issue_details)
    return found_issues, len(charts_data)

async def process_row_async(browser, row, html_dir, screenshots_dir):
    current_id = row['id']
    
    url = None
    if 'url' in row and pd.notna(row['url']):
        url = row['url']
        if not url.startswith('file://'):
            url = f"file://{url}"
    elif 'html' in row and pd.notna(row['html']):
        html_file_path = os.path.join(html_dir, f"{current_id}.html")
        try:
            with open(html_file_path, "w", encoding="utf-8") as f:
                f.write(row['html'])
            url = f"file://{html_file_path}"
        except Exception as e:
            print(f"[ID:{current_id}] Unable to write HTML file: {e}")
            return -1, json.dumps({"error": f"Failed to write HTML file: {str(e)}"})
    else:
        print(f"[ID:{current_id}] Missing 'url' or 'html' field, skipping.")
        return -1, json.dumps({"error": "Missing 'url' or 'html' field"})
    
    print(f"\n--- [Thread-{threading.get_ident()}] Analyzing ID: {current_id} ---")

    try:
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)

        issues_found, chart_count = await analyze_charts_via_browser_api(page, screenshots_dir, current_id)

        if chart_count == 0:
            print(f"[ID:{current_id}] Analysis complete: no accessible chart instances found on the page.")

        if issues_found:
            sorted_issues = sorted(issues_found, key=lambda x: (x['chart_id'], x['data_color_str']))
            reason_json = json.dumps(sorted_issues, ensure_ascii=False, indent=2)
            print(f"[ID:{current_id}] **Found {len(issues_found)} potential contrast issues**")
            for i, issue in enumerate(sorted_issues):
                print(f"Issue {i+1} ({issue['library']}/{issue['chart_id']}): contrast {issue['contrast_ratio']}")
            await page.close()
            return 0, reason_json
        else:
            if chart_count > 0:
                print(f"[ID:{current_id}] Analysis complete: {chart_count} charts detected; no obvious color contrast issues found.")
            await page.close()
            return 1, json.dumps([])

    except Exception as e:
        print(f"[ID:{current_id}] A critical error occurred during processing: {e}")
        logging.exception(f"Detailed traceback (ID: {current_id}):")
        if 'page' in locals() and not page.is_closed():
            await page.close()
        return -1, json.dumps({"error": str(e)})

def worker(chunk_data):
    df_chunk, html_dir, screenshots_dir = chunk_data
    
    chunk_results = []

    async def async_tasks():
        async with BrowserManager() as browser:
            for _, row in df_chunk.iterrows():
                result, reason = await process_row_async(browser, row, html_dir, screenshots_dir)
                chunk_results.append({'id': row['id'], 'result': result, 'reason': reason})
   
    asyncio.run(async_tasks())
    
    return chunk_results

def main(input_path, output_dir, html_dir, screenshots_dir, num_threads=None):

    threads_to_use = num_threads if num_threads is not None else MAX_WORKERS
    
    try:
        df = pd.read_json(input_path, lines=True)
        if 'id' not in df.columns:
            df['id'] = list(df.index)
    except Exception as e:
        print(f"Error reading JSON input file {input_path}: {e}")
        exit(1)

    if not os.path.exists(html_dir): os.makedirs(html_dir)
    if not os.path.exists(screenshots_dir): os.makedirs(screenshots_dir)

    print(f"Starting to process {len(df)} HTML records using {threads_to_use} worker threads...")

    num_chunks = threads_to_use
    chunk_size = math.ceil(len(df) / num_chunks)
    chunks = [df.iloc[i:i + chunk_size] for i in range(0, len(df), chunk_size)]
    
    tasks_with_args = [(chunk, html_dir, screenshots_dir) for chunk in chunks]

    all_results_nested = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads_to_use) as executor:
        all_results_nested = list(executor.map(worker, tasks_with_args))

    all_results_flat = [item for sublist in all_results_nested for item in sublist]

    all_results_sorted = sorted(all_results_flat, key=lambda x: x['id'])

    df['result'] = [res['result'] for res in all_results_sorted]
    df['reason'] = [res['reason'] for res in all_results_sorted]
    
    total_files_with_issues = len(df[df['result'] == 1])
    error_ids = df[df['result'] == 0]['id'].tolist()

    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, 'color_detect_chart.json')
    
    if args.save_detailed:
        detail_output_path = os.path.join(args.output, "color_detect_chart_detailed.jsonl")
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
    
    # 按ID排序
    sorted_results = dict(sorted(status_results.items(), 
                                key=lambda x: int(x[0]) if isinstance(x, str) and x[0].isdigit() else x[0]))
    
    # 构建完整的结果字典，包含统计信息
    complete_results = {
        "total_right": no_issue_count,
        "total_wrong": issue_count,
        "results": sorted_results
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(complete_results, f, ensure_ascii=False, indent=2)

    print(f"Results saved to: {output_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Color Detect of Chart")
    parser.add_argument("--input_jsonl", type=str, required=True)
    parser.add_argument("--output_dir", type=str, required=True)
    parser.add_argument("--num_threads", type=int, default=os.cpu_count() or 4)
    parser.add_argument('--save_detailed', action='store_true', default=False)
    args = parser.parse_args()

    if not os.path.exists(args.input_jsonl):
        print(f"Error: input file not found at {args.input_jsonl}")
        exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    html_dir = os.path.join(args.output_dir, 'html')
    screenshots_dir = os.path.join(args.output_dir, 'screenshots')
    os.makedirs(html_dir, exist_ok=True)
    os.makedirs(screenshots_dir, exist_ok=True)

    main(args.input_jsonl, args.output_dir, html_dir, screenshots_dir, args.num_threads)

