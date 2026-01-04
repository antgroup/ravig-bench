#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import re
import argparse
from pathlib import Path
from lxml import etree

def is_mixed_content_v2(text_content: str) -> bool:
    if not text_content or not isinstance(text_content, str):
        return False

    fenced_pattern = re.compile(r"^\s*```html.*?```\s*$", re.DOTALL)
    doctype_pattern = re.compile(r"^\s*<!doctype html>.*?</html>\s*$", re.DOTALL | re.IGNORECASE)

    if fenced_pattern.fullmatch(text_content) or doctype_pattern.fullmatch(text_content):
        return False
        
    return True

def check_html_structure_v3(file_path, strict_mode=False):
    critical_error_keywords = [
        "mismatch",
        "Unexpected end tag",
        "end of file reached",
        "No DOCTYPE found"
    ]

    try:
        with open(file_path, 'rb') as f:
            html_content = f.read()
            if not html_content:
                return True, []

        parser = etree.HTMLParser()
        etree.fromstring(html_content, parser)

        relevant_errors = []
        for error in parser.error_log:
            error_message = error.message
            
            if strict_mode:
                formatted_error = f"Line {error.line}, Col {error.column}: {error_message}"
                relevant_errors.append(formatted_error)
            else:
                if any(keyword in error_message for keyword in critical_error_keywords):
                    if "No DOCTYPE found" in error_message:
                        formatted_error = f"Info: {error_message}"
                    else:
                        formatted_error = f"Line {error.line}, Col {error.column}: {error_message}"
                    relevant_errors.append(formatted_error)
            
        return len(relevant_errors) == 0, relevant_errors

    except etree.XMLSyntaxError as e:
        return False, [f"Syntax Error: {e}"]
    except Exception as e:
        return False, [f"Error: {e}"]

def check_file_comprehensive(file_path, strict_mode=False, check_mixed=True):
    result = {
        'structure_ok': True,
        'structure_errors': [],
        'is_mixed': False,
        'mixed_info': '',
        'is_empty': False,
        'has_issues': False
    }
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text_content = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                text_content = f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='latin-1') as f:
                text_content = f.read()
    except Exception as e:
        result['structure_ok'] = False
        result['structure_errors'] = [f"Error: {e}"]
        result['has_issues'] = True
        return result
    
    if not text_content or not text_content.strip():
        result['is_empty'] = True
        result['mixed_info'] = "File is empty or only contains whitespace characters."
        result['structure_ok'] = False
        result['structure_errors'] = ["File is empty"]
        result['has_issues'] = True
        return result
    
    structure_ok, structure_errors = check_html_structure_v3(file_path, strict_mode)
    result['structure_ok'] = structure_ok
    result['structure_errors'] = structure_errors
    
    if check_mixed:
        result['is_mixed'] = is_mixed_content_v2(text_content)
        if result['is_mixed']:
            result['mixed_info'] = "Mixing text and HTML code"
        else:
            result['mixed_info'] = "Pure HTML content"
    
    result['has_issues'] = result['is_empty'] or not structure_ok or (check_mixed and result['is_mixed'])
    return result

def check_web_folder_html(base_path="/Users/huqirui/visual_rich_bench/design_res_0829", 
                         strict_mode=False, check_mixed=True):
    results_dict = {}
    base_path = Path(base_path)
    
    for model_folder in base_path.iterdir():
        if model_folder.is_dir():
            model_name = model_folder.name
            web_folder = model_folder / "web"
            
            if not web_folder.exists() or not web_folder.is_dir():
                print(f"No web folder found for model: {model_name}")
                continue
                
            print(f"Processing web folder for model: {model_name}")
            results_dict[model_name] = {}
            
            html_files = list(web_folder.glob("*.html")) + list(web_folder.glob("*.htm"))
            
            for html_file in html_files:
                file_id = html_file.stem
                
                check_result = check_file_comprehensive(
                    html_file, 
                    strict_mode=strict_mode, 
                    check_mixed=check_mixed
                )
                
                status = 0 if check_result['has_issues'] else 1
                
                results_dict[model_name][file_id] = {
                    'status': status,
                    'file_path': str(html_file.relative_to(base_path)),
                    'structure_ok': check_result['structure_ok'],
                    'structure_errors': check_result['structure_errors'],
                    'is_mixed': check_result['is_mixed'],
                    'is_empty': check_result['is_empty'],
                    'mixed_info': check_result['mixed_info']
                }
                
                if check_result['has_issues']:
                    issues = []
                    if check_result['is_empty']:
                        issues.append("Empty")
                    if not check_result['structure_ok']:
                        issues.append("Structure")
                    if check_result['is_mixed']:
                        issues.append("Mixed")
                    
                    print(f"  Issues found in {file_id}: {', '.join(issues)}")
    
    return results_dict

def save_results_by_model(results_dict, output_base_path, filename="web_html_results.json"):
    output_base_path = Path(output_base_path)
    
    for model_name, model_results in results_dict.items():
        model_output_dir = output_base_path / model_name
        model_output_dir.mkdir(parents=True, exist_ok=True)
        
        status_results = {}
        no_issue_count = 0
        issue_count = 0
        empty_count = 0
        mixed_count = 0
        structure_error_count = 0
        
        for file_id, file_result in model_results.items():
            status = file_result['status']
            status_results[file_id] = status
            
            if status == 1:
                no_issue_count += 1
            else:
                issue_count += 1
                if file_result.get('is_empty', False):
                    empty_count += 1
                if file_result.get('is_mixed', False):
                    mixed_count += 1
                if not file_result.get('structure_ok', True):
                    structure_error_count += 1
        
        sorted_results = dict(sorted(status_results.items(), 
                                   key=lambda x: int(x[0]) if x[0].isdigit() else x[0]))
        
        complete_results = {
            "total_right": no_issue_count,
            "total_wrong": issue_count,
            "empty_files": empty_count,
            "mixed_content_files": mixed_count,
            "structure_error_files": structure_error_count,
            "results": sorted_results
        }
        
        output_file = model_output_dir / filename
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(complete_results, f, ensure_ascii=False, indent=2)
        
        print(f"Results for {model_name} saved to {output_file}")
        print(f"  Total items: {len(model_results)}")
        print(f"  No issue (1): {no_issue_count}, Issue (0): {issue_count}")
        if empty_count > 0:
            print(f"  Empty files: {empty_count}")
        if mixed_count > 0:
            print(f"  Mixed content files: {mixed_count}")
        if structure_error_count > 0:
            print(f"  Structure error files: {structure_error_count}")

def save_detailed_results(results_dict, output_base_path, filename="web_html_detailed.json"):
    output_base_path = Path(output_base_path)
    output_base_path.mkdir(parents=True, exist_ok=True)
    
    output_file = output_base_path / filename
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results_dict, f, ensure_ascii=False, indent=2)
    
    print(f"Detailed results saved to {output_file}")

def main():
    parser = argparse.ArgumentParser(description="Execution Eval ...")
    parser.add_argument('--base-path', type=str, 
                       default="/Users/huqirui/visual_rich_bench/Screenshots_0828",
                       help="模型文件夹的基础路径")
    parser.add_argument('--output-path', type=str,
                       default="/Users/huqirui/visual_rich_bench/final_results_0910", 
                       help="Output Path")
    parser.add_argument('--strict', action='store_true', 
                       help="启用严格模式，报告所有HTML解析错误")
    parser.add_argument('--no-mixed-check', action='store_true',
                       help="禁用混合内容检查")
    parser.add_argument('--save-detailed', action='store_true',
                       help="保存详细的检查结果")
    
    args = parser.parse_args()
    
    check_mixed = not args.no_mixed_check
    
    print("=== 检查模型web文件夹中的HTML文件 ===")
    print(f"基础路径: {args.base_path}")
    print(f"输出路径: {args.output_path}")
    print(f"严格模式: {args.strict}")
    print(f"混合内容检查: {check_mixed}")
    print()
    
    # 检查HTML文件
    web_results = check_web_folder_html(
        base_path=args.base_path,
        strict_mode=args.strict,
        check_mixed=check_mixed
    )
    
    print(f"\n=== 检查完成 ===")
    print(f"找到 {len(web_results)} 个模型的web结果")
    
    total_files = 0
    total_issues = 0
    
    for model, results in web_results.items():
        no_issue = sum(1 for file_result in results.values() if file_result['status'] == 1)
        issue = sum(1 for file_result in results.values() if file_result['status'] == 0)
        total_files += len(results)
        total_issues += issue
        print(f"{model}: {len(results)} 个文件 (无问题: {no_issue}, 有问题: {issue})")
    
    print(f"\n总计: {total_files} 个HTML文件，{total_issues} 个有问题")
    
    # 保存结果（参考missing_occlusion_results的格式）
    save_results_by_model(web_results, args.output_path, "web_html_results.json")
    
    # 可选：保存详细结果
    if args.save_detailed:
        save_detailed_results(web_results, args.output_path, "web_html_detailed.json")
    
    print(f"\n所有结果已保存到 {args.output_path}")

if __name__ == "__main__":
    main()
