#!/bin/bash

base_dir=""
infer_file_name=""
model_name=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --base_dir) base_dir="$2"; shift ;;
        --infer_file_name) infer_file_name="$2"; shift ;;
        --model_name) model_name="$2"; shift ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

# 必填参数检查
if [ -z "$base_dir" ] || [ -z "$infer_file_name" ] || [ -z "$model_name" ]; then
    echo "Error: Missing required arguments."
    echo "Usage: $0 --base_dir DIR --infer_file_name FILE --model_name NAME"
    exit 1
fi

echo "Base Dir: $base_dir"
echo "Infer File: $infer_file_name"
echo "Model Name: $model_name"

screenshot_dir="Screenshots"
total_res_dir="final_results"
function_res_dir="function_res"
design_res_dir="design_res"
content_res_dir="content_res"
TEXT_EVAL_MODEL_NAME="gemini-2.5-pro"
DESIGN_EVAL_MODEL_NAME="gpt-4o-2024-11-20"
NUM_THREADS=8

echo "BEGIN: $model_name"

########## screenshot
sh run_screenshot.sh ${model_name} ${base_dir} ${infer_file_name} ${screenshot_dir}

########## function eval
python execution_eval/check_html.py \
    --base-path ${base_dir}/${screenshot_dir} \
    --output-path ${base_dir}/${function_res_dir}

########## design eval

## big chart
python design_eval/big_charts.py \
    --base-path ${base_dir}/${screenshot_dir} \
    --output-path ${base_dir}/${design_res_dir}

## big svg
python design_eval/big_svg.py \
    --input ${base_dir}/${model_name}/${infer_file_name} \
    --output ${base_dir}/${design_res_dir}/${model_name} \
    --processes ${NUM_THREADS}

## overflow detect
python design_eval/overflow_detect.py \
    --input_jsonl ${base_dir}/${model_name}/${infer_file_name} \
    --output_dir ${base_dir}/${design_res_dir}/${model_name} \
    --num_threads ${NUM_THREADS}

## color detect
python design_eval/color_detect.py \
    --input_jsonl ${base_dir}/${model_name}/${infer_file_name} \
    --output_dir ${base_dir}/${design_res_dir}/${model_name} \
    --num_threads ${NUM_THREADS}

## color detect chart
python design_eval/color_detect_chart.py \
    --input_jsonl ${base_dir}/${model_name}/${infer_file_name} \
    --output_dir ${base_dir}/${design_res_dir}/${model_name} \
    --num_threads ${NUM_THREADS}

## missing elements
python design_eval/missing.py \
    --input_jsonl ${base_dir}/${model_name}/${infer_file_name} \
    --screenshot_dir ${base_dir}/${screenshot_dir}/${model_name}/web \
    --output_dir ${base_dir}/${design_res_dir}/${model_name} \
    --num_threads ${NUM_THREADS} \
    --model ${DESIGN_EVAL_MODEL_NAME}

## occlusion
python design_eval/occlusion.py \
    --input_jsonl ${base_dir}/${model_name}/${infer_file_name} \
    --screenshot_dir ${base_dir}/${screenshot_dir}/${model_name}/module \
    --output_dir ${base_dir}/${design_res_dir}/${model_name} \
    --num_threads ${NUM_THREADS} \
    --model ${DESIGN_EVAL_MODEL_NAME} 

######## infomation eval
EVAL_DIR=${base_dir}/${content_res_dir}/${model_name}
mkdir -p "$EVAL_DIR"

TEXT_EVAL_TASK_LIST='reasonableness_eval,comprehensiveness_eval,faith_eval,trigger_rate_eval'

python content_eval/invoke_eval_report.py \
    --input_path "${base_dir}/${model_name}/${infer_file_name}" \
    --output_folder "${EVAL_DIR}" \
    --model_name "${TEXT_EVAL_MODEL_NAME}" \
    --eval_task_list "${TEXT_EVAL_TASK_LIST}" \
    --max_workers "${NUM_THREADS}" \
    --eval_num 1

########## report
python functions/compute_score.py \
    --fsr_dir ${base_dir}/${function_res_dir}/${model_name} \
    --dsr_dir ${base_dir}/${design_res_dir}/${model_name} \
    --info_dir ${base_dir}/${content_res_dir}/${model_name}

echo "END: $model_name"
echo "----------------------------------------"

