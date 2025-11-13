"""
Cost-aware LLM client for Google Gemini API.
Tracks API calls, token usage, and costs for billing integration.

Features:
- Automatic cost tracking across multiple models
- Token counting with fallback estimation
- Rate limiting and retry logic
- Multi-model cost aggregation
- Detailed audit trails for compliance
"""

import os
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
import json

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None

logger = logging.getLogger(__name__)

# --- Pricing Configuration (November 2024) ---
# Updated to match current Google Gemini pricing
PRICING = {
    "gemini-1.5-flash-latest": {
        "input": 0.075 / 1_000_000,   # $0.075 per 1M input tokens
        "output": 0.30 / 1_000_000,   # $0.30 per 1M output tokens
        "display_name": "Gemini 1.5 Flash (Fast & Cheap)"
    },
    "gemini-1.5-pro-latest": {
        "input": 1.50 / 1_000_000,    # $1.50 per 1M input tokens
        "output": 6.00 / 1_000_000,   # $6.00 per 1M output tokens
        "display_name": "Gemini 1.5 Pro (Powerful)"
    },
    "gemini-2.0-flash-lite": {
        "input": 0.075 / 1_000_000,   # $0.075 per 1M input tokens
        "output": 0.30 / 1_000_000,   # $0.30 per 1M output tokens
        "display_name": "Gemini 2.0 Flash Lite (Triaging)"
    },
    "gemini-2.0-flash": {
        "input": 0.10 / 1_000_000,    # $0.10 per 1M input tokens
        "output": 0.40 / 1_000_000,   # $0.40 per 1M output tokens
        "display_name": "Gemini 2.0 Flash (Standard)"
    }
}


class TokenCounter:
    """Estimates token counts for text."""
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Rough estimate: 1 token ≈ 4 characters.
        For accurate counts, use genai.count_tokens() API.
        """
        if not text:
            return 0
        return max(1, len(text) // 4)


class CostTracker:
    """Tracks and reports API call costs."""
    
    def __init__(self):
        self.total_cost = 0.0
        self.call_count = 0
        self.tokens_used = {"input": 0, "output": 0}
        self.calls: List[Dict[str, Any]] = []
    
    def add_call(self, model: str, input_tokens: int, output_tokens: int,
                 duration: float = 0.0) -> float:
        """Record an API call and return its cost."""
        pricing = PRICING.get(model, {})
        if not pricing:
            logger.warning(f"Unknown model {model}. Using zero cost.")
            return 0.0
        
        input_cost = input_tokens * pricing.get("input", 0)
        output_cost = output_tokens * pricing.get("output", 0)
        total_cost = input_cost + output_cost
        
        self.total_cost += total_cost
        self.call_count += 1
        self.tokens_used["input"] += input_tokens
        self.tokens_used["output"] += output_tokens
        
        call_record = {
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_cost": round(input_cost, 8),
            "output_cost": round(output_cost, 8),
            "total_cost": round(total_cost, 8),
            "duration_seconds": round(duration, 2)
        }
        
        self.calls.append(call_record)
        logger.info(f"[COST] {model} | ${total_cost:.6f} | "
                   f"{input_tokens}→{output_tokens} tokens")
        
        return total_cost
    
    def get_summary(self) -> Dict[str, Any]:
        """Get cost summary."""
        return {
            "total_cost": round(self.total_cost, 6),
            "call_count": self.call_count,
            "avg_cost_per_call": round(self.total_cost / max(1, self.call_count), 6),
            "tokens_used": self.tokens_used
        }
    
    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Get all call details."""
        return self.calls


class GeminiClient:
    """
    Cost-aware Gemini API client with comprehensive tracking.
    
    Usage:
        client = GeminiClient(model="gemini-1.5-flash-latest")
        result = client.chat(prompt)
        print(f"Cost: ${result['cost']}")
        print(f"Summary: {client.get_cost_summary()}")
    """
    
    def __init__(self, model: str = "gemini-1.5-flash-latest", api_key: str = None):
        """Initialize with model and API key."""
        if not GENAI_AVAILABLE:
            raise ImportError("Install google-generativeai: pip install google-generativeai")
        
        self.model_name = model
        self.cost_tracker = CostTracker()
        
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        
        genai.configure(api_key=api_key)
        self.client = genai.GenerativeModel(model)
        logger.info(f"GeminiClient initialized: {model}")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens using API, fallback to estimation."""
        try:
            response = self.client.count_tokens(text)
            return response.total_tokens
        except Exception as e:
            logger.debug(f"Token API failed: {e}. Using estimation.")
            return TokenCounter.estimate_tokens(text)
    
    def chat(self, prompt: str, history: Optional[List[Dict[str, str]]] = None,
             max_retries: int = 3) -> Dict[str, Any]:
        """
        Send a chat request and track cost.
        
        Returns:
            {
                'response': str,
                'cost': float,
                'input_tokens': int,
                'output_tokens': int,
                'model': str,
                'timestamp': str,
                'duration_seconds': float
            }
        """
        start_time = time.time()
        input_tokens = self.count_tokens(prompt)
        
        attempt = 0
        response_text = ""
        
        while attempt < max_retries:
            try:
                response = self.client.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.7,
                        top_p=0.9,
                        max_output_tokens=2048
                    )
                )
                response_text = response.text
                break
                
            except Exception as e:
                attempt += 1
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(f"Attempt {attempt} failed: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"All {max_retries} attempts failed: {e}")
                    raise
        
        output_tokens = self.count_tokens(response_text)
        duration = time.time() - start_time
        
        call_cost = self.cost_tracker.add_call(
            self.model_name,
            input_tokens,
            output_tokens,
            duration
        )
        
        return {
            "response": response_text,
            "cost": call_cost,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model": self.model_name,
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": duration
        }
    
    def estimate_cost(self, prompt: str, estimated_output_tokens: int = 500) -> float:
        """Estimate cost before making a call."""
        input_tokens = self.count_tokens(prompt)
        pricing = PRICING.get(self.model_name, {})
        
        input_cost = input_tokens * pricing.get("input", 0)
        output_cost = estimated_output_tokens * pricing.get("output", 0)
        
        return input_cost + output_cost
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """Get cost summary for all calls."""
        return self.cost_tracker.get_summary()
    
    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Get detailed audit trail."""
        return self.cost_tracker.get_audit_trail()
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model pricing info."""
        pricing = PRICING.get(self.model_name, {})
        return {
            "model": self.model_name,
            "display_name": pricing.get("display_name", self.model_name),
            "input_price_per_1m_tokens": round(pricing.get("input", 0) * 1_000_000, 2),
            "output_price_per_1m_tokens": round(pricing.get("output", 0) * 1_000_000, 2),
            "total_calls": self.cost_tracker.call_count,
            "total_cost": round(self.cost_tracker.total_cost, 6)
        }


class MultiModelCostAggregator:
    """Track costs across multiple clients."""
    
    def __init__(self):
        self.clients: Dict[str, GeminiClient] = {}
    
    def register_client(self, name: str, client: GeminiClient):
        """Register a client."""
        self.clients[name] = client
        logger.info(f"Registered client '{name}' using {client.model_name}")
    
    def get_aggregate_cost(self) -> Dict[str, Any]:
        """Get costs across all clients."""
        aggregate = {
            "total_cost": 0.0,
            "by_client": {},
            "by_model": {},
            "total_calls": 0,
            "total_tokens": 0
        }
        
        for name, client in self.clients.items():
            summary = client.get_cost_summary()
            aggregate["total_cost"] += summary["total_cost"]
            aggregate["by_client"][name] = summary
            aggregate["total_calls"] += summary["call_count"]
            aggregate["total_tokens"] += summary["total_tokens"]
            
            model = client.model_name
            if model not in aggregate["by_model"]:
                aggregate["by_model"][model] = {"calls": 0, "cost": 0.0}
            
            aggregate["by_model"][model]["calls"] += summary["call_count"]
            aggregate["by_model"][model]["cost"] += summary["total_cost"]
        
        return aggregate


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    try:
        client = GeminiClient()
        
        # Estimate cost
        test_prompt = "Analyze this character..."
        est_cost = client.estimate_cost(test_prompt)
        print(f"Estimated: ${est_cost:.6f}")
        
        # Make call
        result = client.chat(test_prompt)
        print(f"Response: {result['response'][:100]}...")
        print(f"Cost: ${result['cost']:.6f}")
        print(f"Summary: {client.get_cost_summary()}")
        
    except Exception as e:
        logging.error(f"Error: {e}")
