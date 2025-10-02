from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from task_manager import AgentTaskManager
from agent import BookingAgent
import click
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.command()
@click.option("--host", default="localhost")
@click.option("--port", default=10004)  
def main(host, port):
    try:
        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
            id="booking",
            name="Agent Đặt lịch",
            description="Đặt lịch khám, kiểm tra lịch trống, xác nhận và hủy lịch.",
            tags=["booking", "schedule"],
            examples=["Đặt lịch khám với bác sĩ A ngày 2025-10-05 lúc 9h."],
        )
        agent_card = AgentCard(
            name="Agent Đặt lịch",
            description="Quản lý đặt lịch khám bệnh, kiểm tra lịch trống và gửi email xác nhận/hủy.",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=BookingAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=BookingAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=BookingAgent()),
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
    print("Start BookingAgent")
    main()
