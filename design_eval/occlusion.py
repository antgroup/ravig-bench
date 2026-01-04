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
You are a senior front-end UI design diagnostic expert. You need to inspect various charts and text content in a complex layout for any occlusion phenomena.

The user will provide the following input:
-   **Several screenshots of the rendered page**: These show the actual appearance of the page as rendered in a browser or application.
-   The input data format is as follows:
    {
        "id_1": "Rendered page screenshot",
        "id_2": "Rendered page screenshot",
        ...
    }

Your task is to:
1.  Analyze the input page screenshots, accurately identify each element, its position, and its layer relationship. Based on the definition of **"occlusion"**, carefully inspect and determine if any occlusion issues exist.
2.  If occlusion issues are found:
    -   Clearly identify the specific content or element being occluded (e.g., chart, text, button, image).
    -   Explain the specific cause of the occlusion (e.g., element overlap, layout issues).
    -   Describe its impact on readability or interactive functionality.
3.  If no occlusion issues are found, state clearly that the page rendering is normal and there is no occlusion.

## Core Judgment Principles
1.  **Core Judgment Standard**: Occlusion refers to a foreground element physically covering another foreground or background element in the visual hierarchy, causing the latter's pixels to be partially or completely obscured, thereby compromising information integrity.

## Typical Errors that MUST be Reported:
1.  **Chart Overflow Occlusion**: A chart (e.g., pie chart, bar chart) exceeds the boundaries of its container and covers the text or content of other modules on the page. This is the most typical occlusion error and must be identified.
2.  **Element Overlap**: Any interactive or readable element (text, button, input field, legend) is partially or completely covered by other foreground elements.

## Non-Occlusion Cases to be Exempted:
1.  **Contrast Issues**: An element's outline is complete, but it is difficult to discern solely because its color is similar to the background. **This is not occlusion**.
2.  **Text Rotation or Skewing Issues**: Labels on chart axes (especially the X-axis) are intentionally rotated or skewed to fit into a limited space. As long as these skewed labels do not overlap with each other and are not covered by other foreground elements (such as bars, axis lines, etc.), **this is a common and effective design practice, not occlusion**.
    -   Specific case: To prevent long X-axis labels from overlapping, all labels are uniformly tilted at a 45-degree angle. This is correct design, not an error.
3.  **Other Readability/Layout Issues**: Problems such as text being too small, insufficient white space, or improper alignment are not considered occlusion.

## Definition of Occlusion
1.  **Occlusion between Modules or Components**:
    -   Different modules or components on the page (e.g., charts, text, buttons, images) overlap, preventing the content of some components from being fully displayed.
    -   Occlusion can undermine the page's functionality or aesthetics.

2.  **Occlusion of Text or Content**:
    -   **Pay special attention to the occlusion of chart axes, tick marks, legends, etc.**:
        -   Data lines, bars, legends, etc., within a chart occlude the axis labels, tick marks, etc.
        -   Chart axes, tick marks, legends, etc., overlap with surrounding components or text.
    -   Text or content is partially or completely obscured by other page elements (such as images, charts, overlapping color blocks), making it difficult to read or recognize.
    -   Elements at different layers in the layout overlap, preventing users from clearly distinguishing or recognizing the content.
    -   The following are potential screening directions; you need to check for, but are not limited to, these error types:
        | Occlusion Type                | Error Description                                                                                                   |
        | ----------------------------- | ------------------------------------------------------------------------------------------------------------------- |
        | Text-on-Text Occlusion        | Some text is occluded by other text, making it difficult to read.                                                   |
        | Text-Chart Occlusion          | Some text is occluded by a chart (e.g., bar chart, pie chart), typically at the bottom or top edge of the chart.      |
        | Text-Icon Occlusion           | Some text is occluded by an icon element, making it difficult to read.                                              |

## Output Requirements:
Please return the analysis result in a structured JSON format, including the following fields:
1.  **is_error**: Answer "Yes" or "No". If any of the input images contain occlusion, answer "Yes"; otherwise, "No".
2.  **occluded_image_ids**: Provide the IDs of the images that have occlusion. If none, this should be empty.
3.  **reason_description** (if the answer is "Yes"): Clearly describe the occluded element, the cause of the problem, and its impact on page readability or functionality. If no occlusion exists, this should be empty.

**Output Template**:
{
    "is_error": "Yes/No",
    "occluded_image_ids": "[id]" (IDs of the images with occlusion),
    "reason": "Specifically describe the occluded element, the cause of the problem, and its impact on the user experience. If the answer is 'No', this field should be empty."
}
"""

CASE_1 = """
Here are some real-world examples using this prompt for reference:

### Example 1: Occlusion Issue
**Input Screenshot**:
"""
ANSWER_1 = """
[Model Answer]
{
    "is_error": "Yes",
    "occluded_image_ids": ["542_4, 397_5"],
    "reason": "In screenshot 542_4, the lower half of the large donut chart severely obscures the text and content at the bottom, making it difficult for users to read the covered text. In screenshot 397_5, part of the donut chart obscures the text, making it difficult to read."
}
"""

CASE_2 = """
### Example 3: No occlusion issues
**Input screenshot**:
"""
ANSWER_2 = """
[Model Answer]
{
    "is_error": "No",
    "occluded_image_ids": [],
    "reason": ""
}
"""

CASE_3 = """
### Example 2: The chart and its axes/scales/legend obscure nearby content
**Input screenshot**:
"""
ANSWER_3 = """
[Model Answer]
{
    "is_error": "Yes",
    "occluded_image_ids": ["90_4", "97_4"],
    "reason": "In image '90_4', the source information at the bottom of the chart (Source: World's Top Exports, International Trade Centre (2023 data)) is partially obscured by the color and border of the bar chart, making the text incomplete and difficult to read. This obstruction affects the user's ability to clearly understand the data source. In screenshot 97_4, the category labels at the bottom of the chart (such as 'Iraq War (2003-2011)') are partially obscured by the text below, making them difficult to fully read. This problem occurs because the spacing between the chart and the text below is too small, resulting in overlapping elements. This obstruction affects the readability of the chart information, and users may not be able to clearly understand the category labels corresponding to each bar chart."
}
"""

def find_images_for_id(screenshot_dir, index):
    pattern = os.path.join(screenshot_dir, f"{index}_*.png")
    return sorted(glob.glob(pattern))

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        base64_string = base64.b64encode(image_file.read()).decode('utf-8')
    return base64_string

def process_pair(client, model, image_paths, case1_list, case2_list, case3_list):
    
    input_list = [{"type": "text", "text": "Input page render screenshot:"}]
    for image_path in image_paths:
        image_name = os.path.basename(image_path[:-4])
        base64_image = image_to_base64(image_path)
        input_list.append({"type": "text", "text": image_name + ":"})
        input_list.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}})
    
    user_prompt = case1_list + case3_list + case2_list + input_list
    
    completion = client.chat.completions.create(
        # model='gemini-2.5-pro',
        model=model,
        # temperature=0,
        # max_completion_tokens=2048,
        max_tokens=2048,
        # reasoning_effort="minimal",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": user_prompt
            }
        ]
    )
    return completion.choices[0].message.content

def process_task(client, row, screenshot_dir, case1_list, case2_list, case3_list, model, max_retries=5):
    
    index = row['id']
    image_paths = find_images_for_id(screenshot_dir, index)
    if not image_paths:
        return {'id': index, 'result': "Screenshot not found."}
    
    height_thres = 6000
    for image_path in image_paths:
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                if height > height_thres:
                    return {'id': index, 'result': f"Image too large: {os.path.basename(image_path)}"}
        except Exception as e:
            return {'id': index, 'result': f"Failed to open image:{e}"}

    attempt = 1
    current_max = max_retries
    while attempt <= current_max:
        try:
            result = process_pair(client, model, image_paths, case1_list, case2_list, case3_list)
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
                return {'id': index, 'result': f"Exception: {e} (retried {max_retries} times)."}
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
    parser.add_argument('--selected_ids_json', type=str, default=None)
    parser.add_argument('--refix', action='store_true')
    parser.add_argument('--model', type=str, required=True, help='Judge VLM')
    args = parser.parse_args()

    model = args.model
    assert model in MODEL_CONFIG
    api_key=MODEL_CONFIG[model]['api_key']
    base_url=MODEL_CONFIG[model]['base_url']

    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )

    try:
        df = pd.read_json(args.input_jsonl, lines=True)
        if "id" not in df.columns:
            df['id'] = list(df.index)
        if args.limit is not None:
            df = df.iloc[:args.limit]
    except Exception as e:
        print(f"Error reading JSON input file {args.input_jsonl}: {e}")
        exit(1)

    if args.selected_ids_json:
        try:
            with open(args.selected_ids_json, 'r', encoding='utf-8') as f:
                selected_ids = set(json.load(f))
            df = df[df['id'].isin(selected_ids)].reset_index(drop=True)
            print(f"Filtered based on {args.selected_ids_json}, {len(df)} samples remaining")
        except Exception as e:
            print(f"Error reading selected_ids_json file {args.selected_ids_json}: {e}")
            exit(1)

    target_pairs = None
    if args.input_csv:
        try:
            csv_df = pd.read_csv(args.input_csv)
            if 'model' not in csv_df.columns or 'id' not in csv_df.columns:
                print("SV file must contain 'model' and 'id' columns.")
                exit(1)
            target_pairs = set(zip(csv_df['model'], csv_df['id']))
            print(f"Read {len(target_pairs)} model-id pairs from CSV file.")
        except Exception as e:
            print(f"Error reading CSV file {args.input_csv}: {e}")
            exit(1)

    case1_paths = [
        "data/few_shots/occlusion/542_4.png",
        "data/few_shots/occlusion/397_5.png"
    ]
    case1_list = [{"type": "text", "text": CASE_1}]
    for image_path in case1_paths:
        image_name = os.path.basename(image_path[:-4])
        base64_image = image_to_base64(image_path)
        case1_list.append({"type": "text", "text": image_name + ":"})
        case1_list.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}})
    case1_list.append({"type": "text", "text": ANSWER_1})
    
    case2_paths = [
        "data/few_shots/occlusion/4_1.png",
        "data/few_shots/occlusion/4_2.png"
    ]
    case2_list = [{"type": "text", "text": CASE_2}]
    for image_path in case2_paths:
        image_name = os.path.basename(image_path[:-4])
        base64_image = image_to_base64(image_path)
        case2_list.append({"type": "text", "text": image_name + ":"})
        case2_list.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}})
    case2_list.append({"type": "text", "text": ANSWER_2})
    
    case3_paths = [
        "data/few_shots/occlusion/90_4.png",
        "data/few_shots/occlusion/90_6.png",
        "data/few_shots/occlusion/97_4.png"
    ]
    case3_list = [{"type": "text", "text": CASE_3}]
    for image_path in case3_paths:
        image_name = os.path.basename(image_path[:-4])
        base64_image = image_to_base64(image_path)
        case3_list.append({"type": "text", "text": image_name + ":"})
        case3_list.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}})
    case3_list.append({"type": "text", "text": ANSWER_3})

    os.makedirs(args.output_dir, exist_ok=True)
    if args.input_csv:
        output_file = os.path.join(args.output_dir, f'occlusion_sampled_csv_{model}_largefig.jsonl')
    else:
        output_file = os.path.join(args.output_dir, f'occlusion_{model}.jsonl')

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
        
        screenshot_paths = find_images_for_id(args.screenshot_dir, row['id'])
        if screenshot_paths:
            for path in screenshot_paths:
                path_parts = path.split('/')
                for i, part in enumerate(path_parts):
                    if 'Screenshots' in part and i + 1 < len(path_parts):
                        model_name = path_parts[i + 1]
                        if (model_name, row['id']) in target_pairs:
                            return True
        return False

    def create_task_with_model_info(row):
        screenshot_paths = find_images_for_id(args.screenshot_dir, row['id'])
        model_name = None
        if screenshot_paths:
            for path in screenshot_paths:
                path_parts = path.split('/')
                for i, part in enumerate(path_parts):
                    if 'Screenshots' in part and i + 1 < len(path_parts):
                        model_name = path_parts[i + 1]
                        break
                if model_name:
                    break
        
        return executor.submit(
            process_task_with_model,
            client,
            row,
            model_name,
            args.screenshot_dir,
            case1_list,
            case2_list,
            case3_list,
            model
        )

    def process_task_with_model(client, row, model_name, screenshot_dir, case1_list, case2_list, case3_list, model, max_retries=3):
    
        index = row['id']
        image_paths = find_images_for_id(screenshot_dir, index)
        if not image_paths:
            result = {'model': model_name, 'id': index, 'result': "Screenshot not found."}
            return result
        
        height_thres = 6000
        for image_path in image_paths:
            try:
                with Image.open(image_path) as img:
                    width, height = img.size
                    if height > height_thres:
                        result = {'model': model_name, 'id': index, 'result': f"Image too large: {os.path.basename(image_path)}"}
                        return result
            except Exception as e:
                result = {'model': model_name, 'id': index, 'result': f"Failed to open image:{e}"}
                return result

        attempt = 1
        current_max = max_retries
        while attempt <= current_max:
            try:
                evaluation_result = process_pair(client, model, image_paths, case1_list, case2_list, case3_list)
                result = {'model': model_name, 'id': index, 'result': evaluation_result}
                return result
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
                    result = {'model': model_name, 'id': index, 'result': f"Exception: {e} (retried {max_retries} times)."}
                    return result
                attempt += 1

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
                tasks = [executor.submit(process_task, client, row, args.screenshot_dir, case1_list, case2_list, case3_list, model) for row in rows_to_process]
        else:
            if args.input_csv:
                tasks = [create_task_with_model_info(row) for _, row in df.iterrows() if should_process_row(row)]
            else:
                tasks = [executor.submit(process_task, client, row, args.screenshot_dir, case1_list, case2_list, case3_list, model) for _, row in df.iterrows() if row['id'] not in skip_ids]

        for future in tqdm(concurrent.futures.as_completed(tasks), total=len(tasks)):
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

    print("All tasks completed. [Occlusion] detection results saved to", output_file)


if __name__ == '__main__':
    main()
