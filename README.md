Here's a comprehensive README.md file for your Sentinel QA Analytics Dashboard project:

````markdown
# Sentinel QA Analytics Dashboard

A comprehensive QA analytics dashboard with AI-powered chart generation capabilities. This tool helps QA teams visualize test results, track trends, and gain insights from their testing data.

## 🌟 Features

- **Real-time QA Analytics Dashboard** - View KPIs, test status distribution, and module stability
- **AI-Powered Chart Generation** - Generate charts using natural language prompts
- **Multiple AI Backends** - Support for Gemini AI and Ollama (local LLM)
- **Historical Trend Analysis** - Track test results over time
- **Module Stability Metrics** - Monitor failure rates per module
- **Slow Test Detection** - Identify performance bottlenecks
- **Failure Analysis** - Detailed view of failed tests
- **Chart Gallery** - Save and manage AI-generated charts

## 📋 Prerequisites

### Required Software

- **Python 3.8+** - [Download Python](https://www.python.org/downloads/)
- **Node.js 18+** - [Download Node.js](https://nodejs.org/)
- **npm** or **yarn** - Package manager for frontend
- **Git** - For cloning the repository

### Optional (For AI Features)

- **Ollama** - For local LLM support ([Install Ollama](https://ollama.ai/))
- **Google Gemini API Key** - For cloud-based AI generation

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/sentinel-qa-analytics-dashboard.git
cd sentinel-qa-analytics-dashboard
```
````

### 2. Backend Setup (Python API)

#### Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

#### Install Python Dependencies

```bash
pip install fastapi uvicorn pandas numpy pydantic google-generativeai
```

For Ollama support (optional):

```bash
pip install ollama
```

#### Prepare Test Data

The application includes a data ingestion script that processes Allure test results:

```bash
python ingest.py
```

This will create `qa_analytics_master.json` with sample data if no Allure results are found.

### 3. Frontend Setup (Next.js Dashboard)

```bash
cd frontend/qa-dashboard
npm install
```

### 4. Start the Application

#### Terminal 1 - Start Backend API

```bash
# From the root directory
python gemini_qa_api.py
```

You should see:

```
==================================================
🚀 Starting QA Analytics API with AI Chart Generation
==================================================
📁 Data file: qa_analytics_master.json
🤖 AI Mode: Gemini (Live API)
🌐 API URL: http://localhost:8000
📚 API Docs: http://localhost:8000/docs
==================================================
✨ Ready to accept requests!
```

#### Terminal 2 - Start Frontend

```bash
cd frontend/qa-dashboard
npm run dev
```

The frontend will start at: http://localhost:3000

## 🤖 AI Configuration

### Option 1: Use Gemini AI (Cloud-Based)

1. Get your Gemini API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Set the API key as an environment variable:

```bash
# Windows Command Prompt
set GEMINI_API_KEY=your-api-key-here

# Windows PowerShell
$env:GEMINI_API_KEY="your-api-key-here"

# Mac/Linux
export GEMINI_API_KEY="your-api-key-here"
```

3. Run the API with Gemini support:

```bash
python gemini_qa_api.py
```

### Option 2: Use Demo Mode (No API Key Required)

Simply run without setting the API key:

```bash
python gemini_qa_api.py
```

The system will automatically use intelligent demo mode with realistic chart generation.

### Option 3: Use Ollama (Local LLM)

1. Install Ollama from [ollama.ai](https://ollama.ai/)
2. Pull a model:

```bash
ollama pull qwen2.5-coder:7b
```

3. Use the Ollama version of the API:

```bash
python ai_chart_generator.py
```

## 📁 Project Structure

```
sentinel-qa-analytics-dashboard/
├── gemini_qa_api.py          # Main API server with Gemini AI support
├── ai_chart_generator.py     # Ollama-based chart generator
├── ingest.py                 # Data ingestion script
├── qa_analytics_master.json  # Main data file (generated)
├── generated_charts.json     # Saved AI-generated charts
├── frontend/
│   └── qa-dashboard/         # Next.js frontend application
│       ├── app/              # Next.js app router
│       ├── components/       # React components
│       ├── lib/              # API client utilities
│       ├── types/            # TypeScript type definitions
│       └── package.json      # Frontend dependencies
└── README.md
```

## 🔧 API Endpoints

### Analytics Endpoints

| Endpoint               | Method | Description                    |
| ---------------------- | ------ | ------------------------------ |
| `/kpis`                | GET    | Get key performance indicators |
| `/status-distribution` | GET    | Get test status distribution   |
| `/module-stability`    | GET    | Get module stability metrics   |
| `/slow-tests`          | GET    | Get slowest tests              |
| `/history-trend`       | GET    | Get historical trends          |
| `/failures`            | GET    | Get failed tests               |

### AI Chart Generation Endpoints

| Endpoint               | Method | Description                                 |
| ---------------------- | ------ | ------------------------------------------- |
| `/ai/generate-chart`   | POST   | Generate chart from natural language prompt |
| `/ai/generated-charts` | GET    | Get all generated charts                    |
| `/ai/chart/{chart_id}` | DELETE | Delete a generated chart                    |
| `/ai/chart-stats`      | GET    | Get statistics about generated charts       |
| `/ai/status`           | GET    | Get AI service status                       |

### Example: Generate a Chart

```bash
curl -X POST http://localhost:8000/ai/generate-chart \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Show me test results by module"}'
```

## 🎨 Using the Dashboard

### View Analytics

- **KPIs**: See total tests, pass/fail counts, and average duration
- **Status Chart**: Visualize pass/fail distribution
- **Module Chart**: View test results grouped by module
- **Trend Chart**: Track historical test results
- **Slow Tests**: Identify performance bottlenecks
- **Failures Table**: Detailed view of failed tests

### AI Chart Generation

1. Click on "AI Chart" section
2. Enter a natural language prompt (e.g., "Show me the trend of test failures over time")
3. Click "Generate" to create the chart
4. View and save generated charts in the gallery

### Example Prompts

- "Show me test distribution by module"
- "Display the top 10 slowest tests"
- "Create a pie chart of test status"
- "Show failure rate trends over the last 7 days"
- "Compare pass rates across different modules"

## 🛠️ Development

### Backend Development

```bash
# Run with auto-reload
uvicorn gemini_qa_api:app --reload --port 8000

# Access API documentation
open http://localhost:8000/docs
```

### Frontend Development

```bash
cd frontend/qa-dashboard

# Run development server
npm run dev

# Build for production
npm run build

# Start production server
npm start
```

### Testing

```bash
# Test API endpoints
python test_api.py

# Test frontend
cd frontend/qa-dashboard
npm test
```

## 📊 Data Ingestion

The system can ingest data from Allure test results:

1. Place Allure results in the specified directory
2. Run the ingestion script:

```bash
python ingest.py
```

3. The script will generate `qa_analytics_master.json` with:
   - Test results and metadata
   - Module stability metrics
   - Historical trends
   - Analytics (flaky tests, slow tests, etc.)

## 🔍 Troubleshooting

### Common Issues

#### Port Already in Use

```bash
# Change the port in gemini_qa_api.py
uvicorn.run(app, host="0.0.0.0", port=8001)
```

#### Missing Dependencies

```bash
# Install all dependencies
pip install -r requirements.txt
cd frontend/qa-dashboard && npm install
```

#### CORS Issues

Make sure the CORS origins in the API match your frontend URL:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    ...
)
```

#### Gemini API Key Issues

```bash
# Check if API key is set
echo $GEMINI_API_KEY  # Mac/Linux
echo %GEMINI_API_KEY%  # Windows
```

## 🚀 Deployment

### Backend Deployment (Python API)

```bash
# Using uvicorn
uvicorn gemini_qa_api:app --host 0.0.0.0 --port 8000

# Using gunicorn (production)
gunicorn -w 4 -k uvicorn.workers.UvicornWorker gemini_qa_api:app
```

### Frontend Deployment (Next.js)

```bash
cd frontend/qa-dashboard
npm run build
npm start
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [Next.js](https://nextjs.org/) - React framework for production
- [ApexCharts](https://apexcharts.com/) - Interactive charts
- [Google Gemini AI](https://deepmind.google/technologies/gemini/) - AI model for chart generation
- [Ollama](https://ollama.ai/) - Local LLM runtime

## 📧 Support

For issues, questions, or contributions:

- Open an issue on GitHub
- Contact the maintainers
- Check the API documentation at http://localhost:8000/docs

---

**Happy Testing! 🚀**

```

This README provides:
1. **Clear setup instructions** for both frontend and backend
2. **Multiple AI configuration options** (Gemini, Demo, Ollama)
3. **Project structure** explanation
4. **API documentation** with examples
5. **Troubleshooting guide**
6. **Deployment instructions**
7. **Development tips**

Users can clone the repository and follow these steps to get the application running on their local machine. The instructions are platform-agnostic and include commands for both Windows and Mac/Linux.
```
