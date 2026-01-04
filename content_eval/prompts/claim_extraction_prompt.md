### **Context**
You are an expert AI assistant. Your task is to analyze a user's `query` and the corresponding `html_body` of a chatbot's response.

### **Core Objective**
Your objective is to simultaneously identify and extract information from both **human-readable text** and embedded **charts**. All extracted information must be synthesized into key, verifiable, factual statements (called "claims") and placed into a single `claims` list.

### **Rules for Claim Extraction**

#### **Part 1: Extracting Claims from Text**

1.  **What to Extract:**
    *   From the visible text, extract factual assertions directly relevant to the `query`.
    *   Prioritize: **Dates**, **Numerical Values** (quantities, prices, percentages), **Locations**, and **Specific Names** (people, products, organizations).
    *   You **must** ignore HTML tags and attributes. For this part, **also ignore `<script>` blocks**.

#### **Part 2: Converting Chart Data into Factual Claims**

1.  **Identify and Parse Charts:** Scan `<script>` tags for charting library initializations (e.g., `new Chart(...)`). Mentally parse their `title`, `labels` (e.g., x-axis categories), and `datasets` (containing data series and their names).

2.  **Synthesize Facts, Don't Describe the Chart:** You must convert the structured chart data into self-contained factual statements. **Do not simply describe the chart's contents.** The goal is to state the fact that the chart illustrates.
    *   For each significant data point, create a complete, declarative sentence. This sentence should synthesize information from the chart's `title`, the data point's `label` (e.g., '2021'), the `dataset`'s name (e.g., 'Defense Budget ($B)'), and the `data` value itself.

3.  **Crucial Transformation Example:**
    *   **AVOID (Describing the chart):** "The chart shows a value of 842 for the year 2024 in the 'Defense Budget ($B)' dataset."
    *   **DO (Stating the fact):** "The US Defense Budget for 2024 was $842 billion."

#### **Part 3: General Rules for All Claims**

1.  **Formatting:**
    *   Every claim, regardless of its source (text or chart), must be a **self-contained, complete, declarative sentence**.
    *   Each claim must be fully understandable on its own, without needing the original `query` or `html_body`.
    *   **Text-based claims** should incorporate context from the `query` if needed.
    *   **Chart-based claims** must derive their context from the chart's own elements (title, axes, legends) to become standalone facts.
    *   **Do not use ambiguous pronouns** like "it" or "they".

2.  **What to Avoid:**
    *   Do not extract opinions, hypotheticals, or vague generalities.
    *   If no factual information can be derived from the text or any charts, the `claims` list **must be empty**.

## **Output Format**
Your output must strictly follow this JSON format. The `thoughts` section must explain your reasoning for both text and chart-based claims, including how you synthesized facts from chart data.

```json
{"thoughts": "My thought process for extracting claims from the text and for synthesizing factual statements from the chart data by combining titles, labels, and data points.", "claims": []}
```

### **Example 1: Tech Specs**
**Query:** iPhone 16 Pro Max specs
**html_body:**
```html
<div>
  <h1>iPhone 16 Pro Max Specifications</h1>
  <p>The new iPhone 16 Pro Max features several upgrades. The device sports a larger <strong>6.9-inch Super Retina XDR display</strong>. It weighs <strong>225 grams</strong>, a slight increase from the previous model. Battery life sees a notable improvement, now offering up to <strong>30 hours of video playback</strong>.</p>
</div>
```
**Output:**
```json
{"thoughts": "The html_body contains several numerical values related to the iPhone 16 Pro Max's specifications, which directly answers the user's query. I will extract the screen size, weight, and battery life as separate, complete claims.", "claims": ["The iPhone 16 Pro Max features a 6.9-inch Super Retina XDR display.", "The iPhone 16 Pro Max weighs 225 grams.", "The iPhone 16 Pro Max offers up to 30 hours of video playback."]}
```

### **Example 2: Financial Report**
**Query:** Tesla Q4 2023 earnings
**html_body:**
```html
<div class="report">
  <h2>Tesla, Inc. Fourth Quarter & Full Year 2023 Financial Results</h2>
  <p>In Q4 2023, Tesla's total revenue grew to <strong>$25.2 billion</strong>. Automotive revenue for the quarter was <strong>$21.6 billion</strong>. The company announced it had produced over <strong>560,000</strong> vehicles in the fourth quarter.</p>
</div>
```
**Output:**
```json
{"thoughts": "The user is asking for Tesla's Q4 2023 earnings, and the html_body provides specific numerical values for revenue and production. I will extract these key financial and production figures.", "claims": ["Tesla's total revenue for Q4 2023 was $25.2 billion.", "Tesla's automotive revenue for Q4 2023 was $21.6 billion.", "Tesla produced over 560,000 vehicles in the fourth quarter of 2023."]}
```

### **Example 3: Sports Result**
**Query:** Chiefs vs Ravens game result
**html_body:**
```html
<main>
  <h1>AFC Championship Final Score</h1>
  <p>The Kansas City Chiefs are heading to the Super Bowl after defeating the Baltimore Ravens with a final score of <strong>17-10</strong>. Chiefs tight end Travis Kelce had an outstanding game, recording <strong>11 receptions for 116 yards</strong>.</p>
</main>
```
**Output:**
```json
{"thoughts": "The html_body contains numerical scores and player statistics for the Chiefs vs Ravens game. I will extract the final score and the key player's performance stats as claims.", "claims": ["The Kansas City Chiefs defeated the Baltimore Ravens with a final score of 17-10 in the AFC Championship.", "In the AFC Championship game against the Ravens, Chiefs player Travis Kelce had 11 receptions for 116 yards."]}
```

### **Example 4: Historical Fact**
**Query:** When did Apollo 11 land on the moon?
**html_body:**
```html
<article>
  <h3>One Giant Leap</h3>
  <p>The Apollo 11 mission achieved its goal when the Eagle lunar module landed on the Moon on <strong>July 20, 1969</strong>. The landing site was named <strong>Tranquility Base</strong>, located in the Sea of Tranquility.</p>
</article>
```
**Output:**
```json
{"thoughts": "The html_body provides a specific date and a specific location related to the Apollo 11 moon landing. I will extract both of these facts.", "claims": ["The Apollo 11 mission's Eagle lunar module landed on the Moon on July 20, 1969.", "The Apollo 11 landing site was named Tranquility Base."]}
```

### **Example 5: No Factual Claims**
**Query:** Write me a short poem about the ocean
**html_body:**
```html
<div>
  <p>The ocean vast, in shades of blue,<br>Whispers tales both old and new.<br>Waves that crash upon the shore,<br>Then silently retreat for more.</p>
</div>
```
**Output:**
```json
{"thoughts": "The html_body contains a creative poem. It does not contain any verifiable, factual key information such as dates, numbers, or specific locations. Therefore, the claims list should be empty.", "claims": []}
```

### **Example 6: Synthesizing Text and Chart Facts**
**Query:** what is the percentage of military spending in the us budget.
**html_body:**
```html
<body class="max-w-4xl mx-auto px-4 py-8">
<!-- [Rest of the complex HTML from your original prompt] -->
<div class="chart-container mb-8">
<canvas id="budgetChart"></canvas>
</div>
<!-- ... -->
<script>
        // Budget Chart
        const budgetCtx = document.getElementById('budgetChart').getContext('2d');
        const budgetChart = new Chart(budgetCtx, {
            type: 'bar',
            data: {
                labels: ['2021', '2022', '2023', '2024', '2025*'],
                datasets: [
                    {
                        label: 'Defense Budget ($B)',
                        data: [759, 838, 773, 842, 849.8]
                        // ...
                    },
                    {
                        label: '% of Federal Budget',
                        data: [10.6, 12.7, 13.8, 12.7, 12.9],
                        type: 'line'
                        // ...
                    }
                ]
            },
            options: {
                plugins: {
                    title: {
                        text: 'US Defense Budget Trends (2021-2025)'
                    }
                }
            }
        });
    </script>
</body>
```
**Output:**
```json
{
  "thoughts": "The user is asking about US military spending. I will extract claims from two sources. First, from the visible text, I'll pull specific figures like the 2025 budget request and global spending share. Second, I'll analyze the chart in the script. Instead of describing the chart, I will synthesize its data points into factual statements. For each year in the chart's labels, I will create a claim for the budget amount and another for the budget percentage, using the dataset labels ('Defense Budget ($B)', '% of Federal Budget') and chart title to provide full context. All these statements will be combined into a single claims list.",
  "claims": [
    "The US Department of Defense fiscal year 2025 budget request is $849.8 billion.",
    "The US Department of Defense's 2025 budget request represents approximately 12.9% of total federal spending.",
    "The approved US defense budget for 2024 was $842 billion.",
    "In 2024, the US defense budget constituted 12.7% of the federal budget.",
    "The allocated US defense budget for 2023 was $773 billion.",
    "In 2023, the US defense budget constituted 13.8% of the federal budget.",
    "The US defense budget was $838 billion in 2022, representing 12.7% of the federal budget.",
    "The US defense budget was $759 billion in 2021, representing 10.6% of the federal budget.",
    "The US accounts for 36% of global defense spending.",
    "In FY2013, $63.3 billion was budgeted for Research & Development in the US defense budget."
  ]
}
```
---
## **Task Start**
**Query:** @QUERY
**html_body:**
```html
@RESPONSE
```
**Output:**
```json