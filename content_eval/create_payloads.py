import copy
from typing import Dict, Any
from datetime import datetime
from functions.common import format_checklist, read_prompt_template, create_prompt
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent

def process_payloads_for_comprehensiveness_eval(params: Dict[str, Any]) -> Dict[str, Any]:

    template = read_prompt_template(f"{BASE_DIR}/prompts/comprehensiveness_eval_prompt.md")
    checklist_str = format_checklist(params['checklist'])
    
    replacements = {
        "@QUERY": params['query'],
        "@RESPONSE": params['response'],
        "@CHECKLIST": checklist_str,
        "@CURRENT_TIME": params.get('current_time', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    }
    
    return {
        "prompt": create_prompt(template, replacements),
        "max_output_length": 8192
    }


def process_payloads_for_reasonableness_eval(params: Dict[str, Any]) -> Dict[str, Any]:
    """Main function to process experiment payloads of reasonableness_eval."""

    # Process experiment payloads
    template = read_prompt_template(f"{BASE_DIR}/prompts/reasonableness_eval_prompt.md")

    replacements = {
        "@QUERY": params['query'],
        "@RESPONSE": params['response'],
        "@CURRENT_TIME": params.get('current_time', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    }
    
    payload = copy.deepcopy(params)
    payload['prompt'] = create_prompt(template, replacements)
    payload['max_output_length'] = 8192

    return payload


def process_payloads_for_claim_extraction(params: Dict[str, Any]) -> Dict[str, Any]:
    """Main function to process experiment parameters based on evaluation type."""

    template = read_prompt_template(f"{BASE_DIR}/prompts/claim_extraction_prompt.md")

    replacements = {
        "@QUERY": params['query'],
        "@RESPONSE": params['response'],
        "@CURRENT_TIME": params.get('current_time', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    }
    
    payload = copy.deepcopy(params)
    payload['prompt'] = create_prompt(template, replacements)
    payload['max_output_length'] = 8192

    return payload

def process_payloads_for_faith_eval(params: Dict[str, Any]) -> Dict[str, Any]:

    template = read_prompt_template(f"{BASE_DIR}/prompts/faithfulness_eval_prompt.md")
    payload = {}

    replacements = {
        "@CLAIM": params['claim'],
        "@REFERENCE": params['reference']
    }

    payload['prompt'] = create_prompt(template, replacements)
    payload['max_output_length'] = 8192

    return payload