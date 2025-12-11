# Ryan's Agent Assignment

A production-ready AI Agent service built with FastAPI, capable of autonomous tool selection, web searching, math calculations, and governance note recording.

## 🚀 Getting Started

### Prerequisites

- Python 3.12+
- Docker (optional)

### 1. Setup Environment

1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd ryan-asignment
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### 2. Configure Credentials

Create a `.env` file in the project root:

```bash
touch .env
```

Add your API keys. We support both Google Gemini and OpenAI:

**Option A: Google Gemini (Recommended)**
```env
LLM_PROVIDER=google
GOOGLE_GENAI_API_KEY=your_gemini_api_key_here
GOOGLE_GENAI_MODEL=gemini-2.5-flash
```

**Option B: OpenAI**
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4-turbo
```

### 3. Run the Server

Start the development server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.

---

## 🧪 Quick Test

Ask the agent a question:

```bash
curl -X POST http://localhost:8000/run-task \
  -H "Content-Type: application/json" \
  -d '{"goal": "Who is Elon Musk and what is 50 divided by 2?"}'
```

You should see an intelligent response using multiple tools!
