import json
import argparse
import pandas as pd
from pathlib import Path

def process_fsr_results(model_folder_path):
    """
    """
    model_path = Path(model_folder_path)    
    result_files = [f for f in model_path.glob("*_results.json")]
    if not result_files:
        print(f"No result files found in {model_folder_path}")
        return {}
    
    all_dimensions = {}
    
    for result_file in result_files:
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                dimension_name = result_file.stem.replace('_results', '')
                dimension_results = data.get('results', {})
    
                # 如果使用筛选，只保留valid_ids中的项目
                all_dimensions[dimension_name] = dimension_results
                print(f"Loaded {dimension_name} with {len(dimension_results)} items")
                    
        except Exception as e:
            print(f"Error reading {result_file}: {e}")
            continue
    
    if not all_dimensions:
        return {}
    
    all_ids = set()
    for dimension_results in all_dimensions.values():
        all_ids.update(dimension_results.keys())
    
    integrated_results = {}
    total_right = 0
    total_wrong = 0
    
    for item_id in all_ids:
        all_passed = True
        missing_dimensions = []
        
        for dimension_name, dimension_results in all_dimensions.items():
            if item_id not in dimension_results or dimension_results[item_id] != 1:
                all_passed = False
                if item_id not in dimension_results:
                    missing_dimensions.append(dimension_name)
                break
        
        integrated_results[item_id] = 1 if all_passed else 0
        if all_passed:
            total_right += 1
        else:
            total_wrong += 1
            if missing_dimensions:
                print(f"ID {item_id} missing in dimensions: {missing_dimensions}")
    
    total_items = total_right + total_wrong
    score = (total_right / total_items * 100) if total_items > 0 else 0
    
    result_dict = {
        "score": round(score, 2),
        "total_right": total_right,
        "total_wrong": total_wrong,
        "total_items": total_items,
        "results": integrated_results
    }
    
    return result_dict

def process_dsr_results(model_folder_path, fsr_result=None):
    """
    """
    model_path = Path(model_folder_path)
    
    result_files = [f for f in model_path.glob("*_results.json")]
    
    if not result_files:
        print(f"No result files found in {model_folder_path}")
        return {}
    
    all_dimensions = {}
    
    for result_file in result_files:
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                dimension_name = result_file.stem.replace('_results', '')
                dimension_results = data.get('results', {})
                
                all_dimensions[dimension_name] = dimension_results
                print(f"Loaded {dimension_name} with {len(dimension_results)} items")
                    
        except Exception as e:
            print(f"Error reading {result_file}: {e}")
            continue
    
    if fsr_result:
        all_dimensions['FSR'] = fsr_result

    if not all_dimensions:
        return {}
    
    all_ids = set()
    for dimension_results in all_dimensions.values():
        all_ids.update(dimension_results.keys())
    
    integrated_results = {}
    total_right = 0
    total_wrong = 0
    
    for item_id in all_ids:
        all_passed = True
        missing_dimensions = []
        
        for dimension_name, dimension_results in all_dimensions.items():
            if item_id not in dimension_results or dimension_results[item_id] != 1:
                all_passed = False
                if item_id not in dimension_results:
                    missing_dimensions.append(dimension_name)
                break
        
        integrated_results[item_id] = 1 if all_passed else 0
        if all_passed:
            total_right += 1
        else:
            total_wrong += 1
            if missing_dimensions:
                print(f"ID {item_id} missing in dimensions: {missing_dimensions}")
    
    total_items = total_right + total_wrong
    score = (total_right / total_items * 100) if total_items > 0 else 0
    
    result_dict = {
        "score": round(score, 2),
        "total_right": total_right,
        "total_wrong": total_wrong,
        "total_items": total_items,
        "results": integrated_results
    }
    
    print(f"DSR: ", round(score, 2))
    return result_dict

def calculate_dimension_score(total_pass_rate_data, dimension_data):
    if dimension_data is None:
        return {
            'score': 0.0,
            'total_count': 0,
            'passed_count': 0,
            'failed_count': 0,
            'valid_score_count': 0,
            'individual_scores': []
        }
    
    if 'results' in dimension_data:
        dimension_results = dimension_data['results']
    else:
        dimension_results = dimension_data
    
    scores = []
    passed_count = 0
    failed_count = 0
    valid_score_count = 0
    
    for id_str, pass_value in total_pass_rate_data.items():
        if pass_value == 0:
            scores.append(0.0)
            failed_count += 1
        elif pass_value == 1:
            passed_count += 1
            if id_str in dimension_results:
                score = dimension_results[id_str]
                if isinstance(score, (int, float)) and score >= 0:
                    scores.append(score)
                    valid_score_count += 1
                else:
                    scores.append(0.0)
            else:
                scores.append(0.0)
    
    if scores:
        avg_score = sum(scores) / len(scores)
    else:
        avg_score = 0.0
    
    return {
        'score': avg_score,
        'total_count': len(scores),
        'passed_count': passed_count,
        'failed_count': failed_count,
        'valid_score_count': valid_score_count,
        'individual_scores': scores
    }
    
def process_ecq_results(model_folder_path, total_pass_rate_data=None, eval_dimensions = ['sense_eval', 'comprehensiveness_eval', 'faith_eval']):
    """
    """

    model_path = Path(model_folder_path)
    
    dimension_files = [f for f in model_path.glob("*.jsonl")]
    
    if not dimension_files:
        print(f"No result files found in {model_folder_path}")
        return {}
    
    model_scores = {}
    
    for filename in dimension_files:
        dimension = None
        for dim in eval_dimensions:
            if dim in str(filename):
                dimension = dim
                break
        if not dimension:
            continue
        
        dimension_path = model_path / filename
        
        if dimension_path.exists():
            df = pd.read_json(dimension_path, lines=True)
            df['id'] = df['id'].apply(str)
            if 'faith_eval' == dimension and 'score' not in df.columns:
                df['score'] = df['eval_result'].apply(lambda eval_result: sum([x['score'] for x in eval_result.values()]) / len(eval_result.values()) * 100 if isinstance(eval_result, dict) and len(eval_result.values()) > 0 else -1)
            dimension_data = df.set_index('id')['score'].to_dict()
            dimension_score = calculate_dimension_score(total_pass_rate_data, dimension_data)
            model_scores[dimension] = dimension_score
        else:
            print(f"Warning: {dimension_path} not found!")
            model_scores[dimension] = {
                'score': 0.0,
                'total_count': 0,
                'passed_count': 0,
                'failed_count': 0,
                'valid_score_count': 0,
                'individual_scores': []
            }
        
    for dimension, score_info in model_scores.items():
        print(f"  {dimension}: {score_info['score']:.3f} "
                f"(passed: {score_info['passed_count']}, "
                f"failed: {score_info['failed_count']}, "
                f"valid_scores: {score_info['valid_score_count']})")
    
    return model_scores

if __name__ == '__main__':
    # FSR
    parser = argparse.ArgumentParser()
    parser.add_argument('--fsr_dir', type=str, required=True)
    parser.add_argument('--dsr_dir', type=str, required=True)
    parser.add_argument('--info_dir', type=str, required=True)
    args = parser.parse_args()

    fsr_result_dict = process_fsr_results(args.fsr_dir)
    print(fsr_result_dict['results'])
    fsr_score = fsr_result_dict['score']

    # DSR
    dsr_result_dict = process_dsr_results(args.dsr_dir, fsr_result_dict['results'])
    dsr_score = dsr_result_dict['score']

    # ECQ
    content_socres = process_ecq_results(args.info_dir, dsr_result_dict['results'])

    ecq_score = sum([k['score'] for k in content_socres.values()]) / len(content_socres.values())
    hps_score = dsr_score * ecq_score
    print("FSR: ", fsr_score)
    print("DSR: ", dsr_score)
    print("ECQ: ", ecq_score)
    print("HPS: ", hps_score)