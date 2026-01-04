from openai import OpenAI
import json
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
authorization_file_path = os.path.join(parent_dir, "config", "authorization.json")
MODEL_CONFIG = json.loads(open(authorization_file_path, encoding='utf8').read())

import time

def call_openai_stream(prompt, model="gemini-2.5-flash", max_tokens=8192, temperature=1.0, reasoning_effort=None, system_prompt='You are a helpful assistant.'):
    assert model in MODEL_CONFIG
    api_key=MODEL_CONFIG[model]['api_key']
    base_url=MODEL_CONFIG[model]['base_url']
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=600
    )
    if isinstance(prompt, list):
        messages = prompt
    else:
        messages = [
            {
                "role": "system", 
                "content": system_prompt
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
    ]
    # print("messages: ", messages[1]['content'][0])
    response = client.chat.completions.create(
        model=model,
        reasoning_effort=reasoning_effort,
        max_tokens=max_tokens,
        messages = messages,
        temperature=temperature,
        stream=True
    )
    
    collected_chunks = []
    collected_messages = []
    start_time = time.time()
    # iterate through the stream of events
    for chunk in response:
        collected_chunks.append(chunk)  # save the event response
        chunk_message = chunk.choices[0].delta.content  # extract the message
        if chunk_message:
            collected_messages.append(chunk_message)  # save the message

    response = ''.join(collected_messages)
    request_time = time.time() - start_time
    print(f"Request Finished {request_time:.2f} seconds")
    return response

if __name__ == '__main__':
    prompt = "What day is it today?"
    model = "gpt-4o-2024-11-20"
    response = call_openai_stream(prompt, model, max_tokens=8192, reasoning_effort=None)
    print("model: ", model)
    print("response: ", response)