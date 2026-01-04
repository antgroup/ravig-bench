import os
import copy
import json
import argparse
import pandas as pd
from pprint import pprint
from invoke_eval import Evaluator, MetricsEvaluator


def get_file_length(path):
    with open(path, 'r') as f:
        return len(f.readlines())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Params Parser")
    parser.add_argument("--input_path", type=str, default="data/benchmark/test_data_500.jsonl", help="Input file path")
    parser.add_argument("--output_folder", type=str, default="data/benchmark/", help="Output folder")
    parser.add_argument("--output_path", type=str, default="")
    parser.add_argument("--model_name", type=str, default="gemini-2.5-pro", help="Model name to use (options: gemini-2.5-pro)")
    parser.add_argument("--max_workers", type=int, default=16, help="Maximum number of worker threads")
    parser.add_argument("--eval_task_list", type=str, default="", help="options: faith_eval, sense_eval")
    parser.add_argument("--eval_num", type=int, default=3)
    parser.add_argument("--eval_task", type=str, default="")
    
    args = parser.parse_args()
    args.eval_task_list = [x.strip() for x in args.eval_task_list.split(',')]

    print(f"----------------Params----------------")
    for arg, value in vars(args).items():
        print(f"{arg}: {value}")

    metrics = {}
    for eval_task in args.eval_task_list:
        args.eval_task = eval_task
        metrics[args.eval_task] = []
        for i in range(args.eval_num):
            print(f"Running evaluation task: {args.eval_task}, iteration {i+1}")

            evaluator = Evaluator(args)
            output_path = os.path.join(
                args.output_folder, 
                f"{args.input_path.split('/')[-1].replace('.jsonl', '')}.{args.model_name}.{args.eval_task}.{i+1}.jsonl"
            )
            args.output_path = output_path

            if os.path.exists(output_path) and (get_file_length(args.input_path) == get_file_length(output_path)):
                print(f"output_path: {output_path} already exists; skipping this evaluation")
            else:
                print(f"output_path: {output_path} does not exist; starting evaluation")
                evaluator.run_evaluation(args.input_path, output_path)
                
            metrics[args.eval_task].append(MetricsEvaluator.compute_metrics(args))

            if args.eval_task in ["trigger_rate"]:
                break
        
        avg_metrics = {}
        try:
            for key in metrics[args.eval_task][0].keys():
                values = [x[key] for x in metrics[args.eval_task]]
                if -1 not in values:
                    avg_metrics[f"final_{key}"] = round(sum(values) / len(values), 2)
                else:
                    avg_metrics[f"final_{key}"] = -1

            metrics[args.eval_task].append(copy.deepcopy(avg_metrics))
        except Exception as e:
            pass

    metric_path = os.path.join(args.output_folder, f"{args.input_path.split('/')[-1].replace('.jsonl', '')}.metrics.json")
    with open(metric_path, "w") as f:
        f.write(json.dumps(metrics, ensure_ascii=False, indent=4))
    
    print("------------- Evaluation Metrics -------------")
    pprint(metrics)
    print(f"Metrics file: {metric_path}")