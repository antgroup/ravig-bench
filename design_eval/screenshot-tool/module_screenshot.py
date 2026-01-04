import asyncio
from pyppeteer import launch
from PIL import Image
import numpy as np
from io import BytesIO
import os
import multiprocessing
import platform
import pandas as pd
import argparse
threshold = 0.9

from PIL import Image, ImageChops

async def repair_image_if_needed(image_path: str, threshold: float = 0.95, darkness_level: int = 50):
    try:
        with Image.open(image_path) as img:
            grayscale_img = img.convert('L')
            width, height = grayscale_img.size
            repaired = False

            for y in range(1, height - 1): 
                line_pixels = [grayscale_img.getpixel((x, y)) for x in range(width)]
                
                most_common_pixel = max(set(line_pixels), key=line_pixels.count)
                count = line_pixels.count(most_common_pixel)

                if (count / width) > threshold and most_common_pixel < darkness_level:
                    prev_line_most_common = max(set([grayscale_img.getpixel((x, y-1)) for x in range(width)]), key=line_pixels.count)
                    if prev_line_most_common > darkness_level:
                        line_to_copy = img.crop((0, y - 1, width, y))
                        img.paste(line_to_copy, (0, y))
                        repaired = True
            
            if repaired:
                img.save(image_path)

    except Exception as e:
        print(f"An error occurred while repairing the image  {image_path}: {e}")

def parse_ids(ids_string):
    ids = set()
    
    for part in ids_string.split(','):
        part = part.strip()
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                ids.update(range(start, end + 1))
            except ValueError:
                print(f"Error: Unable to resolve '{part}'")
        else:
            try:
                ids.add(int(part))
            except ValueError:
                print(f"Error: Unable to resolve '{part}'")
    
    return sorted(list(ids))

async def screenshot(output, index, type, url, browser) -> None | int:
    page = None
    try:
        page = await browser.newPage()

        await page.setViewport({
            'width': 390 if type=='app' else 800,
            'height': 100,
            'deviceScaleFactor': 1
        })

        await page.goto(url, {'waitUntil': 'networkidle0', 'timeout': 600000}) 

        content_size_initial = await page.evaluate('''() => {
            const body = document.body;
            const html = document.documentElement;
            return {
                width: Math.max(
                    body.scrollWidth, html.scrollWidth,
                    body.offsetWidth, html.offsetWidth,
                    body.clientWidth, html.clientWidth
                ),
                height: Math.max(
                    body.scrollHeight, html.scrollHeight,
                    body.offsetHeight, html.offsetHeight,
                    body.clientHeight, html.clientHeight
                )
            };
        }''')

        await page.setViewport({
            'width': content_size_initial['width'],
            'height': content_size_initial['height'],
            'deviceScaleFactor': 1
        })

        await page.evaluate(f'(y) => window.scrollTo(0, y)', content_size_initial['height'])

        await asyncio.sleep(20) 

        content_size_final = await page.evaluate('''() => {
            const body = document.body;
            const html = document.documentElement;
            return {
                width: Math.max(
                    body.scrollWidth, html.scrollWidth,
                    body.offsetWidth, html.offsetWidth,
                    body.clientWidth, html.clientWidth
                ),
                height: Math.max(
                    body.scrollHeight, html.scrollHeight,
                    body.offsetHeight, html.offsetHeight,
                    body.clientHeight, html.clientHeight
                )
            };
        }''')

        if content_size_final['height'] > content_size_initial['height']:
            await page.setViewport({
                'width': content_size_final['width'],
                'height': content_size_final['height'],
                'deviceScaleFactor': 1
            })
            await asyncio.sleep(2) 
        
        effective_content_height = content_size_final['height']

        all_headers = await page.querySelectorAll('h1, h2')

        header_data = [] 
        for header_elem in all_headers:
            box = await header_elem.boundingBox()
            if box:
                header_data.append((header_elem, box))

        if not header_data:
            min_y = 0
            max_bottom = effective_content_height
            clip_height = max_bottom - min_y
            
            if clip_height > 0:
                output_path = f'{output}/{index}_full_page.png'

                screenshot_data = await page.screenshot({
                    'type': 'png',
                    'clip': {'x': 0, 'y': min_y, 'width': content_size_final['width'], 'height': clip_height},
                    'path': output_path,
                    'omitBackground': False
                })

                print({
                    'type': 'Full Page',
                    'position': {'x': 0, 'y': min_y, 'width': content_size_final['width'], 'height': clip_height},
                })

            return None 

        for idx, (current_header_elem, current_header_box) in enumerate(header_data):
            min_y = current_header_box['y']

            if idx + 1 < len(header_data):
                next_header_box = header_data[idx + 1][1]
                max_bottom = next_header_box['y']
            else:
                max_bottom = effective_content_height

                quote_div_top = await page.evaluate(f'''(minY) => {{
                    const quoteDivs = document.querySelectorAll('div.quote');
                    for (let i = 0; i < quoteDivs.length; i++) {{
                        const rect = quoteDivs[i].getBoundingClientRect();
                        if (rect.top >= minY) {{
                            return rect.top; 
                        }}
                    }}
                    return null;
                }}''', min_y)

                if quote_div_top is not None:
                    max_bottom = max(min_y, quote_div_top)
                
            clip_x = 0
            clip_width = content_size_final['width']
            clip_height = max_bottom - min_y

            if clip_height <= 0:
                print(f"Web {index} Module {idx+1}: the screenshot height is {clip_height}, skip.")
                continue

            output_path = f'{output}/{index}_{idx+1}.png'

            try:
                screenshot_data = await page.screenshot({
                    'type': 'png',
                    'clip': {'x': round(clip_x), 'y': round(min_y), 'width': round(clip_width), 'height': round(clip_height)},
                    'path': output_path,
                    'omitBackground': False
                })
                print(f'Web {index} Module {idx+1} Done.')
                await repair_image_if_needed(output_path)

                print({
                    'type': 'H1/H2 Section',
                    'position': {'x': clip_x, 'y': min_y, 'width': clip_width, 'height': clip_height},
                })

            except Exception as e:
                print(f"Web {index} Module {idx+1} Error: {e}")

        await page.close()
        return None
    except Exception as e:
        print(f"Web {index} Error: {e}")
        return None 
    finally:
        if page and not page.isClosed():
                print(f"[{url}] Cleaning up page in finally block...")
                await page.close()
    return None

async def main():
    print("Launching a shared browser instance...")
    browser = await launch(
        headless=True,
        args=['--no-sandbox', '--disable-setuid-sandbox']
    )

    try:
        df = pd.read_json(os.path.join(args.root, args.input), lines=True)
        if 'id' not in df.columns:
            df['id'] = df.index.astype(str)

        if args.ids:
            specified_ids = parse_ids(args.ids)
            df = df[df['id'].astype(int).isin(specified_ids)].copy()
        elif args.limit is not None:
            df = df.iloc[:args.limit].copy()
            
    except Exception as e:
        print(f"Read Json {args.input} Error: {e}")
        return

    if len(df) == 0:
        print("No data was found.")
        return

    tasks = []
    for _, row in df.iterrows():
        index = str(row['id'])
        html_file_path = os.path.join(args.output, f'{index}.html')
        cleaned_html = row['html'].replace("```html", "").replace("```", "").strip()
        with open(html_file_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_html)
        file_url = f"file://{os.path.abspath(html_file_path)}"
        task = screenshot(args.output, index, args.type, file_url, browser)
        tasks.append(task)

    semaphore = asyncio.Semaphore(args.processes)  

    async def sem_task(task):
        async with semaphore:
            return await task

    limited_tasks = [sem_task(task) for task in tasks]
    await asyncio.gather(*limited_tasks)

    await browser.close()
    print("\n--- Done! ---")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Module Screenshot Tool")
    parser.add_argument("--root")
    parser.add_argument('--input', type=str, required=True)
    parser.add_argument('--output', type=str, required=True,)
    parser.add_argument('--processes', type=int, default=os.cpu_count() or 4)
    parser.add_argument('--type', type=str, default='web')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--ids', type=str, default=None)
    
    args = parser.parse_args()
    
    input_path = os.path.join(args.root, args.input)
    output_path = os.path.join(args.root, args.output)
    
    os.makedirs(output_path, exist_ok=True)
    
    args.input = input_path
    args.output = output_path
    
    asyncio.run(main())