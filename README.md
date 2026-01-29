# RAViG-Bench  
**A Benchmark for Retrieval-Augmented Visually-rich Generation with Multi-modal Automated Evaluation**

> **Official implementation of**  
> *"RAViG-Bench: A Benchmark for Retrieval-Augmented Visually-rich Generation with Multi-modal Automated Evaluation"*  

---

RAViG-Bench is a comprehensive benchmark for evaluating **Retrieval-Augmented Visually-rich Generation (RAViG)** systems—models that generate HTML/CSS code enriched with visual design informed by retrieved reference documents. Our benchmark introduces a multi-dimensional evaluation framework covering **execution correctness, design quality, and content quality**, supported by **automated, multi-modal** assessment tools.

## 🌟 Key Features

- **Multi-dimensional Evaluation**: Assesses models across three critical dimensions:
  - **Execution Correctness**: Validate HTML execution correctness.
  - **Design Quality**: Assess visual design quality via automated screenshot analysis and heuristic checks.
  - **Content Quality**: Evaluate content quality using LLM-based prompting.

---

## 📁 File Organization

```
config/
├── authorization.json          # API keys and urls for LLM services (e.g., OpenAI, Gemini)

execution_eval/                 # ✅ Functionality Validation
└── check_html.py               # Validates HTML syntax, structure, and renderability

design_eval/                    # 🎨 Design Quality Assessment
├── screenshot-tool/            
│   ├── module_screenshot.py    # Captures screenshots of sections based on H1/H2 headings
│   └── web_screenshot.py       # Takes full-page screenshots
├── big_charts.py               # Detects oversized chart elements
├── big_svg.py                  # Identifies excessively large SVG components
├── missing.py                  # Flags missing expected UI elements
├── occlusion.py                # Detects overlapping or occluded content
├── color_detect.py             # Evaluates text/background color contrast (WCAG compliance)
├── color_detect_chart.py       # Specialized contrast check for chart elements
├── overflow_detect.py          # Identifies layout overflow issues
└── merge_results.py            # Aggregates all design evaluation metrics

information_eval/               # 📝 Content Quality Evaluation
├── information_prompts/        # Prompt templates for assessing Reasonableness, Comprehensiveness and Faithfulness.
└── information_eval_report.sh  # Script to run LLM-based content evaluation

functions/                      # Helper utilities
data/                           # dataset and project-related data
├── dataset/                    # RAViG-Bench dataset
├── few_shots/                  # few-shots for design_eval
└── test_case/                  # Sample inputs
```

---

## ▶️ Execution Methods

### 🔁 End-to-End Evaluation

Run the full evaluation pipeline on your model's generated HTML outputs:

```bash
bash run_eval.sh --base_dir <OUTPUT_DIR> --infer_file_name <GENERATED_HTML_FILE> --model_name <YOUR_MODEL_NAME>
```

> **Note**: Before running, ensure:
> - `config/authorization.json` contains valid API keys for any required LLM services.
> - The `<OUTPUT_DIR>` contains your generated HTML files.
> - Parameters in `run_eval.sh` (e.g., paths, thresholds) are adjusted as needed.

This command will:
1. Validate HTML execution correctness
2. Assess visual design quality via automated screenshot analysis and heuristic checks
3. Evaluate content quality using LLM-based prompting

Results are saved in structured JSON reports under the specified `--base_dir`.

---

### 🧪 Demo Evaluation

To test the pipeline on sample data:

```bash
bash run_eval_demo.sh
```

This runs a lightweight demo using built-in example outputs and prints summarized metrics to the console. Useful for verifying installation and understanding output format.

---

## ⚙️ Setup & Dependencies

1. **Python Environment**  
   We recommend Python ≥3.10. Create a virtual environment:
   ```bash
   python -m venv ravig_env
   source ravig_env/bin/activate  # Linux/Mac
   # or ravig_env\Scripts\activate  # Windows
   ```

2. **Install Requirements**
   ```bash
   pip install -r requirements.txt
   ```
   > *(Ensure `requirements.txt` is included in your repo with dependencies like `selenium`, `Pillow`, `beautifulsoup4`, `openai`, etc.)*

3. **Configure API Keys**  
   Edit `config/authorization.json`:

4. **Install Browser Drivers** (for screenshot tools)  
   Ensure ChromeDriver or GeckoDriver is installed and in your PATH if using Selenium-based screenshot tools.

---

## 📄 License

This project is licensed under the **Apache License 2.0**.  
