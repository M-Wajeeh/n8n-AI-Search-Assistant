# 🎙️ Voice AI Research Assistant (v2)

A production-grade, low-latency AI agent built on **n8n**. This assistant orchestrates a sophisticated pipeline for processing both voice and text inputs, leveraging the latest in LLM and STT technology.

![Workflow Visualization](workflow.png)

---

## 🚀 Key Features

- **Dual-Mode Input Handling**: Seamlessly accepts raw text via JSON bodies or voice recording files (`audio/webm`, `audio/ogg`, etc.) via multipart headers.
- **Instant Transcription**: Powered by **Groq Whisper (`whisper-large-v3-turbo`)** for near-instant Speech-to-Text (STT).
- **Native Multilingualism**: Detects the user's browser language (e.g., `en`, `es`, `fr`) and responds in the same language automatically.
- **Intelligent Intent Routing**: Uses **Llama 3.3 70B** to classify queries into specialized execution branches:
  - 🔍 **Serper Research**: Deep-dive web searches for academic or news queries.
  - 🌤️ **Live Weather**: Real-time atmospheric data via OpenWeatherMap.
  - 📊 **Airtable Integration**: Structured data retrieval and automated request logging.
  - 💡 **General Assistant**: Direct interaction for light Q&A.
- **Session Tracking & Analytics**: Automatically logs every request (SessionID, Query, Intent, Language) to Airtable.
- **Fault-Tolerant Architecture**: Built-in **Error Recovery System** to handle node failures and API timeouts gracefully.

---

## 🛠️ Technology Stack

| Layer | Component | Description |
| :--- | :--- | :--- |
| **Orchestration** | [n8n](https://n8n.io/) | Self-hosted low-code workflow engine. |
| **Voice Engine** | [Groq Whisper v3](https://groq.com/) | Near-real-time transcription (STT). |
| **Brain / Logic** | [Llama 3.3 70B](https://groq.com/) | Advanced intent classification and summarization. |
| **Search API** | [Serper.dev](https://serper.dev/) | High-speed Google Search result retrieval. |
| **Weather Data** | [OpenWeatherMap](https://openweathermap.org/) | Current conditions and forecasts. |
| **Database** | [Airtable](https://airtable.com/) | Session logging and structured data lookup. |

---

## ⚙️ How it Works

1. **Ingestion**: The `/voice-agent` webhook receives a `POST` request.
2. **Transcription/Extraction**: If an audio file is detected, it's transcribed immediately. If no audio is found, it extracts text from the payload.
3. **Intent Classification**: The query is sent to Llama 3.3, which returns one of four labels: `research`, `weather`, `data_query`, or `general_question`.
4. **Execution Branch**:
   - *Research*: Fetches top 5 Google search results.
   - *Weather*: Pulls real-time temperature and conditions for the requested city.
   - *Data Query*: Searches your company/personal Airtable base.
5. **Summarization**: All raw data is funneled into a final Llama 3.3 node that prepares a 2-3 sentence, voice-friendly summary in the user's native tongue.
6. **Response & Log**: The assistant returns a JSON payload with the transcription and answer, while simultaneously logging the entire session to Airtable.

---

## 🚀 Getting Started

### 1. Requirements
You will need API keys for:
- [Groq](https://console.groq.com/)
- [Serper](https://serper.dev/)
- [OpenWeatherMap](https://openweathermap.org/)
- [Airtable](https://airtable.com/)

### 2. Installation
1. Import `Voice-AI-Research-Assistant.json` into your n8n instance.
2. Replace local placeholders (like `YOUR_GROQ_API_KEY`) with your actual keys.
3. Activate the workflow and ensure your webhook path is set to `voice-agent`.
4. Open `voice_frontend.html` in your browser and update the `N8N_URL` in the script section to match your n8n instance.

---

## 📄 License
This project is licensed under the **MIT License**. Use it as a foundation for your own AI voice agents!
