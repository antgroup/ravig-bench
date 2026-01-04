#!/bin/bash

start=$(date +%s)

usage() {
    echo "Usage: $0 -c <config_file>"
    echo "Options:"
    echo "  -c <config_file> : Specify the config file path (required)."
    exit 1
}

while getopts ":c:" opt; do
    case "${opt}" in
        c)
            CONFIG_FILE="${OPTARG}"
            ;;
        \?)
            echo "Error: Invalid option: -${OPTARG}" >&2
            usage
            ;;
        :) 
            echo "Error: Option -${OPTARG} requires an argument." >&2
            usage
            ;;
    esac
done

if [ -z "$CONFIG_FILE" ]; then
    echo "Error: Config file path (-c) is required." >&2
    usage
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file '$CONFIG_FILE' not found." >&2
    exit 1
fi

while IFS='=' read -r key value || [ -n "$key" ]; do
    echo "Processing key: $key=$value"
    case "$key" in
        root) ROOT_DIR="$value" ;;
        input_file) INPUT_FILE="$value" ;;
        type) TYPE="$value" ;;
        width) WIDTH="$value" ;;
        limit) LIMIT="$value" ;;
        output) OUTPUT_DIR="$value" ;;
        processes) PROCESSES="$value" ;;
    esac
done < "$CONFIG_FILE"

if [ -z "$ROOT_DIR" ]; then
    echo "Error: Root directory is required in config.txt." >&2
    exit 1
fi

if [ -z "$INPUT_FILE" ]; then
    echo "Error: Input file is required in config.txt." >&2
    exit 1
fi

if [ -z "$TYPE" ]; then
    echo "Error: Type is required in config.txt." >&2
    exit 1
fi

if [ "$TYPE" = "app" ] && [ -z "$WIDTH" ]; then
    echo "Error: Width is required in config.txt when type is 'app'." >&2
    exit 1
fi

mkdir -p "$ROOT_DIR" 
if [ ! -d "$ROOT_DIR" ]; then
    echo "Error: Root directory '$ROOT_DIR' does not exist or is not a directory." >&2
    exit 1
fi
FULL_INPUT_FILE_PATH="$ROOT_DIR/$INPUT_FILE"
if [ ! -f "$FULL_INPUT_FILE_PATH" ]; then
    echo "Error: Input file '$FULL_INPUT_FILE_PATH' does not exist or is not a regular file." >&2
    exit 1
fi
case "$TYPE" in
    "web"|"app")
        ;;
    *)
        echo "Error: Invalid type '$TYPE'. Allowed types are 'web', 'app'." >&2
        exit 1
        ;;
esac

echo "--- Parameters Parsed Successfully ---"
echo "Root Directory: $ROOT_DIR"
echo "Input File:     $INPUT_FILE"
echo "Type:           $TYPE"
if [ -n "$WIDTH" ]; then 
    echo "Width:          $WIDTH"
fi
echo "--------------------------------------"

mkdir -p "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/web"
mkdir -p "$OUTPUT_DIR/module"

LOG_FILE="$OUTPUT_DIR/screenshots.log" 

log_message() {
    local type="$1"
    local message="$2"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$type] $message" | tee -a "$LOG_FILE" >&2
}

main() {
    if [[ ! -f "$ROOT_DIR/$INPUT_FILE" ]]; then
        log_message ERROR "Input file '$ROOT_DIR/$INPUT_FILE' does not exist."
        exit 1
    fi

    python design_eval/screenshot-tool/web_screenshot.py \
      --root $ROOT_DIR \
      --input $INPUT_FILE \
      --output $OUTPUT_DIR/web \
      --type $TYPE \
      --width $WIDTH \
      --processes $PROCESSES

    if [ "$HUMAN_CONSISTENCY" = "true" ]; then
        python design_eval/screenshot-tool/module_screenshot.py \
          --root $ROOT_DIR \
          --input $INPUT_FILE \
          --output $OUTPUT_DIR/module \
          --type $TYPE \
          --processes $PROCESSES \
          --human_consistency
    else
        python design_eval/screenshot-tool/module_screenshot.py \
          --root $ROOT_DIR \
          --input $INPUT_FILE \
          --output $OUTPUT_DIR/module \
          --type $TYPE \
          --processes $PROCESSES
    fi

    wait

    log_message INFO "Done processing screenshots."
}

main "$@"

end=$(date +%s)
diff=$(( end - start ))
echo "Total Time: $diff seconds."
