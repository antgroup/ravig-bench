# INFER_RESULT_PARSED='/ossfs/team_nas/shanchang/data/asearch/benchmark/visual_rich_benchmark/visual_rich_bench_1798_0822_10_models_infer_result.jsonl'
# EVAL_DIR='/ossfs/team_nas/shanchang/data/asearch/benchmark/visual_rich_benchmark/info_eval_result_final'
INFER_RESULT_PARSED='/ossfs/team_nas/shanchang/data/asearch/benchmark/visual_rich_benchmark/visual_rich_benchmark_test_case.jsonl'
EVAL_DIR='/ossfs/team_nas/shanchang/data/asearch/benchmark/visual_rich_benchmark/info_eval_result_test_1203'
TEXT_EVAL_MODEL_NAME='gemini-2.5-pro'

mkdir -p "$EVAL_DIR"

TEXT_EVAL_TASK_LIST='sense_eval,comprehensiveness_eval,faith_eval,trigger_rate_eval'

MAX_WORKERS=8
eval_num=1
python invoke_eval_report.py \
    --input_path "${INFER_RESULT_PARSED}" \
    --output_folder "${EVAL_DIR}" \
    --model_name "${TEXT_EVAL_MODEL_NAME}" \
    --eval_task_list "${TEXT_EVAL_TASK_LIST}" \
    --max_workers "${MAX_WORKERS}" \
    --eval_num ${eval_num} \
