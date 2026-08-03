from openai import OpenAI
import os
import json
import requests

api_key = os.environ["OPENROUTER_API_KEY"]

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key
)

def add_numbers(a, b):
    return a + b

def get_weather(city):
    geo_response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1}
    )
    geo_data = geo_response.json()

    if "results" not in geo_data:
        return f"Could not find location: {city}"

    lat = geo_data["results"][0]["latitude"]
    lon = geo_data["results"][0]["longitude"]

    weather_response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={"latitude": lat, "longitude": lon, "current_weather": True}
    )

    weather_data = weather_response.json()
    current = weather_data["current_weather"]

    return f"{current['temperature']}°C, wind {current['windspeed']} km/h"

tools = [
    {
        "type": "function",
        "function": {
            "name": "add_numbers",
            "description": "Add two numbers together and return the result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "The first number"},
                    "b": {"type": "number", "description": "The second number"}
                },
                "required": ["a", "b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather (temperature and wind speed) for a given city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "The city name, e.g. 'London' or 'Tokyo'"}
                },
                "required": ["city"]
            }
        }
    },
    {
        "type":"function",
        "function":{
            "name":"add_numbers",
            "description":"add the two numbers and return the result.",
            "parameters":{
                "type":"object",
                "properties":
                {
                    "a":{"type":"integer","description":"the first integer"},
                    "b":{"type":"integer","description":"the second integer"}
                },
                "required":["a","b"]
            }
        }
    }
]

history = [{"role": "system", "content": "You are a useful chatbot. Use tools when needed."}]

while True:
    user_input = input("You : ")

    if user_input in ("quit", "exit"):
        break

    history.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model="openai/gpt-4o",
        messages=history,
        tools=tools,
        max_tokens=500
    )

    message = response.choices[0].message

    if message.tool_calls:
        history.append(message)

        for tool_call in message.tool_calls:
            args = json.loads(tool_call.function.arguments)

            if tool_call.function.name == "add_numbers":
                result = add_numbers(args["a"], args["b"])
            elif tool_call.function.name == "get_weather":
                result = get_weather(args["city"])
            else:
                result = "Unknown tool"

            print(f"[Tool called: {tool_call.function.name}({args}) -> {result}]")

            history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result)
            })

        followup = client.chat.completions.create(
            model="openai/gpt-4o",
            messages=history,
            tools=tools,
            max_tokens=300
        )
        reply = followup.choices[0].message.content
        history.append({"role": "assistant", "content": reply})

    else:
        reply = message.content
        history.append({"role": "assistant", "content": reply})

    print("AI :", reply)