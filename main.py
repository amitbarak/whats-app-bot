from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

from openapi import get_answer_from_ai

app = Flask(__name__)

@app.route('/', methods=['POST'])
def whatsapp():
    print("got here")
    incoming_msg = request.values.get('Body', '').lower()
    resp = MessagingResponse()
    msg = resp.message()
    print(msg)
    open_ai_response = get_answer_from_ai(incoming_msg)
    msg.body(f"Hi there! I'm your WhatsApp botM made by Amit 🤖 below are my answers: \n {open_ai_response}")
    print(resp)
    return str(resp)

if __name__ == '__main__':
    app.run(debug=True)
