# Sentinel QA AI Analytics Dashboard

An intelligent QA analytics dashboard that ingests Allure reports and provides AI-powered chart generation using natural language prompts.

## 🚀 Features

- **Allure Report Integration** - Automatically parse and analyze test results from Allure
- **Interactive Dashboard** - Real-time KPIs, module stability, trend analysis, and failure tracking
- **AI Chart Generator** - Generate custom visualizations using natural language (powered by Ollama)
- **Chart Gallery** - Persistent chart storage with drag-to-reorder functionality

## 📋 Prerequisites

- Node.js 18+
- Python 3.9+
- Ollama (with qwen2.5-coder:1.5b or similar model)

## 🛠️ Tech Stack

**Frontend:** Next.js 16, React 19, Tailwind CSS 4, ApexCharts, Recharts, DnD Kit
**Backend:** FastAPI, Pandas, Ollama

## 🔧 Installation

### 1. Clone the repository

```bash
git clone https://github.com/jaydeep9075/sentinel-qa-analytics-dashboard.git
cd sentinel-qa-analytics-dashboard
```

### 2. Backend Setup

```bash
cd frontend/qa-dashboard/next

# Install Python dependencies
pip install fastapi uvicorn pandas numpy ollama python-multipart

# Start FastAPI server
python app.py
# Server runs at: http://localhost:8000
```

### 3. Frontend Setup

```bash
# In a new terminal
cd frontend/qa-dashboard/next

# Install Node dependencies
npm install

# Start Next.js development server
npm run dev
# App runs at: http://localhost:3000
```

### 4. Ollama Setup

```bash
# Install Ollama from https://ollama.ai
ollama pull qwen2.5-coder:1.5b
```

## 📊 Allure Reports

Place your Allure results in:

```
C:\Users\USERNAME\Downloads\allure-results
```

Run the ingestor to parse reports:

```bash
python ingest.py
```

## 🎯 Usage

1. Open http://localhost:3000
2. View default analytics (KPIs, module stability, trends)
3. Generate AI charts using natural language:
   - "Show pie chart of test status"
   - "Bar chart of top 10 slowest tests"
   - "Scatter plot of duration vs failures"
4. Manage charts in the gallery (drag to reorder, delete unwanted)
