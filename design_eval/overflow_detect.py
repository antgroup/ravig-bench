import os
import json
import argparse
import pandas as pd
import asyncio
import threading
import math
from multiprocessing import Manager
from playwright.async_api import async_playwright, Page, Locator, ElementHandle
from typing import List, Dict, Tuple, Set, Any

VIEWPORT_WIDTH = 800
VIEWPORT_HEIGHT = 900

OVERFLOW_TOLERANCE = 10
MIN_MODULE_WIDTH = 50
MIN_MODULE_HEIGHT = 50

DEFAULT_NUM_WORKERS = 6 #os.cpu_count()
# DEFAULT_NUM_WORKERS = 1

DETECT_OVERFLOW_IN_ONE_GO_JS = """
(params) => {
    const { minWidth, minHeight, ruleSelector, tolerance } = params;

    const normalizeColor = (colorStr) => {
        if (colorStr === "rgba(0, 0, 0, 0)" || colorStr === "hsla(0, 0%, 0%, 0)") {
            return "transparent";
        }
        return colorStr;
    };

    const getElementVisualStyle = (element) => {
        try {
            const computedStyle = window.getComputedStyle(element);
            if (computedStyle.display === 'none' || computedStyle.visibility === 'hidden') {
                return null;
            }
            return {
                backgroundColor: normalizeColor(computedStyle.backgroundColor),
                backgroundImage: computedStyle.backgroundImage,
                border: computedStyle.border,
                boxShadow: computedStyle.boxShadow
            };
        } catch (e) {
            return null;
        }
    };
    
    const isVisuallyDistinct = (element, parentEffectiveBg) => {
        const style = getElementVisualStyle(element);
        if (!style) {
            return { isDistinct: false, effectiveBg: parentEffectiveBg };
        }

        if (style.boxShadow !== 'none' || (style.border && !style.border.startsWith('0px')) || style.backgroundImage !== 'none') {
            return { isDistinct: true, effectiveBg: style.backgroundColor };
        }
        
        const currentBg = style.backgroundColor;
        const effectiveBg = currentBg !== 'transparent' ? currentBg : parentEffectiveBg;
        
        if (effectiveBg !== parentEffectiveBg) {
            return { isDistinct: true, effectiveBg: effectiveBg };
        }
        
        return { isDistinct: false, effectiveBg: effectiveBg };
    };

    const findModulesRecursively = (element, parentEffectiveBg, foundModules) => {
        const box = element.getBoundingClientRect();
        const isBody = element.tagName.toLowerCase() === "body";
        if (!isBody && (!box || box.width < minWidth || box.height < minHeight)) {
            return;
        }

        const { isDistinct, effectiveBg } = isVisuallyDistinct(element, parentEffectiveBg);

        if (isDistinct && !isBody) {
            foundModules.push(element);
        } else {
            for (const child of element.children) {
                findModulesRecursively(child, effectiveBg, foundModules);
            }
        }
    };
    
    const getElementDescription = (el) => {
        if (!el) return "[Element Gone]";
        const tag = el.tagName.toLowerCase();
        if (tag === 'body') return "<body> (entire page)";
        let classStr = el.getAttribute('class') || '';
        const classes = classStr.split(' ').filter(c => c);
        if (classes.length > 4) {
            classStr = classes.slice(0, 4).join(' ') + '...';
        }
        const id = el.getAttribute('id');
        let desc = `<${tag}`;
        if (id) desc += ` id='${id}'`;
        if (classStr) desc += ` class='${classStr}'`;
        desc += '>';
        return desc;
    }

    const body = document.body;
    const bodyStyle = getElementVisualStyle(body);
    const canvasBg = bodyStyle ? bodyStyle.backgroundColor : 'transparent';
    const foundSubModules = [];
    findModulesRecursively(body, canvasBg, foundSubModules);
    const ruleBasedModules = Array.from(document.querySelectorAll(ruleSelector));
    const allPotentialModules = foundSubModules.concat(ruleBasedModules);
    const modulesToCheck = Array.from(new Set(allPotentialModules));

    const isDecorativeIntent = (element, computedStyle) => {
        const isAriaHidden = element.getAttribute('aria-hidden') === 'true';
        const isFadedAbsolute = computedStyle.position === 'absolute' && parseFloat(computedStyle.opacity) < 1.0;
        const isAnEmptyDecorativeDiv =
            element.tagName.toLowerCase() === 'div' &&
            element.children.length === 0 &&
            (element.textContent || '').trim() === '';
        const isAbsoluteAndOutside = computedStyle.position === 'absolute' && (
            parseFloat(computedStyle.top) < 0 ||
            parseFloat(computedStyle.right) < 0 ||
            parseFloat(computedStyle.bottom) < 0 ||
            parseFloat(computedStyle.left) < 0
        );
        return isAriaHidden || isFadedAbsolute || isAnEmptyDecorativeDiv || isAbsoluteAndOutside;
    };

    const isOverflowHandled = (child, container, axis) => {
        let current = child.parentElement;
        const overflowProperty = axis === 'x' ? 'overflowX' : 'overflowY';

        while (current && current !== container && current !== document.body) {
            try {
                const style = window.getComputedStyle(current);
                const overflowValue = style[overflowProperty];
                if (overflowValue === 'auto' || overflowValue === 'scroll') {
                    return true;
                }
            } catch (e) { /* ignore */ }
            current = current.parentElement;
        }
        return false;
    };

    /**
     * @param {Element} element - The element to check.
     * @returns {boolean} - True if the element is an empty (transparent) canvas.
     */
    const isCanvasEmpty = (element) => {
        if (element.tagName.toLowerCase() !== 'canvas') {
            return false;
        }
        // A canvas with no dimensions is effectively empty
        if (element.width === 0 || element.height === 0) {
            return true;
        }
        try {
            const context = element.getContext('2d');
            if (!context) {
                // Could be a WebGL context, safer to assume it's not empty
                return false;
            }
            const imageData = context.getImageData(0, 0, element.width, element.height).data;
            // Check if all pixels are transparent
            for (let i = 3; i < imageData.length; i += 4) {
                if (imageData[i] !== 0) {
                    return false; // Found a non-transparent pixel
                }
            }
            return true; // All pixels are transparent
        } catch (e) {
            // Errors (e.g., tainted canvas) are treated as not-empty for safety
            return false;
        }
    };


    const allOverflowResults = [];

    for (const module of modulesToCheck) {
        try {
            const moduleStyle = window.getComputedStyle(module);
            const overflowX = moduleStyle.overflowX;
            const overflowY = moduleStyle.overflowY;

            const checkXOverflow = overflowX !== 'auto' && overflowX !== 'scroll';
            const checkYOverflow = overflowY !== 'auto' && overflowY !== 'scroll';
            
            if (!checkXOverflow && !checkYOverflow) {
                continue;
            }

            const parentBox = module.getBoundingClientRect();
            if (!parentBox || parentBox.width === 0 || parentBox.height === 0) {
                continue;
            }

            const children = Array.from(module.querySelectorAll('*'));
            
            const elementsToSkip = new Set();
            for (const el of children) {
                try {
                    const style = window.getComputedStyle(el);
                    if (isDecorativeIntent(el, style)) {
                        el.querySelectorAll('*').forEach(descendant => elementsToSkip.add(descendant));
                    }
                } catch(e) { }
            }
            
            for (const child of children) {
                if (elementsToSkip.has(child)) {
                    continue; 
                }

                try {
                    const childBox = child.getBoundingClientRect();
                    const computedStyle = window.getComputedStyle(child);

                    if (computedStyle.display === 'none' ||
                        computedStyle.visibility === 'hidden' ||
                        computedStyle.opacity === '0' ||
                        childBox.width === 0 ||
                        childBox.height === 0) {
                        continue;
                    }
                    
                    if (isCanvasEmpty(child)) {
                        continue;
                    }

                    let isReportableOverflow = false;
                    const overflowDetails = [];

                    const childRight = childBox.left + childBox.width;
                    const childBottom = childBox.top + childBox.height;
                    const parentRight = parentBox.left + parentBox.width;
                    const parentBottom = parentBox.top + parentBox.height;

                    if (checkXOverflow) {
                        if (childBox.left < parentBox.left - tolerance) {
                            if (!isOverflowHandled(child, module, 'x')) {
                                isReportableOverflow = true;
                                overflowDetails.push(`Left overflow ${(parentBox.left - childBox.left).toFixed(2)}px`);
                            }
                        }
                        if (childRight > parentRight + tolerance) {
                            if (!isOverflowHandled(child, module, 'x')) {
                                isReportableOverflow = true;
                                overflowDetails.push(`Right overflow  ${(childRight - parentRight).toFixed(2)}px`);
                            }
                        }
                    }
                    
                    if (checkYOverflow) {
                        if (childBox.top < parentBox.top - tolerance) {
                            if (!isOverflowHandled(child, module, 'y')) {
                                isReportableOverflow = true;
                                overflowDetails.push(`Top overflow ${(parentBox.top - childBox.top).toFixed(2)}px`);
                            }
                        }
                        if (childBottom > parentBottom + tolerance) {
                            if (!isOverflowHandled(child, module, 'y')) {
                                isReportableOverflow = true;
                                overflowDetails.push(`Bottom overflow ${(childBottom - parentBottom).toFixed(2)}px`);
                            }
                        }
                    }

                    if (isReportableOverflow) {
                        if (!isDecorativeIntent(child, computedStyle)) {
                            allOverflowResults.push({
                                overflow_module: getElementDescription(module),
                                child_description: getElementDescription(child),
                                details: overflowDetails.join(', ')
                            });
                        }
                    }
                } catch (e) {}
            }
        } catch (e) {}
    }
    
    return allOverflowResults;
}

"""

def load_reference_results(ref_file_path: str) -> Dict[str, Dict]:
   
    ref_results = {}
    if not ref_file_path or not os.path.exists(ref_file_path):
        print(f"Reference file does not exist or was not specified: {ref_file_path}")
        return ref_results
    
    try:
        with open(ref_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    url = data.get('url', '')
                    result = data.get('result')
                    reason = data.get('reason', '')
                    
                    if url and result is not None:
                        ref_results[url] = {
                            'result': result,
                            'reason': reason
                        }
                except json.JSONDecodeError as e:
                    print(f"JSON parse error at line {line_num} of reference file: {e}")
                    continue
                except Exception as e:
                    print(f"Error processing line {line_num} of reference file: {e}")
                    continue
    except Exception as e:
        print(f"Failed to read reference file: {e}")
    
    print(f"Reference file loaded, containing {len(ref_results)} records.")
    return ref_results

async def process_item_async(page: Page, url: str) -> List[Dict]: 
   
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"Failed to load page {url}: {e}")
        return [{"error": f"Page load failed: {e}"}]

    overflow_issues = await page.evaluate(DETECT_OVERFLOW_IN_ONE_GO_JS, {
        "minWidth": MIN_MODULE_WIDTH,
        "minHeight": MIN_MODULE_HEIGHT,
        "ruleSelector": ".card",  
        "tolerance": OVERFLOW_TOLERANCE
    })
    
    if overflow_issues:
        print(f"Detected {len(overflow_issues)} overflow issues in url: {url}:")
        # Group by module for cleaner logging
        issues_by_module = {}
        for issue in overflow_issues:
            module_desc = issue['overflow_module']
            if module_desc not in issues_by_module:
                issues_by_module[module_desc] = []
            issues_by_module[module_desc].append(issue)
        
        for module_desc, issues in issues_by_module.items():
            print(f"In module [{module_desc}]:")
            for issue in issues:
                 print(f"Check complete. Overflow element: {issue['child_description']} | Details: {issue['details']}")
    else:
        print(f"No overflow detected in url: {url}.")

    return overflow_issues


def worker(
    task_chunk: List[Dict[str, Any]],
    results_list: List[Tuple[int, int, str]],
    html_dir: str,
    worker_id: int,
    ref_results: Dict[str, Dict] = None
):

    print(f"[Worker-{worker_id}] started, will process {len(task_chunk)} tasks.")
    
    async def run_async_tasks():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            
            total_tasks = len(task_chunk)
            for idx, task in enumerate(task_chunk, 1):
                current_id = task['id']
                url = task.get('url')
                html_doc = task.get('html')
                
                target_url = None
                temp_html_path = os.path.join(html_dir, f"temp_{worker_id}_{current_id}.html")
                
                if url:
                    target_url = "file://" + url
                elif html_doc:
                    try:
                        with open(temp_html_path, "w", encoding="utf-8") as f:
                            f.write(html_doc)
                        target_url = "file://" + os.path.abspath(temp_html_path)
                    except Exception as e:
                        print(f"[Worker-{worker_id}] Failed to create temporary HTML file for ID {current_id}: {e}")
                        results_list.append((current_id, -1, json.dumps([{"error": f"File creation failed: {e}"}])))
                        continue
                else:
                    print(f"[Worker-{worker_id}] ID {current_id} has neither 'url' nor 'html' field, skipping.")
                    results_list.append((current_id, -1, json.dumps([{"error": "Missing 'url' or 'html' field."}])))
                    continue

                if ref_results and url in ref_results:
                    ref_result = ref_results[url]['result']
                    ref_reason = ref_results[url]['reason']
                    
                    if ref_result in [0, 1]:  
                        print(f"[Worker-{worker_id}] Retrieved result from reference file for ID {current_id}: result={ref_result}")
                        results_list.append((current_id, ref_result, ref_reason))
                        
                        if os.path.exists(temp_html_path):
                            os.remove(temp_html_path)
                        continue
                    else:
                        print(f"[Worker-{worker_id}] Result for ID {current_id} in reference file is {ref_result}, rechecking.")

                page = await context.new_page()
                await page.set_viewport_size({"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT})
                await page.evaluate(f"document.title = '{current_id}'")

                try:
                    overflow_issues = await process_item_async(page, target_url)
                    
                    if overflow_issues and isinstance(overflow_issues, list) and overflow_issues and "error" in overflow_issues[0]:
                         results_list.append((current_id, -1, json.dumps(overflow_issues, ensure_ascii=False)))
                    elif overflow_issues:
                        results_list.append((current_id, 0, json.dumps(overflow_issues, ensure_ascii=False)))
                    else:
                        results_list.append((current_id, 1, json.dumps([], ensure_ascii=False)))
                
                except Exception as e:
                    print(f"[Worker-{worker_id}] Critical error while processing ID {current_id}: {e}")
                    results_list.append((current_id, -1, json.dumps([{"error": str(e)}], ensure_ascii=False)))
                finally:
                    await page.close()
                    if os.path.exists(temp_html_path):
                        os.remove(temp_html_path)

            await browser.close()
            
    asyncio.run(run_async_tasks())
    print(f"[Worker-{worker_id}] Processing complete.")


def main(input_path: str, output_dir: str, html_dir: str, num_workers: int, ref_file: str = None):
  
    try:
        df = pd.read_json(input_path, lines=True)
        if 'id' not in df.columns:
            df['id'] = list(df.index)
        
    except Exception as e:
        print(f"Error reading JSON input file {input_path}: {e}")
        exit(1)

    ref_results = load_reference_results(ref_file) if ref_file else {}

    tasks = df.to_dict('records')
    if not tasks:
        print("Input file is empty.")
        return

    if ref_results:
        print(f"Will skip existing results (result=0 or 1) using the reference file...")
    
    chunk_size = math.ceil(len(tasks) / num_workers)
    task_chunks = [tasks[i:i + chunk_size] for i in range(0, len(tasks), chunk_size)]
    
    threads = []
    manager = Manager()
    shared_results_list = manager.list()
    
    for i, chunk in enumerate(task_chunks):
        thread = threading.Thread(target=worker, args=(chunk, shared_results_list, html_dir, i + 1, ref_results))
        threads.append(thread)
        thread.start()
        
    for thread in threads:
        thread.join()

    final_results = sorted(list(shared_results_list), key=lambda x: x[0])
    
    results_map = {item[0]: (item[1], item[2]) for item in final_results}
    
    df['result'] = df['id'].map(lambda i: results_map.get(i, (-2, '{"error": "Result not found"}'))[0])
    df['reason'] = df['id'].map(lambda i: results_map.get(i, (-2, '{"error": "Result not found"}'))[1])
    
    error_ids = df[df['result'] == 1]['id'].tolist()
    failed_ids = df[df['result'] == -1]['id'].tolist()
    skipped_from_ref = 0
    
    if ref_results:
        for task in tasks:
            url = task.get('url')
            if url in ref_results and ref_results[url]['result'] in [0, 1]:
                skipped_from_ref += 1
    
    if error_ids:
        print(f"List of problematic IDs: {error_ids}")
    if failed_ids:
        print(f"Number of failed tasks: {len(failed_ids)}")
        print(f"List of failed IDs: {failed_ids}")
    if skipped_from_ref > 0:
        print(f"Number of tasks skipped from reference file: {skipped_from_ref}")
        
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, 'overflow_detect.json')
    
    if args.save_detailed:
        detail_output_path = os.path.join(args.output, "overflow_detect_detailed.jsonl")
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_jsonl", type=str, required=True)
    parser.add_argument("--output_dir", type=str, required=True)
    parser.add_argument("--num_threads", type=int, default=DEFAULT_NUM_WORKERS)
    parser.add_argument("--ref", default=None)
    parser.add_argument('--save_detailed', action='store_true', default=False)
    
    args = parser.parse_args()

    if not os.path.exists(args.input_jsonl):
        print(f"Error: Input file not found at {args.input_jsonl}")
        exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    html_dir = os.path.join(args.output_dir, 'html')
    os.makedirs(html_dir, exist_ok=True)
    
    main(args.input_jsonl, args.output_dir, html_dir, args.num_threads, args.ref)
            
    print("----Done!----")
