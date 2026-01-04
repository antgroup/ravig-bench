import nest_asyncio
nest_asyncio.apply()
import pandas as pd
import asyncio
from pyppeteer import launch
import time
import os
import argparse
from PIL import Image

async def wait_for_page_stable(page, timeout=30000, check_interval=500):

    print("Waiting for the page to stabilize...")
    start_time = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start_time) * 1000 < timeout:
        last_height = await page.evaluate('document.body.scrollHeight')
        await asyncio.sleep(check_interval / 1000) 
        new_height = await page.evaluate('document.body.scrollHeight')

        if new_height == last_height:
            return

    raise TimeoutError(f"Timeout: Page height continues to change within {timeout}ms.")

async def capture_content_bound(browser, url, output_path, max_retries=3):
    retry_count = 0
    page = None
    while retry_count < max_retries:
        try:
            page = await browser.newPage()
            await page.setViewport({
                'width': args.width if args.type=='app' else 800,
                'height': 844 if args.type=='app' else 100
            })
            await page.goto(url, {'waitUntil': 'networkidle0', 'timeout': 600000})

            print("Adjusting viewport-dependent element heights...")
            await page.evaluate('''() => {
                const vhElements = document.querySelectorAll('.h-screen, .min-h-screen');
                for (const el of vhElements) {
                    el.style.height = 'auto';
                    el.style.minHeight = 'auto';
                }
                                
                const revealElements = document.querySelectorAll('.reveal');
                for (const el of revealElements) {
                    el.classList.add('show');
                }
            }''')

            content_metrics = await page.evaluate('''() => {
                const body = document.body;
                const html = document.documentElement;
                return {
                    body_scrollHeight: body.scrollHeight,
                    html_scrollHeight: html.scrollHeight,
                    body_offsetHeight: body.offsetHeight,
                    html_offsetHeight: html.offsetHeight,
                    body_clientHeight: body.clientHeight,
                    html_clientHeight: html.clientHeight,
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
                'width': 800,
                'height': content_metrics['height']
            })

            await page.evaluate(f'(y) => window.scrollTo(0, y)', content_metrics['height'])

            try:
                await wait_for_page_stable(page, timeout=60000, check_interval=3000) 
            except TimeoutError as e:
                print(e)

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

            await page.setViewport({
                'width': 800,
                'height': content_size_final['height']
            })
            await asyncio.sleep(5)

            await page.screenshot({
                'path': output_path,
                'clip': {  
                    'x': 0,
                    'y': 0,
                    'width': content_size_final['width'],
                    'height': content_size_final['height']
                }
            })

            await page.close()
            return True  
        except Exception as e:
            retry_count += 1
            print(f"Attempt {retry_count} failed for {url}: {str(e)}")
            if retry_count < max_retries:
                print(f"Retrying... ({retry_count}/{max_retries})")
                await asyncio.sleep(2) 
            else:
                print(f"Max retries reached for {url}. Giving up.")
                return False  
        finally:
            if page and not page.isClosed():
                print(f"[{url}] Cleaning up page in finally block...")
                await page.close()

async def process_url(browser, url, output_path, semaphore):
    async with semaphore:  
        if os.path.exists(output_path):
            return url, output_path, True 
        
        success = await capture_content_bound(browser, url, output_path)
        return url, output_path, success

async def screenshot(urls, concurrency=5, output = '/Users/yangwei/Downloads/iphone12pro_screenshot'):
    semaphore = asyncio.Semaphore(concurrency)
    outputs = []
    failed_urls = []
    skipped_count = 0
    
    print("Launching a shared browser instance...")
    browser = await launch(
        headless=True,
        args=['--no-sandbox', '--disable-setuid-sandbox'] 
    )

    tasks = []
    for i, url in enumerate(urls):
        output_path = f"{output}/{url.split('/')[-1].split('.')[0]}.png"
        outputs.append(output_path)
        
        if os.path.exists(output_path):
            skipped_count += 1
            continue
            
        tasks.append(process_url(browser, url, output_path, semaphore))

    if tasks:  
        results = await asyncio.gather(*tasks)

        for i, (url, output_path, success) in enumerate(results):
            if success:
                print(f"{i}, url:", url)
                print(f"Screenshot saved to {output_path}")
            else:
                failed_urls.append(url)
                print(f"Failed to capture {url}")
            print("----" * 100)
    else:
        print("All files already exist.")

    print("Closing the shared browser instance.")
    await browser.close()

    return outputs, failed_urls

def main():

    try:
        df = pd.read_json(input,lines=True)
        if "id" not in df.columns:
            df['id']=list(df.index)
        if args.limit is not None:
            df = df.iloc[:args.limit]
    except Exception as e:
        print(f"Read Json {input} Error: {e}")
        exit(1)

    urls=[]
    html_skipped_count = 0
    
    for _,row in df.iterrows():
        index=row['id']
        html_path = os.path.join(output,f'{index}.html')
        png_path = os.path.join(output,f'{index}.png')

        if not os.path.exists(png_path):
            with open(html_path, 'w',encoding='utf-8') as file:
                file.write(row['html'].replace("```html", "").replace("```", ""))
            urls.append(f"file://{output}/{index}.html")
        else:
            html_skipped_count += 1

    if urls:  
        outputs, failed_urls = asyncio.get_event_loop().run_until_complete(screenshot(urls,concurrency=args.processes,output=output))
        print("Failed URLs:", failed_urls)
    else:
        print("All PNG files already exist.")

    print("\n--- Done! ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Web Screenshot Tool")
    parser.add_argument("--root")
    parser.add_argument('--input', type=str, required=True)
    parser.add_argument('--output', type=str, required=True)
    parser.add_argument('--processes', type=int, default=os.cpu_count() or 4)
    parser.add_argument('--type', type=str, default='web')
    parser.add_argument('--width', type=int, default=718)
    parser.add_argument('--limit', type=int, default=None)
    args = parser.parse_args()

    if not os.path.exists(args.root):
        os.makedirs(args.root)
    input=os.path.join(args.root,args.input)
    output=os.path.join(args.root,args.output)
    if not os.path.exists(output):
        os.makedirs(output)

    main()
