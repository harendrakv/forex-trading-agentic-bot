# core/model_router.py
import os, time, json
from openai import OpenAI
from config.config_loader import load_config

class ModelRouter:
    def __init__(self, config):
        self.config = config

    def call_groq(self, prompt, max_tokens=256):
        client = OpenAI(api_key=self.config['models']['groq']['api_key'], base_url=self.config['models']['groq']['endpoint'])
        model_name = self.config['models']['groq']['model_name']
        response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a conservative trading analyst. Answer concisely."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.15,
                max_tokens=2000
            )
        return response
    def call_openai(self, prompt, max_tokens=1024, temperature=0.0):
        openai = OpenAI(api_key=self.config["models"]["openai"]["api_key"])
        return openai.chat.completions.create(
            model=self.config["models"]["openai"]["model_name"],
            messages=[
                {"role":"system", "content":"You are a conservative trading analyst. Answer concisely."},
                {"role":"user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature
        )
    def groq_then_openai_for_final(self, context_prompt):
        groq_resp = self.call_groq(context_prompt, max_tokens=256)
        groq_text = groq_resp.choices[0].message.content
        import re, json
        groq_json = json.loads(re.search(r"(\{.*\})", groq_text, re.S).group(1))

        if groq_json["confidence"] >= self.config["thresholds"]["groq_high_confidence"]:
            return groq_json, None
        
        elif groq_json["confidence"] >= self.config["thresholds"]["groq_low_confidence"]:
            # escalate to GPT-4o-mini for final decision
            print("Escalating to OpenAI for final decision...")
            final_prompt = f"""Context: {context_prompt}
                        Groq suggested: {groq_json}

                        Please produce:
                        1) final_decision: buy/sell/skip
                        2) entry_price, sl, tp
                        3) rationale (3 bullets)
                        4) numeric confidence (0-1)
                        Return only JSON object."""
            openai_resp = self.call_openai(final_prompt, max_tokens=600)
            final_text = openai_resp.choices[0].message.content
            final_json = json.loads(re.search(r"(\{.*\})", final_text, re.S).group(1))
            return groq_json, final_json
        else:
            return groq_json, None
