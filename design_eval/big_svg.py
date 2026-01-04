import pandas as pd
import asyncio
import os
import argparse
import json
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser

TAILWIND_WIDTH_CLASSES = {
    # Key: Tailwind class, Value: Expected CSS width
    "w-4": "16px",
    "w-5": "20px",
    "w-6": "24px",
    "w-8": "32px",
    "w-10": "40px",
    "w-full": "100%", # Percentage is also supported
}

MAX_CONCURRENT_TASKS = 10

async def check_svg_widths_async(html_content: str, browser: Browser, row_index: int) -> dict:

    eval_details = {
        'overall_status': 'OK',
        'summary': '',
        'svg_checks': []
    }
    
    page = None
    try:
        page = await browser.new_page()
        await page.route(
            "**/*",  
            lambda route: route.abort() if route.request.resource_type == "image" else route.continue_()
        )

        await page.set_content(html_content, timeout=60000, wait_until="load" )
        
        svg_elements = await page.locator("svg").all()
        
        if not svg_elements:
            eval_details['summary'] = 'No SVG element found'
            return eval_details

        eval_details['summary'] = f"Find {len(svg_elements)} SVG elements."
        
        for i, svg in enumerate(svg_elements):
            svg_check_result = {
                'svg_index': i + 1,
                'status': 'INFO', # Status: OK, FAILED, INFO
                'message': '',
                'tailwind_class': 'N/A',
                'expected_width': 'N/A',
                'actual_width': 'N/A',
            }
            
            class_string = await svg.get_attribute("class")
            if not class_string:
                svg_check_result['message'] = 'SVG elements do not have a class attribute'
                eval_details['svg_checks'].append(svg_check_result)
                continue
            
            svg_classes = set(class_string.split())
            found_testable_class = False

            for tw_class, expected_width in TAILWIND_WIDTH_CLASSES.items():
                if tw_class in svg_classes:
                    found_testable_class = True
                    svg_check_result['tailwind_class'] = tw_class
                    svg_check_result['expected_width'] = expected_width

                    actual_width = await svg.evaluate("element => window.getComputedStyle(element).width")
                    svg_check_result['actual_width'] = actual_width
                    
                    if 'px' in actual_width and float(actual_width.split('px')[0]) >= 100:
                        svg_check_result['status'] = 'FAILED'
                        svg_check_result['message'] = f"Width detection failed! Expected'{expected_width}', actual '{actual_width}'."
                        eval_details['overall_status'] = 'FAILED'
                        break
                    else:
                        svg_check_result['status'] = 'OK'
                        svg_check_result['message'] = f"Width detection passed ({tw_class})"
                                
            if not found_testable_class:
                svg_check_result['message'] = "No testable width class (such as 'w-4', 'w-full', etc.) was found."
                
            eval_details['svg_checks'].append(svg_check_result)

    except Exception as e:
        error_message = f"Error: {e}"
        print(f"[Task {row_index}] Error: {error_message}")
        eval_details['overall_status'] = 'ERROR'
        eval_details['summary'] = error_message
    finally:
        if page:
            await page.close()
            
    print(f"[Task {row_index}] Done, Status: {eval_details['overall_status']}.")
    return eval_details


async def process_dataframe_async(df: pd.DataFrame) -> pd.DataFrame:
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    
    async def worker(index, row, browser):
        async with semaphore:
            return await check_svg_widths_async(row['html'], browser, index)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        
        tasks = [worker(index, row, browser) for index, row in df.iterrows()]
        
        results = await asyncio.gather(*tasks)
        
        await browser.close()
        
    df['eval_result'] = results
    return df

def get_result(eval_result):
    try:
        svg_checks = eval_result['svg_checks']
        for k in svg_checks:
            actual_width = float(k['actual_width'].split('px')[0]) if 'px' in str(k['actual_width']) else 0
            expected_width = float(k['expected_width'].split('px')[0]) if 'px' in str(k['expected_width']) else 0
            if k['status'] == 'FAILED' and actual_width >= 100 and expected_width < actual_width:
                return 0
    except:
        print(eval_result)
    return 1

async def main():
    input_path=args.input
    df = pd.read_json(input_path, lines=True)
    
    result_df = await process_dataframe_async(df.copy())
    print(result_df[['id', 'eval_result']].to_string())

    if args.save_detailed:
        detail_output_path = os.path.join(args.output, "big_svg_detailed.jsonl")
        result_df.to_json(detail_output_path, orient='records', lines=True, force_ascii=False)
    
    output_path = os.path.join(args.output, "big_svg.json")

    status_results = {}
    no_issue_count = 0
    issue_count = 0
    
    for idx, row in result_df.iterrows():
        status = get_result(row['eval_result'])
        file_id = row['id']
        status_results[file_id] = status
        if status == 1:
            no_issue_count += 1
        else:
            issue_count += 1
    
    # 按ID排序
    sorted_results = dict(sorted(status_results.items(), 
                                key=lambda x: int(x[0]) if isinstance(x, str) and x[0].isdigit() else x))
    
    # 构建完整的结果字典，包含统计信息
    complete_results = {
        "total_right": no_issue_count,
        "total_wrong": issue_count,
        "results": sorted_results
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(complete_results, f, ensure_ascii=False, indent=2)

    print(f"\nResults have been saved to: {os.path.abspath(output_path)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Big SVG")
    parser.add_argument('--input', type=str, required=True, default = '')
    parser.add_argument('--output', type=str, required=True)
    parser.add_argument('--processes', type=int, default=os.cpu_count() or 4)
    parser.add_argument('--save_detailed', action='store_true', default=False)
    args = parser.parse_args()

    if not os.path.exists(args.output):
        os.makedirs(args.output)
    asyncio.run(main())