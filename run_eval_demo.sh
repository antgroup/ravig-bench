#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sh run_eval.sh \
  --base_dir $SCRIPT_DIR/data \
  --infer_file_name visual_rich_benchmark_test_case.jsonl \
  --model_name test_case


