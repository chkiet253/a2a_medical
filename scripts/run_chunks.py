from dotenv import load_dotenv
import os
from diagnose_agent.preprocessor import DataPreprocessor

# load biến môi trường từ .env
load_dotenv()

if __name__ == "__main__":
    dp = DataPreprocessor(
        in_dir=os.getenv("IN_DIR", "data/raw_pdfs"),
        out_jsonl=os.getenv("OUT_JSONL", "data/chunks.jsonl"),
        log_path=os.getenv("LOG_PATH", "data/preprocess.log"),
        use_vncorenlp=True
    )
    output_path = dp.build()
    print("Xử lí xong và lưu ở", output_path)
