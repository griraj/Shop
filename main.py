import os 
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

respone= client.chat.completions.create(
    model="gpt-4o-mini",
    max_tokens=200,
    messages=[{"role":"user","content":"explain recursion in one sentence"}]
)

print(respone.choices[0].message.content)
