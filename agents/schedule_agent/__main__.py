from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from task_manager import AgentTaskManager
from agent import SchedulingAgent
import click
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.command()
@click.option("--host", default="localhost")
@click.option("--port", default=10003)
def main(host, port):
    try:
        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
            id="de_xuat_va_dat_lich",
            name="Agent Lên Lịch Khám Bệnh",
            description="Đề xuất khung thời gian và đặt lịch hẹn cho một bệnh/khoa cụ thể; gửi lại biểu mẫu lên lịch có thể chỉnh sửa.",
            tags=["lịch trình", "đặt chỗ", "cuộc hẹn"],
            examples=["Đặt lịch khám bệnh tiểu đường cho tôi vào tuần tới."],
        )
        agent_card = AgentCard(
            name="Agent Lên Lịch Khám Bệnh",
            description="Gợi ý khung giờ và đặt lịch hẹn; người dùng có thể điều chỉnh ngày/giờ trước khi đặt lịch.",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=SchedulingAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=SchedulingAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=SchedulingAgent()),
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
    print("Start SchedulingAgent")
    main()
