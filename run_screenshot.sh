#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

model_name=$1
root=$2
input_file=$3
output_dir=$4
type="${5:-web}"
width="${6:-800}"
processes="${7:-10}"

echo "BEGIN: $model_name"

cat > design_eval/screenshot-tool/config_temp.txt << EOF
root=${root}
input_file=${model_name}/${input_file}
type=${type}
width=${width}
output=${root}/${output_dir}/${model_name}
processes=${processes}
EOF

sh design_eval/screenshot-tool/run_screenshot.sh -c design_eval/screenshot-tool/config_temp.txt
pkill -f "pyppeteer"

echo "END: $model_name"
echo "----------------------------------------"

rm design_eval/screenshot-tool/config_temp.txt
