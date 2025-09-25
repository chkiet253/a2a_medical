from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from task_manager import AgentTaskManager
from agent import CostAgent
import click
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.command()
@click.option("--host", default="localhost")
@click.option("--port", default=10002)
def main(host, port):
    try:
        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
            id="uoc_luong_chi_phi",
            name="Agent Ước Tính Chi Phí",
            description="Ước tính chi phí khám/xét nghiệm cho một căn bệnh cụ thể và gửi lại biểu mẫu chi phí có thể chỉnh sửa.",
            tags=["chi phí", "giá", "ước tính"],
            examples=["Ước tính chi phí xét nghiệm nghi ngờ mắc bệnh tiểu đường."],
        )
        agent_card = AgentCard(
            name="Agent Ước Tính Chi Phí",
            description="Trả về bảng phân tích có cấu trúc và có thể chỉnh sửa về chi phí y tế cho một căn bệnh.",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=CostAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=CostAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=CostAgent()),
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
    print("Start CostAgent")
    main()
