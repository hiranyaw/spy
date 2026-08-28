# claude_client.py
"""Minimal client for Claude API that accepts a PNG image and returns analysis text.
Replace the placeholder implementation with real API calls as needed.
"""
import os
import base64
import json
import requests

CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')
CLAUDE_API_URL = os.getenv('CLAUDE_API_URL', 'https://api.anthropic.com/v1/messages')

def send_image(image_bytes):
    """Send PNG image bytes to Claude and return the generated analysis.
    This implementation uses a mock response if the API key is not set.
    """
    if not CLAUDE_API_KEY:
        # Mock response for local development
        return "[Mock analysis] No Claude API key provided."
    # Prepare base64 image
    img_b64 = base64.b64encode(image_bytes).decode('utf-8')
    payload = {
        "model": "claude-3-5-sonnet-20240620",  # adjust as needed
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
                    {"type": "text", "text": "Please provide a concise analysis of this TradingView chart."}
                ]
            }
        ]
    }
    headers = {
        "x-api-key": CLAUDE_API_KEY,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }
    response = requests.post(CLAUDE_API_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    # Extract text from Claude's response
    for msg in data.get('content', []):
        if msg.get('type') == 'text':
            return msg.get('text')
    return ""
