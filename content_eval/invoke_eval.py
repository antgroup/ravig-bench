import os
import sys
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(parent_dir)

import re
import copy
import json
import time
import asyncio
import json_repair
import argparse
import pandas as pd
from tqdm import tqdm
from typing import List, Union
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from functions.call_openai_api import call_openai_stream
from functions.common import (
    compute_metrics as compute_metrics_sklearn, 
    extract_chart_code,
    parse_html_body
)
from create_payloads import process_payloads_for_comprehensiveness_eval, process_payloads_for_reasonableness_eval, process_payloads_for_claim_extraction, process_payloads_for_faith_eval

class Extractor:
    """Regular expression extractor for model output content"""
    @staticmethod
    def extract_json_from_markdown(text):
        pattern = r'```json\\n(.*?)\\n```'
        match = re.search(pattern, text, re.DOTALL)
        
        if match:
            return match.group(1)
        else:
            return None

class DatasetLoader:
    """Utility class for loading datasets"""
    @staticmethod
    def load(path):
        if path.endswith(".jsonl"):
            with open(path, "r", encoding="utf-8") as f:
                return [json.loads(line) for line in f]
        elif path.endswith(".json"):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            raise ValueError("Invalid file format: only .jsonl or .json formats are supported")


class ScoreCalculator:
    """Utility class for compute score"""
    PATTERNS = {
        "checklist_score": r'"label"\s*:\s*"?([01])"?(?!\d)',
        "comprehensiveness_eval": r'"score":\s*"([^"]+)"',
    }
    
    @classmethod
    def compute(cls, all_results: List[str], eval_task) -> Union[float, str]:
        """Calculate score from evaluation results.
        
        Args:
            all_results: List of evaluation result strings            
        Returns:
            Calculated score or "failed" if calculation failed
        """
        if not all_results or any(result is None for result in all_results):
            return "failed"
        
        if True:
            try:
                pattern = r'"score"\s*:\s*(?:"([^"]+)"|(\d+\.?\d*))'
                score_weight = 10
                
                scores = []
                for result in all_results:
                    match = re.search(pattern, result)
                    score = match.group(1) or match.group(2)
                    if match:
                        scores.append(int(score))
                
                if not scores:
                    return "failed"
                    
                return sum(scores) / len(scores) * score_weight
            except Exception as e:
                print(f"Failed to compute score: {e}, raw_result: {all_results}")
                return "failed"        

class MetricsEvaluator:
    """Utility class for compute metrics"""
    @staticmethod
    def compute_metrics(args):
        results_path = args.output_path
        eval_task = args.eval_task

        if eval_task in ['comprehensiveness_eval', 'reasonableness_eval']:
            results = DatasetLoader.load(results_path)
            success_scores = [line['score'] for line in results if 'score' in line and line['score'] != "failed"]
            total_count = len(results)
            success_count = len(success_scores)
            success_rate = round(success_count / total_count * 100, 2) if total_count > 0 else -1
            avg_score = round(sum(success_scores) / success_count, 2) if success_count > 0 else -1

            print(f"Total data volume: {total_count}")
            print(f"Number of valid samples: {success_count}")
            print(f"Percentage of valid samples: {success_rate}%")
            print(f"Average score: {avg_score}")
        
            return {
                "total_count": total_count,
                "success_count": success_count,
                "success_rate": success_rate,
                "score": avg_score
            }
        
        if eval_task == "trigger_rate_eval":
            df_res = pd.DataFrame(DatasetLoader.load(results_path))
            trigger_rate_stats = {}

            table_rate = round(sum(df_res['eval_result'].apply(lambda x: x['has_table']).to_list()) / df_res.shape[0] * 100, 2)
            chart_rate = round(sum(df_res['eval_result'].apply(lambda x: x['has_chart']).to_list()) / df_res.shape[0] * 100, 2)
            print(f"Table_Trigger_Rate: {table_rate}%")
            print(f"Chart_Trigger_Rate: {chart_rate}%")

            trigger_rate_stats["Table_Trigger_Rate"] = table_rate
            trigger_rate_stats["Chart_Trigger_Rate"] = chart_rate
            return trigger_rate_stats

        if eval_task in ["faith_eval"]:
            results = DatasetLoader.load(results_path)
            claim_count = 0
            case_count = 0
            claim_level_score_lst, case_level_score_lst = [], []

            for line in results:
                if 'eval_result' in line and len(line['eval_result']) > 0:
                    claim_score_lst = [x['score'] for x in line['eval_result'].values()]
                    claim_level_score = sum(claim_score_lst) / len(claim_score_lst)
                    case_level_score = min(claim_score_lst)
                    claim_level_score_lst.append(claim_level_score)
                    case_level_score_lst.append(case_level_score)

                    case_count += 1
                    claim_count += len(line['eval_result'])
            
            claim_avg_count = round(claim_count / case_count, 2) if case_count > 0 else -1
            claim_level_score = round(sum(claim_level_score_lst) / case_count * 100, 2) if case_count > 0 else -1
            case_level_score = round(sum(case_level_score_lst) / case_count * 100, 2) if case_count > 0 else -1
            print(f"Number of valid evaluation samples: {case_count}")
            print(f"Average number of claims per case: {claim_avg_count}")
            print(f"Claim-level average score: {claim_level_score}")
            print(f"Case-level average score: {case_level_score}")

            return {
                "success_count": case_count,
                "faith_claim_avg_count": claim_avg_count,
                "faith_claim_level_score": claim_level_score,
                "faith_case_level_score": case_level_score,
            }

    @staticmethod
    def compute_accuracy(golden_label_lst, predict_label_lst):
        return compute_metrics_sklearn(golden_label_lst, predict_label_lst)


class DataValidator:
    """Utility class for validating data comprehensiveness"""
    @staticmethod
    def data_validate(path):
        dataset = DatasetLoader.load(path)
        for data in dataset:
            query = data.get("query", "")
            checklist = data.get("checklist", "")
            reference = data.get("reference", "")
            html = data.get("html", "")

            if not query:
                raise ValueError(f"[query error] Invalid data exists: {data}")
            if not reference:
                raise ValueError(f"[reference error] Invalid data exists: {data}")
            if not html:
                raise ValueError(f"[html error] Invalid data exists: {data}")

            if isinstance(checklist, str):
                try:
                    json.loads(checklist)
                except json.JSONDecodeError:
                    raise ValueError(f"[checklist error] Invalid data exists: {data}")
            elif not isinstance(checklist, list):
                raise ValueError(f"[checklist error] Invalid data exists: {data}")
            elif not checklist:
                raise ValueError(f"[checklist error] Invalid data exists: {data}")

        return True

class Evaluator:
    """Main Evaluator Class"""
    def __init__(self, args):
        self.args = args
        self.model_name = args.model_name
        self.max_workers = args.max_workers
        self.eval_task = args.eval_task

    def call_client(self, payload, max_retries=3):
        for attempt in range(1, max_retries + 1):
            try:
                resp = call_openai_stream(payload['prompt'], self.model_name, max_tokens=payload.get('max_output_length', 8192), temperature=payload.get('temperature', 0))
                if resp and resp != "falied":
                    return resp
            except Exception as e:
                error_msg = f"API ERROR (payload: {payload}, attempt: {attempt}): {e}"
                print(error_msg)
                if attempt == max_retries:
                    return "failed"
                continue
            return "failed"

    def comprehensiveness_evaluation(self, data):
        
        data['response'] = parse_html_body(data['html'])

        payload = process_payloads_for_comprehensiveness_eval(data)
        data['eval_result'] = {}

        llm_result = self.call_client(payload)
        data['eval_result'] = [llm_result]
        data['score'] = ScoreCalculator.compute(data['eval_result'], eval_task='comprehensiveness_evaluation')

        return data

    def reasonableness_evaluation(self, data):
        data['eval_result'] = {}
        data['response'] = parse_html_body(data['html'])
        reasonableness_payload = process_payloads_for_reasonableness_eval(data)
        try:
            llm_result = self.call_client(reasonableness_payload).strip("```json").strip("```")
            data['eval_result']['llm_output'] = llm_result

            pattern = r'"label":\s*"([^"]+)"'
            match = re.search(pattern, llm_result)
            if match:
                label = match.group(1).lower()
                data['eval_result']['label'] = label

                if label.lower() == "unreasonable":
                    data['score'] = 0
                else:
                    data['score'] = 100
            else:
                if "unreasonable" in llm_result.lower():
                    data['score'] = 0
                else:
                    data['score'] = 100
        except Exception as e:
            print(f"reasonableness_eval error: {e}")
            data['score'] = 'failed'

        return data

    def faith_evaluation(self, data):
        data['response'] = parse_html_body(data['html'])
        data['markdown_text'] = data['response']
        claim_ext_payload = process_payloads_for_claim_extraction(data)
        try:
            claims_result = self.call_client(claim_ext_payload).strip("```json").strip("```")
            claims = json_repair.loads(claims_result.replace("\\n", "\n"))['claims']
        except Exception as e:
            print(f"error info: {e}")
            claims = []
        
        data['all_claims'] = claims
        if len(claims) == 0:
            return data

        data['eval_result'] = {}

        for claim in claims:
            data['eval_result'][claim] = {}
            data['eval_result'][claim]['claim_eval_result'] = []
            data['eval_result'][claim]['score'] = 1
            tmp_data = {"query": data["query"], "claim": claim, "reference": data['reference']}
            if 'current_time' in data:
                tmp_data = {"current_time": data["current_time"], **tmp_data}
            claim_faith_check_payload = process_payloads_for_faith_eval(tmp_data)
            claim_faith_check_result = self.call_client(claim_faith_check_payload).strip("```json").strip("```")
            pattern = r'"label":\s*"([^"]+)"'
            match = re.search(pattern, claim_faith_check_result)
            claim_faith_check_label = 'neutral'
            if match:
                claim_faith_check_label = str(match.group(1)).lower()
                data['eval_result'][claim]['claim_eval_result'].append({"llm_result": claim_faith_check_result, "label": claim_faith_check_label})
            elif "contradiction" in claim_faith_check_label:
                data['eval_result'][claim]['score'] = 0
            elif "entailment" in claim_faith_check_label:
                data['eval_result'][claim]['score'] = 1

        data['score'] = 0
        data['case_level_score'] = 0
        if 'eval_result' in data and len(data['eval_result']) > 0:
            claim_score_lst = [x['score'] for x in data['eval_result'].values()]
            data['score'] = sum(claim_score_lst) / len(claim_score_lst)
            data['case_level_score'] = min(claim_score_lst)
        return data


    def trigger_rate_evaluation(self, data):
        soup = BeautifulSoup(data['html'], 'html.parser')
        ## table trigger rate
        tables = soup.find_all('table')
        data['eval_result'] = {}
        if len(tables) > 0:
            data['eval_result']['has_table'] = 1
        else:
            data['eval_result']['has_table'] = 0

        ## echart trigger rate
        echarts = extract_chart_code(data['html'])
        if echarts:
            data['eval_result']['has_chart'] = 1
        else:
            data['eval_result']['has_chart'] = 0
        return data

    def run_evaluation(self, input_path, output_path):
        ## validate data
        eval_function = None
        if self.eval_task in ["comprehensiveness_eval"]:
            DataValidator.data_validate(input_path)
            eval_function = self.comprehensiveness_evaluation
        elif self.eval_task == "reasonableness_eval":
            DataValidator.data_validate(input_path)
            eval_function = self.reasonableness_evaluation
        elif self.eval_task == "faith_eval":
            DataValidator.data_validate(input_path)
            eval_function = self.faith_evaluation
        elif self.eval_task == "trigger_rate_eval":
            DataValidator.data_validate(input_path)
            eval_function = self.trigger_rate_evaluation
        else:
            raise ValueError("eval_task is not within the supported scope")

        if eval_function is not None:
            dataset = DatasetLoader.load(input_path)
            with open(output_path, "w", encoding="utf-8") as wf, \
                ThreadPoolExecutor(max_workers=self.max_workers) as executor:

                future_to_data = {
                    executor.submit(eval_function, data): data
                    for data in dataset
                }

                for future in tqdm(as_completed(future_to_data), total=len(future_to_data), desc="Processing", unit="task"):
                    autoeval_result = future.result()
                    wf.write(json.dumps(autoeval_result, ensure_ascii=False) + "\n")
                    wf.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Params Parser")
    parser.add_argument("--input_path", type=str, default="data/benchmark/test_data_500.jsonl", help="Input file path")
    parser.add_argument("--output_path", type=str, default="data/benchmark/test_data_500.result.jsonl", help="Output file path")
    parser.add_argument("--model_name", type=str, default="gemini-2.5-pro", help="Model name to use (options: gemini-2.5-pro)")
    parser.add_argument("--max_workers", type=int, default=16, help="Maximum number of worker threads")
    parser.add_argument("--eval_task", type=str, default="wildbench_score", help="options: checklist_score, wildbench_score")
    
    args = parser.parse_args()
    print(f"----------------Params----------------")
    for arg, value in vars(args).items():
        print(f"{arg}: {value}")

    evaluator = Evaluator(args)

    ## run evaluation with your input file
    evaluator.run_evaluation(args.input_path, args.output_path)
    MetricsEvaluator.compute_metrics(args)
