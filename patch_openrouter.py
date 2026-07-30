from pathlib import Path

path = Path(r'C:\Users\mohit\OneDrive\Desktop\Shop\inventory.py')
text = path.read_text(encoding='utf-8')
start = text.find('def gemini_generate_content(contents, tools=None, temperature=0.7):')
end = text.find('def generate_description(conn):')
if start == -1 or end == -1:
    raise SystemExit('Marker not found')

old_block = text[start:end]
new_block = '''# ---------------------------------------------------------
# OpenRouter API — low-level request helper
# ---------------------------------------------------------

def _openrouter_request(payload):
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to your .env file.")

    endpoint = f"{OPENROUTER_BASE_URL.rstrip('/')}/v1/chat/completions"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            response_text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        error_body = err.read().decode("utf-8")
        raise RuntimeError(f"OpenRouter API error {err.code}: {error_body}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(f"OpenRouter request failed: {err.reason}") from err

    return json.loads(response_text)


def openrouter_chat(messages, temperature=0.7, functions=None, function_call="auto"):
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if functions is not None:
        payload["functions"] = functions
    if function_call is not None:
        payload["function_call"] = function_call

    response_data = _openrouter_request(payload)
    choices = response_data.get("choices")
    if not choices:
        raise RuntimeError(f"Unexpected OpenRouter response: {response_data}")
    return choices[0]["message"]


def openrouter_text(prompt_text, temperature=0.7):
    response_message = openrouter_chat(
        messages=[{"role": "user", "content": prompt_text}],
        temperature=temperature,
        functions=None,
        function_call=None,
    )
    return response_message.get("content", "").strip()
'''
if old_block == new_block:
    print('Already patched')
else:
    path.write_text(text[:start] + new_block + text[end:], encoding='utf-8')
    print('Patched inventory.py')
