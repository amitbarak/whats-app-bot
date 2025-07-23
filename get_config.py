# config.py
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables from .env file

GROK_LOCAL_TOKEN = os.getenv("GROK_LOCAL_TOKEN")
ACCOUNT_SID_TWILIO = os.getenv("ACCOUNT_SID_TWILIO")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
