import re
import base64
import requests
from Crypto.Cipher import AES
from binascii import b2a_hex, a2b_hex
from sklearn import metrics
from typing import List, Dict, Any
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
import json
import os
import sys

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(parent_dir)

def url_to_base64(image_url):
    response = requests.get(image_url)
    
    if response.status_code == 200:
        base64_string = base64.b64encode(response.content).decode('utf-8')
        return base64_string
    else:
        print(f"ERROR: Status Code {response.status_code}")
        return None


def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        base64_string = base64.b64encode(image_file.read()).decode('utf-8')
    return base64_string


def compute_metrics(golden_label, predict_label):
    print('Acc: %.4f' % metrics.accuracy_score(golden_label, predict_label), '\n',
    'F1-score: %.4f' % metrics.f1_score(golden_label, predict_label, average='macro'), '\n',
    'Confusion Matrix: \n%s' % metrics.confusion_matrix(golden_label, predict_label), '\n',
    'Report:\n%s' % metrics.classification_report(golden_label, predict_label, digits=4))


def parse_input_data(value: Any, expected_type: type) -> Any:
    """Parse input data from string to expected type if needed."""
    if isinstance(value, str) and value.strip():
        return json.loads(value)
    return value if isinstance(value, expected_type) else expected_type()


def format_history(history: List[Dict[str, str]]) -> str:
    """Format conversation history into a string."""
    return "\n".join(
        f"Query: {his['query']}\nAnswer: {his['response']}"
        for his in history
    )


def format_checklist(checklist: List[str]) -> str:
    """Format checklist items into a numbered list string."""
    return "\n".join(
        f"{i+1}. {item}"
        for i, item in enumerate(checklist)
    )


def read_prompt_template(file_path: str) -> str:
    """Read prompt template from file with proper error handling."""
    path = Path(file_path)
    try:
        with path.open(encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Prompt template not found at: {file_path}")


def create_prompt(template: str, replacements: Dict[str, str]) -> str:
    """Create prompt by replacing placeholders in template."""
    prompt = template
    for key, value in replacements.items():
        prompt = prompt.replace(key, str(value))
    return prompt


def extract_echarts_code(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    script_tags = soup.find_all('script')
    
    echarts_blocks = []
    
    for script in script_tags:
        script_content = script.string
        if script_content is None:
            continue
            
        if re.search(r'echarts\.init\(', script_content, re.IGNORECASE):
            echarts_blocks.append(script_content.strip())
            
        elif re.search(r'option\s*=\s*\{', script_content, re.IGNORECASE):
            echarts_blocks.append(script_content.strip())
            
    return echarts_blocks

def process_image_from_url(url, enable_cut=False, max_ratio=4):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'image/webp,image/*,*/*;q=0.8'
    }
    try:
        # Load the image from the URL
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            # Check if the content-type is an image
            content_type = response.headers.get('Content-Type')
            if 'image' not in content_type:
                raise ValueError(f"URL did not return an image. Content-Type: {content_type}")
        
        img = Image.open(BytesIO(response.content))
        
        # Convert RGBA to RGB if needed (to avoid JPEG save error)
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        
        width, height = img.size
        aspect_ratio = height / width 
        # print(f"Original image size: width{width}, heigth{height}")
        # print("Original aspect ratio:", aspect_ratio)

        if not enable_cut:
            if aspect_ratio <= max_ratio:
                return 'url', url
        
        base64_images = []

        # Calculate the number of cuts needed
        num_cuts = int(height / (max_ratio * width)) + 1
        
        # Calculate the new width for each segment
        new_height = int(height/num_cuts)

        # Cut the image
        for i in range(num_cuts):
            top = i * new_height
            bottom = min((i + 1) * new_height, height)
            
            box = (0, top, width, bottom)
            # print(box)
            segment = img.crop(box)

            # Convert each segment to Base64
            buffered = BytesIO()
            segment.save(buffered, format="JPEG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            base64_images.append(img_base64)

        return 'base64', base64_images
    
    except Exception as e:
        print(f"Error processing image from URL: {e}")
        return 'url', url
    
def process_score(score):
    if isinstance(score, int):
        return score
    elif isinstance(score, float):
        return score
    else:
        score = score[0]
        if score == "X":
            return score
        else:
            return int(score)

def extract_chart_code(html):
    soup = BeautifulSoup(html, 'html.parser')
    scripts = soup.find_all('script')
    chart_scripts = []

    for script in scripts:
        if not script.string:
            continue
        code = script.string

        keywords = ['echarts', 'Chart.', 'plotly', 'd3', 'apexcharts', 'option', 'series']
        if any(kw in code for kw in keywords):
            chart_scripts.append(code.strip())

        if re.search(r'option\s*=', code):
            match = re.search(r'(var\s+option\s*=.*?;)', code, re.DOTALL)
            if match:
                chart_scripts.append(match.group(1))

    return chart_scripts

def get_docs_str(docs_list):
    docs_str_list = []
    for doc in docs_list:
        result = \
f'''<doc id="{doc['id']}" authority_level="{doc['authority_level']}" publish_time="{doc['publish_time']}" site="{doc['site']}" >
    <title>{doc.find('title').text}</title>
    <summary>{doc.find('summary').text}</summary>
    <content>{doc.find('content').text}</content>
</doc>'''
        docs_str_list.append(result)

    return '\n\n'.join(str(doc) for doc in docs_str_list)

def parse_html_body(html_content):
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        body_tag = soup.body
        body_outer_html = str(body_tag)
        return body_outer_html
    except Exception as e:
        print('parse_html_body error!')
        return html_content
