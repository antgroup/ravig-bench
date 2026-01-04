import argparse
import os
import json
import base64
import pandas as pd
from tqdm import tqdm
import concurrent.futures 
from openai import OpenAI
from PIL import Image
import threading
import glob

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
authorization_file_path = os.path.join(parent_dir, "config", "authorization.json")
MODEL_CONFIG = json.loads(open(authorization_file_path, encoding='utf8').read())

SYSTEM_PROMPT = """ 
## Role and Goal
You are a senior Web developer. You need to check if a webpage has missing information in its rendered output due to component rendering failures or image loading failures (e.g., JavaScript charts, failure to load external resources). The page's functionality and layout are implemented using HTML, CSS, and JavaScript.

The user will provide the following two types of input:
1. **HTML Code**: This includes the page structure, styles, script resources, etc. It may use external libraries such as TailwindCSS, Chart.js, etc.
2. **Screenshot of the rendered page from the HTML code**: This shows the visual appearance of the page after being rendered in a browser.

Your task is to:
1. Read and analyze the HTML code to identify parts that could affect the display of page components, such as charts within <canvas>, images, dynamic content, or dependent external resources.
2. Determine which visual components or images are present in the HTML code and should be rendered, but are not correctly displayed in the actual rendering, resulting in missing information. Pay special attention to abnormal white spaces, as they are often caused by missing information.
3. Based on the rendered screenshot, check for elements that are present in the code but missing from the screenshot. The reasons for this absence might include: external images failing to load, charts not loading, components not rendering correctly, etc.
4. If such issues exist, please clearly point out:
    - Which parts have issues?
    - Which elements exist in the HTML code but are missing in the actual rendering, causing the information loss?
    - The specific potential reasons for the issue.
4. If no issues are found, please state clearly that no abnormalities were detected.

## Special Notes
- **Missing information refers to**: information that should have been presented to the user but is not included in the final rendered result due to visual design or rendering issues, making it inaccessible to the user.
- **Core Principle**: Determine if there is missing information by comparing the correspondence between elements in the HTML code and elements in the rendered screenshot.
- Do not consider cases where some bars in a bar chart are missing. This is often because the corresponding values are too small or incorrect, making them visually close to zero, which is not a rendering anomaly that causes a blank space.
- For instance, a bar chart might have a situation where the values for some categories are so small compared to others that their bars are too short to be visible, appearing close to zero. This is not considered an abnormal blank space.
- Not all white space is due to missing information; this must be verified against the HTML code. Not all missing information leads to abnormal white space, for example, an image failing to load but its placeholder is still present.

## Output Requirements:
Please return the analysis result in a structured JSON format. If there are no errors, the value for "reason" should be an empty string. Output the result directly. Do not wrap it with ```json ```.
{
    "is_error": "Yes or No",
    "reason": "Specify which part has an issue, which chart was not rendered correctly, and the specific reason for the problem."
}
"""

CASE_1 = """
## Example usage cases:
Here is a practical example of using this prompt for reference:

### Example 1:
**Background: Dynamically Generated Chart Page**
- **HTML Code**:
<!DOCTYPE html>
<html lang="en">

<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Average Cost of Raising a Child in the US</title>
  <link href="https://cdn.jsdelivr.net/npm/preline@2.0.3/dist/preline.min.css" rel="stylesheet">
  <link href="https://cdn.staticfile.org/tailwindcss/2.2.19/tailwind.min.css" rel="stylesheet">
  <style>
    body {
      font-family: Tahoma, Arial, Roboto, "Droid Sans", "Helvetica Neue", "Droid Sans Fallback", "Heiti SC",
        "Hiragino Sans GB", Simsun, sans-self;
    }

   .hero {
      background-color: #f0f2f5;
      padding: 2rem;
      text-align: center;
    }

   .card {
      margin: 1rem;
      padding: 1rem;
      border-radius: 0.5rem;
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }

   .chart-container {
      max-width: 800px;
      margin: 0 auto;
    }
  </style>
</head>

<body>
  <div class="hero">
    <h1 class="text-3xl font-bold">Average Cost of Raising a Child in the US</h1>
    <p class="text-lg">Get insights into the annual expenses and regional variations.</p>
  </div>

  <div class="card">
    <h2 class="text-2xl font-bold mb-2">Core Insight</h2>
    <p>A 2023 study by LendingTree estimated the average annual cost at $21,681, with significant regional differences
      (e.g., Massachusetts ~$36k vs. Mississippi ~$16k per year).</p>
  </div>

  <div class="card">
    <h2 class="text-2xl font-bold mb-2">Expense Breakdown (Percentage)</h2>
    <canvas id="expensePieChart" width="400" height="400"></canvas>
    <script>
      const ctx = document.getElementById('expensePieChart').getContext('2d');
      const expensePieChart = new Chart(ctx, {
        type: 'pie',
        data: {
          labels: ['Housing', 'Child Care & Education', 'Food', 'Transportation', 'Healthcare', 'Miscellaneous', 'Clothing'],
          datasets: [{
            label: 'Expense Percentage',
            data: [29, 16, 18, 15, 9, 7, 6],
            backgroundColor: ['#4CAF50', '#2196F3', '#FFC107', '#FF5722', '#9C27B0', '#607D8B', '#795548']
          }]
        },
        options: {
          plugins: {
            legend: {
              position: 'right'
            }
          }
        }
      });
    </script>
  </div>

  <div class="card">
    <h2 class="text-2xl font-bold mb-2">State Cost Comparison (Top 5 & Bottom 5)</h2>
    <canvas id="stateBarChart" width="400" height="400"></canvas>
    <script>
      const stateCtx = document.getElementById('stateBarChart').getContext('2d');
      const stateBarChart = new Chart(stateCtx, {
        type: 'bar',
        data: {
          labels: ['Massachusetts', 'Hawaii', 'Connecticut', 'Colorado', 'New York', 'Mississippi', 'Arkansas', 'Louisiana', 'Alabama', 'Kentucky'],
          datasets: [{
            label: 'Annual Cost ($)',
            data: [35841, 35049, 32803, 30425, 30247, 16151, 17424, 17918, 18653, 18588],
            backgroundColor: ['#4CAF50', '#2196F3', '#FFC107', '#FF5722', '#9C27B0', '#607D8B', '#795548', '#4CAF50', '#2196F3', '#FFC107']
          }]
        },
        options: {
          indexAxis: 'y',
          plugins: {
            legend: {
              display: false
            }
          }
        }
      });
    </script>
  </div>

  <div class="card">
    <h2 class="text-2xl font-bold mb-2">Key Takeaways</h2>
    <ul>
      <li>Housing is the largest expense (29%).</li>
      <li>Childcare costs vary drastically by state (e.g., Massachusetts ~$21.5k vs. Mississippi ~$4.7k).</li>
      <li>Overall annual average (2023) ~$21.7k, but rising (e.g., 25.3% increase in LendingTree's updated estimate).</li>
    </ul>
  </div>

  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
</body>

</html>

- **Screenshot of render result**:
"""

ANSWER_1 = """
[Model Answer]
{
"is_error": "Yes",
"reason": "Two chart components (Expense Breakdown and State Cost Comparison) did not render correctly, resulting in missing information and unusual white space on the page. This may be because the chart rendering script failed to load or execute properly. The specific reasons are as follows: 1. The Chart.js script file (https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js) is placed in the last <script> tag at the bottom of the HTML document. This may prevent the chart from being correctly referenced and rendered during initialization. 2. The chart initialization code directly calls `document.getElementById('expensePieChart')` and `document.getElementById('stateBarChart')`. However, if the chart elements are not fully loaded before initialization, a `null` error may occur. 3. If network loading issues prevent the Chart.js script file from loading successfully, the chart code will not execute at all."
}
"""

CASE_2 = """
### Example 2:
**Background: A functioning text and chart page**
- **HTML Code: **
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jimmy Johns in the US</title>
    <link href="https://cdn.jsdelivr.net/npm/preline@2.0.3/dist/preline.min.css" rel="stylesheet">
    <link href="https://cdn.staticfile.org/tailwindcss/2.2.19/tailwind.min.css" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
    <style>
        body {
            font-family: 'Tahoma, Arial, Roboto, "Droid Sans", "Helvetica Neue", "Droid Sans Fallback", "Heiti SC", "Hiragino Sans GB", Simsun, sans-self';
            background-color: #f8f9fa;
        }

       .hero {
            background-color: #007bff;
            color: white;
            text-align: center;
            padding: 50px 0;
        }

       .container {
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }

       .card {
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            margin-bottom: 20px;
            padding: 20px;
        }

       .chart-container {
            width: 100%;
            height: 300px;
        }
    </style>
</head>

<body>
    <div class="hero">
        <h1 class="text-4xl font-bold">Jimmy Johns in the US</h1>
        <p class="text-xl mt-3">As of July 16, 2024, there are 2,687 Jimmy Johns stores in the United States.</p>
    </div>

    <div class="container">
        <div class="card">
            <h2 class="text-2xl font-bold mb-3">Top States with Jimmy Johns Stores</h2>
            <canvas id="barChart" class="chart-container"></canvas>
        </div>

        <div class="card">
            <h2 class="text-2xl font-bold mb-3">Key Information</h2>
            <ul class="list-disc pl-5">
                <li class="mb-2">Illinois has the most stores (285), accounting for about 11% of all Jimmy Johns stores in the US.</li>
                <li class="mb-2">Michigan (210 stores, 8%) and Texas (202 stores, 8%) follow.</li>
                <li class="mb-2">There are Jimmy Johns stores in 46 states and territories, with 11 states/territories having no stores.</li>
            </ul>
        </div>
    </div>

    <script>
        // Bar Chart Data
        const ctx = document.getElementById('barChart').getContext('2d');
        const barChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Illinois', 'Michigan', 'Texas', 'Florida', 'Ohio'],
                datasets: [{
                    label: 'Number of Stores',
                    data: [285, 210, 202, 144, 136],
                    backgroundColor: [
                        'rgba(75, 192, 192, 0.2)',
                        'rgba(54, 162, 235, 0.2)',
                        'rgba(255, 206, 86, 0.2)',
                        'rgba(255, 99, 132, 0.2)',
                        'rgba(153, 102, 255, 0.2)'
                    ],
                    borderColor: [
                        'rgba(75, 192, 192, 1)',
                        'rgba(54, 162, 235, 1)',
                        'rgba(255, 206, 86, 1)',
                        'rgba(255, 99, 132, 1)',
                        'rgba(153, 102, 255, 1)'
                    ],
                    borderWidth: 1
                }]
            },
            options: {
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    </script>
</body>

</html>

- **Screenshot of render result**:
"""

ANSWER_2 = """
[Model Answer]
{
"is error": "No",
"reason": ""
}
"""

INPUT_TEMPLATE = """
HTML Code:
{html}

Screenshot of render result:
"""

CASE1_PATH = "data/few_shots/missing/85.png"
CASE2_PATH = "data/few_shots/missing/0.png"

def find_images_for_id(screenshot_dir, index):
    image_path = os.path.join(screenshot_dir, f"{index}.png")
    if os.path.exists(image_path):
        return [image_path]
    return []

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        base64_string = base64.b64encode(image_file.read()).decode('utf-8')
    return base64_string

def process_pair(client, html, image_path, base64_case1, base64_case2, request_model):
    
    base64_image = image_to_base64(image_path)
    prompt = INPUT_TEMPLATE.format(html=html)
    completion = client.chat.completions.create(
        # model parameter is now passed from main through the call chain
        model=request_model,
        # temperature=0,
        # max_completion_tokens=2048,
        max_tokens=4096,
        # reasoning_effort="minimal",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": CASE_1},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_case1}"}},
                    {"type": "text", "text": ANSWER_1},
                    {"type": "text", "text": CASE_2},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_case2}"}},
                    {"type": "text", "text": ANSWER_2},
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                ]
            }
        ]
    )
    return completion.choices[0].message.content

def process_task(client, row, screenshot_dir, base64_case1, base64_case2, request_model, max_retries=3):
   
    index = row['id']
    html = row['html'].replace("```html", "").replace("```", "")
    image_paths = find_images_for_id(screenshot_dir, index)
    
    if not image_paths:
        return {'id': index, 'result': "Screenshot not found."}
    
    image_path = image_paths[0]  
    
    attempt = 1
    current_max = max_retries
    while attempt <= current_max:
        try:
            height_thres = 6000
            with Image.open(image_path) as img:
                width, height = img.size
                if height > height_thres:
                    return {'id': index, 'result': "Image too large."}

            result = process_pair(client, html, image_path, base64_case1, base64_case2, request_model)
            return {'id': index, 'result': result}
        except Exception as e:
            err_text = str(e)
            if 'Error code: 429' in err_text or 'insufficient_quota' in err_text or '429' in err_text:
                if current_max < 20:
                    current_max = 20
                import time
                time.sleep(5)
            else:
                import time
                time.sleep(1)

            if attempt >= current_max:
                return {'id': index, 'result': f"Exception: {e} (retried {max_retries} times)"}
            attempt += 1

def process_task_with_model(client, row, model_name, screenshot_dir, base64_case1, base64_case2, request_model, max_retries=5):
   
    index = row['id']
    html = row['html'].replace("```html", "").replace("```", "")
    image_paths = find_images_for_id(screenshot_dir, index)
    
    if not image_paths:
        return {'model': model_name, 'id': index, 'result': "Screenshot not found."}
    
    image_path = image_paths[0] 
    
    attempt = 1
    current_max = max_retries
    while attempt <= current_max:
        try:
            height_thres = 6000
            with Image.open(image_path) as img:
                width, height = img.size
                if height > height_thres:
                    return {'model': model_name, 'id': index, 'result': "Image too large."}

            result = process_pair(client, html, image_path, base64_case1, base64_case2, request_model)
            return {'model': model_name, 'id': index, 'result': result}
        except Exception as e:
            err_text = str(e)
            if 'Error code: 429' in err_text or 'insufficient_quota' in err_text or '429' in err_text:
                if current_max < 20:
                    current_max = 20
                import time
                time.sleep(5)
            else:
                import time
                time.sleep(1)

            if attempt >= current_max:
                return {'model': model_name, 'id': index, 'result': f"Exception: {e} (retried {max_retries} times)"}
            attempt += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_jsonl', type=str, required=True)
    parser.add_argument('--screenshot_dir', type=str, required=True)
    parser.add_argument('--output_dir', type=str, required=True)
    parser.add_argument('--input_csv', type=str, default=None)
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--num_threads', type=int, default=4)
    parser.add_argument('--skip_path', type=str, default=None)
    parser.add_argument('--human_consistency', action='store_true')
    parser.add_argument('--selected_ids_json', type=str, default=None)
    parser.add_argument('--refix', action='store_true')
    parser.add_argument('--model', type=str, default='', help='Judge VLM')
    
    args = parser.parse_args()

    model = args.model
    assert model in MODEL_CONFIG
    api_key=MODEL_CONFIG[model]['api_key']
    base_url= MODEL_CONFIG[model]['base_url']

    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )

    try:
        df = pd.read_json(args.input_jsonl, lines=True)
        if "id" not in df.columns:
            df['id'] = list(df.index)
    except Exception as e:
        print(f"Error reading JSON input file {args.input_jsonl}: {e}")
        exit(1)

    target_pairs = None
    if args.input_csv:
        try:
            csv_df = pd.read_csv(args.input_csv)
            if 'model' not in csv_df.columns or 'id' not in csv_df.columns:
                print("CSV file must contain 'model' and 'id' columns.")
                exit(1)
            target_pairs = set(zip(csv_df['model'], csv_df['id']))
            print(f"Read {len(target_pairs)} model-id pairs from CSV file.")
        except Exception as e:
            print(f"Error reading CSV file {args.input_csv}: {e}.")
            exit(1)

    if args.human_consistency:
        random_numbers_path = './random_numbers.json'
        try:
            with open(random_numbers_path, 'r', encoding='utf-8') as f:
                random_numbers = json.load(f)
            print(f"Human consistency mode enabled. Read {len(random_numbers)} IDs from {random_numbers_path}.")
            
            df = df[df['id'].isin(random_numbers)].reset_index(drop=True)
            print(f"{len(df)} samples remain for evaluation after filtering.")
            
        except Exception as e:
            print(f"Error reading random_numbers.json: {e}.")
            exit(1)
    else:
        if args.limit is not None:
            df = df.iloc[:args.limit]

    if args.selected_ids_json:
        try:
            with open(args.selected_ids_json, 'r', encoding='utf-8') as f:
                selected_ids = set(json.load(f))
            df = df[df['id'].isin(selected_ids)].reset_index(drop=True)
            print(f"Filtered based on {args.selected_ids_json}, {len(df)} samples remaining")
        except Exception as e:
            print(f"Error reading selected_ids_json file {args.selected_ids_json}: {e}")
            exit(1)

    base64_case1 = image_to_base64(CASE1_PATH)
    base64_case2 = image_to_base64(CASE2_PATH)

    os.makedirs(args.output_dir, exist_ok=True)
    
    if args.input_csv:
        output_file = os.path.join(args.output_dir, f'missing_sampled_csv_{model}.jsonl')
    elif args.human_consistency:
        output_file = os.path.join(args.output_dir, f'missing_{model}_human_consistency.jsonl')
    else:
        output_file = os.path.join(args.output_dir, f'missing_{model}.jsonl')

    existing_results = {}
    ids_to_refix = set()
    if args.refix and os.path.exists(output_file):
        try:
            existing_order = []
            with open(output_file, 'r', encoding='utf-8') as fr:
                for line in fr:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                        key = str(obj.get('id'))
                        existing_order.append(key)
                        existing_results[key] = obj
                        res_text = obj.get('result', '')
                        if isinstance(res_text, (dict, list)):
                            res_text = json.dumps(res_text, ensure_ascii=False)
                        if isinstance(res_text, str) and 'Exception' in res_text:
                            ids_to_refix.add(key)
                    except Exception:
                        continue
            df_ids = set([str(x) for x in df['id'].tolist()])
            missing_in_existing = df_ids - set(existing_results.keys())
            if missing_in_existing:
                ids_to_refix.update(missing_in_existing)
            print(f"Refix mode enabled: loaded {len(existing_results)} existing results; {len(ids_to_refix)} samples need re-evaluation.")
        except Exception as e:
            print(f"Error reading existing output file {output_file}; proceeding with normal processing: {e}.")
            existing_results = {}
            ids_to_refix = set()
            existing_order = []

    lock = threading.Lock() 

    skip_ids = set()
    skip_path = args.skip_path
    if skip_path and os.path.exists(skip_path):
        with open(skip_path, 'r', encoding='utf-8') as f:
            skip_ids = set(json.load(f))

    def should_process_row(row):
        if row['id'] in skip_ids:
            return False
        
        if target_pairs is None:
            return True
        
        image_paths = find_images_for_id(args.screenshot_dir, row['id'])
        if image_paths:
            for path in image_paths:
                path_parts = path.split('/')
                for i, part in enumerate(path_parts):
                    if 'Screenshots' in part and i + 1 < len(path_parts):
                        model_name = path_parts[i + 1]
                        if (model_name, row['id']) in target_pairs:
                            return True
        return False

    def create_task_with_model_info(row):
        image_paths = find_images_for_id(args.screenshot_dir, row['id'])
        model_name = None
        if image_paths:
            for path in image_paths:
                path_parts = path.split('/')
                for i, part in enumerate(path_parts):
                    if 'Screenshots' in part and i + 1 < len(path_parts):
                        model_name = path_parts[i + 1]
                        break
                if model_name:
                    break
        
        # pass the global `model` (from main) as the request_model so the actual API call
        # uses the same model string defined in main. model_name is preserved as metadata.
        return executor.submit(
            process_task_with_model,
            client,
            row,
            model_name,
            args.screenshot_dir,
            base64_case1,
            base64_case2,
            model
        )

    collected_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.num_threads) as executor:
        if args.refix and ids_to_refix:
            rows_to_process = []
            for _, row in df.iterrows():
                key = str(row['id'])
                if key not in ids_to_refix:
                    continue
                if row['id'] in skip_ids:
                    continue
                if args.input_csv and not should_process_row(row):
                    continue
                rows_to_process.append(row)

            if args.input_csv:
                tasks = [create_task_with_model_info(row) for row in rows_to_process]
            else:
                tasks = [executor.submit(process_task, client, row, args.screenshot_dir, base64_case1, base64_case2, model) for row in rows_to_process]
        else:
            if args.input_csv:
                tasks = [create_task_with_model_info(row) for _, row in df.iterrows() if should_process_row(row)]
            else:
                tasks = [executor.submit(process_task, client, row, args.screenshot_dir, base64_case1, base64_case2, model) for _, row in df.iterrows() if row['id'] not in skip_ids]

        if args.input_csv:
            progress_desc = "CSV-based evaluation filtering."
        elif args.human_consistency:
            progress_desc = "Human consistency evaluation."
        else:
            progress_desc = "Processing progress."

        for future in tqdm(concurrent.futures.as_completed(tasks), total=len(tasks), desc=progress_desc):
            try:
                result = future.result()
                collected_results.append(result)
            except Exception as e:
                print(f"Exception occurred while processing task: {e}")

    if args.refix and existing_results:
        final_results = dict(existing_results)
        for r in collected_results:
            key = str(r.get('id'))
            if key in final_results:
                final_results[key]['result'] = r.get('result')
            else:
                final_results[key] = r

        ordered_keys = []
        if 'existing_order' in locals():
            ordered_keys.extend(existing_order)
        for _id in df['id'].tolist():
            k = str(_id)
            if k not in ordered_keys:
                ordered_keys.append(k)

        with open(output_file, 'w', encoding='utf-8') as fout:
            for key in ordered_keys:
                if key in final_results:
                    fout.write(json.dumps(final_results[key], ensure_ascii=False) + '\n')
    else:
        with open(output_file, 'w', encoding='utf-8') as fout:
            for r in collected_results:
                fout.write(json.dumps(r, ensure_ascii=False) + '\n')

    if args.input_csv:
        print(f"CSV-based evaluation filtering completed. Results saved to: {output_file}")
    elif args.human_consistency:
        print(f"Human consistency evaluation completed. Processed {len(df)} samples. Results saved to: {output_file}")
    else:
        print(f"All tasks completed. [Information Missing] detection results saved to: {output_file}")


if __name__ == '__main__':
    main()
