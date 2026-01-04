#!/usr/bin/env python3

import os
import json
import argparse
from pathlib import Path
from PIL import Image
import concurrent.futures
import threading
from tqdm import tqdm

def check_image_size(image_path, height_threshold=6000):
    
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            if height > height_threshold:
                return True  
        return False 
    except Image.DecompressionBombError:
        print(f"Image {image_path} is too large.")
        return True
    except Exception as e:
        print(f"Error processing image {image_path}: {e}")
        return True

def check_web_folder_images(base_path="/Users/huqirui/visual_rich_bench/design_res_0829", 
                           height_threshold=6000, num_threads=4):
   
    results_dict = {}
    base_path = Path(base_path)
    
    all_tasks = []
    
    for model_folder in base_path.iterdir():
        if model_folder.is_dir():
            model_name = model_folder.name
            web_folder = model_folder / "web"
            
            if not web_folder.exists() or not web_folder.is_dir():
                print(f"No web folder found for model: {model_name}")
                continue
                
            print(f"Processing web folder for model: {model_name}")
            results_dict[model_name] = {}
            
            png_files = list(web_folder.glob("*.png"))
            
            for png_file in png_files:
                file_id = png_file.stem
                all_tasks.append((model_name, file_id, str(png_file), height_threshold))
    
    lock = threading.Lock()
    
    def process_image_task(task):
        model_name, file_id, image_path, threshold = task
        has_issue = check_image_size(image_path, threshold)
        status = 0 if has_issue else 1 
        with lock:
            if model_name not in results_dict:
                results_dict[model_name] = {}
            results_dict[model_name][file_id] = status
            
        if has_issue:
            print(f"  Issue found in {model_name}/{file_id}: image too large/tall")
        
        return model_name, file_id, status
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        tasks = [executor.submit(process_image_task, task) for task in all_tasks]
        
        for future in tqdm(concurrent.futures.as_completed(tasks), 
                          total=len(tasks)):
            try:
                future.result()
            except Exception as e:
                print(f"Error: {e}")
    
    return results_dict

def save_results_by_model(results_dict, output_base_path, filename="big_charts_results.json"):
    output_base_path = Path(output_base_path)
    
    for model_name, model_results in results_dict.items():

        model_output_dir = output_base_path / model_name
        model_output_dir.mkdir(parents=True, exist_ok=True)
        
        status_results = {}
        no_issue_count = 0
        issue_count = 0
        
        for file_id, status in model_results.items():
            status_results[file_id] = status
            
            if status == 1:
                no_issue_count += 1
            else:
                issue_count += 1
        
        sorted_results = dict(sorted(status_results.items(), 
                                   key=lambda x: int(x[0]) if x[0].isdigit() else x[0]))
        
        complete_results = {
            "total_right": no_issue_count,
            "total_wrong": issue_count,
            "results": sorted_results
        }
        
        output_file = model_output_dir / filename
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(complete_results, f, ensure_ascii=False, indent=2)
        
        print(f"Results for {model_name} saved to {output_file}")
        print(f"  Total items: {len(model_results)}")
        print(f"  No issue (1): {no_issue_count}, Issue (0): {issue_count}")

def save_detailed_results(results_dict, output_base_path, filename="big_charts_detailed.json"):
    output_base_path = Path(output_base_path)
    output_base_path.mkdir(parents=True, exist_ok=True)
    
    output_file = output_base_path / filename
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results_dict, f, ensure_ascii=False, indent=2)
    
    print(f"Detailed results saved to {output_file}")

def main():
    parser = argparse.ArgumentParser(description="Big Charts")
    parser.add_argument('--base-path', type=str, default="")
    parser.add_argument('--output-path', type=str, default="")
    parser.add_argument('--height-threshold', type=int, default=5000)
    parser.add_argument('--num-threads', type=int, default=4)
    parser.add_argument('--save-detailed', action='store_true')
    
    args = parser.parse_args()
    
    image_results = check_web_folder_images(
        base_path=args.base_path,
        height_threshold=args.height_threshold,
        num_threads=args.num_threads
    )
    
    print(f"\n=== Done! ===")
    
    total_files = 0
    total_issues = 0
    
    for model, results in image_results.items():
        no_issue = sum(1 for status in results.values() if status == 1)
        issue = sum(1 for status in results.values() if status == 0)
        total_files += len(results)
        total_issues += issue
    
    save_results_by_model(image_results, args.output_path, "big_charts_results.json")
    
    if args.save_detailed:
        save_detailed_results(image_results, args.output_path, "big_charts_detailed.json")
    
    print(f"\nAll results have been saved to {args.output_path}")

if __name__ == "__main__":
    main()