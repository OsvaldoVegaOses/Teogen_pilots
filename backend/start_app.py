import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

if __name__ == "__main__":
    # Get host and port from environment or use defaults
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    print(f"Starting TheoGen application on {host}:{port}")
    print(f"Azure OpenAI Endpoint: {os.getenv('AZURE_OPENAI_ENDPOINT')}")
    print(f"Advanced Reasoning Model: {os.getenv('MODEL_REASONING_ADVANCED')}")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=True,  # Set to False in production
        log_level="info"
    )