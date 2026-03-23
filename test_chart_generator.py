from ai_chart_generator_gemini import AIChartGenerator
import json
import traceback

def test():
    try:
        print("Initializing AI Chart Generator...")
        # Note: In a real app, never hardcode API keys. 
        # Using the key present in your original file for testing purposes.
        api_key = "AIzaSyD1wDd6FZlinwfeaiUFmGLzHjqsnrw-bGM"
        generator = AIChartGenerator("qa_analytics_master.json", api_key)
        
        print("\nSending prompt to Gemini: 'show pie chart of pass/fail status distribution'")
        res = generator.generate_chart("show pie chart of pass/fail status distribution")
        
        print("\n--- FINAL OUTPUT CONFIGURATION ---")
        print(json.dumps(res, indent=2))
        
    except Exception as e:
        print("\n❌ Exception occurred:")
        traceback.print_exc()

if __name__ == "__main__":
    test()
