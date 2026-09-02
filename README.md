# Marine WhatsApp Chatbot

Independent Marine chatbot service using the same proven FastAPI and typed
configuration conventions as the Entartica chatbot. Company credentials,
customer data, business rules, deployments, and webhook URLs remain isolated.

## Local setup

```powershell
cd "C:\Users\mandi\OneDrive\Documents\marine_whatsapp_chat_bot"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Verify the service at `http://127.0.0.1:8000/health`.

## Safety defaults

The chatbot and Exotel outbound sending are disabled by default. Add only
Marine-owned credentials to the local `.env`; never copy the Entartica `.env`.

