from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from agent import Diagnose
from task_manager import AgentTaskManager
import click
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command() # cho phép chạy script với tham số CLI --host và --port
@click.option("--host", default="localhost")
@click.option("--port", default=10001)
def main(host, port):
    try:
        # if not os.getenv("GOOGLE_API_KEY"):
        #         raise MissingAPIKeyError("GOOGLE_API_KEY environment variable not set.")
        
        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
            id="medical_diagnose",
            name="Agent Chuẩn Đoán",
            description="Chẩn đoán sơ bộ dựa trên triệu chứng + nguồn guideline nội bộ.",
            tags=["chuẩn đoán", "y tế", "bệnh"], #gắn nhãn để phân loại.
            examples=["Nam 35 tuổi sốt, ho thì khả năng bị bệnh gì?"],
        )
        agent_card = AgentCard(
            name="Agent Chuẩn Đoán",
            description="Agent chẩn đoán hỗ trợ quyết định dựa trên y khoa",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=Diagnose.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=Diagnose.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=Diagnose()),
            host=host,
            port=port,
        )
        server.start()
    except MissingAPIKeyError as e:
        logger.error(f"Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)
    
if __name__ == "__main__":
    print("Start Medical Diagnosis Agent")
    main()

