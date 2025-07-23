from openai import OpenAI
from get_config import OPENAI_API_KEY

def __create_client():
  client = OpenAI(
    api_key=OPENAI_API_KEY
  )
  return client

def get_answer_from_ai(input_message_to_ai: str):
  client = __create_client()
  response = client.responses.create(
    model="gpt-4o-mini",
    input=input_message_to_ai,
    store=True,
  )
  print(response)
  return response.output_text

